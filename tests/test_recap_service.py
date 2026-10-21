import unittest

from app.errors import NotFoundError
from app.services import order_service, recap_service
from tests.helpers import NOW, make_conn, make_customer, make_item, make_owner, make_po


class RecapTests(unittest.TestCase):
    def setUp(self):
        self.conn = make_conn()
        self.owner = make_owner(self.conn)
        self.sari, self.dimas = make_customer(self.conn, "sari"), make_customer(self.conn, "dimas")
        self.geprek, self.brownies = make_item(self.conn, "Geprek", "18000"), make_item(self.conn, "Brownies", "35000")
        self.po = make_po(self.conn, self.owner, quota=20)

    def order(self, quantities, customer=None):
        return order_service.place_order(self.conn, self.po, customer or self.sari, quantities, "", NOW)

    def recap(self):
        return recap_service.po_recap(self.conn, self.po, NOW)

    def test_an_empty_po_has_zeros_everywhere(self):
        recap = self.recap()
        self.assertEqual((recap["per_menu"], recap["total_portions"], recap["revenue_paid"], recap["revenue_pending"]), ([], 0, 0, 0))
        self.assertEqual({s: v["orders"] for s, v in recap["by_status"].items()}, {"PENDING_PAYMENT": 0, "PAID": 0, "CANCELLED": 0})

    def test_portions_and_amount_are_added_up_per_menu_item(self):
        self.order({self.geprek: "2", self.brownies: "1"})
        self.order({self.geprek: "3"}, customer=self.dimas)
        rows = [(r["item_name"], r["portions"], r["amount"]) for r in self.recap()["per_menu"]]
        self.assertEqual(rows, [("Brownies", 1, 35_000), ("Geprek", 5, 90_000)])
        self.assertEqual(self.recap()["total_portions"], 6)

    def test_revenue_separates_verified_money_from_money_still_to_verify(self):
        paid = self.order({self.geprek: "2"})
        self.order({self.brownies: "1"}, customer=self.dimas)
        order_service.verify_payment(self.conn, paid, self.owner, NOW)
        recap = self.recap()
        self.assertEqual((recap["revenue_paid"], recap["revenue_pending"]), (36_000, 35_000))

    def test_cancelled_orders_are_left_out_of_portions_and_revenue_but_still_counted_as_orders(self):
        keep = self.order({self.geprek: "2"})
        dropped = self.order({self.geprek: "5"}, customer=self.dimas)
        order_service.verify_payment(self.conn, keep, self.owner, NOW)
        order_service.verify_payment(self.conn, dropped, self.owner, NOW)
        order_service.void_order(self.conn, dropped, self.owner, NOW)
        recap = self.recap()
        self.assertEqual((recap["total_portions"], recap["revenue_paid"]), (2, 36_000))
        self.assertEqual((recap["by_status"]["PAID"]["orders"], recap["by_status"]["CANCELLED"]["orders"]), (1, 1))
        self.assertEqual(recap["per_menu"][0]["portions"], 2)

    def test_the_recap_shows_the_quota_numbers_of_the_session(self):
        self.order({self.geprek: "5"})
        session = self.recap()["session"]
        self.assertEqual((session["quota"], session["used"], session["remaining"]), (20, 5, 15))

    def test_unknown_po_is_not_found(self):
        with self.assertRaises(NotFoundError):
            recap_service.po_recap(self.conn, 999, NOW)


if __name__ == "__main__":
    unittest.main()
