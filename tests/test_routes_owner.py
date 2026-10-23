from datetime import datetime, timedelta

from app import rules
from app.repositories import menu_items as menu_repo
from app.services import menu_service, order_service, po_service
from tests.web_helpers import WebTestCase, flashes, page_text

FUTURE = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")


class AccessControlTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.order_id = self.make_order(self.sari_id, {self.geprek: "2"})

    def admin_routes(self):
        po, item, order = self.po, self.geprek, self.order_id
        return [
            ("get", "/admin"), ("get", "/admin/po/new"), ("get", f"/admin/po/{po}"), ("get", f"/admin/po/{po}/edit"),
            ("get", "/admin/menu"), ("get", f"/admin/menu/{item}/edit"),
            ("post", "/admin/po/new"), ("post", f"/admin/po/{po}/edit"), ("post", f"/admin/po/{po}/status"),
            ("post", "/admin/menu"), ("post", f"/admin/menu/{item}/edit"),
            ("post", f"/admin/orders/{order}/verify"), ("post", f"/admin/orders/{order}/void"),
        ]

    def test_a_customer_gets_403_on_every_admin_route_and_nothing_changes(self):
        client = self.login("sari")
        data = {"name": "Hacked", "price": "1000", "quota": "1", "deadline": FUTURE, "status": "CLOSED"}
        for method, path in self.admin_routes():
            with self.subTest(method=method, path=path):
                self.assertEqual(getattr(client, method)(path, data=data).status_code, 403)
        self.assertEqual(self.order_row(self.order_id)["status"], rules.ORDER_PENDING)
        self.assertEqual((self.po_row()["name"], self.po_row()["status"]), ("PO Weekend", "OPEN"))
        self.assertEqual(menu_service.get_item(self.db, self.geprek)["name"], "Geprek")
        self.assertEqual(len(po_service.list_all_sessions(self.db)), 1)

    def test_nobody_logged_in_is_sent_to_the_login_page_instead(self):
        client = self.app.test_client()
        for method, path in self.admin_routes():
            with self.subTest(method=method, path=path):
                response = getattr(client, method)(path)
                self.assertEqual((response.status_code, response.headers["Location"]), (302, "/login"))


class PoSessionPageTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.login("owner")

    def po_form(self, **overrides):
        return {"name": "PO Brownies", "quota": "20", "deadline": FUTURE, "payment_info": "GoPay 0812", **overrides}

    def test_the_dashboard_lists_every_po_with_its_status(self):
        closed = self.new_po("Old One")
        po_service.set_status(self.db, closed, rules.PO_CLOSED)
        text = page_text(self.client.get("/admin"))
        self.assertIn("PO Weekend Open", text)
        self.assertIn("Old One Closed", text)

    def test_creating_a_po_opens_its_recap_page(self):
        response = self.client.post("/admin/po/new", data=self.po_form())
        self.assertEqual(response.status_code, 302)
        new_id = int(response.headers["Location"].rsplit("/", 1)[1])
        self.assertEqual((self.po_row(new_id)["name"], self.po_row(new_id)["quota"], self.po_row(new_id)["status"]),
                         ("PO Brownies", 20, "OPEN"))
        self.assertEqual(self.po_row(new_id)["created_by"], self.owner_id)

    def test_an_invalid_po_shows_the_error_keeps_the_values_and_saves_nothing(self):
        for overrides, message in [({"quota": "0"}, "Quota must be"), ({"deadline": "2020-01-01T10:00"}, "in the future"),
                                   ({"name": ""}, "PO name is required")]:
            with self.subTest(message=message):
                response = self.client.post("/admin/po/new", data=self.po_form(**overrides))
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, flashes(response)[0][1])
                self.assertIn("GoPay 0812", response.get_data(as_text=True))
        self.assertEqual(len(po_service.list_all_sessions(self.db)), 1)

    def test_editing_a_po_saves_the_changes(self):
        response = self.client.post(f"/admin/po/{self.po}/edit", data=self.po_form(name="Renamed", quota="12"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual((self.po_row()["name"], self.po_row()["quota"]), ("Renamed", 12))
        self.assertIn('value="Renamed"', self.client.get(f"/admin/po/{self.po}/edit").get_data(as_text=True))

    def test_the_quota_can_not_be_edited_below_what_is_already_ordered(self):
        self.make_order(self.sari_id, {self.geprek: "6"})
        response = self.client.post(f"/admin/po/{self.po}/edit", data=self.po_form(quota="5"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("lower than the 6 portions", flashes(response)[0][1])
        self.assertEqual(self.po_row()["quota"], 10)

    def test_the_owner_can_close_and_reopen_a_po(self):
        self.client.post(f"/admin/po/{self.po}/status", data={"status": "CLOSED"})
        self.assertEqual(self.po_row()["status"], "CLOSED")
        self.client.post(f"/admin/po/{self.po}/status", data={"status": "OPEN"})
        self.assertEqual(self.po_row()["status"], "OPEN")

    def test_reopening_after_the_deadline_shows_an_error(self):
        self.force_deadline_past()
        self.po_row()  # reading closes the expired PO
        response = self.client.post(f"/admin/po/{self.po}/status", data={"status": "OPEN"}, follow_redirects=True)
        self.assertIn("deadline has passed", flashes(response)[0][1])
        self.assertEqual(self.po_row()["status"], "CLOSED")

    def test_unknown_po_is_a_404_on_every_po_page(self):
        for path in ["/admin/po/999", "/admin/po/999/edit"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.post("/admin/po/999/status", data={"status": "OPEN"}).status_code, 404)


class MenuPageTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.login("owner")

    def test_adding_a_menu_item_shows_it_in_the_list(self):
        response = self.client.post("/admin/menu", data={"name": "Dimsum", "price": "25.000", "description": "6 pcs"}, follow_redirects=True)
        self.assertEqual(flashes(response)[0][0], "ok")
        self.assertIn("Dimsum", page_text(response))
        self.assertIn("Rp 25.000", page_text(response))

    def test_a_duplicate_or_invalid_item_is_refused_and_the_form_keeps_its_values(self):
        for data, message in [({"name": "geprek", "price": "10000"}, "already exists"), ({"name": "Okay", "price": "abc"}, "whole number")]:
            with self.subTest(message=message):
                response = self.client.post("/admin/menu", data=data)
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, flashes(response)[0][1])
                self.assertIn(f'value="{data["name"]}"', response.get_data(as_text=True))
        self.assertEqual(len(menu_repo.list_items(self.db)), 2)

    def test_editing_an_item_changes_it_and_unticking_available_hides_it_from_customers(self):
        self.client.post(f"/admin/menu/{self.brownies}/edit", data={"name": "Fudgy Brownies", "price": "40000", "description": ""})
        item = menu_service.get_item(self.db, self.brownies)
        self.assertEqual((item["name"], item["price"], item["is_active"]), ("Fudgy Brownies", 40_000, 0))
        self.assertNotIn("Fudgy", self.login("sari").get(f"/po/{self.po}").get_data(as_text=True))

    def test_an_invalid_edit_shows_the_error_and_changes_nothing(self):
        response = self.client.post(f"/admin/menu/{self.geprek}/edit", data={"name": "Geprek", "price": "0", "is_active": "on"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(menu_service.get_item(self.db, self.geprek)["price"], 18_000)
        self.assertEqual(self.client.get("/admin/menu/999/edit").status_code, 404)


class RecapAndOrderActionTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.login("owner")
        self.sari_order = self.make_order(self.sari_id, {self.geprek: "2", self.brownies: "1"})
        self.dimas_order = self.make_order(self.dimas_id, {self.geprek: "3"})
        self.url = f"/admin/po/{self.po}"

    def test_the_recap_shows_portions_per_menu_revenue_and_quota(self):
        order_service.verify_payment(self.db, self.dimas_order, self.owner_id)
        text = page_text(self.client.get(self.url))
        self.assertIn("Geprek 5 Rp 90.000", text)
        self.assertIn("Brownies 1 Rp 35.000", text)
        self.assertIn("Revenue paid Rp 54.000", text)
        self.assertIn("Waiting for verification Rp 71.000", text)
        self.assertIn("Portions ordered 6", text)
        self.assertIn("4 of 10 portions left", text)
        self.assertIn("1 paid, 1 waiting for payment, 0 cancelled", text)

    def test_the_recap_shows_the_customer_names_lines_and_payment_claims(self):
        order_service.confirm_payment(self.db, self.sari_order, self.sari_id, "E_WALLET")
        text = page_text(self.client.get(self.url))
        self.assertIn("Sari Wulandari", text)
        self.assertIn("2 x Geprek", text)
        self.assertIn("Customer says they paid by E-wallet", text)
        self.assertIn("has not confirmed a payment yet", text)  # Dimas

    def test_verifying_marks_the_order_as_paid(self):
        response = self.client.post(f"/admin/orders/{self.sari_order}/verify", follow_redirects=True)
        self.assertEqual(flashes(response)[0][0], "ok")
        self.assertEqual(self.order_row(self.sari_order)["status"], rules.ORDER_PAID)
        self.assertEqual(self.order_row(self.sari_order)["verified_by"], self.owner_id)
        again = self.client.post(f"/admin/orders/{self.sari_order}/verify", follow_redirects=True)
        self.assertIn("already marked as paid", flashes(again)[0][1])

    def test_voiding_cancels_the_order_and_gives_the_quota_back_on_the_customer_page(self):
        customer = self.login("sari")
        self.assertIn("<strong>4</strong> of 10", customer.get("/po").get_data(as_text=True))
        response = self.client.post(f"/admin/orders/{self.dimas_order}/void", follow_redirects=True)
        self.assertIn("back in the quota", flashes(response)[0][1])
        self.assertEqual(self.order_row(self.dimas_order)["status"], rules.ORDER_CANCELLED)
        self.assertIn("<strong>7</strong> of 10", customer.get("/po").get_data(as_text=True))
        again = self.client.post(f"/admin/orders/{self.dimas_order}/void", follow_redirects=True)
        self.assertIn("already cancelled", flashes(again)[0][1])
        self.assertEqual(self.po_row()["remaining"], 7)

    def test_an_unknown_order_is_a_404(self):
        for action in ("verify", "void"):
            with self.subTest(action=action):
                self.assertEqual(self.client.post(f"/admin/orders/999/{action}").status_code, 404)
