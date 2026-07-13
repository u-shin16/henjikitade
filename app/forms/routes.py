import logging
import re

from flask import Blueprint, current_app, flash, jsonify, render_template, request

from app.auth.decorators import current_user_id, login_required
from app.auth.google_oauth import ReauthRequired, get_user_credentials
from app.firebase_config import FirebaseConfigError
from app.repositories import get_repositories
from app.services import count_service

from . import google_drive_api, sync_service

logger = logging.getLogger(__name__)

forms_bp = Blueprint("forms", __name__)

SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _is_valid_id(value):
    return bool(value and SAFE_ID_PATTERN.match(value))


@forms_bp.route("/forms")
@login_required
def forms_page():
    user_id = current_user_id()
    user_repo, form_repo, _ = get_repositories()

    try:
        managed_forms = {f["form_id"]: f for f in form_repo.get_forms(user_id)}
    except FirebaseConfigError:
        logger.exception("Firestoreへの接続に失敗しました")
        return render_template(
            "errors/500.html",
            message="データベースへの接続に失敗しました。Firebaseの設定を確認してください",
        ), 500

    drive_error = None
    available_forms = []
    if current_app.config.get("MOCK_MODE"):
        available_forms = form_repo.store.get("available_forms", [])
    else:
        try:
            credentials = get_user_credentials(user_repo, user_id)
            available_forms = google_drive_api.list_google_forms(credentials)
        except ReauthRequired:
            drive_error = "Googleアカウントへの接続が切れました。もう一度ログインしてください"
        except Exception:
            logger.exception("Googleフォーム一覧の取得に失敗しました")
            drive_error = "Googleフォーム一覧の取得に失敗しました。時間を空けて再度お試しください"

    # Drive上のフォームと管理対象情報をマージして表示用リストを作る
    rows = []
    seen_ids = set()
    for f in available_forms:
        form_id = f.get("id")
        seen_ids.add(form_id)
        managed = managed_forms.get(form_id)
        rows.append({
            "form_id": form_id,
            "title": f.get("name", "無題のフォーム"),
            "modified_time": f.get("modifiedTime"),
            "web_view_link": f.get("webViewLink"),
            "is_managed": managed is not None and managed.get("is_active", False),
            "was_managed": managed is not None,
            "response_count": (managed or {}).get("response_count", 0),
            "unread_count": (managed or {}).get("unread_count", 0),
            "unhandled_count": (managed or {}).get("unhandled_count", 0),
            "last_synced_at": (managed or {}).get("last_synced_at"),
            "missing_on_drive": False,
        })

    # Driveから取得できなかった管理対象フォーム(削除・権限喪失など)
    for form_id, managed in managed_forms.items():
        if form_id in seen_ids:
            continue
        rows.append({
            "form_id": form_id,
            "title": managed.get("title", "無題のフォーム"),
            "modified_time": None,
            "web_view_link": None,
            "is_managed": managed.get("is_active", False),
            "was_managed": True,
            "response_count": managed.get("response_count", 0),
            "unread_count": managed.get("unread_count", 0),
            "unhandled_count": managed.get("unhandled_count", 0),
            "last_synced_at": managed.get("last_synced_at"),
            "missing_on_drive": not current_app.config.get("MOCK_MODE"),
        })

    has_active = any(r["is_managed"] for r in rows)

    return render_template(
        "forms.html",
        rows=rows,
        drive_error=drive_error,
        has_active=has_active,
    )


@forms_bp.route("/api/forms/manage", methods=["POST"])
@login_required
def add_managed_forms():
    user_id = current_user_id()
    payload = request.get_json(silent=True) or {}
    forms = payload.get("forms") or []
    if not isinstance(forms, list) or not forms:
        return jsonify({"success": False, "message": "追加するフォームを選択してください"}), 400

    _, form_repo, _ = get_repositories()
    added = 0
    try:
        for f in forms:
            form_id = (f or {}).get("id", "")
            title = ((f or {}).get("title") or "無題のフォーム")[:300]
            if not _is_valid_id(form_id):
                continue
            form_repo.add_form(user_id, form_id, title)
            added += 1
    except FirebaseConfigError:
        logger.exception("管理対象フォームの登録に失敗しました")
        return jsonify({"success": False, "message": "データベースへの接続に失敗しました"}), 500

    if added == 0:
        return jsonify({"success": False, "message": "フォームを登録できませんでした"}), 400
    return jsonify({
        "success": True,
        "message": f"{added}件のフォームを管理対象に追加しました",
        "data": {"added": added},
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
    try:
        # 管理対象から外してもFirestoreの過去データは削除しない
        updated = form_repo.set_active(user_id, form_id, is_active)
    except FirebaseConfigError:
        logger.exception("管理対象の変更に失敗しました")
        return jsonify({"success": False, "message": "データベースへの接続に失敗しました"}), 500

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
