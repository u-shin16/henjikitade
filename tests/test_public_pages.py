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

    PUBLIC_PATHS = ["/", "/how-to-use", "/faq", "/about", "/contact", "/privacy", "/terms"]

    def test_landing_is_public(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_all_public_pages_respond(self):
        for path in self.PUBLIC_PATHS:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_public_pages_have_own_canonical(self):
        """canonicalが各ページ自身を指していること（全部トップを指すと重複扱いになる）。"""
        expected = {
            "/how-to-use": "https://henji.webtool-labs.com/how-to-use",
            "/faq": "https://henji.webtool-labs.com/faq",
            "/about": "https://henji.webtool-labs.com/about",
            "/contact": "https://henji.webtool-labs.com/contact",
            "/privacy": "https://henji.webtool-labs.com/privacy",
            "/terms": "https://henji.webtool-labs.com/terms",
        }
        for path, url in expected.items():
            with self.subTest(path=path):
                html = self.client.get(path).get_data(as_text=True)
                self.assertIn(f'<link rel="canonical" href="{url}">', html)

    def test_sibling_pages_have_own_description(self):
        """メタディスクリプションが使い回しになっていないこと。"""
        import re
        seen = {}
        for path in self.PUBLIC_PATHS:
            html = self.client.get(path).get_data(as_text=True)
            m = re.search(r'<meta name="description" content="([^"]+)"', html)
            self.assertIsNotNone(m, f"{path} にdescriptionが無い")
            self.assertNotIn(m.group(1), seen, f"{path} のdescriptionが {seen.get(m.group(1))} と同じ")
            seen[m.group(1)] = path

    def test_faq_has_faqpage_structured_data(self):
        import json
        import re
        html = self.client.get("/faq").get_data(as_text=True)
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        self.assertTrue(blocks, "構造化データが無い")
        data = json.loads(blocks[0])
        self.assertEqual(data["@type"], "FAQPage")
        self.assertGreaterEqual(len(data["mainEntity"]), 5)

    def test_pages_link_to_each_other(self):
        """どのページからも兄弟ページへ辿れること。"""
        for path in self.PUBLIC_PATHS:
            with self.subTest(path=path):
                html = self.client.get(path).get_data(as_text=True)
                for href in ["/how-to-use", "/faq", "/about", "/contact"]:
                    self.assertIn(f'href="{href}"', html)

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
        for path in ("/how-to-use", "/faq", "/about", "/contact"):
            self.assertIn(f"<loc>https://henji.webtool-labs.com{path}</loc>", body)
        # ログイン後の画面をsitemapへ載せない
        self.assertNotIn("/app", body)
        self.assertNotIn("/login", body)

    def test_login_page_stays_noindex(self):
        html = self.client.get("/login").get_data(as_text=True)
        self.assertIn("noindex", html)


if __name__ == "__main__":
    unittest.main()
