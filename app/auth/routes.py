import logging
import secrets
import time

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.repositories import get_repositories

from . import google_oauth
from .decorators import current_user_id, login_required

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)
ACCOUNT_DELETE_REAUTH_SECONDS = 10 * 60


@auth_bp.route("/login")
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))
    return render_template("login.html")


@auth_bp.route("/privacy")
def privacy():
    # 公開ページなので紹介ページと同じ外枠を使う。canonicalとog:urlに使う値を渡す。
    from app.public.routes import render_public
    return render_public("privacy.html", "auth.privacy")


@auth_bp.route("/terms")
def terms():
    from app.public.routes import render_public
    return render_public("terms.html", "auth.terms")


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

    oauth_error = request.args.get("error")
    if oauth_error:
        logger.info("Google OAuthが拒否されました (error=%s)", oauth_error)
        if oauth_error == "access_denied":
            flash(
                "Googleログインが許可されませんでした。"
                "管理者から指定されたGoogleアカウントでログインしているか確認してください",
                "error",
            )
        elif oauth_error == "temporarily_unavailable":
            flash("Googleログインを一時的に利用できません。時間を空けて再度お試しください", "error")
        else:
            flash("Googleログインを完了できませんでした。もう一度お試しください", "error")
        return redirect(url_for("auth.login"))

    if not saved_code_verifier:
        logger.warning("OAuth code_verifierがセッションに見つかりませんでした")
        flash("ログインの検証に失敗しました。もう一度お試しください", "error")
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


@auth_bp.route("/api/account/delete", methods=["POST"])
@login_required
def delete_account():
    """アプリ内のアカウントと保存データをすべて削除する。"""
    user_id = current_user_id()
    authenticated_at = session.get("authenticated_at")
    session_age = None
    if isinstance(authenticated_at, (int, float)):
        session_age = time.time() - authenticated_at
    if session_age is None or not 0 <= session_age <= ACCOUNT_DELETE_REAUTH_SECONDS:
        return jsonify({
            "success": False,
            "message": "セキュリティのため、一度ログアウトして再度ログインしてから削除してください",
            "data": {"need_reauth": True},
        }), 403

    user_repo, form_repo, _ = get_repositories()
    credentials = None

    if not current_app.config.get("MOCK_MODE"):
        try:
            credentials = google_oauth.get_user_credentials(user_repo, user_id)
        except google_oauth.ReauthRequired:
            # すでにGoogle側の許可が無効でも、アプリ内データは削除できる。
            logger.info("退会時に有効なGoogle認証がありません (user=%s)", user_id)
        except Exception:
            logger.warning(
                "退会時のGoogle認証情報取得に失敗しました (user=%s)",
                user_id,
                exc_info=True,
            )

    if credentials is not None:
        try:
            from app.forms import watch_service

            watch_service.stop_response_watches(user_id, credentials)
        except Exception:
            # watchは最長7日で失効するため、停止失敗だけで退会を止めない。
            logger.warning(
                "退会時のフォームwatch停止処理に失敗しました (user=%s)",
                user_id,
                exc_info=True,
            )

    try:
        # users配下を消すだけではトップレベルの通知経路が残るため、先に明示削除する。
        form_repo.delete_watch_routes_for_user(user_id)
        user_repo.delete_user(user_id)
    except Exception:
        logger.exception("アカウントデータの削除に失敗しました (user=%s)", user_id)
        return jsonify({
            "success": False,
            "message": "アカウントの削除に失敗しました。時間を空けて再度お試しください",
        }), 500

    if credentials is not None:
        try:
            google_oauth.revoke_credentials(credentials)
        except Exception:
            # アプリ内データの削除は完了しているため、Google側の一時エラーは警告に留める。
            logger.warning(
                "退会時のGoogle OAuth許可取り消しに失敗しました (user=%s)",
                user_id,
                exc_info=True,
            )

    session.clear()
    flash("アカウントを削除しました。同じGoogleアカウントで再登録できます", "success")
    return jsonify({
        "success": True,
        "message": "アカウントを削除しました",
        "data": {"redirect_url": url_for("auth.login")},
    })


def _establish_session(user_id, name, email, picture_url):
    session.clear()
    session["user_id"] = user_id
    session["google_authorized"] = True
    session["authenticated_at"] = time.time()
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
