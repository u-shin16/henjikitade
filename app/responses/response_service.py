"""受信箱(複数フォーム横断の回答一覧)の取得と絞り込み。

フォームID・対応状況・未読既読・重要・回答期間・文字列検索はFlask側で行う。
Firestoreではフォームごとの回答一覧だけを取得し、複合インデックス不足で
受信箱が開けなくなるのを避ける。
将来的に全文検索サービスへ移行する場合は_apply_text_filterを
差し替えられる構成にしている。
"""
from datetime import datetime, time, timedelta, timezone

from app.constants import STATUSES
from app.services import count_service


def parse_filters(args):
    """リクエストパラメータから絞り込み条件を組み立てる。"""
    filters = {
        "form_id": None,
        "status": None,
        "is_read": None,
        "is_important": None,
        "date_from": None,
        "date_to": None,
        "query": (args.get("q") or "").strip().lower(),
        "order_desc": args.get("order", "desc") != "asc",
    }

    form_id = args.get("form_id")
    if form_id:
        filters["form_id"] = form_id

    status = args.get("status")
    if status in STATUSES:
        filters["status"] = status

    read = args.get("read")
    if read in ("true", "false"):
        filters["is_read"] = read == "true"

    important = args.get("important")
    if important in ("true", "false"):
        filters["is_important"] = important == "true"

    local_tz = datetime.now().astimezone().tzinfo
    date_from = args.get("date_from")
    if date_from:
        try:
            d = datetime.strptime(date_from, "%Y-%m-%d").date()
            filters["date_from"] = datetime.combine(d, time.min, tzinfo=local_tz)
        except ValueError:
            pass
    date_to = args.get("date_to")
    if date_to:
        try:
            d = datetime.strptime(date_to, "%Y-%m-%d").date()
            filters["date_to"] = datetime.combine(d, time.max, tzinfo=local_tz)
        except ValueError:
            pass

    return filters


def get_inbox(user_id, form_repo, response_repo, filters):
    """絞り込み済みの回答一覧と、全体の件数集計を返す。"""
    active_forms = form_repo.get_forms(user_id, active_only=True)
    form_titles = {f["form_id"]: f.get("title", "") for f in active_forms}

    target_form_ids = list(form_titles.keys())
    if filters["form_id"]:
        target_form_ids = [fid for fid in target_form_ids if fid == filters["form_id"]]

    # 件数集計用に、管理対象全フォームの回答を取得する
    all_responses = []
    for form_id in form_titles:
        all_responses.extend(
            response_repo.list_for_form(user_id, form_id, order_desc=True)
        )
    counts = count_service.summarize_responses(all_responses)

    listed = [
        r for r in all_responses
        if r.get("form_id") in target_form_ids
    ]
    listed = _apply_structured_filters(listed, filters)

    # 文字列検索はFlask側で絞り込む(MVPでは外部全文検索を使わない)
    if filters["query"]:
        listed = _apply_text_filter(listed, filters["query"])

    listed.sort(
        key=lambda r: r.get("submitted_at") or datetime.now(timezone.utc),
        reverse=filters["order_desc"],
    )

    items = [serialize_list_item(r, form_titles) for r in listed]
    forms_summary = [
        {
            "form_id": f["form_id"],
            "title": f.get("title", ""),
            "response_count": f.get("response_count", 0),
            "unread_count": f.get("unread_count", 0),
            "unhandled_count": f.get("unhandled_count", 0),
            "last_synced_at": _iso(f.get("last_synced_at")),
        }
        for f in active_forms
    ]

    return {"responses": items, "counts": counts, "forms": forms_summary}


def _apply_structured_filters(responses, filters):
    results = []
    for r in responses:
        if filters["status"] is not None and r.get("status") != filters["status"]:
            continue
        if filters["is_read"] is not None and bool(r.get("is_read")) != filters["is_read"]:
            continue
        if filters["is_important"] is not None and bool(r.get("is_important")) != filters["is_important"]:
            continue

        submitted = _as_datetime(r.get("submitted_at"))
        if filters["date_from"] is not None:
            if submitted is None or submitted < _as_utc(filters["date_from"]):
                continue
        if filters["date_to"] is not None:
            if submitted is None or submitted > _as_utc(filters["date_to"]):
                continue
        results.append(r)
    return results


def _apply_text_filter(responses, query):
    results = []
    for r in responses:
        haystack = " ".join([
            r.get("search_text", ""),
            (r.get("admin_memo") or "").lower(),
        ])
        if query in haystack:
            results.append(r)
    return results


def _as_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str):
        try:
            return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def serialize_list_item(response, form_titles):
    return {
        "form_id": response.get("form_id"),
        "response_id": response.get("response_id"),
        "form_title": form_titles.get(response.get("form_id"), "不明なフォーム"),
        "respondent_name": response.get("respondent_name", ""),
        "respondent_email": response.get("respondent_email", ""),
        "summary_text": response.get("summary_text", ""),
        "submitted_at": _iso(response.get("submitted_at")),
        "is_read": bool(response.get("is_read")),
        "status": response.get("status", "unhandled"),
        "is_important": bool(response.get("is_important")),
        "has_memo": bool((response.get("admin_memo") or "").strip()),
    }


def serialize_detail(response, form):
    answers = sorted(
        (response.get("answers") or {}).values(),
        key=lambda a: a.get("order", 9999),
    )
    detail = serialize_list_item(
        response, {form["form_id"]: form.get("title", "")} if form else {}
    )
    detail.update({
        "answers": [
            {
                "question": a.get("question", ""),
                "answer": a.get("answer", ""),
            }
            for a in answers
        ],
        "admin_memo": response.get("admin_memo", ""),
        "google_response_id": response.get("google_response_id", ""),
        "form_url": f"https://docs.google.com/forms/d/{response.get('form_id')}/edit"
        if response.get("form_id") else None,
    })
    return detail
