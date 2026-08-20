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
