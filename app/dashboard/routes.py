import logging

from flask import Blueprint, flash, redirect, render_template, session, url_for

from app.auth.decorators import current_user_id, login_required
from app.firebase_config import FirebaseConfigError
from app.repositories import get_repositories

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    user_id = current_user_id()
    _, form_repo, _ = get_repositories()
    try:
        active_forms = form_repo.get_forms(user_id, active_only=True)
    except FirebaseConfigError:
        logger.exception("Firestoreへの接続に失敗しました")
        return render_template(
            "errors/500.html",
            message="データベースへの接続に失敗しました。Firebaseの設定を確認してください",
        ), 500

    if not active_forms:
        flash("管理するGoogleフォームを選択してください", "info")
        return redirect(url_for("forms.forms_page"))

    return render_template("dashboard.html", active_forms=active_forms)


@dashboard_bp.route("/settings")
@login_required
def settings():
    user_id = current_user_id()
    user_repo, form_repo, _ = get_repositories()
    user = None
    managed_forms = []
    try:
        user = user_repo.get_user(user_id)
        managed_forms = form_repo.get_forms(user_id)
    except FirebaseConfigError:
        logger.exception("設定画面のデータ取得に失敗しました")
        flash("データベースへの接続に失敗しました", "error")

    return render_template("settings.html", user=user, managed_forms=managed_forms)
