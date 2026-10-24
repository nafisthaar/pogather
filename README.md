# POGather

POGather is a small web app for running pre-order (PO) sales from home. The seller opens a PO with a quota and a deadline, customers order from a menu, and the app keeps the quota, the payment status and the recap per menu item up to date.

Stack: Python, Flask and SQLite. Tests use Python's built-in `unittest`.

## Problem statement

**Who has the problem.** Students and other home-based sellers who run small food businesses through pre-order (PO). A typical seller cooks or bakes in batches. They announce a PO on WhatsApp or Instagram, take orders for a few days, then produce everything after the deadline and hand it over on a fixed day. The seller usually works alone, with a limit on how many portions one batch can hold.

**How they cope today.** Orders arrive as chat messages or Google Form answers, and the seller copies them into a notebook or a spreadsheet. The quota lives in the seller's head. Payment proof is a screenshot somewhere in a chat thread. A few days later the seller counts everything by hand to know how much to buy. This works for fifteen orders. It breaks down at fifty:

- Orders go past what one batch can make, because nobody is keeping a live count. The seller then has to refuse someone who already ordered, or cook past their limit.
- Late orders slip in after the deadline because they are hard to refuse politely, and the production list changes after shopping is done.
- Payment status is a guess. The seller scrolls through chats and compares screenshots against the spreadsheet.
- A cancelled order does not free up its portions unless the seller remembers to fix the count.
- The recap per menu item, which decides what to buy, is calculated by hand and usually at night.

**Why POGather is better.** POGather puts the whole PO in one place and does the counting:

- Every PO has a quota and a deadline. An order that goes over the remaining quota is refused with a clear message, and an order after the deadline is blocked and closes the PO.
- A new order starts as *waiting for payment* and holds its portions straight away. The customer sees the bill and the payment options (bank transfer, e-wallet or QRIS) and presses "I have paid". Only the seller can mark the order as paid, after checking the money.
- When the seller voids an order, its portions go back to the quota automatically.
- The seller opens one dashboard and sees portions per menu item, revenue that is already verified, money still waiting to be checked, and every order with its status.
- Customers and the seller have separate accounts, and customers can not open the seller's pages.

It does not process payments and it does not handle delivery. The seller still checks the money, and that is intended: it keeps the app simple enough for one person to run.

## What it does

**Owner (seller)**
- Create and edit PO sessions: name, quota (total portions), deadline, payment info
- Close or reopen a PO by hand. A PO also closes by itself when its deadline passes
- Add and edit menu items (name, price, description) and hide items without deleting them
- Verify payments (`PENDING_PAYMENT` to `PAID`) and void orders (`CANCELLED`, which gives the quota back)
- Dashboard per PO: portions per menu item, revenue paid, money waiting for verification, orders by status

**Customer (buyer)**
- Register an account, then see the POs that are open
- Pick items and place an order
- See the bill, the payment options (bank transfer, e-wallet, QRIS) and confirm "I have paid"
- Follow the status of their own orders

## The business rules that matter

1. **Quota.** An order that has more portions than the PO has left is refused (`ValidationError`). Nothing is saved.
2. **Deadline lock.** An order at or after the deadline is blocked, and the PO is saved as `CLOSED`.
3. **Status and refund.** A new order is `PENDING_PAYMENT` and takes its portions at once. The owner can verify it (`PAID`) or void it (`CANCELLED`). A cancelled order is not counted, so its portions are free again.
4. **Access control.** A customer who opens an owner page gets HTTP 403.

## Requirements

- Python 3.10 or newer (developed and tested on 3.12 and 3.13)
- `pip` (comes with Python) and a web browser
- Docker is optional

Flask is the only dependency and is installed from `requirements.txt`.

## Quick start (about 5 minutes)

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app seed-demo --owner-password demo-owner-1 --customer-password demo-customer-1
flask --app app run
```

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app app seed-demo --owner-password demo-owner-1 --customer-password demo-customer-1
flask --app app run
```

If PowerShell refuses to run the activate script, run `Set-ExecutionPolicy -Scope Process RemoteSigned` once in that window and try again.

Open <http://127.0.0.1:5000> and log in with one of the test accounts below. The database (`instance/pogather.sqlite3`) and a random secret key are created on first run. Both are git-ignored.

To start over, stop the server, delete `instance/pogather.sqlite3` and run `seed-demo` again. Run `seed-demo` on an empty database only.

## Test accounts

`seed-demo` creates these accounts. The passwords are the ones you typed in the command above. They are not stored in the source code.

| Username | Password | Role |
|---|---|---|
| `owner` | `demo-owner-1` | owner |
| `sari` | `demo-customer-1` | customer |
| `dimas` | `demo-customer-1` | customer |

It also adds five menu items (one hidden) and two POs. **PO Weekend Batch 12** is open, with 40 portions of quota and three orders (one waiting for verification, one paid, one cancelled). **PO Weekend Batch 11** is already closed. Anyone can also create a new customer account on the register page.

For real use, skip the demo and create your own owner login. The password is asked with hidden input:

```bash
flask --app app create-owner --username mybakery --full-name "Your Name"
```

## Run the tests

One command, from the project folder, with the virtual environment active:

```bash
python -m unittest discover -v
```

There are 146 tests and they usually take under 20 seconds. They need no extra install, no network and no running server. Every web test gets its own temporary database, so your real data is never touched. The tests cover the repositories, every service, the routes (including the 403 checks) and the command line commands.

## Run with Docker

```bash
docker build -t pogather .
docker run --name pogather -p 5000:5000 -v pogather-data:/app/instance pogather
```

Open <http://localhost:5000>. To add the demo accounts, run this in a second terminal:

```bash
docker exec pogather flask --app app seed-demo --owner-password demo-owner-1 --customer-password demo-customer-1
```

## Project structure

```
app/
  __init__.py        app factory and error pages
  rules.py           constants: roles, statuses, payment methods, limits
  errors.py          ValidationError, BusinessRuleError, DeadlineError, ...
  validation.py      turns raw form text into clean values, or raises ValidationError
  formatting.py      rupiah and date formatting for the templates
  db.py, schema.sql  SQLite connection, schema, write_transaction()
  repositories/      SQL only: users, menu_items, po_sessions, orders
  services/          all business rules: auth, menu, po, order, recap
  routes/            Flask views: auth, shop (customer), owner, plus login/CSRF helpers
  templates/, static/
  cli.py, demo.py    create-owner and seed-demo commands
tests/               one test module per layer or service
docs/                problem statement and user stories
```

Dependencies only point downwards. `routes` call `services`, `services` call `repositories`, and `repositories` talk to SQLite. Services never import Flask, so the quota and deadline rules are tested directly on an in-memory database.

## Design notes

- **Quota is derived, not stored.** The portions used by a PO are summed from the order lines that are not cancelled. Voiding an order gives the portions back without any refund code, and the number can not drift.
- **The deadline lock saves first and raises after.** When an order arrives late, the PO is saved as `CLOSED` and the transaction is committed before the error is raised. Raising inside the transaction would roll the status back.
- **Writes use `BEGIN IMMEDIATE`.** Two customers ordering the last portions at the same moment can not both pass the quota check.
- **Orders keep a copy of the name and price** of each item, so editing the menu later does not change old orders.
- **Money is whole rupiah stored as integers.**
- **Security.** Passwords are hashed with Werkzeug. All forms carry a CSRF token. Text typed by users is escaped in every page. The secret key comes from `POGATHER_SECRET_KEY` or from a random file in `instance/`. Public registration can only create customers.

## Configuration

| Setting | How | Default |
|---|---|---|
| Session secret key | environment variable `POGATHER_SECRET_KEY` | random key saved in `instance/secret_key` |
| Database file | `DATABASE` config value in `create_app()` | `instance/pogather.sqlite3` |
| Limits (max quota, max quantity, deadline range) | edit `app/rules.py` | see the file |

## Known limitations

- Payment is checked by hand. There is no payment gateway.
- Times are the server's local time. There is no time zone handling.
- Customers can not cancel or edit an order. Only the owner can void it.
- The menu is one shared list. Every open PO offers all menu items that are marked available.
- The recap shows portions per menu item. It does not turn them into ingredient amounts.
- No rate limiting on the login form, and no notifications to customers.
- `flask run` is Flask's development server. It is fine for one seller on a local network, not for the open internet. SQLite also allows one writer at a time.

## AI Usage

AI tools were used strictly for troubleshooting and code review during development:
- **Google Gemini**: Helping with debugging, checking syntax errors, and fixing Flask error logs.
- **Claude**: Reviewing code structure, suggesting clean refactoring, and checking test edge cases.

## Credits

- [Flask](https://flask.palletsprojects.com/), Werkzeug, Jinja2 and Click (BSD-3-Clause license)
- Python standard library: `sqlite3`, `unittest`, `datetime`
