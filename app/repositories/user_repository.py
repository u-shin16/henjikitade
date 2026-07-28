"""users/{userId} の読み書き。"""
from datetime import datetime, timezone

from app.firebase_config import get_db


def _now():
    return datetime.now(timezone.utc)


class UserRepository:
    def _doc(self, user_id):
        return get_db().collection("users").document(user_id)

    def get_user(self, user_id):
        snap = self._doc(user_id).get()
        return snap.to_dict() if snap.exists else None

    def list_user_ids(self):
        return [snap.id for snap in get_db().collection("users").stream()]

    def create_or_update_user(self, user_id, data):
        doc = self._doc(user_id)
        snap = doc.get()
        now = _now()
        payload = {
            "google_user_id": user_id,
            "email": data.get("email", ""),
            "name": data.get("name", ""),
            "picture_url": data.get("picture_url", ""),
            "updated_at": now,
        }
        if snap.exists:
            doc.update(payload)
        else:
            payload["created_at"] = now
            doc.set(payload)
        return payload

    # OAuthトークンは暗号化済みの文字列を専用サブコレクションへ保存する
    def _token_doc(self, user_id):
        return self._doc(user_id).collection("private").document("oauth_token")

    def save_oauth_token(self, user_id, encrypted_token):
        self._token_doc(user_id).set({
            "token": encrypted_token,
            "updated_at": _now(),
        })

    def get_oauth_token(self, user_id):
        snap = self._token_doc(user_id).get()
        if not snap.exists:
            return None
        return (snap.to_dict() or {}).get("token")

    def delete_oauth_token(self, user_id):
        self._token_doc(user_id).delete()

    def delete_user(self, user_id):
        """ユーザー文書と配下の全サブコレクションを再帰的に削除する。"""
        return get_db().recursive_delete(self._doc(user_id))
