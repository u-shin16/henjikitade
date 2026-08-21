"""ログイン不要の公開ページ。

`/`はアプリ本体ではなく紹介ページ。アプリ本体は`/app`（ログイン必須）。
検索エンジンに拾わせるのはここだけで、ログイン後の画面はnoindexにしている。
"""
from flask import Blueprint, Response, current_app, render_template, session, url_for

public_bp = Blueprint("public", __name__)


def absolute_url(endpoint, **values):
    """公開URLを絶対URLで返す。

    nginxがX-Forwarded-Protoを送っていないため`_external=True`はhttpを返す。
    canonicalやsitemapがhttpになるとhttps版と別URL扱いになるので、
    設定済みのAPP_BASE_URLを基準にする。
    """
    base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    path = url_for(endpoint, **values)
    if not base:
        return url_for(endpoint, _external=True, **values)
    return f"{base}{path}"

# sitemap.xmlに載せる公開ページ。ログイン後にしか意味を持たないページは載せない。
PUBLIC_PAGES = [
    ("public.landing", "1.0"),
    ("public.how_to_use", "0.7"),
    ("public.faq", "0.7"),
    ("public.about", "0.4"),
    ("public.contact", "0.4"),
    ("auth.privacy", "0.3"),
    ("auth.terms", "0.3"),
]


def render_public(template, endpoint):
    """公開ページ共通の変数を渡す。

    canonical_endpoint はcanonicalとog:urlに使う。
    logged_in はヘッダーの導線を「はじめる」か「受信箱へ」かの出し分けに使う。
    """
    return render_template(
        template,
        canonical_endpoint=endpoint,
        logged_in=bool(session.get("user_id")),
    )


@public_bp.route("/")
def landing():
    # ログイン済みの人には「はじめる」ではなく受信箱への導線を出す。
    # 以前は`/`が受信箱だったため、ブックマークから来る人がいる。
    return render_public("landing.html", "public.landing")


@public_bp.route("/how-to-use")
def how_to_use():
    return render_public("how_to_use.html", "public.how_to_use")


@public_bp.route("/faq")
def faq():
    return render_public("faq.html", "public.faq")


@public_bp.route("/about")
def about():
    return render_public("about.html", "public.about")


@public_bp.route("/contact")
def contact():
    return render_public("contact.html", "public.contact")


@public_bp.route("/robots.txt")
def robots():
    lines = [
        "User-agent: *",
        "Disallow: /app",
        "Disallow: /forms",
        "Disallow: /settings",
        "Disallow: /login",
        "Disallow: /auth/",
        "Disallow: /api/",
        "",
        f"Sitemap: {absolute_url('public.sitemap')}",
        "",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@public_bp.route("/sitemap.xml")
def sitemap():
    urls = []
    for endpoint, priority in PUBLIC_PAGES:
        urls.append(
            "  <url>\n"
            f"    <loc>{absolute_url(endpoint)}</loc>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    return Response(body, mimetype="application/xml")
