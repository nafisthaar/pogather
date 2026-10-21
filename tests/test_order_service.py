import unittest
from datetime import timedelta

from app import rules
from app.errors import (
    BusinessRuleError,
    DeadlineError,
    InvalidTransitionError,
    NotFoundError,
    ValidationError,
)
from app.repositories import orders as orders_repo
from app.services import menu_service, order_service, po_service
from tests.helpers import DEADLINE, NOW, make_conn, make_customer, make_item, make_owner, make_po


class OrderTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = make_conn()
        self.owner = make_owner(self.conn)
        self.sari = make_customer(self.conn, "sari")
        self.dimas = make_customer(self.conn, "dimas")
        self.geprek = make_item(self.conn, "Geprek", "18000")
        self.brownies = make_item(self.conn, "Brownies", "35000")
        self.po = make_po(self.conn, self.owner, quota=10)

    def order(self, quantities, customer=None, now=NOW, po=None, note=""):
        return order_service.place_order(self.conn, po or self.po, customer or self.sari, quantities, note, now)

    def remaining(self, now=NOW):
        return po_service.get_session(self.conn, self.po, now)["remaining"]

    def row(self, order_id):
        return orders_repo.get(self.conn, order_id)

    def count_orders(self):
        return len(orders_repo.list_for_session(self.conn, self.po))


class QuotaTests(OrderTestCase):
    def test_a_new_order_is_pending_payment_and_takes_its_portions_from_the_quota(self):
        row = self.row(self.order({self.geprek: "3"}))
        self.assertEqual((row["status"], row["portions"], row["paid_claimed_at"]), (rules.ORDER_PENDING, 3, None))
        self.assertEqual(self.remaining(), 7)

    def test_the_total_is_the_sum_of_all_lines(self):
        row = self.row(self.order({self.geprek: "2", self.brownies: "1"}))
        self.assertEqual((row["total"], row["portions"]), (71_000, 3))

    def test_ordering_exactly_the_remaining_quota_is_allowed(self):
        self.order({self.geprek: "10"})
        self.assertEqual(self.remaining(), 0)

    def test_an_order_over_the_remaining_quota_is_refused_and_not_saved(self):
        self.order({self.geprek: "8"})
        with self.assertRaises(ValidationError) as ctx:
            self.order({self.geprek: "3"}, customer=self.dimas)
        self.assertIn("Only 2 portion(s) left", str(ctx.exception))
        self.assertEqual((self.count_orders(), self.remaining()), (1, 2))

    def test_the_quota_is_shared_by_all_items_and_all_customers(self):
        self.order({self.geprek: "4"}, customer=self.sari)
        self.order({self.brownies: "4"}, customer=self.dimas)
        with self.assertRaises(ValidationError):
            self.order({self.geprek: "1", self.brownies: "2"})

    def test_the_order_keeps_the_price_from_the_moment_it_was_placed(self):
        order = self.order({self.geprek: "2"})
        menu_service.update_item(self.conn, self.geprek, "Geprek", "25000", "", True)
        self.assertEqual(self.row(order)["total"], 36_000)
        self.assertEqual(orders_repo.items(self.conn, order)[0]["unit_price"], 18_000)

    def test_inactive_and_unknown_items_are_refused(self):
        menu_service.update_item(self.conn, self.brownies, "Brownies", "35000", "", False)
        for quantities in ({self.brownies: "1"}, {999: "1"}):
            with self.subTest(quantities=quantities):
                with self.assertRaises(ValidationError):
                    self.order(quantities)
        self.assertEqual(self.count_orders(), 0)

    def test_bad_quantities_and_notes_are_refused_before_anything_is_saved(self):
        for quantities, note in [({}, ""), ({self.geprek: "abc"}, ""), ({self.geprek: "0"}, ""),
                                 ({self.geprek: "51"}, ""), ({self.geprek: "1"}, "x" * 201)]:
            with self.subTest(quantities=quantities, note=len(note)):
                with self.assertRaises(ValidationError):
                    self.order(quantities, note=note)
        self.assertEqual(self.count_orders(), 0)

    def test_unknown_po_is_not_found(self):
        with self.assertRaises(NotFoundError):
            self.order({self.geprek: "1"}, po=999)


class DeadlineLockTests(OrderTestCase):
    def test_an_order_one_minute_before_the_deadline_is_accepted(self):
        self.order({self.geprek: "1"}, now=DEADLINE - timedelta(minutes=1))
        self.assertEqual(self.count_orders(), 1)

    def test_an_order_after_the_deadline_is_blocked_and_the_po_becomes_closed(self):
        with self.assertRaises(DeadlineError):
            self.order({self.geprek: "1"}, now=DEADLINE + timedelta(hours=2))
        self.assertEqual(self.count_orders(), 0)
        # the CLOSED status must be saved, not rolled back together with the error
        self.assertEqual(po_service.get_session(self.conn, self.po, NOW)["status"], rules.PO_CLOSED)

    def test_an_order_exactly_at_the_deadline_is_blocked(self):
        with self.assertRaises(DeadlineError):
            self.order({self.geprek: "1"}, now=DEADLINE)
        self.assertEqual(po_service.get_session(self.conn, self.po, NOW)["status"], rules.PO_CLOSED)

    def test_a_po_the_owner_closed_by_hand_is_refused_with_a_closed_message(self):
        po_service.set_status(self.conn, self.po, rules.PO_CLOSED, NOW)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.order({self.geprek: "1"})
        self.assertNotIsInstance(ctx.exception, DeadlineError)
        self.assertIn("closed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
