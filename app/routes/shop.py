from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..services import menu_service, order_service, po_service
from .common import attempt, customer_required, get_db

bp = Blueprint("shop", __name__)


def _quantities_from_form():
    quantities = {}
    for key, value in request.form.items():
        if key.startswith("qty_") and key[4:].isdigit() and len(key) <= 16:
            quantities[int(key[4:])] = value
    return quantities


@bp.get("/po")
@customer_required
def po_list():
    return render_template("shop/po_list.html", sessions=po_service.list_open_sessions(get_db()))


@bp.get("/po/<int:po_id>")
@customer_required
def po_detail(po_id):
    db = get_db()
    return render_template(
        "shop/po_detail.html",
        po=po_service.get_session(db, po_id),
        items=menu_service.list_items(db, active_only=True),
    )


@bp.post("/po/<int:po_id>/order")
@customer_required
def place_order(po_id):
    order_id, error = attempt(
        lambda: order_service.place_order(
            get_db(), po_id, g.user["id"], _quantities_from_form(), request.form.get("note")
        )
    )
    if error:
        flash(error, "error")
        return redirect(url_for("shop.po_detail", po_id=po_id))
    flash("Order placed and your portions are reserved. Please pay below.", "ok")
    return redirect(url_for("shop.order_detail", order_id=order_id))


@bp.get("/orders")
@customer_required
def my_orders():
    return render_template(
        "shop/my_orders.html", orders=order_service.list_orders_for_customer(get_db(), g.user["id"])
    )


@bp.get("/orders/<int:order_id>")
@customer_required
def order_detail(order_id):
    detail = order_service.get_order_for_customer(get_db(), order_id, g.user["id"])
    return render_template("shop/order_detail.html", **detail)


@bp.post("/orders/<int:order_id>/pay")
@customer_required
def confirm_payment(order_id):
    _, error = attempt(
        lambda: order_service.confirm_payment(
            get_db(), order_id, g.user["id"], request.form.get("payment_method")
        )
    )
    flash(error or "Thanks. The seller will check your payment.", "error" if error else "ok")
    return redirect(url_for("shop.order_detail", order_id=order_id))
