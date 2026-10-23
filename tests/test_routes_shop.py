from app import rules
from app.repositories import orders as orders_repo
from app.services import menu_service, order_service, po_service
from tests.web_helpers import WebTestCase, flashes, page_text


class BrowsingTests(WebTestCase):
    def test_the_list_shows_open_pos_with_their_quota_and_hides_closed_ones(self):
        closed = self.new_po("Closed One")
        po_service.set_status(self.db, closed, rules.PO_CLOSED)
        html = self.login("sari").get("/po").get_data(as_text=True)
        self.assertIn("PO Weekend", html)
        self.assertIn("<strong>10</strong> of 10 portions left", html)
        self.assertNotIn("Closed One", html)

    def test_the_detail_page_offers_active_menu_items_only(self):
        menu_service.update_item(self.db, self.brownies, "Brownies", "35000", "", False)
        html = self.login("sari").get(f"/po/{self.po}").get_data(as_text=True)
        self.assertIn("Geprek", html)
        self.assertNotIn("Brownies", html)
        self.assertIn(f'name="qty_{self.geprek}"', html)

    def test_a_closed_po_shows_a_notice_and_no_order_form(self):
        po_service.set_status(self.db, self.po, rules.PO_CLOSED)
        html = self.login("sari").get(f"/po/{self.po}").get_data(as_text=True)
        self.assertIn("closed and does not take orders", html)
        self.assertNotIn("qty_", html)

    def test_a_sold_out_po_shows_a_notice_and_no_order_form(self):
        self.make_order(self.dimas_id, {self.geprek: "10"})
        html = self.login("sari").get(f"/po/{self.po}").get_data(as_text=True)
        self.assertIn("All portions are taken", html)
        self.assertNotIn("qty_", html)

    def test_unknown_po_is_a_404(self):
        self.assertEqual(self.login("sari").get("/po/999").status_code, 404)


class PlacingOrderTests(WebTestCase):
    def test_a_valid_order_opens_its_page_and_takes_the_portions(self):
        client = self.login("sari")
        response = client.post(f"/po/{self.po}/order", data={**self.form({self.geprek: "3", self.brownies: "1"}), "note": "Less spicy"})
        self.assertEqual(response.status_code, 302)
        page = client.get(response.headers["Location"])
        text = page_text(page)
        self.assertIn("Waiting for payment", text)
        self.assertIn("Rp 89.000", text)          # 3 x 18.000 + 35.000
        self.assertIn("Less spicy", text)
        self.assertEqual(self.po_row()["remaining"], 6)

    def test_an_order_over_the_quota_shows_the_error_and_saves_nothing(self):
        client = self.login("sari")
        response = client.post(f"/po/{self.po}/order", data=self.form({self.geprek: "11"}), follow_redirects=True)
        self.assertIn("Only 10 portion(s) left", flashes(response)[0][1])
        self.assertEqual(orders_repo.list_for_session(self.db, self.po), [])

    def test_bad_quantities_show_an_error_and_save_nothing(self):
        client = self.login("sari")
        for data in [{f"qty_{self.geprek}": "abc"}, {f"qty_{self.geprek}": ""}, {f"qty_{self.geprek}": "-1"}, {}]:
            with self.subTest(data=data):
                response = client.post(f"/po/{self.po}/order", data=data, follow_redirects=True)
                self.assertEqual(flashes(response)[0][0], "error")
        self.assertEqual(orders_repo.list_for_session(self.db, self.po), [])

    def test_fields_that_are_not_quantities_are_ignored(self):
        client = self.login("sari")
        data = {**self.form({self.geprek: "1"}), "qty_": "5", "qty_abc": "5", "qty_" + "9" * 40: "5", "other": "5"}
        self.assertEqual(client.post(f"/po/{self.po}/order", data=data).status_code, 302)
        self.assertEqual(self.po_row()["used"], 1)

    def test_an_order_after_the_deadline_is_blocked_and_the_po_is_closed(self):
        self.force_deadline_past()
        client = self.login("sari")
        response = client.post(f"/po/{self.po}/order", data=self.form({self.geprek: "1"}))
        self.assertEqual(response.status_code, 302)
        # Look at the database before any other page is opened: later page views also close
        # expired POs, which could hide a lock that was never saved.
        stored = self.db.execute("SELECT status FROM po_sessions WHERE id = ?", (self.po,)).fetchone()
        self.assertEqual(stored["status"], "CLOSED")
        self.assertEqual(orders_repo.list_for_session(self.db, self.po), [])
        self.assertIn("deadline has passed", flashes(client.get(response.headers["Location"]))[0][1])

    def test_text_typed_by_users_is_escaped_on_the_owner_page(self):
        client = self.login("sari")
        client.post(f"/po/{self.po}/order", data={**self.form({self.geprek: "1"}), "note": "<script>alert(1)</script>"})
        html = self.login("owner").get(f"/admin/po/{self.po}").get_data(as_text=True)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)", html)


class PayingTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.login("sari")
        self.order_id = self.make_order(self.sari_id, {self.geprek: "2"})
        self.url = f"/orders/{self.order_id}"

    def test_the_order_page_shows_payment_info_and_the_three_options(self):
        html = self.client.get(self.url).get_data(as_text=True)
        for expected in ["Bank 123", "Bank transfer", "E-wallet", "QRIS", "I have paid", "Rp 36.000"]:
            self.assertIn(expected, html)

    def test_confirming_payment_shows_a_waiting_notice_and_keeps_the_status(self):
        response = self.client.post(f"{self.url}/pay", data={"payment_method": "QRIS"}, follow_redirects=True)
        self.assertEqual(flashes(response)[0][0], "ok")
        self.assertIn("You said you paid by QRIS", page_text(response))
        self.assertEqual(self.order_row(self.order_id)["status"], rules.ORDER_PENDING)

    def test_confirming_twice_or_without_a_method_shows_an_error(self):
        response = self.client.post(f"{self.url}/pay", data={}, follow_redirects=True)
        self.assertIn("Choose a payment method", flashes(response)[0][1])
        self.client.post(f"{self.url}/pay", data={"payment_method": "QRIS"}, follow_redirects=True)
        response = self.client.post(f"{self.url}/pay", data={"payment_method": "E_WALLET"}, follow_redirects=True)
        self.assertIn("already confirmed", flashes(response)[0][1])

    def test_the_page_follows_the_status_after_the_owner_acts(self):
        order_service.verify_payment(self.db, self.order_id, self.owner_id)
        self.assertIn("verified your payment", page_text(self.client.get(self.url)))
        order_service.void_order(self.db, self.order_id, self.owner_id)
        self.assertIn("cancelled this order", page_text(self.client.get(self.url)))

    def test_my_orders_lists_only_my_own_orders(self):
        self.make_order(self.dimas_id, {self.geprek: "1"})
        html = self.client.get("/orders").get_data(as_text=True)
        self.assertIn(f"Order #{self.order_id}", html)
        self.assertEqual(html.count("Order #"), 1)

    def test_someone_elses_order_looks_like_it_does_not_exist(self):
        other = self.make_order(self.dimas_id, {self.geprek: "1"})
        self.assertEqual(self.client.get(f"/orders/{other}").status_code, 404)
        self.assertEqual(self.client.post(f"/orders/{other}/pay", data={"payment_method": "QRIS"}).status_code, 404)
        self.assertIsNone(self.order_row(other)["paid_claimed_at"])


class RoleTests(WebTestCase):
    def test_the_owner_gets_403_on_customer_pages(self):
        client = self.login("owner")
        for method, path in [("get", "/po"), ("get", f"/po/{self.po}"), ("post", f"/po/{self.po}/order"), ("get", "/orders")]:
            with self.subTest(path=path):
                self.assertEqual(getattr(client, method)(path).status_code, 403)
        self.assertEqual(orders_repo.list_for_session(self.db, self.po), [])
