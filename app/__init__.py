import logging

from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError

from .config import Config
from .constants import APP_DESCRIPTION, APP_NAME, CONTACT_FORM_URL, STATUS_LABELS
from .extensions import csrf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    csrf.init_app(app)

    from .auth.routes import auth_bp
    from .dashboard.routes import dashboard_bp
    from .forms.routes import forms_bp
    from .responses.routes import responses_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(forms_bp)
    app.register_blueprint(responses_bp)

    @app.template_filter("jpdatetime")
    def jpdatetime_filter(value):
        """FirestoreのTimestamp(datetime)をローカル時刻の文字列へ整形する。"""
        from datetime import datetime

        if value is None:
            return "未同期"
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return value
        try:
            return value.astimezone().strftime("%Y/%m/%d %H:%M")
        except (ValueError, OSError):
            return str(value)

    @app.context_processor
    def inject_globals():
        return {
            "APP_NAME": APP_NAME,
            "APP_DESCRIPTION": APP_DESCRIPTION,
            "CONTACT_FORM_URL": CONTACT_FORM_URL,
            "STATUS_LABELS": STATUS_LABELS,
            "MOCK_MODE": app.config.get("MOCK_MODE", False),
        }

    _register_error_handlers(app)

    return app


def _is_api_request():
    return request.path.startswith("/api/")


def _register_error_handlers(app):
    logger = logging.getLogger(__name__)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if _is_api_request():
            return jsonify({"success": False, "message": "セッションの有効期限が切れました。ページを再読み込みしてください"}), 400
        return render_template("errors/400.html", message="不正なリクエストです"), 400

    @app.errorhandler(400)
    def handle_400(e):
        if _is_api_request():
            return jsonify({"success": False, "message": "リクエストの内容が正しくありません"}), 400
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def handle_403(e):
        if _is_api_request():
            return jsonify({"success": False, "message": "この操作を行う権限がありません"}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def handle_404(e):
        if _is_api_request():
            return jsonify({"success": False, "message": "データが見つかりませんでした"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def handle_500(e):
        logger.exception("内部エラーが発生しました")
        if _is_api_request():
            return jsonify({"success": False, "message": "サーバーでエラーが発生しました。時間を空けて再度お試しください"}), 500
        return render_template("errors/500.html"), 500
