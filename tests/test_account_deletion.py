import time
import unittest

import app.repositories as repositories
from app import create_app
from app.mock.mock_data import MOCK_USER


class AccountDeletionTestCase(unittest.TestCase):
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

    def test_delete_account_removes_all_mock_data_and_logs_out(self):
        user_id = MOCK_USER["google_user_id"]
        with self.app.app_context():
            user_repo, form_repo, _ = repositories.get_repositories()
            form_repo.save_watch_route(
                user_id,
                "mock-form-ushin",
                "mock-watch-001",
            )
            self.assertIsNotNone(user_repo.get_user(user_id))

        response = self.client.post("/api/account/delete", json={})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        with self.app.app_context():
            user_repo, form_repo, _ = repositories.get_repositories()
            self.assertIsNone(user_repo.get_user(user_id))
            self.assertEqual(form_repo.get_forms(user_id), [])
            self.assertIsNone(form_repo.get_watch_route("mock-watch-001"))
        self.assertEqual(self.client.get("/settings").status_code, 302)

    def test_delete_account_requires_recent_login(self):
        with self.client.session_transaction() as browser_session:
            browser_session["authenticated_at"] = time.time() - 3600

        response = self.client.post("/api/account/delete", json={})

        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.get_json()["data"]["need_reauth"])
        with self.app.app_context():
            user_repo, _, _ = repositories.get_repositories()
            self.assertIsNotNone(user_repo.get_user(MOCK_USER["google_user_id"]))


if __name__ == "__main__":
    unittest.main()
