import secrets
from datetime import datetime

from app import db, rules
from app.repositories import users as users_repo
from app.services import menu_service, po_service

NOW = datetime(2026, 3, 1, 10, 0)
DEADLINE = datetime(2026, 3, 5, 17, 0)


def make_conn():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    return conn


def random_password():
    return secrets.token_urlsafe(12)


def make_user(conn, username, role, full_name=None):
    user_id = users_repo.create(conn, username, full_name or username.title(), None, "not-a-real-hash", role)
    conn.commit()  # a bare INSERT leaves a transaction open, and the services start their own
    return user_id


def make_owner(conn, username="owner"):
    return make_user(conn, username, rules.ROLE_OWNER)


def make_customer(conn, username="sari"):
    return make_user(conn, username, rules.ROLE_CUSTOMER)
