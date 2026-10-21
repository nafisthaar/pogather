import unittest
from datetime import timedelta

from app import rules
from app.errors import BusinessRuleError, NotFoundError, ValidationError
from app.services import order_service, po_service
from tests.helpers import DEADLINE, NOW, make_conn, make_customer, make_item, make_owner, make_po


class PoServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = make_conn()
        self.owner = make_owner(self.conn)
        self.sari = make_customer(self.conn)
        self.item = make_item(self.conn)
        self.po = make_po(self.conn, self.owner, quota=10)

    def get(self, now=NOW):
        return po_service.get_session(self.conn, self.po, now)


class CreateAndEditTests(PoServiceTestCase):
    def test_create_stores_an_open_po_with_the_full_quota_left(self):
        po = self.get()
        self.assertEqual((po["name"], po["quota"], po["status"], po["used"], po["remaining"]), ("PO Test", 10, "OPEN", 0, 10))
        self.assertEqual(po["deadline_dt"], DEADLINE)

    def test_create_refuses_bad_quota_name_and_deadline(self):
        cases = [("PO", "0", "2026-03-05T17:00"), ("", "10", "2026-03-05T17:00"),
                 ("PO", "10", "2026-03-01T10:00"), ("PO", "10", "next friday")]
        for name, quota, deadline in cases:
            with self.subTest(name=name, quota=quota, deadline=deadline):
                with self.assertRaises(ValidationError):
                    po_service.create_session(self.conn, self.owner, name, quota, deadline, "", now=NOW)

    def test_update_changes_the_fields(self):
        po_service.update_session(self.conn, self.po, "New name", "25", "2026-03-09T12:00", "GoPay 0812", now=NOW)
        po = self.get()
        self.assertEqual((po["name"], po["quota"], po["deadline"], po["payment_info"]),
                         ("New name", 25, "2026-03-09T12:00:00", "GoPay 0812"))

    def test_quota_can_not_drop_below_the_portions_already_ordered(self):
        order_service.place_order(self.conn, self.po, self.sari, {self.item: "6"}, "", NOW)
        with self.assertRaises(ValidationError):
            po_service.update_session(self.conn, self.po, "PO Test", "5", "2026-03-05T17:00", "", now=NOW)
        po_service.update_session(self.conn, self.po, "PO Test", "6", "2026-03-05T17:00", "", now=NOW)
        self.assertEqual(self.get()["remaining"], 0)

    def test_a_past_po_can_be_renamed_but_not_given_another_past_deadline(self):
        later = DEADLINE + timedelta(days=2)
        po_service.update_session(self.conn, self.po, "Renamed", "10", "2026-03-05T17:00", "", now=later)
        self.assertEqual(self.get(later)["name"], "Renamed")
        with self.assertRaises(ValidationError):
            po_service.update_session(self.conn, self.po, "Renamed", "10", "2026-03-06T17:00", "", now=later)

    def test_unknown_po_is_not_found(self):
        with self.assertRaises(NotFoundError):
            po_service.get_session(self.conn, 999, NOW)
        with self.assertRaises(NotFoundError):
            po_service.update_session(self.conn, 999, "PO", "10", "2026-03-05T17:00", "", now=NOW)
        with self.assertRaises(NotFoundError):
            po_service.set_status(self.conn, 999, rules.PO_CLOSED, NOW)


class StatusAndDeadlineTests(PoServiceTestCase):
    def test_owner_can_close_and_reopen_before_the_deadline(self):
        po_service.set_status(self.conn, self.po, rules.PO_CLOSED, NOW)
        self.assertEqual(self.get()["status"], "CLOSED")
        po_service.set_status(self.conn, self.po, rules.PO_OPEN, NOW)
        self.assertEqual(self.get()["status"], "OPEN")

    def test_reopening_after_the_deadline_is_refused(self):
        po_service.set_status(self.conn, self.po, rules.PO_CLOSED, NOW)
        with self.assertRaises(BusinessRuleError):
            po_service.set_status(self.conn, self.po, rules.PO_OPEN, DEADLINE + timedelta(minutes=1))

    def test_unknown_status_is_refused(self):
        with self.assertRaises(ValidationError):
            po_service.set_status(self.conn, self.po, "PAUSED", NOW)

    def test_reading_a_po_after_its_deadline_closes_it_automatically(self):
        view = self.get(DEADLINE)  # exactly at the deadline
        self.assertEqual((view["status"], view["is_expired"], view["accepting_orders"]), ("CLOSED", True, False))

    def test_open_list_closes_expired_pos_and_leaves_them_out(self):
        other = po_service.create_session(self.conn, self.owner, "Later", "5", "2026-03-20T10:00", "", now=NOW)
        ids = [po["id"] for po in po_service.list_open_sessions(self.conn, DEADLINE + timedelta(hours=1))]
        self.assertEqual(ids, [other])
        self.assertEqual(self.get(NOW)["status"], "CLOSED")  # the close was saved, not just hidden

    def test_sync_expired_reports_how_many_it_closed(self):
        self.assertEqual(po_service.sync_expired(self.conn, NOW), 0)
        self.assertEqual(po_service.sync_expired(self.conn, DEADLINE + timedelta(days=1)), 1)

    def test_list_all_keeps_closed_pos_newest_first(self):
        newer = po_service.create_session(self.conn, self.owner, "Newer", "5", "2026-03-20T10:00", "", now=NOW)
        po_service.set_status(self.conn, self.po, rules.PO_CLOSED, NOW)
        self.assertEqual([po["id"] for po in po_service.list_all_sessions(self.conn, NOW)], [newer, self.po])

    def test_view_numbers_follow_the_orders(self):
        order_service.place_order(self.conn, self.po, self.sari, {self.item: "4"}, "", NOW)
        view = self.get()
        self.assertEqual((view["used"], view["remaining"], view["fill_percent"]), (4, 6, 40))
        order_service.place_order(self.conn, self.po, self.sari, {self.item: "6"}, "", NOW)
        view = self.get()
        self.assertEqual((view["remaining"], view["fill_percent"], view["accepting_orders"]), (0, 100, True))


if __name__ == "__main__":
    unittest.main()
