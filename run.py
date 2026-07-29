from app import create_app

app = create_app()

if __name__ == "__main__":
    # GOOGLE_REDIRECT_URI(.env)を http://localhost:5000/... に統一しているため、
    # ここも127.0.0.1ではなくlocalhostへバインドしてCookieのドメイン不一致を防ぐ
    app.run(host="localhost", port=5000
            , debug=app.config.get("FLASK_ENV") == "development")
