"""users/{userId}/managed_forms/{formId} の読み書き。"""
from datetime import datetime, timezone

from app.firebase_config import get_db


def _now():
    return datetime.now(timezone.utc)


class ManagedFormRepository:
    def _col(self, user_id):
        return get_db().collection("users").document(user_id).collection("managed_forms")

    def get_forms(self, user_id, active_only=False):
        forms = []
        for snap in self._col(user_id).stream():
            data = snap.to_dict() or {}
            data["form_id"] = snap.id
            if active_only and not data.get("is_active"):
                continue
            forms.append(data)
        forms.sort(key=lambda f: (f.get("title") or ""))
        return forms

    def get_form(self, user_id, form_id):
        snap = self._col(user_id).document(form_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        data["form_id"] = snap.id
        return data

    def add_form(self, user_id, form_id, title):
        """管理対象へ追加する。過去に登録済みなら再有効化する。"""
        doc = self._col(user_id).document(form_id)
        snap = doc.get()
        now = _now()
        if snap.exists:
            doc.update({"is_active": True, "title": title, "updated_at": now})
        else:
            doc.set({
                "google_form_id": form_id,
                "title": title,
                "is_active": True,
                "response_count": 0,
                "unread_count": 0,
                "unhandled_count": 0,
                "last_synced_at": None,
                "created_at": now,
                "updated_at": now,
            })

    def set_active(self, user_id, form_id, is_active):
        """管理対象から外す場合もデータは削除せずis_activeのみ変更する。"""
        doc = self._col(user_id).document(form_id)
        if not doc.get().exists:
            return False
        doc.update({"is_active": bool(is_active), "updated_at": _now()})
        return True

    def update_form(self, user_id, form_id, fields):
        doc = self._col(user_id).document(form_id)
        if not doc.get().exists:
            return False
        fields = dict(fields)
        fields["updated_at"] = _now()
        doc.update(fields)
        return True
