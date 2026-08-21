import unittest

from app import create_app


class AppNavTestCase(unittest.TestCase):
    """ログイン後の4タブ（受信箱・フォーム・設定・アカウント）が全画面に出ることを確認する。"""

    PAGES = {
        "/app": "inbox",
        "/forms": "forms",
        "/settings": "settings",
        "/account": "account",
    }

    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            MOCK_MODE=True,
            WTF_CSRF_ENABLED=False,
            SESSION_COOKIE_SECURE=False,
        )
        self.client = self.app.test_client()
        self.client.get("/auth/google")  # モックログイン

    def test_every_page_shows_all_four_tabs(self):
        for path in self.PAGES:
            with self.subTest(path=path):
                html = self.client.get(path).get_data(as_text=True)
                for label in ("受信箱", "フォーム", "設定", "アカウント"):
                    self.assertIn(label, html)
                for href in ("/app", "/forms", "/settings", "/account"):
                    self.assertIn(f'href="{href}"', html)

    def test_current_tab_is_marked(self):
        """開いている画面のタブだけが is-active になる。"""
        for path in self.PAGES:
            with self.subTest(path=path):
                html = self.client.get(path).get_data(as_text=True)
                self.assertEqual(html.count("app-tab is-active"), 1)
                self.assertEqual(html.count('aria-current="page"'), 1)

    def test_account_page_requires_login(self):
        client = self.app.test_client()
        response = client.get("/account")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_logged_in_pages_are_noindex(self):
        for path in self.PAGES:
            with self.subTest(path=path):
                html = self.client.get(path).get_data(as_text=True)
                self.assertIn("noindex", html)

    def test_account_page_has_deletion_and_logout(self):
        html = self.client.get("/account").get_data(as_text=True)
        self.assertIn("account-delete-btn", html)
        self.assertIn("/logout", html)

    def test_settings_no_longer_duplicates_account_or_forms(self):
        """アカウント削除はアカウントタブへ、フォーム一覧はフォームタブへ寄せた。"""
        html = self.client.get("/settings").get_data(as_text=True)
        self.assertNotIn("account-delete-btn", html)
        self.assertNotIn("settings-form-list", html)

    def test_inbox_keeps_filter_hooks_used_by_js(self):
        """絞り込みを上部へ移したあとも dashboard.js が参照するidが残っていること。"""
        html = self.client.get("/app").get_data(as_text=True)
        for element_id in ("box-nav", "form-nav", "search-input", "date-from",
                           "date-to", "order-select", "clear-filters",
                           "inbox-list", "detail-panel", "sync-btn", "last-synced"):
            self.assertIn(f'id="{element_id}"', html)
        for box in ("all", "unread", "unhandled", "in_progress",
                    "completed", "on_hold", "important"):
            self.assertIn(f'data-box="{box}"', html)


if __name__ == "__main__":
    unittest.main()
