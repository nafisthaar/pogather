import os

from flask import Flask, g, render_template
from werkzeug.exceptions import HTTPException

from . import rules
from .config import load_secret_key
from .db import connect, init_schema
from .errors import NotFoundError
from .formatting import format_datetime, format_rupiah
from .routes import auth
from .routes.common import check_csrf, close_db, csrf_token, load_user


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "pogather.sqlite3"),
        CSRF_ENABLED=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = load_secret_key(app.instance_path)

    conn = connect(app.config["DATABASE"])
    init_schema(conn)
    conn.close()

    app.before_request(check_csrf)
    app.before_request(load_user)
    app.teardown_appcontext(close_db)
    app.jinja_env.filters["rupiah"] = format_rupiah
    app.jinja_env.filters["dt"] = format_datetime
    app.jinja_env.globals["PAYMENT_LABELS"] = rules.PAYMENT_LABELS
    app.context_processor(lambda: {"csrf_token": csrf_token, "user": g.get("user")})
    for blueprint in (auth.bp,):
        app.register_blueprint(blueprint)
    _register_error_pages(app)
    return app


def _register_error_pages(app):
    @app.errorhandler(NotFoundError)
    def not_found(error):
        return render_template("error.html", code=404, message=str(error)), 404

    @app.errorhandler(HTTPException)
    def http_error(error):
        return render_template("error.html", code=error.code, message=error.description), error.code

    @app.errorhandler(Exception)
    def unexpected(error):
        app.logger.exception("Unexpected error: %s", error)
        return render_template("error.html", code=500, message="Something went wrong on our side."), 500