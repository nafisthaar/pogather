from datetime import datetime

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..services import menu_service, order_service, po_service, recap_service
from .common import attempt, get_db, owner_required

bp = Blueprint("owner", __name__, url_prefix="/admin")


def _po_form_page(po, status=200):
    return render_template(
        "owner/po_form.html",
        po=po,
        form=request.form if request.method == "POST" else {},
        min_deadline=datetime.now().strftime("%Y-%m-%dT%H:%M"),
    ), status


@bp.get("")
@owner_required
def dashboard():
    return render_template("owner/dashboard.html", sessions=po_service.list_all_sessions(get_db()))


@bp.route("/po/new", methods=["GET", "POST"])
@owner_required
def po_new():
    if request.method == "GET":
        return _po_form_page(None)
    po_id, error = attempt(
        lambda: po_service.create_session(
            get_db(),
            g.user["id"],
            request.form.get("name"),
            request.form.get("quota"),
            request.form.get("deadline"),
            request.form.get("payment_info"),
        )
    )
    if error:
        flash(error, "error")
        return _po_form_page(None, 400)
    flash("PO created.", "ok")
    return redirect(url_for("owner.po_detail", po_id=po_id))


@bp.route("/po/<int:po_id>/edit", methods=["GET", "POST"])
@owner_required
def po_edit(po_id):
    po = po_service.get_session(get_db(), po_id)
    if request.method == "GET":
        return _po_form_page(po)
    _, error = attempt(
        lambda: po_service.update_session(
            get_db(),
            po_id,
            request.form.get("name"),
            request.form.get("quota"),
            request.form.get("deadline"),
            request.form.get("payment_info"),
        )
    )
    if error:
        flash(error, "error")
        return _po_form_page(po, 400)
    flash("PO saved.", "ok")
    return redirect(url_for("owner.po_detail", po_id=po_id))


@bp.post("/po/<int:po_id>/status")
@owner_required
def po_status(po_id):
    _, error = attempt(lambda: po_service.set_status(get_db(), po_id, request.form.get("status")))
    flash(error or "PO status updated.", "error" if error else "ok")
    return redirect(url_for("owner.po_detail", po_id=po_id))


@bp.get("/po/<int:po_id>")
@owner_required
def po_detail(po_id):
    db = get_db()
    return render_template(
        "owner/po_detail.html",
        recap=recap_service.po_recap(db, po_id),
        orders=order_service.list_orders_for_session(db, po_id),
    )


def _change_order(action, ok_message, order_id):
    db = get_db()
    po_id = order_service.get_order_detail(db, order_id)["order"]["po_session_id"]
    _, error = attempt(lambda: action(db, order_id, g.user["id"]))
    flash(error or ok_message, "error" if error else "ok")
    return redirect(url_for("owner.po_detail", po_id=po_id))


@bp.post("/orders/<int:order_id>/verify")
@owner_required
def verify_order(order_id):
    return _change_order(order_service.verify_payment, "Payment verified. The order is paid.", order_id)


@bp.post("/orders/<int:order_id>/void")
@owner_required
def void_order(order_id):
    return _change_order(order_service.void_order, "Order cancelled. The portions are back in the quota.", order_id)


@bp.route("/menu", methods=["GET", "POST"])
@owner_required
def menu_list():
    status = 200
    if request.method == "POST":
        _, error = attempt(
            lambda: menu_service.add_item(
                get_db(), request.form.get("name"), request.form.get("price"), request.form.get("description")
            )
        )
        if error is None:
            flash("Menu item added.", "ok")
            return redirect(url_for("owner.menu_list"))
        flash(error, "error")
        status = 400
    form = request.form if request.method == "POST" else {}
    return render_template("owner/menu_list.html", items=menu_service.list_items(get_db()), form=form), status


@bp.route("/menu/<int:item_id>/edit", methods=["GET", "POST"])
@owner_required
def menu_edit(item_id):
    item = menu_service.get_item(get_db(), item_id)
    if request.method == "POST":
        _, error = attempt(
            lambda: menu_service.update_item(
                get_db(),
                item_id,
                request.form.get("name"),
                request.form.get("price"),
                request.form.get("description"),
                request.form.get("is_active") == "on",
            )
        )
        if error is None:
            flash("Menu item saved.", "ok")
            return redirect(url_for("owner.menu_list"))
        flash(error, "error")
        return render_template("owner/menu_edit.html", item=item, form=request.form), 400
    return render_template("owner/menu_edit.html", item=item, form={})
