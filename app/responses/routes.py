import logging
import re

from flask import Blueprint, jsonify, request

from app.auth.decorators import current_user_id, login_required
from app.constants import ADMIN_MEMO_MAX_LENGTH, STATUS_LABELS, STATUSES
from app.firebase_config import FirebaseConfigError
from app.repositories import get_repositories
from app.services import count_service

from . import response_service

logger = logging.getLogger(__name__)

responses_bp = Blueprint("responses", __name__)

SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _db_error():
    return jsonify({"success": False, "message": "データベースへの接続に失敗しました"}), 500


def _not_found():
    return jsonify({"success": False, "message": "問い合わせが見つかりませんでした"}), 404


def _get_owned_response(user_id, form_id, response_id):
    """ログインユーザーの管理対象フォーム配下の回答のみ取得する。

    不正なIDや他ユーザーのデータパスを指定できないようにする。
    """
    if not (SAFE_ID_PATTERN.match(form_id or "") and SAFE_ID_PATTERN.match(response_id or "")):
        return None, None
    _, form_repo, response_repo = get_repositories()
    form = form_repo.get_form(user_id, form_id)
    if form is None:
        return None, None
    response = response_repo.get_response(user_id, form_id, response_id)
    return form, response


@responses_bp.route("/api/responses")
@login_required
def list_responses():
    user_id = current_user_id()
    _, form_repo, response_repo = get_repositories()
    try:
        filters = response_service.parse_filters(request.args)
        data = response_service.get_inbox(user_id, form_repo, response_repo, filters)
    except FirebaseConfigError:
        logger.exception("回答一覧の取得に失敗しました")
        return _db_error()
    except Exception:
        logger.exception("回答一覧の取得中にエラーが発生しました")
        return jsonify({
            "success": False,
            "message": "回答の取得に失敗しました。時間を空けて再度お試しください",
        }), 500

    return jsonify({"success": True, "message": "", "data": data})


@responses_bp.route("/api/responses/<form_id>/<response_id>")
@login_required
def response_detail(form_id, response_id):
    user_id = current_user_id()
    _, form_repo, response_repo = get_repositories()
    try:
        form, response = _get_owned_response(user_id, form_id, response_id)
        if response is None:
            return _not_found()

        # 詳細を開いたタイミングで既読へ変更する
        marked_read = False
        if not response.get("is_read"):
            response_repo.update_fields(user_id, form_id, response_id, {"is_read": True})
            response["is_read"] = True
            marked_read = True
            count_service.recalculate_form_counts(form_repo, response_repo, user_id, form_id)
    except FirebaseConfigError:
        logger.exception("回答詳細の取得に失敗しました")
        return _db_error()

    detail = response_service.serialize_detail(response, form)
    detail["marked_read"] = marked_read
    return jsonify({"success": True, "message": "", "data": detail})


@responses_bp.route("/api/responses/<form_id>/<response_id>/read", methods=["POST"])
@login_required
def update_read(form_id, response_id):
    payload = request.get_json(silent=True) or {}
    is_read = payload.get("is_read")
    if not isinstance(is_read, bool):
        return jsonify({"success": False, "message": "リクエストの内容が正しくありません"}), 400
    return _update_response_field(
        form_id, response_id,
        {"is_read": is_read},
        "既読にしました" if is_read else "未読にしました",
        recalculate=True,
    )


@responses_bp.route("/api/responses/<form_id>/<response_id>/status", methods=["POST"])
@login_required
def update_status(form_id, response_id):
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if status not in STATUSES:
        return jsonify({"success": False, "message": "対応状況の値が正しくありません"}), 400
    return _update_response_field(
        form_id, response_id,
        {"status": status},
        f"対応状況を「{STATUS_LABELS[status]}」に変更しました",
        recalculate=True,
        extra_data={"status": status},
    )


@responses_bp.route("/api/responses/<form_id>/<response_id>/important", methods=["POST"])
@login_required
def update_important(form_id, response_id):
    payload = request.get_json(silent=True) or {}
    is_important = payload.get("is_important")
    if not isinstance(is_important, bool):
        return jsonify({"success": False, "message": "リクエストの内容が正しくありません"}), 400
    return _update_response_field(
        form_id, response_id,
        {"is_important": is_important},
        "重要マークを付けました" if is_important else "重要マークを外しました",
        extra_data={"is_important": is_important},
    )


@responses_bp.route("/api/responses/<form_id>/<response_id>/memo", methods=["POST"])
@login_required
def update_memo(form_id, response_id):
    payload = request.get_json(silent=True) or {}
    memo = payload.get("memo")
    if not isinstance(memo, str):
        return jsonify({"success": False, "message": "リクエストの内容が正しくありません"}), 400
    if len(memo) > ADMIN_MEMO_MAX_LENGTH:
        return jsonify({
            "success": False,
            "message": f"メモは{ADMIN_MEMO_MAX_LENGTH}文字以内で入力してください",
        }), 400
    return _update_response_field(
        form_id, response_id,
        {"admin_memo": memo},
        "メモを保存しました",
        failure_message="メモの保存に失敗しました",
    )


def _update_response_field(
    form_id,
    response_id,
    fields,
    success_message,
    recalculate=False,
    extra_data=None,
    failure_message=None,
):
    user_id = current_user_id()
    _, form_repo, response_repo = get_repositories()
    try:
        form, response = _get_owned_response(user_id, form_id, response_id)
        if response is None:
            return _not_found()
        updated = response_repo.update_fields(user_id, form_id, response_id, fields)
        if not updated:
            return _not_found()
        if recalculate:
            count_service.recalculate_form_counts(form_repo, response_repo, user_id, form_id)
    except FirebaseConfigError:
        logger.exception("回答の更新に失敗しました")
        return _db_error()
    except Exception:
        logger.exception("回答の更新中にエラーが発生しました")
        return jsonify({
            "success": False,
            "message": failure_message or "更新に失敗しました。時間を空けて再度お試しください",
        }), 500

    return jsonify({"success": True, "message": success_message, "data": extra_data or {}})
