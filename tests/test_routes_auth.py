import re

from app.repositories import users as users_repo
from tests.helpers import random_password
from tests.web_helpers import WebTestCase, flashes


class LoginTests(WebTestCase):
    def test_every_page_redirects_to_login_when_nobody_is_logged_in(self):
        for path in ["/", "/po", "/po/1", "/orders", "/orders/1", "/admin", "/admin/menu", "/admin/po/1"]:
            with self.subTest(path=path):
                response = self.app.test_client().get(path)
                self.assertEqual((response.status_code, response.headers["Location"]), (302, "/login"))

    def test_login_sends_each_role_to_its_own_start_page(self):
        for username, expected in [("owner", "/admin"), ("sari", "/po")]:
            with self.subTest(username=username):
                client = self.login(username)
                self.assertEqual(client.get("/").headers["Location"], expected)

    def test_wrong_password_gives_a_generic_error_and_no_session(self):
        client = self.app.test_client()
        response = client.post("/login", data={"username": "owner", "password": "wrong-password"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(flashes(response), [("error", "Invalid username or password.")])
        self.assertEqual(client.get("/admin").status_code, 302)

    def test_logout_ends_the_session(self):
        client = self.login("sari")
        client.post("/logout")
        self.assertEqual(client.get("/po").status_code, 302)


class RegisterTests(WebTestCase):
    def test_a_new_customer_can_register_and_log_in(self):
        client, password = self.app.test_client(), random_password()
        response = client.post("/register", data={"full_name": "Rina Putri", "username": "Rina_P", "password": password,
                                                  "phone": "081234567899"}, follow_redirects=True)
        self.assertEqual(flashes(response), [("ok", "Account created. You can log in now.")])
        user = users_repo.get_by_username(self.db, "rina_p")
        self.assertEqual((user["role"], user["full_name"]), ("customer", "Rina Putri"))
        self.assertNotIn(password, user["password_hash"])
        self.assertEqual(client.post("/login", data={"username": "rina_p", "password": password}).status_code, 302)

    def test_registration_can_never_create_an_owner(self):
        client = self.app.test_client()
        client.post("/register", data={"full_name": "Sneaky", "username": "sneaky", "password": random_password(),
                                       "role": "owner"})
        self.assertEqual(users_repo.get_by_username(self.db, "sneaky")["role"], "customer")

    def test_duplicate_username_and_weak_password_are_refused_and_the_form_keeps_its_values(self):
        client = self.app.test_client()
        for data, message in [({"full_name": "Other Sari", "username": "sari", "password": random_password()}, "already taken"),
                              ({"full_name": "Weak One", "username": "weak_one", "password": "short"}, "Password must be")]:
            with self.subTest(message=message):
                response = client.post("/register", data=data)
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, flashes(response)[0][1])
                self.assertIn(f'value="{data["full_name"]}"', response.get_data(as_text=True))
        self.assertIsNone(users_repo.get_by_username(self.db, "weak_one"))


class CsrfAndErrorPageTests(WebTestCase):
    csrf = True

    def test_a_post_without_a_valid_token_is_rejected(self):
        client = self.app.test_client()
        data = {"username": "owner", "password": self.passwords["owner"]}
        self.assertEqual(client.post("/login", data=data).status_code, 400)
        client.get("/login")
        self.assertEqual(client.post("/login", data={**data, "csrf_token": "wrong"}).status_code, 400)

    def test_a_post_with_the_token_from_the_form_is_accepted(self):
        client = self.app.test_client()
        html = client.get("/login").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        data = {"username": "owner", "password": self.passwords["owner"], "csrf_token": token}
        self.assertEqual(client.post("/login", data=data).status_code, 302)

    def test_unknown_url_shows_the_error_page(self):
        response = self.app.test_client().get("/no-such-page")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Error 404", response.get_data(as_text=True))
