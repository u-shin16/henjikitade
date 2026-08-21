import unittest

from app import create_app


class PublicPagesTestCase(unittest.TestCase):
    """紹介ページ・robots.txt・sitemap.xmlと、アプリ本体の場所を確認する。"""

    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            MOCK_MODE=True,
            WTF_CSRF_ENABLED=False,
            SESSION_COOKIE_SECURE=False,
            APP_BASE_URL="https://henji.webtool-labs.com",
        )
        self.client = self.app.test_client()

    def test_landing_is_public(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_landing_is_indexable(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('content="index, follow"', html)
        self.assertNotIn("noindex", html)

    def test_landing_has_canonical_with_https(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn(
            '<link rel="canonical" href="https://henji.webtool-labs.com/">', html
        )

    def test_app_requires_login(self):
        """アプリ本体は / ではなく /app にあり、未ログインならログインへ送る。"""
        response = self.client.get("/app")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_landing_shows_inbox_link_when_logged_in(self):
        with self.client.session_transaction() as session:
            session["user_id"] = "dummy"
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('class="lp-header-cta">受信箱へ', html)

    def test_robots_blocks_app_and_points_to_sitemap(self):
        body = self.client.get("/robots.txt").get_data(as_text=True)
        self.assertIn("Disallow: /app", body)
        self.assertIn("Disallow: /api/", body)
        self.assertIn("Sitemap: https://henji.webtool-labs.com/sitemap.xml", body)

    def test_sitemap_lists_public_pages_only(self):
        body = self.client.get("/sitemap.xml").get_data(as_text=True)
        self.assertIn("<loc>https://henji.webtool-labs.com/</loc>", body)
        self.assertIn("<loc>https://henji.webtool-labs.com/privacy</loc>", body)
        self.assertIn("<loc>https://henji.webtool-labs.com/terms</loc>", body)
        # ログイン後の画面をsitemapへ載せない
        self.assertNotIn("/app", body)
        self.assertNotIn("/login", body)

    def test_login_page_stays_noindex(self):
        html = self.client.get("/login").get_data(as_text=True)
        self.assertIn("noindex", html)


if __name__ == "__main__":
    unittest.main()
