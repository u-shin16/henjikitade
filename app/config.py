import os

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name, default="false"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-me"
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000")

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")

    FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")
    FIREBASE_CREDENTIALS_PATH = os.environ.get("FIREBASE_CREDENTIALS_PATH", "")

    GOOGLE_FORMS_PUBSUB_TOPIC = os.environ.get("GOOGLE_FORMS_PUBSUB_TOPIC", "")
    GOOGLE_FORMS_PUBSUB_PUSH_TOKEN = os.environ.get("GOOGLE_FORMS_PUBSUB_PUSH_TOKEN", "")

    MOCK_MODE = _env_bool("MOCK_MODE")

    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", "true")
    SESSION_COOKIE_HTTPONLY = _env_bool("SESSION_COOKIE_HTTPONLY", "true")
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")

    WTF_CSRF_TIME_LIMIT = None
