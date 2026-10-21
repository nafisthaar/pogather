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


class StatusTransitionTests(OrderTestCase):
    def setUp(self):
        super().setUp()
        self.order_id = self.order({self.geprek: "4"})

    def test_confirming_payment_records_method_and_time_but_keeps_the_status(self):
        order_service.confirm_payment(self.conn, self.order_id, self.sari, "QRIS", NOW)
        row = self.row(self.order_id)
        self.assertEqual((row["status"], row["payment_method"], row["paid_claimed_at"]),
                         (rules.ORDER_PENDING, "QRIS", "2026-03-01T10:00:00"))

    def test_confirming_twice_or_with_a_bad_method_is_refused(self):
        with self.assertRaises(ValidationError):
            order_service.confirm_payment(self.conn, self.order_id, self.sari, "CASH", NOW)
        order_service.confirm_payment(self.conn, self.order_id, self.sari, "QRIS", NOW)
        with self.assertRaises(InvalidTransitionError):
            order_service.confirm_payment(self.conn, self.order_id, self.sari, "E_WALLET", NOW)
        self.assertEqual(self.row(self.order_id)["payment_method"], "QRIS")

    def test_a_customer_can_not_confirm_someone_elses_order(self):
        with self.assertRaises(NotFoundError):
            order_service.confirm_payment(self.conn, self.order_id, self.dimas, "QRIS", NOW)
        self.assertIsNone(self.row(self.order_id)["paid_claimed_at"])

    def test_verify_moves_pending_payment_to_paid_and_records_who_and_when(self):
        order_service.verify_payment(self.conn, self.order_id, self.owner, NOW)
        row = self.row(self.order_id)
        self.assertEqual((row["status"], row["verified_by"], row["verified_at"]), (rules.ORDER_PAID, self.owner, "2026-03-01T10:00:00"))

    def test_verify_works_without_a_customer_confirmation_for_cash_on_pickup(self):
        order_service.verify_payment(self.conn, self.order_id, self.owner, NOW)
        self.assertEqual(self.row(self.order_id)["status"], rules.ORDER_PAID)

    def test_verifying_a_paid_or_cancelled_order_is_refused(self):
        order_service.verify_payment(self.conn, self.order_id, self.owner, NOW)
        with self.assertRaises(InvalidTransitionError):
            order_service.verify_payment(self.conn, self.order_id, self.owner, NOW)
        other = self.order({self.geprek: "1"})
        order_service.void_order(self.conn, other, self.owner, NOW)
        with self.assertRaises(InvalidTransitionError):
            order_service.verify_payment(self.conn, other, self.owner, NOW)
        self.assertEqual(self.row(other)["status"], rules.ORDER_CANCELLED)

    def test_a_cancelled_order_can_not_be_confirmed_by_the_customer(self):
        order_service.void_order(self.conn, self.order_id, self.owner, NOW)
        with self.assertRaises(InvalidTransitionError):
            order_service.confirm_payment(self.conn, self.order_id, self.sari, "QRIS", NOW)


class QuotaRefundTests(OrderTestCase):
    def test_voiding_a_pending_order_cancels_it_and_gives_the_quota_back(self):
        order_id = self.order({self.geprek: "4"})
        self.assertEqual(self.remaining(), 6)
        order_service.void_order(self.conn, order_id, self.owner, NOW)
        row = self.row(order_id)
        self.assertEqual((row["status"], row["cancelled_by"]), (rules.ORDER_CANCELLED, self.owner))
        self.assertEqual(self.remaining(), 10)

    def test_voiding_a_paid_order_also_gives_the_quota_back(self):
        order_id = self.order({self.geprek: "4"})
        order_service.verify_payment(self.conn, order_id, self.owner, NOW)
        order_service.void_order(self.conn, order_id, self.owner, NOW)
        self.assertEqual((self.row(order_id)["status"], self.remaining()), (rules.ORDER_CANCELLED, 10))

    def test_refunded_portions_can_be_ordered_by_someone_else(self):
        full = self.order({self.geprek: "10"})
        with self.assertRaises(ValidationError):
            self.order({self.geprek: "1"}, customer=self.dimas)
        order_service.void_order(self.conn, full, self.owner, NOW)
        self.order({self.geprek: "10"}, customer=self.dimas)
        self.assertEqual(self.remaining(), 0)

    def test_voiding_twice_or_voiding_an_unknown_order_is_refused(self):
        order_id = self.order({self.geprek: "2"})
        order_service.void_order(self.conn, order_id, self.owner, NOW)
        with self.assertRaises(InvalidTransitionError):
            order_service.void_order(self.conn, order_id, self.owner, NOW)
        self.assertEqual(self.remaining(), 10)  # the second void must not refund twice
        with self.assertRaises(NotFoundError):
            order_service.void_order(self.conn, 999, self.owner, NOW)


class OrderQueryTests(OrderTestCase):
    def test_a_customer_only_sees_their_own_orders(self):
        mine, theirs = self.order({self.geprek: "1"}), self.order({self.geprek: "1"}, customer=self.dimas)
        self.assertEqual(order_service.get_order_for_customer(self.conn, mine, self.sari)["order"]["id"], mine)
        with self.assertRaises(NotFoundError):
            order_service.get_order_for_customer(self.conn, theirs, self.sari)
        self.assertEqual([o["id"] for o in order_service.list_orders_for_customer(self.conn, self.sari)], [mine])

    def test_the_owner_sees_every_order_of_a_po_with_its_lines(self):
        self.order({self.geprek: "2", self.brownies: "1"})
        self.order({self.geprek: "1"}, customer=self.dimas)
        entries = order_service.list_orders_for_session(self.conn, self.po)
        self.assertEqual([len(e["items"]) for e in entries], [1, 2])  # newest first
        self.assertEqual(order_service.get_order_detail(self.conn, entries[0]["order"]["id"])["order"]["customer_name"], "Dimas")

    def test_unknown_order_is_not_found(self):
        with self.assertRaises(NotFoundError):
            order_service.get_order_detail(self.conn, 999)
        with self.assertRaises(NotFoundError):
            order_service.get_order_for_customer(self.conn, 999, self.sari)


if __name__ == "__main__":
    unittest.main()
