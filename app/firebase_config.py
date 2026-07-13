"""Firebase Admin SDKの初期化とFirestoreクライアントの管理。

Firebaseへの接続処理はこのファイルへ集約する。
MOCK_MODE時はFirebaseへ一切接続しない。
"""
import logging
import os
import threading

from flask import current_app

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_db = None


class FirebaseConfigError(RuntimeError):
    """Firebaseの設定不備・接続失敗を表すエラー。"""


def get_db():
    """Firestoreクライアントを返す。初期化は一度だけ行う。"""
    global _db

    if current_app.config.get("MOCK_MODE"):
        raise FirebaseConfigError("MOCK_MODE中はFirebaseへ接続しません")

    if _db is not None:
        return _db

    with _lock:
        if _db is not None:
            return _db

        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError as exc:
            raise FirebaseConfigError(
                "firebase-adminがインストールされていません。requirements.txtをインストールしてください"
            ) from exc

        cred_path = current_app.config.get("FIREBASE_CREDENTIALS_PATH")
        if not cred_path:
            raise FirebaseConfigError("FIREBASE_CREDENTIALS_PATH が設定されていません")
        if not os.path.exists(cred_path):
            raise FirebaseConfigError(
                "Firebaseサービスアカウントの認証情報が見つかりません。"
                "FIREBASE_CREDENTIALS_PATHの設定を確認してください"
            )

        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            options = {}
            project_id = current_app.config.get("FIREBASE_PROJECT_ID")
            if project_id:
                options["projectId"] = project_id
            firebase_admin.initialize_app(cred, options or None)
            logger.info("Firebase Admin SDKを初期化しました")

        _db = firestore.client()
        return _db
