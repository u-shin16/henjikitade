"""モックモード用のRepository実装。

Firestoreへ接続せず、メモリ上のデータストアに対して
本番Repositoryと同じインターフェースを提供する。
"""
import copy
from datetime import datetime, timezone

from app.constants import STATUS_UNHANDLED


def _now():
    return datetime.now(timezone.utc)


class MockUserRepository:
    def __init__(self, store):
        self.store = store

    def get_user(self, user_id):
        return copy.deepcopy(self.store["users"].get(user_id))

    def list_user_ids(self):
        return list(self.store["users"].keys())

    def create_or_update_user(self, user_id, data):
        now = _now()
        user = self.store["users"].get(user_id) or {"created_at": now}
        user.update({
            "google_user_id": user_id,
            "email": data.get("email", ""),
            "name": data.get("name", ""),
            "picture_url": data.get("picture_url", ""),
            "updated_at": now,
        })
        self.store["users"][user_id] = user
        return copy.deepcopy(user)

    def save_oauth_token(self, user_id, encrypted_token):
        self.store["tokens"][user_id] = encrypted_token

    def get_oauth_token(self, user_id):
        return self.store["tokens"].get(user_id)

    def delete_oauth_token(self, user_id):
        self.store["tokens"].pop(user_id, None)

    def delete_user(self, user_id):
        self.store["users"].pop(user_id, None)
        self.store["tokens"].pop(user_id, None)
        self.store["forms"].pop(user_id, None)
        self.store["responses"].pop(user_id, None)


class MockManagedFormRepository:
    def __init__(self, store):
        self.store = store

    def _forms(self, user_id):
        return self.store["forms"].setdefault(user_id, {})

    def get_forms(self, user_id, active_only=False):
        forms = []
        for form_id, form in self._forms(user_id).items():
            if active_only and not form.get("is_active"):
                continue
            data = copy.deepcopy(form)
            data["form_id"] = form_id
            forms.append(data)
        forms.sort(key=lambda f: (f.get("title") or ""))
        return forms

    def get_form(self, user_id, form_id):
        form = self._forms(user_id).get(form_id)
        if form is None:
            return None
        data = copy.deepcopy(form)
        data["form_id"] = form_id
        return data

    def add_form(self, user_id, form_id, title):
        forms = self._forms(user_id)
        now = _now()
        if form_id in forms:
            forms[form_id].update({"is_active": True, "title": title, "updated_at": now})
        else:
            forms[form_id] = {
                "google_form_id": form_id,
                "title": title,
                "is_active": True,
                "response_count": 0,
                "unread_count": 0,
                "unhandled_count": 0,
                "last_synced_at": None,
                "created_at": now,
                "updated_at": now,
            }
            self.store["responses"].setdefault(user_id, {}).setdefault(form_id, {})

    def set_active(self, user_id, form_id, is_active):
        form = self._forms(user_id).get(form_id)
        if form is None:
            return False
        form["is_active"] = bool(is_active)
        form["updated_at"] = _now()
        return True

    def update_form(self, user_id, form_id, fields):
        form = self._forms(user_id).get(form_id)
        if form is None:
            return False
        form.update(fields)
        form["updated_at"] = _now()
        return True

    def save_watch_route(self, user_id, form_id, watch_id):
        if not watch_id:
            return False
        self.store.setdefault("watch_routes", {})[watch_id] = {
            "watch_id": watch_id,
            "user_id": user_id,
            "form_id": form_id,
            "event_type": "RESPONSES",
            "updated_at": _now(),
        }
        return True

    def get_watch_route(self, watch_id):
        route = self.store.setdefault("watch_routes", {}).get(watch_id)
        return copy.deepcopy(route) if route else None

    def delete_form(self, user_id, form_id):
        forms = self._forms(user_id)
        if form_id not in forms:
            return False
        del forms[form_id]
        # 回答も一緒に消す（本番のrecursive_deleteに合わせる）。
        # 残すと、同じフォームを登録し直したときに古い回答が復活する。
        self.store.get("responses", {}).get(user_id, {}).pop(form_id, None)
        return True

    def delete_watch_routes_for_form(self, user_id, form_id):
        routes = self.store.setdefault("watch_routes", {})
        targets = [
            watch_id
            for watch_id, route in routes.items()
            if route.get("user_id") == user_id and route.get("form_id") == form_id
        ]
        for watch_id in targets:
            del routes[watch_id]
        return len(targets)

    def delete_watch_routes_for_user(self, user_id):
        routes = self.store.setdefault("watch_routes", {})
        targets = [
            watch_id
            for watch_id, route in routes.items()
            if route.get("user_id") == user_id
        ]
        for watch_id in targets:
            routes.pop(watch_id, None)
        return len(targets)


class MockFormResponseRepository:
    def __init__(self, store):
        self.store = store

    def _responses(self, user_id, form_id):
        return (
            self.store["responses"]
            .setdefault(user_id, {})
            .setdefault(form_id, {})
        )

    def exists(self, user_id, form_id, response_id):
        return response_id in self._responses(user_id, form_id)

    def add_response(self, user_id, form_id, response_id, data):
        responses = self._responses(user_id, form_id)
        if response_id in responses:
            return False
        now = _now()
        responses[response_id] = {
            "google_response_id": response_id,
            "respondent_email": data.get("respondent_email", ""),
            "respondent_name": data.get("respondent_name", ""),
            "summary_text": data.get("summary_text", ""),
            "search_text": data.get("search_text", ""),
            "submitted_at": data.get("submitted_at") or now,
            "answers": data.get("answers", {}),
            "is_read": data.get("is_read", False),
            "status": data.get("status", STATUS_UNHANDLED),
            "is_important": data.get("is_important", False),
            "admin_memo": data.get("admin_memo", ""),
            "created_at": now,
            "updated_at": now,
        }
        return True

    def get_response(self, user_id, form_id, response_id):
        response = self._responses(user_id, form_id).get(response_id)
        if response is None:
            return None
        data = copy.deepcopy(response)
        data["response_id"] = response_id
        data["form_id"] = form_id
        return data

    def update_fields(self, user_id, form_id, response_id, fields):
        response = self._responses(user_id, form_id).get(response_id)
        if response is None:
            return False
        response.update(fields)
        response["updated_at"] = _now()
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
        results = []
        for response_id, response in self._responses(user_id, form_id).items():
            if status is not None and response.get("status") != status:
                continue
            if is_read is not None and bool(response.get("is_read")) != is_read:
                continue
            if is_important is not None and bool(response.get("is_important")) != is_important:
                continue
            submitted = response.get("submitted_at")
            if date_from is not None and (submitted is None or submitted < date_from):
                continue
            if date_to is not None and (submitted is None or submitted > date_to):
                continue
            data = copy.deepcopy(response)
            data["response_id"] = response_id
            data["form_id"] = form_id
            results.append(data)
        results.sort(
            key=lambda r: r.get("submitted_at") or _now(),
            reverse=order_desc,
        )
        return results

    def count_for_form(self, user_id, form_id):
        responses = self._responses(user_id, form_id)
        return {
            "response_count": len(responses),
            "unread_count": sum(1 for r in responses.values() if not r.get("is_read")),
            "unhandled_count": sum(
                1 for r in responses.values() if r.get("status") == STATUS_UNHANDLED
            ),
        }
