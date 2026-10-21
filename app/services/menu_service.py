import sqlite3

from .. import validation
from ..db import write_transaction
from ..errors import BusinessRuleError, NotFoundError
from ..repositories import menu_items as menu_repo


def _duplicate(name):
    return BusinessRuleError(f"A menu item named '{name}' already exists.")


def add_item(conn, name_raw, price_raw, description_raw):
    name = validation.clean_item_name(name_raw)
    price = validation.parse_price(price_raw)
    description = validation.clean_description(description_raw)
    with write_transaction(conn):
        try:
            return menu_repo.create(conn, name, price, description)
        except sqlite3.IntegrityError:
            raise _duplicate(name) from None


def get_item(conn, item_id):
    item = menu_repo.get(conn, item_id)
    if item is None:
        raise NotFoundError("Menu item not found.")
    return item


def update_item(conn, item_id, name_raw, price_raw, description_raw, is_active):
    name = validation.clean_item_name(name_raw)
    price = validation.parse_price(price_raw)
    description = validation.clean_description(description_raw)
    with write_transaction(conn):
        get_item(conn, item_id)
        try:
            menu_repo.update(conn, item_id, name, price, description, is_active)
        except sqlite3.IntegrityError:
            raise _duplicate(name) from None


def list_items(conn, active_only=False):
    return menu_repo.list_items(conn, active_only)
