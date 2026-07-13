from functools import wraps

from flask import jsonify, redirect, request, session, url_for


def login_required(f):
    """ログイン必須のルートへ付けるデコレーター。

    APIエンドポイントの場合はJSONで401を返し、
    画面の場合はログインページへリダイレクトする。
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "ログインが必要です"}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return wrapper


def current_user_id():
    """セッションからログインユーザーIDを取得する。

    URLパラメータ等から渡されたuserIdは信用しない。
    """
    return session.get("user_id")
