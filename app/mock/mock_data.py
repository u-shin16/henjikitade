"""モックモード用のダミーデータ。

Google APIとFirebaseへ接続せずにUIを確認するためのデータ。
"""
from datetime import datetime, timedelta, timezone

from app.constants import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_ON_HOLD,
    STATUS_UNHANDLED,
)

MOCK_USER = {
    "google_user_id": "mock-user-001",
    "email": "mock.user@example.com",
    "name": "モック ユーザー",
    "picture_url": "",
}

FORM_USHIN = "mock-form-ushin"
FORM_HAYAOKI = "mock-form-hayaoki"
FORM_MATOME = "mock-form-matome"
FORM_EXTRA = "mock-form-extra"


def _now():
    return datetime.now(timezone.utc)


def _ago(**kwargs):
    return _now() - timedelta(**kwargs)


def _answers(pairs):
    answers = {}
    for i, (question, answer) in enumerate(pairs, start=1):
        qid = f"q{i:02d}"
        answers[qid] = {
            "question_id": qid,
            "question": question,
            "answer": answer,
            "order": i,
        }
    return answers


def _search_text(name, email, answers, memo=""):
    parts = [name, email, memo]
    for a in answers.values():
        parts.append(a["question"])
        value = a["answer"]
        if isinstance(value, list):
            parts.extend(value)
        else:
            parts.append(str(value))
    return " ".join(p for p in parts if p).lower()


def _response(
    response_id,
    submitted_at,
    name,
    email,
    body,
    answers,
    is_read=False,
    status=STATUS_UNHANDLED,
    is_important=False,
    admin_memo="",
):
    return {
        "google_response_id": response_id,
        "respondent_name": name,
        "respondent_email": email,
        "summary_text": (body or "")[:100],
        "search_text": _search_text(name, email, answers, admin_memo),
        "submitted_at": submitted_at,
        "answers": answers,
        "is_read": is_read,
        "status": status,
        "is_important": is_important,
        "admin_memo": admin_memo,
        "created_at": submitted_at,
        "updated_at": submitted_at,
    }


def build_mock_store():
    """モックRepositoryが使用するメモリ上のデータストアを構築する。"""
    now = _now()

    forms = {
        FORM_USHIN: {
            "google_form_id": FORM_USHIN,
            "title": "u-shin お問い合わせフォーム",
            "is_active": True,
            "response_count": 0,
            "unread_count": 0,
            "unhandled_count": 0,
            "last_synced_at": _ago(hours=2),
            "created_at": _ago(days=30),
            "updated_at": _ago(hours=2),
        },
        FORM_HAYAOKI: {
            "google_form_id": FORM_HAYAOKI,
            "title": "はよおきんかい フィードバック",
            "is_active": True,
            "response_count": 0,
            "unread_count": 0,
            "unhandled_count": 0,
            "last_synced_at": _ago(hours=2),
            "created_at": _ago(days=25),
            "updated_at": _ago(hours=2),
        },
        FORM_MATOME: {
            "google_form_id": FORM_MATOME,
            "title": "まとめときや フィードバック",
            "is_active": True,
            "response_count": 0,
            "unread_count": 0,
            "unhandled_count": 0,
            "last_synced_at": _ago(hours=2),
            "created_at": _ago(days=20),
            "updated_at": _ago(hours=2),
        },
    }

    responses = {
        FORM_USHIN: {},
        FORM_HAYAOKI: {},
        FORM_MATOME: {},
    }

    # 未読・未対応・重要な問い合わせ(今日)
    a = _answers([
        ("お名前", "山田太郎"),
        ("メールアドレス", "taro.yamada@example.com"),
        ("お問い合わせ内容", "ログインしようとすると「認証に失敗しました」と表示されて先へ進めません。昨日までは問題なく使えていました。急ぎで確認をお願いします。"),
    ])
    responses[FORM_USHIN]["mock-res-001"] = _response(
        "mock-res-001", _ago(hours=1),
        "山田太郎", "taro.yamada@example.com",
        "ログインしようとすると「認証に失敗しました」と表示されて先へ進めません。昨日までは問題なく使えていました。急ぎで確認をお願いします。",
        a, is_read=False, status=STATUS_UNHANDLED, is_important=True,
    )

    # 未読・未対応(今日)
    a = _answers([
        ("氏名", "佐藤花子"),
        ("メール", "hanako@example.com"),
        ("ご意見", "アラーム音の種類をもっと増やしてほしいです。自然の音があると嬉しいです。"),
        ("希望する機能", ["通知機能", "ダークモード"]),
    ])
    responses[FORM_HAYAOKI]["mock-res-002"] = _response(
        "mock-res-002", _ago(hours=3),
        "佐藤花子", "hanako@example.com",
        "アラーム音の種類をもっと増やしてほしいです。自然の音があると嬉しいです。",
        a, is_read=False, status=STATUS_UNHANDLED,
    )

    # 未読・メールアドレスが取得できない問い合わせ
    a = _answers([
        ("フィードバック", "まとめ記事の表示が崩れることがあります。スマホのChromeで発生します。"),
    ])
    responses[FORM_MATOME]["mock-res-003"] = _response(
        "mock-res-003", _ago(hours=5),
        "", "",
        "まとめ記事の表示が崩れることがあります。スマホのChromeで発生します。",
        a, is_read=False, status=STATUS_UNHANDLED,
    )

    # 既読・対応中・管理者メモあり
    a = _answers([
        ("お名前", "鈴木一郎"),
        ("メールアドレス", "ichiro.s@example.com"),
        ("お問い合わせ内容", "データのエクスポート機能はありますか?CSVで出力できると助かります。"),
    ])
    responses[FORM_USHIN]["mock-res-004"] = _response(
        "mock-res-004", _ago(days=1, hours=2),
        "鈴木一郎", "ichiro.s@example.com",
        "データのエクスポート機能はありますか?CSVで出力できると助かります。",
        a, is_read=True, status=STATUS_IN_PROGRESS,
        admin_memo="7月15日に返信予定。CSV出力は次回アップデートで対応。",
    )

    # 既読・対応済み
    a = _answers([
        ("氏名", "田中美咲"),
        ("メール", "misaki.t@example.com"),
        ("ご意見", "とても使いやすいアプリです。毎朝助かっています!"),
        ("満足度", "5"),
    ])
    responses[FORM_HAYAOKI]["mock-res-005"] = _response(
        "mock-res-005", _ago(days=2),
        "田中美咲", "misaki.t@example.com",
        "とても使いやすいアプリです。毎朝助かっています!",
        a, is_read=True, status=STATUS_COMPLETED,
    )

    # 既読・保留・管理者メモあり
    a = _answers([
        ("フィードバック", "広告が多すぎる気がします。有料プランで広告を消せるようにしてほしいです。"),
        ("利用頻度", "毎日"),
    ])
    responses[FORM_MATOME]["mock-res-006"] = _response(
        "mock-res-006", _ago(days=3),
        "", "",
        "広告が多すぎる気がします。有料プランで広告を消せるようにしてほしいです。",
        a, is_read=True, status=STATUS_ON_HOLD,
        admin_memo="有料プランは検討中のため保留。方針が決まり次第対応する。",
    )

    # 既読・対応済み・重要
    a = _answers([
        ("お名前", "高橋健"),
        ("メールアドレス", "ken.takahashi@example.com"),
        ("お問い合わせ内容", "退会したのにメールが届き続けています。個人情報の削除をお願いします。"),
    ])
    responses[FORM_USHIN]["mock-res-007"] = _response(
        "mock-res-007", _ago(days=4),
        "高橋健", "ken.takahashi@example.com",
        "退会したのにメールが届き続けています。個人情報の削除をお願いします。",
        a, is_read=True, status=STATUS_COMPLETED, is_important=True,
        admin_memo="7月10日対応済み。メール配信リストから削除完了。",
    )

    # 既読・未対応(迷惑問い合わせの可能性)
    a = _answers([
        ("氏名", "spam bot"),
        ("メール", "spam@example.com"),
        ("ご意見", "Check out this amazing offer!!! Click here now!!!"),
    ])
    responses[FORM_HAYAOKI]["mock-res-008"] = _response(
        "mock-res-008", _ago(days=5),
        "spam bot", "spam@example.com",
        "Check out this amazing offer!!! Click here now!!!",
        a, is_read=True, status=STATUS_UNHANDLED,
        admin_memo="迷惑問い合わせの可能性あり。返信不要。",
    )

    # 既読・対応済み(古い問い合わせ)
    a = _answers([
        ("フィードバック", "検索機能が便利になりました。ありがとうございます。"),
    ])
    responses[FORM_MATOME]["mock-res-009"] = _response(
        "mock-res-009", _ago(days=10),
        "", "",
        "検索機能が便利になりました。ありがとうございます。",
        a, is_read=True, status=STATUS_COMPLETED,
    )

    # Google Drive上に存在する(未管理の)フォームも含めた一覧
    available_forms = [
        {"id": FORM_USHIN, "name": "u-shin お問い合わせフォーム",
         "modifiedTime": (_ago(days=1)).isoformat(),
         "webViewLink": "https://docs.google.com/forms/d/mock-ushin/edit"},
        {"id": FORM_HAYAOKI, "name": "はよおきんかい フィードバック",
         "modifiedTime": (_ago(days=2)).isoformat(),
         "webViewLink": "https://docs.google.com/forms/d/mock-hayaoki/edit"},
        {"id": FORM_MATOME, "name": "まとめときや フィードバック",
         "modifiedTime": (_ago(days=3)).isoformat(),
         "webViewLink": "https://docs.google.com/forms/d/mock-matome/edit"},
        {"id": FORM_EXTRA, "name": "新サービス 事前アンケート",
         "modifiedTime": (_ago(days=5)).isoformat(),
         "webViewLink": "https://docs.google.com/forms/d/mock-extra/edit"},
    ]

    store = {
        "users": {},
        "tokens": {},
        "forms": {MOCK_USER["google_user_id"]: forms},
        "responses": {MOCK_USER["google_user_id"]: responses},
        "watch_routes": {},
        "available_forms": available_forms,
        "sync_done": False,
    }

    # 集計値を初期化する
    for form_id, form in forms.items():
        rs = responses.get(form_id, {})
        form["response_count"] = len(rs)
        form["unread_count"] = sum(1 for r in rs.values() if not r["is_read"])
        form["unhandled_count"] = sum(1 for r in rs.values() if r["status"] == STATUS_UNHANDLED)

    return store


def build_new_mock_response():
    """モックの手動同期で追加される「新しい回答」。"""
    a = _answers([
        ("お名前", "中村さくら"),
        ("メールアドレス", "sakura.n@example.com"),
        ("お問い合わせ内容", "パスワードの再設定メールが届きません。迷惑メールフォルダも確認しましたが見つかりませんでした。"),
    ])
    return FORM_USHIN, "mock-res-new-001", _response(
        "mock-res-new-001", _now(),
        "中村さくら", "sakura.n@example.com",
        "パスワードの再設定メールが届きません。迷惑メールフォルダも確認しましたが見つかりませんでした。",
        a, is_read=False, status=STATUS_UNHANDLED,
    )
