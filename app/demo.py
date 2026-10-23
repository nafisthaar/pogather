from datetime import datetime, timedelta

from . import rules
from .db import write_transaction
from .repositories import menu_items as menu_repo
from .repositories import orders as orders_repo
from .repositories import po_sessions as po_repo
from .services import auth_service


def _iso(moment):
    return moment.isoformat(timespec="seconds")


def _place(conn, po_id, customer_id, lines, created, claimed=None, verified_by=None, cancelled_by=None):
    order_id = orders_repo.create(conn, po_id, customer_id, None, _iso(created))
    for item_id, name, price, quantity in lines:
        orders_repo.add_item(conn, order_id, item_id, name, price, quantity)
    if claimed:
        orders_repo.mark_payment_claimed(conn, order_id, claimed, _iso(created + timedelta(hours=2)))
    if verified_by:
        orders_repo.mark_paid(conn, order_id, verified_by, _iso(created + timedelta(hours=3)))
    if cancelled_by:
        orders_repo.mark_cancelled(conn, order_id, cancelled_by, _iso(created + timedelta(hours=4)))
    return order_id


def seed(conn, owner_password, customer_password, now=None):
    now = now or datetime.now()
    owner_id = auth_service.create_owner(conn, "owner", owner_password, "Dina Seller")
    sari = auth_service.register_customer(conn, "sari", customer_password, "Sari Wulandari", "081234567801")
    dimas = auth_service.register_customer(conn, "dimas", customer_password, "Dimas Pratama", "081234567802")

    with write_transaction(conn):
        geprek = menu_repo.create(conn, "Chicken Geprek", 18_000, "Crispy chicken, rice and sambal")
        brownies = menu_repo.create(conn, "Baked Brownies", 35_000, "Box of 6 pieces")
        dimsum = menu_repo.create(conn, "Dimsum Mentai", 25_000, "6 pieces with mentai sauce")
        coffee = menu_repo.create(conn, "Iced Milk Coffee", 15_000, "250 ml bottle")
        tea = menu_repo.create(conn, "Jumbo Iced Tea", 8_000, "Not available this month")
        menu_repo.update(conn, tea, "Jumbo Iced Tea", 8_000, "Not available this month", False)

        payment_info = "Bank transfer: 0000 0000 00 a.n. Dina Seller. E-wallet and QRIS: 0812 0000 0000."
        open_po = po_repo.create(
            conn, "PO Weekend Batch 12", 40,
            _iso((now + timedelta(days=3)).replace(hour=17, minute=0, second=0, microsecond=0)),
            payment_info, owner_id, _iso(now - timedelta(days=1)),
        )
        old_po = po_repo.create(
            conn, "PO Weekend Batch 11", 30,
            _iso((now - timedelta(days=5)).replace(hour=17, minute=0, second=0, microsecond=0)),
            payment_info, owner_id, _iso(now - timedelta(days=12)),
        )
        po_repo.set_status(conn, old_po, rules.PO_CLOSED)

        day = timedelta(days=1)
        _place(conn, open_po, sari, [(geprek, "Chicken Geprek", 18_000, 2), (brownies, "Baked Brownies", 35_000, 1)],
               now - day, claimed="E_WALLET")
        _place(conn, open_po, dimas, [(dimsum, "Dimsum Mentai", 25_000, 3)],
               now - day, claimed="BANK_TRANSFER", verified_by=owner_id)
        _place(conn, open_po, sari, [(coffee, "Iced Milk Coffee", 15_000, 5)],
               now - day, cancelled_by=owner_id)
        _place(conn, old_po, dimas, [(geprek, "Chicken Geprek", 18_000, 4)],
               now - 10 * day, claimed="QRIS", verified_by=owner_id)
        _place(conn, old_po, sari, [(brownies, "Baked Brownies", 35_000, 2)],
               now - 10 * day, claimed="E_WALLET", verified_by=owner_id)

