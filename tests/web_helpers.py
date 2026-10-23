import os
import re
import secrets
import tempfile
import unittest
from datetime import datetime, timedelta

from app import create_app, rules
from app.db import connect
from app.repositories import orders as orders_repo
from werkzeug.security import generate_password_hash

from app.repositories import users as users_repo
from app.services import menu_service, order_service, po_service
from tests.helpers import random_password

# Tests only: a light hash keeps the suite fast. The app itself uses Werkzeug's default,
# and check_password_hash reads the method from the stored hash, so login works the same.
_TEST_HASH = "pbkdf2:sha256:1000"


def flashes(response):
    return re.findall(r'<p class="flash (\w+)">(.*?)</p>', response.get_data(as_text=True))


def page_text(response):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", response.get_data(as_text=True)))


class WebTestCase(unittest.TestCase):
    csrf = False

    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.app = create_app(
            {"TESTING": True, "DATABASE": self.db_path, "SECRET_KEY": secrets.token_hex(16), "CSRF_ENABLED": self.csrf}
        )
        self.db = connect(self.db_path)
        self.passwords = {name: random_password() for name in ("owner", "sari", "dimas")}
        self.owner_id = self.add_user("owner", "Dina Seller", rules.ROLE_OWNER)
        self.sari_id = self.add_user("sari", "Sari Wulandari", rules.ROLE_CUSTOMER)
        self.dimas_id = self.add_user("dimas", "Dimas Pratama", rules.ROLE_CUSTOMER)
        self.geprek = menu_service.add_item(self.db, "Geprek", "18000", "Crispy")
        self.brownies = menu_service.add_item(self.db, "Brownies", "35000", "")
        self.po = self.new_po("PO Weekend", quota=10)

    def tearDown(self):
        self.db.close()
        os.remove(self.db_path)

    def add_user(self, username, full_name, role):
        password_hash = generate_password_hash(self.passwords[username], method=_TEST_HASH)
        user_id = users_repo.create(self.db, username, full_name, None, password_hash, role)
        self.db.commit()
        return user_id

    def new_po(self, name, quota=10, days=3):
        deadline = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
        return po_service.create_session(self.db, self.owner_id, name, str(quota), deadline, "Bank 123")

    def login(self, username):
        client = self.app.test_client()
        response = client.post("/login", data={"username": username, "password": self.passwords[username]})
        self.assertEqual(response.status_code, 302)
        return client

    def make_order(self, customer_id, quantities, po=None):
        return order_service.place_order(self.db, po or self.po, customer_id, quantities, "")

    def order_row(self, order_id):
        return orders_repo.get(self.db, order_id)

    def po_row(self, po_id=None):
        return po_service.get_session(self.db, po_id or self.po)

    def force_deadline_past(self, po_id=None):
        past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        self.db.execute("UPDATE po_sessions SET deadline = ? WHERE id = ?", (past, po_id or self.po))
        self.db.commit()

    def form(self, quantities):
        return {f"qty_{item_id}": qty for item_id, qty in quantities.items()}
