from flask import Flask
import os


def create_app():
    app = Flask(__name__)

    # Configuration
    app.config["SECRET_KEY"] = "RAJNISH_SHRIKANT_SECRET_KEY_2026"
    app.config["UPLOAD_FOLDER"] = os.path.join(
        app.root_path,
        "static",
        "uploads"
    )

    # Ensure uploads directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Register Blueprints
    from .views import views
    from .auth import auth

    app.register_blueprint(views, url_prefix="/")
    app.register_blueprint(auth, url_prefix="/")

    return app