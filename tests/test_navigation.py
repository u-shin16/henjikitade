import unittest

import app.repositories as repositories
from app import create_app


class MainNavigationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            MOCK_MODE=True,
            SESSION_COOKIE_SECURE=False,
        )
        repositories._mock_repos = None
        self.client = self.app.test_client()
        self.client.get("/auth/google")

    def test_four_main_destinations_are_available(self):
        destinations = {
            "/": "受信箱",
            "/forms": "フォーム",
            "/settings": "設定",
            "/account": "アカウント",
        }

        for path, title in destinations.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(title.encode(), response.data)
                for nav_label in destinations.values():
                    self.assertIn(nav_label.encode(), response.data)

    def test_account_actions_are_separated_from_settings(self):
        account_response = self.client.get("/account")
        settings_response = self.client.get("/settings")

        self.assertIn("ログアウト".encode(), account_response.data)
        self.assertIn("アカウントを削除".encode(), account_response.data)
        self.assertNotIn("アカウントを削除".encode(), settings_response.data)

    def test_forms_are_rendered_as_cards(self):
        response = self.client.get("/forms")

        self.assertIn(b'class="form-card', response.data)
        self.assertNotIn(b'class="forms-table"', response.data)


if __name__ == "__main__":
    unittest.main()
