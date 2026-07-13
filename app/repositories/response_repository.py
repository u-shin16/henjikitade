"""users/{userId}/managed_forms/{formId}/responses/{responseId} の読み書き。

Google FormsのresponseIdをドキュメントIDとして使用することで、
同じ回答の重複登録を防止する。
"""
from datetime import datetime, timezone

from app.constants import STATUS_UNHANDLED
from app.firebase_config import get_db


def _now():
    return datetime.now(timezone.utc)


class FormResponseRepository:
    def _col(self, user_id, form_id):
        return (
            get_db()
            .collection("users").document(user_id)
            .collection("managed_forms").document(form_id)
            .collection("responses")
        )

    def exists(self, user_id, form_id, response_id):
        return self._col(user_id, form_id).document(response_id).get().exists

    def add_response(self, user_id, form_id, response_id, data):
        """新規回答を登録する。既存の場合は登録せずFalseを返す。

        is_read / status / is_important / admin_memo は初期値で登録し、
        同期による上書きはしない(既存回答はスキップされるため)。
        """
        doc = self._col(user_id, form_id).document(response_id)
        if doc.get().exists:
            return False
        now = _now()
        payload = {
            "google_response_id": response_id,
            "respondent_email": data.get("respondent_email", ""),
            "respondent_name": data.get("respondent_name", ""),
            "summary_text": data.get("summary_text", ""),
            "search_text": data.get("search_text", ""),
            "submitted_at": data.get("submitted_at") or now,
            "answers": data.get("answers", {}),
            "is_read": False,
            "status": STATUS_UNHANDLED,
            "is_important": False,
            "admin_memo": "",
            "created_at": now,
            "updated_at": now,
        }
        doc.set(payload)
        return True

    def get_response(self, user_id, form_id, response_id):
        snap = self._col(user_id, form_id).document(response_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        data["response_id"] = snap.id
        data["form_id"] = form_id
        return data

    def update_fields(self, user_id, form_id, response_id, fields):
        """is_read / status / is_important / admin_memo などを更新する。"""
        doc = self._col(user_id, form_id).document(response_id)
        if not doc.get().exists:
            return False
        fields = dict(fields)
        fields["updated_at"] = _now()
        doc.update(fields)
        return True

    def list_for_form(
        self,
        user_id,
        form_id,
        status=None,
        is_read=None,
        is_important=None,
        date_from=None,
        date_to=None,
        order_desc=True,
    ):
        """1フォーム分の回答を取得する。

        status / is_read / is_important / 期間はFirestoreクエリで絞り込む。
        文字列検索は呼び出し側(Flask)で行う。
        """
        from google.cloud.firestore_v1 import FieldFilter
        from google.cloud.firestore_v1.base_query import BaseQuery

        query = self._col(user_id, form_id)
        if status is not None:
            query = query.where(filter=FieldFilter("status", "==", status))
        if is_read is not None:
            query = query.where(filter=FieldFilter("is_read", "==", is_read))
        if is_important is not None:
            query = query.where(filter=FieldFilter("is_important", "==", is_important))
        if date_from is not None:
            query = query.where(filter=FieldFilter("submitted_at", ">=", date_from))
        if date_to is not None:
            query = query.where(filter=FieldFilter("submitted_at", "<=", date_to))

        direction = BaseQuery.DESCENDING if order_desc else BaseQuery.ASCENDING
        query = query.order_by("submitted_at", direction=direction)

        results = []
        for snap in query.stream():
            data = snap.to_dict() or {}
            data["response_id"] = snap.id
            data["form_id"] = form_id
            results.append(data)
        return results

    def count_for_form(self, user_id, form_id):
        """集計値の再計算用。全回答を走査して件数を数え直す。"""
        total = 0
        unread = 0
        unhandled = 0
        for snap in self._col(user_id, form_id).stream():
            data = snap.to_dict() or {}
            total += 1
            if not data.get("is_read"):
                unread += 1
            if data.get("status") == STATUS_UNHANDLED:
                unhandled += 1
        return {
            "response_count": total,
            "unread_count": unread,
            "unhandled_count": unhandled,
        }
