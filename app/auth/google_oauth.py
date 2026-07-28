"""Google OAuth 2.0の認可フローとトークン管理。

トークンはFernetで暗号化した上でFirestoreへ保存する。
トークンそのものをログ・画面・APIレスポンスへ出さないこと。
"""
import base64
import hashlib
import json
import logging
import os
from datetime import datetime

from flask import current_app

logger = logging.getLogger(__name__)

# 必要最小限のスコープのみ要求する
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/forms.body.readonly",
    "https://www.googleapis.com/auth/forms.responses.readonly",
]

USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"


class ReauthRequired(Exception):
    """トークンが無効・失効しており再ログインが必要な状態。"""


def is_oauth_configured():
    return bool(
        current_app.config.get("GOOGLE_CLIENT_ID")
        and current_app.config.get("GOOGLE_CLIENT_SECRET")
        and current_app.config.get("GOOGLE_REDIRECT_URI")
    )


def _allow_insecure_transport_for_dev():
    # ローカル開発(http)でoauthlibを動かすための設定。本番はHTTPS必須。
    if current_app.config.get("FLASK_ENV") == "development":
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


def _client_config():
    return {
        "web": {
            "client_id": current_app.config["GOOGLE_CLIENT_ID"],
            "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [current_app.config["GOOGLE_REDIRECT_URI"]],
        }
    }


def build_flow(state=None, code_verifier=None):
    from google_auth_oauthlib.flow import Flow

    _allow_insecure_transport_for_dev()
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
        code_verifier=code_verifier,
        # code_verifierはこちらでセッションに保存して引き継ぐため、
        # ライブラリ側の自動生成(=別インスタンス間で失われる)は無効にする
        autogenerate_code_verifier=False,
    )
    flow.redirect_uri = current_app.config["GOOGLE_REDIRECT_URI"]
    return flow


def fetch_userinfo(credentials):
    import requests

    res = requests.get(
        USERINFO_ENDPOINT,
        headers={"Authorization": f"Bearer {credentials.token}"},
        timeout=10,
    )
    res.raise_for_status()
    return res.json()


def revoke_credentials(credentials):
    """Googleへ保存済みのOAuth許可を取り消す。"""
    import requests

    token = credentials.refresh_token or credentials.token
    if not token:
        return False
    res = requests.post(
        REVOKE_ENDPOINT,
        data={"token": token},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    res.raise_for_status()
    return True


# --- トークンの暗号化保存 ---

def _fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(current_app.config["SECRET_KEY"].encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def credentials_to_dict(credentials):
    expiry = None
    if credentials.expiry:
        expiry = credentials.expiry.isoformat()
    return {
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "scopes": list(credentials.scopes or []),
        "expiry": expiry,
    }


def encrypt_token(token_dict):
    return _fernet().encrypt(json.dumps(token_dict).encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted):
    return json.loads(_fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8"))


def save_credentials(user_repo, user_id, credentials):
    user_repo.save_oauth_token(user_id, encrypt_token(credentials_to_dict(credentials)))


def get_user_credentials(user_repo, user_id):
    """保存済みトークンからCredentialsを復元する。

    期限切れの場合はrefresh_tokenで更新し、更新に失敗した場合は
    ReauthRequiredを投げて再ログインを促す。
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    encrypted = user_repo.get_oauth_token(user_id)
    if not encrypted:
        raise ReauthRequired("OAuthトークンが保存されていません")

    try:
        data = decrypt_token(encrypted)
    except Exception:
        logger.warning("OAuthトークンの復号に失敗しました (user=%s)", user_id)
        raise ReauthRequired("OAuthトークンを読み込めませんでした")

    credentials = Credentials(
        token=data.get("access_token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=data.get("client_id") or current_app.config["GOOGLE_CLIENT_ID"],
        client_secret=current_app.config["GOOGLE_CLIENT_SECRET"],
        scopes=data.get("scopes") or SCOPES,
    )
    if data.get("expiry"):
        try:
            expiry = datetime.fromisoformat(data["expiry"])
            # google.authはnaiveなUTC日時を期待する
            if expiry.tzinfo is not None:
                expiry = expiry.astimezone(tz=None).replace(tzinfo=None)
            credentials.expiry = expiry
        except ValueError:
            pass

    if credentials.expired:
        if not credentials.refresh_token:
            raise ReauthRequired("refresh_tokenがありません")
        try:
            credentials.refresh(Request())
            save_credentials(user_repo, user_id, credentials)
        except Exception:
            logger.warning("OAuthトークンの更新に失敗しました (user=%s)", user_id)
            raise ReauthRequired("トークンの更新に失敗しました")

    return credentials
