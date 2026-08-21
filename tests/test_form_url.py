import unittest

import app.repositories as repositories
from app import create_app
from app.forms import form_url
from app.mock.mock_data import MOCK_USER


class ExtractFormIdTestCase(unittest.TestCase):
    def test_edit_url(self):
        self.assertEqual(
            form_url.extract_form_id(
                "https://docs.google.com/forms/d/1AbC_dEfG-hIjKlMnOpQrStUvWxYz0123456789/edit"
            ),
            "1AbC_dEfG-hIjKlMnOpQrStUvWxYz0123456789",
        )

    def test_edit_url_with_account_index(self):
        self.assertEqual(
            form_url.extract_form_id(
                "https://docs.google.com/forms/u/0/d/1AbC_dEfG-hIjKlMnOpQrStUvWxYz0123456789/edit#responses"
            ),
            "1AbC_dEfG-hIjKlMnOpQrStUvWxYz0123456789",
        )

    def test_bare_id(self):
        self.assertEqual(
            form_url.extract_form_id("  1AbC_dEfG-hIjKlMnOpQrStUvWxYz0123456789  "),
            "1AbC_dEfG-hIjKlMnOpQrStUvWxYz0123456789",
        )

    def test_responder_url_is_rejected_with_reason(self):
        """回答用URLのIDはForms APIのformIdではないため、そのまま登録してはいけない。"""
        with self.assertRaises(form_url.FormUrlError) as ctx:
            form_url.extract_form_id(
                "https://docs.google.com/forms/d/e/1FAIpQLSd_LONGRESPONDERIDxxxxxxxxxxxxxxxx/viewform"
            )
        self.assertIn("回答者向け", str(ctx.exception))

    def test_short_url_is_rejected_with_reason(self):
        with self.assertRaises(form_url.FormUrlError) as ctx:
            form_url.extract_form_id("https://forms.gle/abcd1234")
        self.assertIn("短縮URL", str(ctx.exception))

    def test_empty_input(self):
        with self.assertRaises(form_url.FormUrlError):
            form_url.extract_form_id("   ")

    def test_unrelated_url(self):
        with self.assertRaises(form_url.FormUrlError) as ctx:
            form_url.extract_form_id("https://example.com/forms/d/xxxxxxxxxx/edit")
        self.assertIn("読み取れませんでした", str(ctx.exception))


class AddFormByUrlTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            MOCK_MODE=True,
            WTF_CSRF_ENABLED=False,
            SESSION_COOKIE_SECURE=False,
        )
        repositories._mock_repos = None
        self.client = self.app.test_client()
        self.client.get("/auth/google")

    def test_adds_form_from_edit_url(self):
        response = self.client.post(
            "/api/forms/add-by-url",
            json={"url": "https://docs.google.com/forms/d/newform123456789/edit"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        with self.app.app_context():
            _, form_repo, _ = repositories.get_repositories()
            form_ids = {f["form_id"] for f in form_repo.get_forms(MOCK_USER["google_user_id"])}
        self.assertIn("newform123456789", form_ids)

    def test_registration_syncs_immediately(self):
        """登録直後に取り込まないと「未同期・回答0件」の画面になり失敗に見える。"""
        response = self.client.post(
            "/api/forms/add-by-url",
            json={"url": "https://docs.google.com/forms/d/syncnow123456789/edit"},
        )

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            _, form_repo, _ = repositories.get_repositories()
            form = form_repo.get_form(MOCK_USER["google_user_id"], "syncnow123456789")
        self.assertIsNotNone(form.get("last_synced_at"), "登録直後に同期されていない")

    def test_rejects_responder_url_before_touching_the_database(self):
        response = self.client.post(
            "/api/forms/add-by-url",
            json={"url": "https://docs.google.com/forms/d/e/1FAIpQLSdxxxxxxxxxxxxxxxxxxxx/viewform"},
        )

        self.assertEqual(response.status_code, 400)
        body = response.get_json()
        self.assertFalse(body["success"])
        self.assertIn("回答者向け", body["message"])

    def test_duplicate_registration_is_refused(self):
        url = "https://docs.google.com/forms/d/duplicate12345678/edit"
        self.client.post("/api/forms/add-by-url", json={"url": url})

        response = self.client.post("/api/forms/add-by-url", json={"url": url})

        self.assertEqual(response.status_code, 409)
        self.assertIn("すでに登録", response.get_json()["message"])


class OAuthScopeTestCase(unittest.TestCase):
    def test_no_restricted_drive_scope(self):
        """制限付きスコープを要求すると検証にCASAが必要になるため、含めない。"""
        from app.auth import google_oauth

        self.assertNotIn(
            "https://www.googleapis.com/auth/drive.metadata.readonly",
            google_oauth.SCOPES,
        )
        self.assertFalse(
            [s for s in google_oauth.SCOPES if "drive" in s],
            "Driveスコープは不要になったはず",
        )


if __name__ == "__main__":
    unittest.main()


class DeleteFormTestCase(unittest.TestCase):
    """登録したフォームを完全に削除する操作。

    「管理対象から外す」(set_active)はデータを残すため、間違えて登録した
    フォームが一覧に残り続ける。こちらは取り消せない削除。
    """

    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            MOCK_MODE=True,
            WTF_CSRF_ENABLED=False,
            SESSION_COOKIE_SECURE=False,
        )
        repositories._mock_repos = None
        self.client = self.app.test_client()
        self.client.get("/auth/google")
        self.user_id = MOCK_USER["google_user_id"]

    def _form_ids(self):
        with self.app.app_context():
            _, form_repo, _ = repositories.get_repositories()
            return {f["form_id"] for f in form_repo.get_forms(self.user_id)}

    def test_deletes_the_form_from_the_list(self):
        form_id = next(iter(self._form_ids()))

        response = self.client.post(f"/api/forms/{form_id}/delete")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertNotIn(form_id, self._form_ids())

    def test_deletes_saved_responses_too(self):
        """回答を残すと、同じフォームを登録し直したときに復活してしまう。"""
        form_id = next(iter(self._form_ids()))
        with self.app.app_context():
            _, _, response_repo = repositories.get_repositories()
            response_repo.add_response(self.user_id, form_id, "r1", {"answers": {}})
            self.assertTrue(response_repo.exists(self.user_id, form_id, "r1"))

        self.client.post(f"/api/forms/{form_id}/delete")

        with self.app.app_context():
            _, _, response_repo = repositories.get_repositories()
            self.assertFalse(response_repo.exists(self.user_id, form_id, "r1"))

    def test_deletes_the_watch_route(self):
        """経路が残ると、届いた通知が存在しないフォームを指したままになる。"""
        form_id = next(iter(self._form_ids()))
        with self.app.app_context():
            _, form_repo, _ = repositories.get_repositories()
            form_repo.save_watch_route(self.user_id, form_id, "watch-to-delete")
            self.assertIsNotNone(form_repo.get_watch_route("watch-to-delete"))

        self.client.post(f"/api/forms/{form_id}/delete")

        with self.app.app_context():
            _, form_repo, _ = repositories.get_repositories()
            self.assertIsNone(form_repo.get_watch_route("watch-to-delete"))

    def test_unknown_form_returns_404(self):
        response = self.client.post("/api/forms/notregistered123/delete")

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.get_json()["success"])

    def test_other_forms_are_untouched(self):
        before = self._form_ids()
        self.assertGreater(len(before), 1, "モックに複数フォームが必要")
        target = next(iter(before))

        self.client.post(f"/api/forms/{target}/delete")

        self.assertEqual(self._form_ids(), before - {target})
