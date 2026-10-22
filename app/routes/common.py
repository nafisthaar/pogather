import functools
import hmac
import secrets

from flask import abort, current_app, g, redirect, request, session, url_for

from .. import rules
from ..db import connect
from ..errors import BusinessRuleError, ValidationError
from ..repositories import users as users_repo


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def load_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        g.user = users_repo.get(get_db(), user_id)


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(**kwargs)

    return wrapped


def role_required(role):
    def decorator(view):
        @login_required
        @functools.wraps(view)
        def wrapped(**kwargs):
            if g.user["role"] != role:
                abort(403, "You do not have access to this page.")
            return view(**kwargs)

        return wrapped

    return decorator


owner_required = role_required(rules.ROLE_OWNER)
customer_required = role_required(rules.ROLE_CUSTOMER)


def attempt(call):
    try:
        return call(), None
    except (ValidationError, BusinessRuleError) as error:
        return None, str(error)


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def check_csrf():
    if request.method != "POST" or not current_app.config["CSRF_ENABLED"]:
        return
    sent = request.form.get("csrf_token", "").encode()
    expected = session.get("csrf_token", "").encode()
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, "The form expired or is invalid. Please go back and try again.")
