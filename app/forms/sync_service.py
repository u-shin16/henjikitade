"""管理対象フォームの回答をGoogle Forms APIから取得しFirestoreへ同期する。

- responseIdをドキュメントIDに使い、重複登録を防止する
- 既存回答のis_read / status / is_important / admin_memoは上書きしない
- 一部のフォームで失敗しても処理全体は中断しない
"""
import logging
from datetime import datetime, timezone

from flask import current_app

from app.auth import google_oauth
from app.repositories import get_repositories
from app.services import answer_parser, count_service

from . import google_forms_api

logger = logging.getLogger(__name__)


def sync_all_forms(user_id):
    """管理対象の全フォームを同期し、結果を返す。

    戻り値: {"new_count": int, "failed_forms": [フォーム名], "no_forms": bool}
    """
    if current_app.config.get("MOCK_MODE"):
        return _mock_sync(user_id)

    user_repo, form_repo, response_repo = get_repositories()
    credentials = google_oauth.get_user_credentials(user_repo, user_id)

    forms = form_repo.get_forms(user_id, active_only=True)
    if not forms:
        return {"new_count": 0, "failed_forms": [], "no_forms": True}

    new_count = 0
    failed_forms = []

    for form in forms:
        try:
            new_count += _sync_one_form(user_id, form, credentials, form_repo, response_repo)
        except Exception:
            # 本文やトークンはログへ出さない
            logger.exception("フォームの同期に失敗しました (form_id=%s)", form["form_id"])
            failed_forms.append(form.get("title") or form["form_id"])

    return {"new_count": new_count, "failed_forms": failed_forms, "no_forms": False}


def sync_form(user_id, form_id):
    """Pub/Sub通知を受けた1フォーム分だけ同期する。"""
    if current_app.config.get("MOCK_MODE"):
        return _mock_sync_form(user_id, form_id)

    user_repo, form_repo, response_repo = get_repositories()
    credentials = google_oauth.get_user_credentials(user_repo, user_id)
    form = form_repo.get_form(user_id, form_id)
    if form is None or not form.get("is_active", False):
        return {"new_count": 0, "failed_forms": [], "no_forms": True}

    try:
        new_count = _sync_one_form(user_id, form, credentials, form_repo, response_repo)
    except Exception:
        logger.exception("フォームの同期に失敗しました (form_id=%s)", form_id)
        return {"new_count": 0, "failed_forms": [form.get("title") or form_id], "no_forms": False}

    return {"new_count": new_count, "failed_forms": [], "no_forms": False}


def _sync_one_form(user_id, form, credentials, form_repo, response_repo):
    form_id = form["form_id"]
    form_data = google_forms_api.get_form(credentials, form_id)
    question_map = answer_parser.build_question_map(form_data)
    api_responses = google_forms_api.list_all_responses(credentials, form_id)

    new_count = 0
    for api_response in api_responses:
        response_id = api_response.get("responseId")
        if not response_id:
            continue
        if response_repo.exists(user_id, form_id, response_id):
            continue
        parsed = answer_parser.parse_response(question_map, api_response)
        if response_repo.add_response(user_id, form_id, response_id, parsed):
            new_count += 1

    update_fields = {"last_synced_at": datetime.now(timezone.utc)}
    title = (form_data.get("info") or {}).get("title")
    if title:
        update_fields["title"] = title
    form_repo.update_form(user_id, form_id, update_fields)
    count_service.recalculate_form_counts(form_repo, response_repo, user_id, form_id)
    return new_count


def build_sync_message(result):
    if result.get("no_forms"):
        return "管理対象のフォームが登録されていません"
    if result["new_count"] > 0:
        message = f"{result['new_count']}件の新しい回答を取得しました"
    else:
        message = "新しい回答はありませんでした"
    if result["failed_forms"]:
        message += f"。{len(result['failed_forms'])}件のフォームで取得に失敗しました"
    return message


def _mock_sync(user_id):
    """モックモードの同期。初回だけ新しい回答を1件追加する。"""
    from app.mock.mock_data import build_new_mock_response

    _, form_repo, response_repo = get_repositories()
    forms = form_repo.get_forms(user_id, active_only=True)
    if not forms:
        return {"new_count": 0, "failed_forms": [], "no_forms": True}

    new_count = 0
    form_id, response_id, data = build_new_mock_response()
    if form_repo.get_form(user_id, form_id) and not response_repo.exists(user_id, form_id, response_id):
        response_repo.add_response(user_id, form_id, response_id, data)
        new_count = 1

    now = datetime.now(timezone.utc)
    for form in forms:
        form_repo.update_form(user_id, form["form_id"], {"last_synced_at": now})
        count_service.recalculate_form_counts(
            form_repo, response_repo, user_id, form["form_id"]
        )

    return {"new_count": new_count, "failed_forms": [], "no_forms": False}


def _mock_sync_form(user_id, form_id):
    from app.mock.mock_data import build_new_mock_response

    _, form_repo, response_repo = get_repositories()
    form = form_repo.get_form(user_id, form_id)
    if form is None or not form.get("is_active", False):
        return {"new_count": 0, "failed_forms": [], "no_forms": True}

    new_count = 0
    new_form_id, response_id, data = build_new_mock_response()
    if form_id == new_form_id and not response_repo.exists(user_id, form_id, response_id):
        response_repo.add_response(user_id, form_id, response_id, data)
        new_count = 1

    form_repo.update_form(user_id, form_id, {"last_synced_at": datetime.now(timezone.utc)})
    count_service.recalculate_form_counts(form_repo, response_repo, user_id, form_id)
    return {"new_count": new_count, "failed_forms": [], "no_forms": False}
