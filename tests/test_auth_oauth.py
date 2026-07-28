import unittest
from unittest.mock import patch

from app import create_app


class OAuthCallbackErrorTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            MOCK_MODE=False,
            SESSION_COOKIE_SECURE=False,
        )
        self.client = self.app.test_client()

    def _set_oauth_session(self, state="expected-state", code_verifier="verifier"):
        with self.client.session_transaction() as browser_session:
            browser_session["oauth_state"] = state
            browser_session["oauth_code_verifier"] = code_verifier

    def test_access_denied_explains_account_access_problem(self):
        self._set_oauth_session()

        with patch("app.auth.routes.google_oauth.build_flow") as build_flow:
            response = self.client.get(
                "/auth/callback?state=expected-state&error=access_denied",
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Googleログインが許可されませんでした".encode(), response.data)
        self.assertIn("指定されたGoogleアカウント".encode(), response.data)
        build_flow.assert_not_called()

    def test_oauth_error_still_requires_valid_state(self):
        self._set_oauth_session()

        response = self.client.get(
            "/auth/callback?state=wrong-state&error=access_denied",
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("ログインの検証に失敗しました".encode(), response.data)
        self.assertNotIn("指定されたGoogleアカウント".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
