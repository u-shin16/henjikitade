"""GoogleフォームのURLまたはIDから、Forms APIで使えるフォームIDを取り出す。

利用者が貼るURLには、APIで使えるものと使えないものがある。
使えないURLを黙って弾くと原因が分からないため、種類ごとに理由を返す。

- 使える  : https://docs.google.com/forms/d/<FORM_ID>/edit
- 使えない: https://docs.google.com/forms/d/e/<LONG_ID>/viewform （回答用の別ID）
- 使えない: https://forms.gle/xxxx （短縮URL。展開しないとIDが分からない）
"""
import re

# Forms APIのformIdとして扱える文字種。Driveのファイルidと同じ形式。
FORM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,128}$")

# /forms/d/e/ は回答用URLで、ここに入るのはformIdではない
_RESPONDER_URL = re.compile(r"docs\.google\.com/forms/(?:u/\d+/)?d/e/", re.IGNORECASE)
_SHORT_URL = re.compile(r"forms\.gle/", re.IGNORECASE)
_EDIT_URL = re.compile(
    r"docs\.google\.com/forms/(?:u/\d+/)?d/([A-Za-z0-9_-]{10,128})",
    re.IGNORECASE,
)

RESPONDER_URL_MESSAGE = (
    "そのURLは回答者向けのものです。"
    "フォームの編集画面を開いたときのURL（/forms/d/ で始まるもの）を貼ってください"
)
SHORT_URL_MESSAGE = (
    "短縮URL（forms.gle）は使えません。"
    "フォームの編集画面を開いたときのURLを貼ってください"
)
UNKNOWN_MESSAGE = (
    "GoogleフォームのURLとして読み取れませんでした。"
    "フォームの編集画面を開いたときのURLをそのまま貼ってください"
)


class FormUrlError(ValueError):
    """貼られたURLからフォームIDを取り出せない。messageはそのまま画面に出す。"""


def extract_form_id(value):
    """URLまたはIDの文字列からフォームIDを返す。取り出せなければFormUrlError。"""
    text = (value or "").strip()
    if not text:
        raise FormUrlError("フォームのURLを入力してください")

    # 回答用URLと短縮URLは、編集用URLの判定より先に弾く
    if _RESPONDER_URL.search(text):
        raise FormUrlError(RESPONDER_URL_MESSAGE)
    if _SHORT_URL.search(text):
        raise FormUrlError(SHORT_URL_MESSAGE)

    match = _EDIT_URL.search(text)
    if match:
        return match.group(1)

    # URLではなくIDを直接貼られた場合
    if FORM_ID_PATTERN.match(text):
        return text

    raise FormUrlError(UNKNOWN_MESSAGE)
