import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from .. import rules, validation
from ..db import write_transaction
from ..errors import BusinessRuleError
from ..repositories import users as users_repo


def _create_user(conn, username_raw, password_raw, full_name_raw, phone_raw, role):
    username = validation.clean_username(username_raw)
    password = validation.check_password(password_raw)
    full_name = validation.clean_full_name(full_name_raw)
    phone = validation.clean_phone(phone_raw)
    with write_transaction(conn):
        try:
            return users_repo.create(conn, username, full_name, phone, generate_password_hash(password), role)
        except sqlite3.IntegrityError:
            raise BusinessRuleError(f"Username '{username}' is already taken.") from None


def register_customer(conn, username_raw, password_raw, full_name_raw, phone_raw=None):
    """Public sign-up. It can only ever create a customer, never an owner."""
    return _create_user(conn, username_raw, password_raw, full_name_raw, phone_raw, rules.ROLE_CUSTOMER)


def create_owner(conn, username_raw, password_raw, full_name_raw):
    """Used by the command line only. There is no web page that creates owners."""
    return _create_user(conn, username_raw, password_raw, full_name_raw, None, rules.ROLE_OWNER)


def authenticate(conn, username_raw, password_raw):
    """Returns the user row, or None. The caller never learns which half was wrong."""
    user = users_repo.get_by_username(conn, (username_raw or "").strip().lower())
    if user is None or not check_password_hash(user["password_hash"], password_raw or ""):
        return None
    return user
