import logging
import base64
import hmac
import json
import re

from flask import Blueprint, current_app, flash, jsonify, render_template, request

from app.auth.decorators import current_user_id, login_required
from app.auth.google_oauth import ReauthRequired, get_user_credentials
from app.extensions import csrf
from app.firebase_config import FirebaseConfigError
from app.repositories import get_repositories
from app.services import count_service, realtime

from . import form_url, google_forms_api, sync_service, watch_service

logger = logging.getLogger(__name__)

forms_bp = Blueprint("forms", __name__)

SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _is_valid_id(value):
    return bool(value and SAFE_ID_PATTERN.match(value))


@forms_bp.route("/forms")
@login_required
def forms_page():
    user_id = current_user_id()
    _, form_repo, _ = get_repositories()

    try:
        managed_forms = form_repo.get_forms(user_id)
    except FirebaseConfigError:
        logger.exception("Firestoreへの接続に失敗しました")
        return render_template(
            "errors/500.html",
            message="データベースへの接続に失敗しました。Firebaseの設定を確認してください",
        ), 500

    rows = []
    for managed in managed_forms:
        form_id = managed.get("form_id")
        rows.append({
            "form_id": form_id,
            "title": managed.get("title", "無題のフォーム"),
            "web_view_link": f"https://docs.google.com/forms/d/{form_id}/edit",
            "is_managed": managed.get("is_active", False),
            "was_managed": True,
            "response_count": managed.get("response_count", 0),
            "unread_count": managed.get("unread_count", 0),
            "unhandled_count": managed.get("unhandled_count", 0),
            "last_synced_at": managed.get("last_synced_at"),
        })

    has_active = any(r["is_managed"] for r in rows)

    return render_template("forms.html", rows=rows, has_active=has_active)


@forms_bp.route("/api/forms/add-by-url", methods=["POST"])
@login_required
def add_form_by_url():
    """貼られたURLからフォームIDを取り出し、実在を確かめてから管理対象に追加する。"""
    user_id = current_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        form_id = form_url.extract_form_id(payload.get("url"))
    except form_url.FormUrlError as err:
        return jsonify({"success": False, "message": str(err)}), 400

    user_repo, form_repo, _ = get_repositories()

    try:
        existing = {f["form_id"] for f in form_repo.get_forms(user_id)}
    except FirebaseConfigError:
        logger.exception("管理対象フォームの取得に失敗しました")
        return jsonify({"success": False, "message": "データベースへの接続に失敗しました"}), 500

    if form_id in existing:
        return jsonify({
            "success": False,
            "message": "そのフォームはすでに登録されています",
        }), 409

    # 登録前にForms APIで開けることを確かめる。開けないIDを登録すると、
    # 受信箱に出てくるのに永久に同期できないフォームが残ってしまう。
    if current_app.config.get("MOCK_MODE"):
        title = "テスト用フォーム"
    else:
        try:
            credentials = get_user_credentials(user_repo, user_id)
            form = google_forms_api.get_form(credentials, form_id)
        except ReauthRequired:
            return jsonify({
                "success": False,
                "message": "Googleアカウントへの接続が切れました。もう一度ログインしてください",
                "data": {"need_login": True},
            }), 401
        except Exception:
            logger.info("フォームを開けませんでした (user=%s form=%s)", user_id, form_id, exc_info=True)
            return jsonify({
                "success": False,
                "message": (
                    "そのフォームを開けませんでした。"
                    "ログイン中のGoogleアカウントで作成したフォームか確認してください"
                ),
            }), 404
        title = (form.get("info", {}).get("title") or "無題のフォーム")[:300]

    try:
        form_repo.add_form(user_id, form_id, title)
    except FirebaseConfigError:
        logger.exception("管理対象フォームの登録に失敗しました")
        return jsonify({"success": False, "message": "データベースへの接続に失敗しました"}), 500

    try:
        watch_service.ensure_response_watches(user_id, [form_id])
    except ReauthRequired:
        logger.info("watch登録のためのGoogle認証が切れています (user=%s)", user_id)
    except Exception:
        # watchが張れなくても手動同期で回答は取れるため、登録自体は成功として扱う
        logger.exception("フォームwatchの登録に失敗しました")

    # 登録した直後に一度取り込む。ここを省くと「登録したのに未同期・回答0件」の
    # 画面になり、失敗したように見える
    new_count = None
    try:
        new_count = sync_service.sync_form(user_id, form_id).get("new_count", 0)
    except Exception:
        logger.exception("登録直後の同期に失敗しました (form_id=%s)", form_id)

    if new_count:
        message = f"「{title}」を管理対象に追加し、回答{new_count}件を取り込みました"
    elif new_count == 0:
        message = f"「{title}」を管理対象に追加しました（まだ回答はありません）"
    else:
        message = f"「{title}」を管理対象に追加しました"

    return jsonify({
        "success": True,
        "message": message,
        "data": {"form_id": form_id, "title": title, "new_count": new_count},
    })


@forms_bp.route("/api/forms/<form_id>/active", methods=["POST"])
@login_required
def set_form_active(form_id):
    user_id = current_user_id()
    if not _is_valid_id(form_id):
        return jsonify({"success": False, "message": "フォームが見つかりませんでした"}), 404

    payload = request.get_json(silent=True) or {}
    is_active = payload.get("is_active")
    if not isinstance(is_active, bool):
        return jsonify({"success": False, "message": "リクエストの内容が正しくありません"}), 400

    _, form_repo, _ = get_repositories()
    updated = False
    try:
        # 管理対象から外してもFirestoreの過去データは削除しない
        updated = form_repo.set_active(user_id, form_id, is_active)
        if updated and is_active:
            watch_service.ensure_response_watches(user_id, [form_id])
    except FirebaseConfigError:
        logger.exception("管理対象の変更に失敗しました")
        return jsonify({"success": False, "message": "データベースへの接続に失敗しました"}), 500
    except ReauthRequired:
        logger.info("watch登録のためのGoogle認証が切れています (user=%s)", user_id)
    except Exception:
        logger.exception("フォームwatchの登録に失敗しました")

    if not updated:
        return jsonify({"success": False, "message": "フォームが見つかりませんでした"}), 404

    message = "管理対象に追加しました" if is_active else "管理対象から外しました"
    return jsonify({"success": True, "message": message, "data": {"is_active": is_active}})


@forms_bp.route("/api/sync", methods=["POST"])
@login_required
def sync_responses():
    user_id = current_user_id()
    try:
        result = sync_service.sync_all_forms(user_id)
    except ReauthRequired:
        return jsonify({
            "success": False,
            "message": "Googleアカウントへの接続が切れました。もう一度ログインしてください",
            "data": {"need_login": True},
        }), 401
    except FirebaseConfigError:
        logger.exception("同期中にFirestoreへの接続に失敗しました")
        return jsonify({"success": False, "message": "データベースへの接続に失敗しました"}), 500
    except Exception:
        logger.exception("回答の同期に失敗しました")
        return jsonify({
            "success": False,
            "message": "回答の取得に失敗しました。時間を空けて再度お試しください",
        }), 500

    return jsonify({
        "success": True,
        "message": sync_service.build_sync_message(result),
        "data": {
            "new_count": result["new_count"],
            "failed_forms": len(result["failed_forms"]),
        },
    })


@forms_bp.route("/api/forms/watches/ensure", methods=["POST"])
@login_required
def ensure_form_watches():
    """既存の管理対象フォームにも回答通知watchを整備する。"""
    user_id = current_user_id()
    try:
        result = watch_service.ensure_response_watches(user_id)
    except ReauthRequired:
        return jsonify({
            "success": False,
            "message": "Googleアカウントへの接続が切れました。もう一度ログインしてください",
            "data": {"need_login": True},
        }), 401
    except FirebaseConfigError:
        logger.exception("watch整備中にFirestoreへの接続に失敗しました")
        return jsonify({"success": False, "message": "データベースへの接続に失敗しました"}), 500
    except Exception:
        logger.exception("watch整備に失敗しました")
        return jsonify({
            "success": False,
            "message": "リアルタイム更新の準備に失敗しました",
        }), 500

    return jsonify({"success": True, "message": "", "data": result})


@forms_bp.route("/api/pubsub/forms", methods=["POST"])
@csrf.exempt
def receive_forms_pubsub_push():
    """Google FormsのPub/Sub push通知を受けて対象フォームだけ同期する。"""
    if not _is_valid_pubsub_token():
        return jsonify({"success": False, "message": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    message = payload.get("message") or {}
    attributes = _pubsub_attributes(message)
    event_type = attributes.get("eventType")
    form_id = attributes.get("formId")
    watch_id = attributes.get("watchId")

    if event_type != "RESPONSES":
        return "", 204
    if not (_is_valid_id(form_id) and _is_valid_id(watch_id)):
        logger.warning("不正なPub/Sub通知を受信しました")
        return "", 204

    _, form_repo, _ = get_repositories()
    route = form_repo.get_watch_route(watch_id)
    if not route:
        logger.warning("watchIdに対応するフォームが見つかりません (watch_id=%s)", watch_id)
        return "", 204

    user_id = route.get("user_id")
    target_form_id = route.get("form_id") or form_id
    try:
        result = sync_service.sync_form(user_id, target_form_id)
        realtime.publish(user_id, {
            "type": "responses_updated",
            "form_id": target_form_id,
            "new_count": result.get("new_count", 0),
            "failed_forms": len(result.get("failed_forms", [])),
            "message": sync_service.build_sync_message(result),
        })
    except ReauthRequired:
        logger.info("Pub/Sub通知同期のためのGoogle認証が切れています (user=%s)", user_id)
    except Exception:
        logger.exception("Pub/Sub通知からの同期に失敗しました (form_id=%s)", target_form_id)

    return "", 204


@forms_bp.route("/api/forms/recalculate", methods=["POST"])
@login_required
def recalculate_counts():
    """集計値がずれた場合の再計算処理。"""
    user_id = current_user_id()
    _, form_repo, response_repo = get_repositories()
    try:
        count_service.recalculate_all_counts(form_repo, response_repo, user_id)
    except FirebaseConfigError:
        logger.exception("件数の再計算に失敗しました")
        return jsonify({"success": False, "message": "データベースへの接続に失敗しました"}), 500

    return jsonify({"success": True, "message": "件数を再計算しました"})


def _is_valid_pubsub_token():
    expected = current_app.config.get("GOOGLE_FORMS_PUBSUB_PUSH_TOKEN")
    if not expected:
        return False
    provided = request.args.get("token") or request.headers.get("X-PubSub-Token") or ""
    return hmac.compare_digest(provided, expected)


def _pubsub_attributes(message):
    attributes = dict(message.get("attributes") or {})
    data = message.get("data")
    if data:
        try:
            decoded = base64.b64decode(data).decode("utf-8")
            data_payload = json.loads(decoded)
            if isinstance(data_payload, dict):
                for key in ("eventType", "formId", "watchId"):
                    if key in data_payload:
                        attributes[key] = data_payload[key]
                attributes.update(data_payload.get("attributes") or {})
        except (ValueError, TypeError):
            pass
    return attributes
