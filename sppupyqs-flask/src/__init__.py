import os

from flask import Flask, render_template, request, send_from_directory, abort, url_for
from flask_compress import Compress
from werkzeug.exceptions import HTTPException


def create_app():
    from .config import MAINTENANCE_MODE, SECRET_KEY
    from .async_logger import api_logger
    from .db import init_db

    app = Flask(__name__, template_folder="../templates", static_folder=None)
    app.secret_key = SECRET_KEY
    Compress(app)
    init_db()
    api_logger.start()

    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))

    @app.route("/static/<path:filename>", endpoint="static")
    def static_files(filename):
        file_path = os.path.join(static_dir, filename)
        if not os.path.exists(file_path):
            abort(404)
        return send_from_directory(static_dir, filename, max_age=_static_max_age(filename))

    @app.before_request
    def maintenance():
        if MAINTENANCE_MODE:
            if request.path.startswith("/static") or request.path.startswith("/images"):
                return None
            return render_template("maintenance.html"), 503
        return None

    @app.after_request
    def add_asset_cache_headers(response):
        if request.path == "/static/search.1.json":
            response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=86400"
        elif request.path.startswith(("/static/dist/", "/static/fonts/", "/static/pdfjs/", "/static/images/")):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.path.startswith(("/static/css/", "/static/js/")):
            response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
        return response

    @app.context_processor
    def asset_helpers():
        from .assets import asset_path

        def asset_url(filename):
            return url_for("static", filename=asset_path(filename))

        return {"asset_url": asset_url}

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", error_code=404, requested_path=request.path), 404

    @app.errorhandler(500)
    def server_error(error):
        error_message = str(error) if app.debug else None
        return render_template("error.html", error_code=500, error_message=error_message), 500

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        code = getattr(error, "code", 500) or 500
        description = getattr(error, "description", "")
        return render_template(
            "error.html",
            error_code=code,
            error_message=description,
            requested_path=request.path,
        ), code

    from .routes.main import main_bp
    from .routes.question_papers import question_papers_bp
    from .routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(question_papers_bp)

    return app


def _static_max_age(filename):
    if filename == "search.1.json":
        return 300
    if filename.startswith(("dist/", "fonts/", "pdfjs/", "images/")):
        return 31536000
    if filename.startswith(("css/", "js/")):
        return 86400
    return None
