import sqlite3
import unittest

from app import rules
from app.repositories import menu_items as menu_repo
from app.repositories import orders as orders_repo
from app.repositories import po_sessions as po_repo
from app.repositories import users as users_repo
from tests.helpers import make_conn, make_customer, make_owner

T0 = "2026-03-01T10:00:00"


class RepoTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = make_conn()
        self.owner = make_owner(self.conn)
        self.sari = make_customer(self.conn)
        self.geprek = menu_repo.create(self.conn, "Geprek", 18_000, None)
        self.brownies = menu_repo.create(self.conn, "Brownies", 35_000, "Box of 6")

    def new_po(self, deadline="2026-03-05T17:00:00", quota=10):
        return po_repo.create(self.conn, "PO", quota, deadline, None, self.owner, T0)

    def new_order(self, po, lines, customer=None):
        order = orders_repo.create(self.conn, po, customer or self.sari, None, T0)
        for item, name, price, qty in lines:
            orders_repo.add_item(self.conn, order, item, name, price, qty)
        return order


class UserRepoTests(RepoTestCase):
    def test_create_then_fetch_by_id_and_by_username(self):
        row = users_repo.get(self.conn, self.sari)
        self.assertEqual((row["username"], row["role"]), ("sari", rules.ROLE_CUSTOMER))
        self.assertEqual(users_repo.get_by_username(self.conn, "sari")["id"], self.sari)
        self.assertIsNone(users_repo.get_by_username(self.conn, "nobody"))

    def test_username_is_unique_and_role_is_checked(self):
        with self.assertRaises(sqlite3.IntegrityError):
            users_repo.create(self.conn, "sari", "X", None, "hash", rules.ROLE_CUSTOMER)
        with self.assertRaises(sqlite3.IntegrityError):
            users_repo.create(self.conn, "boss", "Boss", None, "hash", "admin")


class MenuRepoTests(RepoTestCase):
    def test_update_changes_every_field(self):
        menu_repo.update(self.conn, self.geprek, "Geprek XL", 22_000, "Bigger", False)
        row = menu_repo.get(self.conn, self.geprek)
        self.assertEqual((row["name"], row["price"], row["description"], row["is_active"]),
                         ("Geprek XL", 22_000, "Bigger", 0))

    def test_active_only_hides_inactive_items_and_list_is_sorted(self):
        menu_repo.update(self.conn, self.geprek, "Geprek", 18_000, None, False)
        self.assertEqual([r["name"] for r in menu_repo.list_items(self.conn)], ["Brownies", "Geprek"])
        self.assertEqual([r["name"] for r in menu_repo.list_items(self.conn, active_only=True)], ["Brownies"])

    def test_name_is_unique_ignoring_case_and_price_must_be_positive(self):
        with self.assertRaises(sqlite3.IntegrityError):
            menu_repo.create(self.conn, "GEPREK", 10_000, None)
        with self.assertRaises(sqlite3.IntegrityError):
            menu_repo.create(self.conn, "Free", 0, None)


class PoRepoTests(RepoTestCase):
    def test_new_po_is_open_with_nothing_used(self):
        row = po_repo.get(self.conn, self.new_po())
        self.assertEqual((row["status"], row["used"], row["quota"]), (rules.PO_OPEN, 0, 10))
        self.assertIsNone(po_repo.get(self.conn, 999))

    def test_used_counts_only_orders_that_are_not_cancelled(self):
        po = self.new_po()
        self.new_order(po, [(self.geprek, "Geprek", 18_000, 3)])
        paid = self.new_order(po, [(self.brownies, "Brownies", 35_000, 2)])
        cancelled = self.new_order(po, [(self.geprek, "Geprek", 18_000, 4)])
        orders_repo.mark_paid(self.conn, paid, self.owner, T0)
        self.assertEqual(po_repo.get(self.conn, po)["used"], 9)
        orders_repo.mark_cancelled(self.conn, cancelled, self.owner, T0)
        self.assertEqual(po_repo.get(self.conn, po)["used"], 5)

    def test_close_expired_only_closes_open_pos_at_or_past_the_deadline(self):
        past, at_deadline, future = (self.new_po("2026-03-02T09:00:00"), self.new_po("2026-03-02T10:00:00"),
                                     self.new_po("2026-03-02T10:00:01"))
        self.assertEqual(po_repo.close_expired(self.conn, "2026-03-02T10:00:00"), 2)
        status = {po: po_repo.get(self.conn, po)["status"] for po in (past, at_deadline, future)}
        self.assertEqual(status, {past: "CLOSED", at_deadline: "CLOSED", future: "OPEN"})
        self.assertEqual(po_repo.close_expired(self.conn, "2026-03-02T10:00:00"), 0)

    def test_list_open_skips_closed_and_sorts_by_deadline(self):
        late, early, closed = self.new_po("2026-03-09T10:00:00"), self.new_po("2026-03-03T10:00:00"), self.new_po()
        po_repo.set_status(self.conn, closed, rules.PO_CLOSED)
        self.assertEqual([r["id"] for r in po_repo.list_open(self.conn)], [early, late])
        self.assertEqual([r["id"] for r in po_repo.list_all(self.conn)], [closed, early, late])

    def test_update_changes_name_quota_deadline_and_payment_info(self):
        po = self.new_po()
        po_repo.update(self.conn, po, "Renamed", 25, "2026-04-01T08:00:00", "BCA 123")
        row = po_repo.get(self.conn, po)
        self.assertEqual((row["name"], row["quota"], row["deadline"], row["payment_info"]),
                         ("Renamed", 25, "2026-04-01T08:00:00", "BCA 123"))


class OrderRepoTests(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.po = self.new_po()

    def test_totals_and_portions_are_summed_from_the_lines(self):
        order = self.new_order(self.po, [(self.geprek, "Geprek", 18_000, 2), (self.brownies, "Brownies", 35_000, 1)])
        row = orders_repo.get(self.conn, order)
        self.assertEqual((row["total"], row["portions"], row["status"]), (71_000, 3, rules.ORDER_PENDING))
        self.assertEqual((row["po_name"], row["customer_name"]), ("PO", "Sari"))
        self.assertEqual([i["item_name"] for i in orders_repo.items(self.conn, order)], ["Brownies", "Geprek"])
        self.assertIsNone(orders_repo.get(self.conn, 999))

    def test_lists_for_customer_and_for_session_are_newest_first(self):
        dimas = make_customer(self.conn, "dimas")
        first = self.new_order(self.po, [(self.geprek, "Geprek", 18_000, 1)])
        second = self.new_order(self.po, [(self.geprek, "Geprek", 18_000, 1)])
        other = self.new_order(self.po, [(self.geprek, "Geprek", 18_000, 1)], customer=dimas)
        self.assertEqual([o["id"] for o in orders_repo.list_for_customer(self.conn, self.sari)], [second, first])
        self.assertEqual([o["id"] for o in orders_repo.list_for_session(self.conn, self.po)], [other, second, first])

    def test_status_markers_record_who_and_when(self):
        order = self.new_order(self.po, [(self.geprek, "Geprek", 18_000, 1)])
        orders_repo.mark_payment_claimed(self.conn, order, "QRIS", "2026-03-01T11:00:00")
        orders_repo.mark_paid(self.conn, order, self.owner, "2026-03-01T12:00:00")
        row = orders_repo.get(self.conn, order)
        self.assertEqual((row["status"], row["payment_method"], row["paid_claimed_at"], row["verified_by"],
                          row["verified_at"]), ("PAID", "QRIS", "2026-03-01T11:00:00", self.owner, "2026-03-01T12:00:00"))
        orders_repo.mark_cancelled(self.conn, order, self.owner, "2026-03-01T13:00:00")
        row = orders_repo.get(self.conn, order)
        self.assertEqual((row["status"], row["cancelled_by"], row["cancelled_at"]), ("CANCELLED", self.owner, "2026-03-01T13:00:00"))

    def test_portions_per_menu_leaves_out_cancelled_orders(self):
        self.new_order(self.po, [(self.geprek, "Geprek", 18_000, 2)])
        self.new_order(self.po, [(self.geprek, "Geprek", 18_000, 1), (self.brownies, "Brownies", 35_000, 1)])
        dropped = self.new_order(self.po, [(self.brownies, "Brownies", 35_000, 9)])
        orders_repo.mark_cancelled(self.conn, dropped, self.owner, T0)
        rows = [(r["item_name"], r["portions"], r["amount"]) for r in orders_repo.portions_per_menu(self.conn, self.po)]
        self.assertEqual(rows, [("Brownies", 1, 35_000), ("Geprek", 3, 54_000)])

    def test_totals_by_status_groups_orders_portions_and_rupiah(self):
        paid = self.new_order(self.po, [(self.geprek, "Geprek", 18_000, 2)])
        self.new_order(self.po, [(self.brownies, "Brownies", 35_000, 1)])
        orders_repo.mark_paid(self.conn, paid, self.owner, T0)
        totals = {r["status"]: (r["orders"], r["portions"], r["amount"]) for r in orders_repo.totals_by_status(self.conn, self.po)}
        self.assertEqual(totals, {"PAID": (1, 2, 36_000), "PENDING_PAYMENT": (1, 1, 35_000)})

    def test_database_rejects_unknown_customers_zero_quantities_and_bad_status(self):
        with self.assertRaises(sqlite3.IntegrityError):
            orders_repo.create(self.conn, self.po, 999, None, T0)  # foreign keys are on
        order = self.new_order(self.po, [(self.geprek, "Geprek", 18_000, 1)])
        with self.assertRaises(sqlite3.IntegrityError):
            orders_repo.add_item(self.conn, order, self.geprek, "Geprek", 18_000, 0)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE orders SET status = 'SHIPPED' WHERE id = ?", (order,))


if __name__ == "__main__":
    unittest.main()
