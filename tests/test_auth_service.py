import unittest

from app import rules
from app.errors import BusinessRuleError, ValidationError
from app.repositories import users as users_repo
from app.services import auth_service
from tests.helpers import make_conn, random_password


class AuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.conn = make_conn()
        self.password = random_password()
        self.sari = auth_service.register_customer(self.conn, "Sari_1", self.password, "Sari Wulandari", "0812 3456 7890")

    def test_register_creates_a_customer_with_a_cleaned_profile(self):
        user = users_repo.get(self.conn, self.sari)
        self.assertEqual((user["username"], user["role"], user["full_name"], user["phone"]),
                         ("sari_1", rules.ROLE_CUSTOMER, "Sari Wulandari", "081234567890"))

    def test_create_owner_makes_an_owner(self):
        owner = auth_service.create_owner(self.conn, "boss", random_password(), "Dina Seller")
        self.assertEqual(users_repo.get(self.conn, owner)["role"], rules.ROLE_OWNER)

    def test_password_is_stored_hashed_never_in_plain_text(self):
        stored = users_repo.get(self.conn, self.sari)["password_hash"]
        self.assertNotIn(self.password, stored)

    def test_login_works_and_the_username_is_case_insensitive(self):
        self.assertEqual(auth_service.authenticate(self.conn, "SARI_1", self.password)["id"], self.sari)

    def test_wrong_password_unknown_user_and_empty_input_all_fail(self):
        for username, password in [("sari_1", "wrong-password"), ("nobody", self.password), ("", ""), (None, None)]:
            with self.subTest(username=username):
                self.assertIsNone(auth_service.authenticate(self.conn, username, password))

    def test_duplicate_username_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            auth_service.register_customer(self.conn, "sari_1", random_password(), "Someone Else")

    def test_bad_profile_data_is_refused(self):
        cases = [("ab", random_password(), "Name", None), ("new_user", "short", "Name", None),
                 ("new_user", random_password(), "", None), ("new_user", random_password(), "Name", "123")]
        for username, password, full_name, phone in cases:
            with self.subTest(username=username, full_name=full_name, phone=phone):
                with self.assertRaises(ValidationError):
                    auth_service.register_customer(self.conn, username, password, full_name, phone)


if __name__ == "__main__":
    unittest.main()
