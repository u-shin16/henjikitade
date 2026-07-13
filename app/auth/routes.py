import logging
import secrets

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.repositories import get_repositories

from . import google_oauth
from .decorators import current_user_id

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login")
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))
    return render_template("login.html")


@auth_bp.route("/auth/google")
def google_login():
    if current_app.config.get("MOCK_MODE"):
        return _mock_login()

    if not google_oauth.is_oauth_configured():
        flash("Google OAuthの設定が完了していません。環境変数を確認してください", "error")
        return redirect(url_for("auth.login"))

    state = secrets.token_urlsafe(32)
    # PKCE用のcode_verifierを生成し、コールバックで同じ値を使えるようセッションへ保存する
    code_verifier = secrets.token_urlsafe(64)
    flow = google_oauth.build_flow(state=state, code_verifier=code_verifier)
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    session["oauth_state"] = state
    session["oauth_code_verifier"] = code_verifier
    return redirect(authorization_url)


@auth_bp.route("/auth/callback")
def google_callback():
    if current_app.config.get("MOCK_MODE"):
        return redirect(url_for("dashboard.index"))

    # CSRF対策: OAuthのstateを検証する。値は使い切りなので成功・失敗を問わずここで削除する
    saved_state = session.pop("oauth_state", None)
    saved_code_verifier = session.pop("oauth_code_verifier", None)
    returned_state = request.args.get("state")
    if not saved_state or saved_state != returned_state:
        logger.warning("OAuth stateの検証に失敗しました")
        flash("ログインの検証に失敗しました。もう一度お試しください", "error")
        return redirect(url_for("auth.login"))

    if not saved_code_verifier:
        logger.warning("OAuth code_verifierがセッションに見つかりませんでした")
        flash("ログインの検証に失敗しました。もう一度お試しください", "error")
        return redirect(url_for("auth.login"))

    if request.args.get("error"):
        flash("Googleログインがキャンセルされました", "error")
        return redirect(url_for("auth.login"))

    try:
        flow = google_oauth.build_flow(state=saved_state, code_verifier=saved_code_verifier)
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        userinfo = google_oauth.fetch_userinfo(credentials)
    except Exception:
        logger.exception("Googleログイン処理に失敗しました")
        flash("Googleログインに失敗しました。時間を空けて再度お試しください", "error")
        return redirect(url_for("auth.login"))

    google_user_id = userinfo.get("sub")
    if not google_user_id:
        flash("Googleアカウント情報を取得できませんでした", "error")
        return redirect(url_for("auth.login"))

    user_repo, form_repo, _ = get_repositories()
    try:
        user_repo.create_or_update_user(
            google_user_id,
            {
                "email": userinfo.get("email", ""),
                "name": userinfo.get("name", ""),
                "picture_url": userinfo.get("picture", ""),
            },
        )
        google_oauth.save_credentials(user_repo, google_user_id, credentials)
    except Exception:
        logger.exception("ユーザー情報の保存に失敗しました")
        flash("ログイン情報の保存に失敗しました。Firebaseの設定を確認してください", "error")
        return redirect(url_for("auth.login"))

    _establish_session(
        google_user_id,
        userinfo.get("name", ""),
        userinfo.get("email", ""),
        userinfo.get("picture", ""),
    )

    # 管理対象フォームが0件なら、フォーム選択画面へ誘導する
    try:
        active_forms = form_repo.get_forms(google_user_id, active_only=True)
    except Exception:
        active_forms = []
    if not active_forms:
        return redirect(url_for("forms.forms_page"))
    return redirect(url_for("dashboard.index"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("ログアウトしました", "info")
    return redirect(url_for("auth.login"))


def _establish_session(user_id, name, email, picture_url):
    session.clear()
    session["user_id"] = user_id
    session["google_authorized"] = True
    session["user_name"] = name
    session["user_email"] = email
    session["user_picture"] = picture_url


def _mock_login():
    from app.mock.mock_data import MOCK_USER

    user_repo, _, _ = get_repositories()
    user_repo.create_or_update_user(
        MOCK_USER["google_user_id"],
        {
            "email": MOCK_USER["email"],
            "name": MOCK_USER["name"],
            "picture_url": MOCK_USER["picture_url"],
        },
    )
    _establish_session(
        MOCK_USER["google_user_id"],
        MOCK_USER["name"],
        MOCK_USER["email"],
        MOCK_USER["picture_url"],
    )
    return redirect(url_for("dashboard.index"))
