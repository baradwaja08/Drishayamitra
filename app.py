import os
from datetime import timedelta
from flask import Flask
from config import Config

def create_app():
    app = Flask(__name__)

    # ── Core config ───────────────────────────────────────────
    app.secret_key = Config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH
    app.permanent_session_lifetime = timedelta(days=7)

    # ── Ensure upload directory exists ────────────────────────
    os.makedirs(Config.UPLOAD_BASE_FOLDER, exist_ok=True)

    # ── Register blueprints ───────────────────────────────────
    from auth import auth_bp
    from routes import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=Config.DEBUG, host="0.0.0.0", port=5000)