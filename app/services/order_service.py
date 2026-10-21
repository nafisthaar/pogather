from datetime import datetime

from .. import rules, validation
from ..db import write_transaction
from ..errors import (
    BusinessRuleError,
    DeadlineError,
    InvalidTransitionError,
    NotFoundError,
    ValidationError,
)
from ..repositories import menu_items as menu_repo
from ..repositories import orders as orders_repo
from ..repositories import po_sessions as po_repo


def _iso(moment):
    return moment.isoformat(timespec="seconds")


def _get_order(conn, order_id):
    order = orders_repo.get(conn, order_id)
    if order is None:
        raise NotFoundError("Order not found.")
    return order


def _order_lines(conn, quantities):
    lines = []
    for item_id, quantity in quantities.items():
        item = menu_repo.get(conn, item_id)
        if item is None or not item["is_active"]:
            raise ValidationError("One of the chosen items is not on the menu anymore.")
        lines.append((item["id"], item["name"], item["price"], quantity))
    return lines


def _insert_order(conn, po, customer_id, quantities, note, now):
    if po["status"] != rules.PO_OPEN:
        raise BusinessRuleError("This PO is closed, so it does not take orders anymore.")
    lines = _order_lines(conn, quantities)
    wanted = sum(quantities.values())
    left = po["quota"] - po["used"]
    if wanted > left:
        raise ValidationError(f"Only {left} portion(s) left in this PO, but your order has {wanted}.")
    order_id = orders_repo.create(conn, po["id"], customer_id, note, _iso(now))
    for item_id, name, price, quantity in lines:
        orders_repo.add_item(conn, order_id, item_id, name, price, quantity)
    return order_id


def place_order(conn, po_id, customer_id, quantities_raw, note_raw, now=None):
    now = now or datetime.now()
    quantities = validation.parse_quantities(quantities_raw)
    note = validation.clean_note(note_raw)
    with write_transaction(conn):
        po = po_repo.get(conn, po_id)
        if po is None:
            raise NotFoundError("PO not found.")
        if now < datetime.fromisoformat(po["deadline"]):
            return _insert_order(conn, po, customer_id, quantities, note, now)
        po_repo.set_status(conn, po_id, rules.PO_CLOSED)
    raise DeadlineError("The deadline has passed, so this PO is now closed.")


def confirm_payment(conn, order_id, customer_id, method_raw, now=None):
    now = now or datetime.now()
    method = validation.parse_payment_method(method_raw)
    with write_transaction(conn):
        order = _get_order(conn, order_id)
        if order["customer_id"] != customer_id:
            raise NotFoundError("Order not found.")
        if order["status"] != rules.ORDER_PENDING:
            raise InvalidTransitionError("Only an order that is waiting for payment can be confirmed.")
        if order["paid_claimed_at"] is not None:
            raise InvalidTransitionError(
                "You already confirmed this payment. Please wait for the seller to verify it."
            )
        orders_repo.mark_payment_claimed(conn, order_id, method, _iso(now))


def verify_payment(conn, order_id, owner_id, now=None):
    now = now or datetime.now()
    with write_transaction(conn):
        order = _get_order(conn, order_id)
        if order["status"] == rules.ORDER_PAID:
            raise InvalidTransitionError("This order is already marked as paid.")
        if order["status"] == rules.ORDER_CANCELLED:
            raise InvalidTransitionError("A cancelled order can not be marked as paid.")
        orders_repo.mark_paid(conn, order_id, owner_id, _iso(now))


def void_order(conn, order_id, owner_id, now=None):
    now = now or datetime.now()
    with write_transaction(conn):
        order = _get_order(conn, order_id)
        if order["status"] == rules.ORDER_CANCELLED:
            raise InvalidTransitionError("This order is already cancelled.")
        orders_repo.mark_cancelled(conn, order_id, owner_id, _iso(now))


def get_order_for_customer(conn, order_id, customer_id):
    order = _get_order(conn, order_id)
    if order["customer_id"] != customer_id:
        raise NotFoundError("Order not found.")
    return {"order": order, "items": orders_repo.items(conn, order_id)}


def get_order_detail(conn, order_id):
    order = _get_order(conn, order_id)
    return {"order": order, "items": orders_repo.items(conn, order_id)}


def list_orders_for_customer(conn, customer_id):
    return orders_repo.list_for_customer(conn, customer_id)


def list_orders_for_session(conn, po_id):
    return [
        {"order": order, "items": orders_repo.items(conn, order["id"])}
        for order in orders_repo.list_for_session(conn, po_id)
    ]
