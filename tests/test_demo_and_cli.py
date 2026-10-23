import os
import tempfile
import unittest

from app import create_app, demo, rules
from app.errors import BusinessRuleError
from app.repositories import users as users_repo
from app.services import menu_service, po_service, recap_service
from tests.helpers import NOW, make_conn, random_password


class DemoDataTests(unittest.TestCase):
    def setUp(self):
        self.conn = make_conn()
        demo.seed(self.conn, random_password(), random_password(), now=NOW)

    def test_the_demo_has_two_pos_one_open_and_one_closed(self):
        sessions = {po["name"]: po for po in po_service.list_all_sessions(self.conn, NOW)}
        self.assertEqual(sessions["PO Weekend Batch 12"]["status"], rules.PO_OPEN)
        self.assertEqual(sessions["PO Weekend Batch 11"]["status"], rules.PO_CLOSED)

    def test_the_open_po_has_a_cancelled_order_whose_portions_are_free_again(self):
        open_po = next(po for po in po_service.list_all_sessions(self.conn, NOW) if po["status"] == rules.PO_OPEN)
        self.assertEqual((open_po["quota"], open_po["used"], open_po["remaining"]), (40, 6, 34))
        recap = recap_service.po_recap(self.conn, open_po["id"], NOW)
        self.assertEqual((recap["revenue_paid"], recap["revenue_pending"]), (75_000, 71_000))
        self.assertEqual({s: v["orders"] for s, v in recap["by_status"].items()},
                         {"PENDING_PAYMENT": 1, "PAID": 1, "CANCELLED": 1})

    def test_the_menu_has_one_hidden_item_and_the_accounts_have_the_right_roles(self):
        self.assertEqual((len(menu_service.list_items(self.conn)), len(menu_service.list_items(self.conn, active_only=True))), (5, 4))
        roles = {u: users_repo.get_by_username(self.conn, u)["role"] for u in ("owner", "sari", "dimas")}
        self.assertEqual(roles, {"owner": "owner", "sari": "customer", "dimas": "customer"})

    def test_seeding_the_same_database_twice_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            demo.seed(self.conn, random_password(), random_password(), now=NOW)


class CommandTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path, "SECRET_KEY": "x" * 32, "CSRF_ENABLED": False})
        self.runner = self.app.test_cli_runner()

    def tearDown(self):
        os.remove(self.db_path)

    def test_seed_demo_creates_accounts_that_can_log_in(self):
        owner_pw, customer_pw = random_password(), random_password()
        result = self.runner.invoke(args=["seed-demo", "--owner-password", owner_pw, "--customer-password", customer_pw])
        self.assertEqual((result.exit_code, "Demo data added" in result.output), (0, True))
        client = self.app.test_client()
        self.assertEqual(client.post("/login", data={"username": "owner", "password": owner_pw}).status_code, 302)
        self.assertEqual(client.get("/admin").status_code, 200)
        self.assertEqual(self.app.test_client().post("/login", data={"username": "sari", "password": customer_pw}).status_code, 302)

    def test_seed_demo_twice_fails_with_a_clear_message_instead_of_a_traceback(self):
        args = ["seed-demo", "--owner-password", random_password(), "--customer-password", random_password()]
        self.runner.invoke(args=args)
        result = self.runner.invoke(args=args)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("already taken", result.output)
        self.assertNotIn("Traceback", result.output)

    def test_create_owner_makes_a_working_owner_login(self):
        password = random_password()
        result = self.runner.invoke(args=["create-owner", "--username", "mybakery", "--full-name", "Rina Bakery", "--password", password])
        self.assertEqual(result.exit_code, 0)
        response = self.app.test_client().post("/login", data={"username": "mybakery", "password": password})
        self.assertEqual(response.status_code, 302)

    def test_create_owner_refuses_a_weak_password_and_a_taken_username(self):
        weak = self.runner.invoke(args=["create-owner", "--username", "mybakery", "--full-name", "Rina", "--password", "abc"])
        self.assertNotEqual(weak.exit_code, 0)
        self.assertIn("Password must be", weak.output)
        args = ["create-owner", "--username", "mybakery", "--full-name", "Rina", "--password", random_password()]
        self.runner.invoke(args=args)
        self.assertIn("already taken", self.runner.invoke(args=args).output)
