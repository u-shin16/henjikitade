"""Google Forms Watches APIによる回答通知の管理。"""
import logging
from datetime import datetime, timedelta, timezone

from flask import current_app
from googleapiclient.errors import HttpError

from app.auth import google_oauth
from app.repositories import get_repositories

from . import google_forms_api

logger = logging.getLogger(__name__)

RENEW_BEFORE = timedelta(days=1)


def is_push_enabled():
    return bool(current_app.config.get("GOOGLE_FORMS_PUBSUB_TOPIC"))


def ensure_response_watches(user_id, form_ids=None):
    """管理対象フォームのRESPONSES watchを作成・更新する。

    Pub/Sub topicが未設定の場合は何もせず、手動同期だけで動く状態を保つ。
    """
    if current_app.config.get("MOCK_MODE"):
        return {"enabled": True, "watched": 0, "failed": [], "mock": True}

    topic_name = current_app.config.get("GOOGLE_FORMS_PUBSUB_TOPIC")
    if not topic_name:
        return {"enabled": False, "watched": 0, "failed": [], "reason": "topic_missing"}

    user_repo, form_repo, _ = get_repositories()
    credentials = google_oauth.get_user_credentials(user_repo, user_id)
    forms = form_repo.get_forms(user_id, active_only=True)
    if form_ids is not None:
        wanted = set(form_ids)
        forms = [form for form in forms if form["form_id"] in wanted]

    watched = 0
    failed = []
    for form in forms:
        try:
            watch = _ensure_one_watch(credentials, form_repo, user_id, form, topic_name)
            if watch:
                watched += 1
        except Exception:
            logger.exception("フォームwatchの整備に失敗しました (form_id=%s)", form["form_id"])
            failed.append(form.get("title") or form["form_id"])

    return {"enabled": True, "watched": watched, "failed": failed}


def ensure_all_response_watches():
    """全ユーザー分のwatchを整備する。cron等から呼ぶ定期更新用。"""
    user_repo, _, _ = get_repositories()
    users = user_repo.list_user_ids()
    result = {"users": len(users), "watched": 0, "failed_users": []}

    for user_id in users:
        try:
            user_result = ensure_response_watches(user_id)
            result["watched"] += user_result.get("watched", 0)
            if user_result.get("failed"):
                result["failed_users"].append(user_id)
        except google_oauth.ReauthRequired:
            logger.info("watch整備のためのGoogle認証が切れています (user=%s)", user_id)
            result["failed_users"].append(user_id)
        except Exception:
            logger.exception("ユーザーのwatch整備に失敗しました (user=%s)", user_id)
            result["failed_users"].append(user_id)

    return result


def stop_response_watches(user_id, credentials):
    """退会前に、ユーザーのGoogle Forms watchを可能な範囲で停止する。"""
    if current_app.config.get("MOCK_MODE"):
        return {"stopped": 0, "failed": []}

    _, form_repo, _ = get_repositories()
    stopped = 0
    failed = []
    for form in form_repo.get_forms(user_id):
        watch_id = form.get("response_watch_id")
        if not watch_id:
            continue
        try:
            google_forms_api.delete_watch(credentials, form["form_id"], watch_id)
            stopped += 1
        except Exception:
            logger.warning(
                "退会時のフォームwatch停止に失敗しました (form_id=%s)",
                form["form_id"],
                exc_info=True,
            )
            failed.append(form.get("title") or form["form_id"])
    return {"stopped": stopped, "failed": failed}


def _ensure_one_watch(credentials, form_repo, user_id, form, topic_name):
    form_id = form["form_id"]
    watch_id = form.get("response_watch_id")
    expire_at = _parse_time(form.get("response_watch_expire_at"))

    if watch_id and expire_at and expire_at - datetime.now(timezone.utc) > RENEW_BEFORE:
        form_repo.save_watch_route(user_id, form_id, watch_id)
        return {"id": watch_id, "expireTime": expire_at.isoformat()}

    if watch_id:
        try:
            watch = google_forms_api.renew_watch(credentials, form_id, watch_id)
            _store_watch(form_repo, user_id, form_id, watch)
            return watch
        except HttpError:
            logger.info("既存watchの更新に失敗したため再作成を試します (form_id=%s)", form_id)

    existing = _find_existing_response_watch(credentials, form_id, topic_name)
    if existing:
        _store_watch(form_repo, user_id, form_id, existing)
        return existing

    watch = google_forms_api.create_response_watch(credentials, form_id, topic_name)
    _store_watch(form_repo, user_id, form_id, watch)
    return watch


def _find_existing_response_watch(credentials, form_id, topic_name):
    try:
        watches = google_forms_api.list_watches(credentials, form_id)
    except HttpError:
        return None

    for watch in watches:
        target = watch.get("target") or {}
        topic = target.get("topic") or {}
        if watch.get("eventType") != "RESPONSES":
            continue
        if topic.get("topicName") != topic_name:
            continue
        if watch.get("state") and watch.get("state") != "ACTIVE":
            continue
        return watch
    return None


def _store_watch(form_repo, user_id, form_id, watch):
    watch_id = watch.get("id")
    fields = {
        "response_watch_id": watch_id,
        "response_watch_expire_at": _parse_time(watch.get("expireTime")),
        "response_watch_state": watch.get("state"),
        "response_watch_error_type": watch.get("errorType"),
    }
    form_repo.update_form(user_id, form_id, fields)
    form_repo.save_watch_route(user_id, form_id, watch_id)


def _parse_time(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None
