import unittest

from app.errors import BusinessRuleError, NotFoundError, ValidationError
from app.services import menu_service
from tests.helpers import make_conn


class MenuServiceTests(unittest.TestCase):
    def setUp(self):
        self.conn = make_conn()
        self.geprek = menu_service.add_item(self.conn, "  Chicken   Geprek ", "18.000", "  Crispy  ")

    def test_add_item_cleans_the_input(self):
        item = menu_service.get_item(self.conn, self.geprek)
        self.assertEqual((item["name"], item["price"], item["description"], item["is_active"]),
                         ("Chicken Geprek", 18_000, "Crispy", 1))

    def test_duplicate_name_is_refused_ignoring_case(self):
        with self.assertRaises(BusinessRuleError):
            menu_service.add_item(self.conn, "chicken geprek", "20000", "")

    def test_bad_name_or_price_is_refused(self):
        for name, price in [("", "10000"), ("<b>x</b>", "10000"), ("Ok", "abc"), ("Ok", "0")]:
            with self.subTest(name=name, price=price):
                with self.assertRaises(ValidationError):
                    menu_service.add_item(self.conn, name, price, "")

    def test_update_changes_the_item_and_can_hide_it(self):
        menu_service.update_item(self.conn, self.geprek, "Geprek XL", "22000", "Bigger", False)
        item = menu_service.get_item(self.conn, self.geprek)
        self.assertEqual((item["name"], item["price"], item["is_active"]), ("Geprek XL", 22_000, 0))
        self.assertEqual(menu_service.list_items(self.conn, active_only=True), [])
        self.assertEqual(len(menu_service.list_items(self.conn)), 1)

    def test_update_refuses_a_name_that_another_item_already_has(self):
        other = menu_service.add_item(self.conn, "Brownies", "35000", "")
        with self.assertRaises(BusinessRuleError):
            menu_service.update_item(self.conn, other, "Chicken Geprek", "35000", "", True)

    def test_unknown_item_is_not_found(self):
        with self.assertRaises(NotFoundError):
            menu_service.get_item(self.conn, 999)
        with self.assertRaises(NotFoundError):
            menu_service.update_item(self.conn, 999, "X Item", "1000", "", True)


if __name__ == "__main__":
    unittest.main()
