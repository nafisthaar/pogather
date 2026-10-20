_TOTAL = "(SELECT COALESCE(SUM(unit_price * quantity), 0) FROM order_items WHERE order_id = o.id)"
_PORTIONS = "(SELECT COALESCE(SUM(quantity), 0) FROM order_items WHERE order_id = o.id)"

_SELECT = f"""
SELECT o.*, p.name AS po_name, p.status AS po_status, p.payment_info AS payment_info,
       u.full_name AS customer_name, u.phone AS customer_phone,
       {_TOTAL} AS total, {_PORTIONS} AS portions
FROM orders o
JOIN po_sessions p ON p.id = o.po_session_id
JOIN users u ON u.id = o.customer_id
"""


def create(conn, po_id, customer_id, note, created_at):
    cursor = conn.execute(
        "INSERT INTO orders (po_session_id, customer_id, note, created_at) VALUES (?, ?, ?, ?)",
        (po_id, customer_id, note, created_at),
    )
    return cursor.lastrowid


def add_item(conn, order_id, menu_item_id, item_name, unit_price, quantity):
    conn.execute(
        """INSERT INTO order_items (order_id, menu_item_id, item_name, unit_price, quantity)
           VALUES (?, ?, ?, ?, ?)""",
        (order_id, menu_item_id, item_name, unit_price, quantity),
    )


def get(conn, order_id):
    return conn.execute(_SELECT + " WHERE o.id = ?", (order_id,)).fetchone()


def items(conn, order_id):
    return conn.execute(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY item_name", (order_id,)
    ).fetchall()


def list_for_customer(conn, customer_id):
    return conn.execute(_SELECT + " WHERE o.customer_id = ? ORDER BY o.id DESC", (customer_id,)).fetchall()


def list_for_session(conn, po_id):
    return conn.execute(_SELECT + " WHERE o.po_session_id = ? ORDER BY o.id DESC", (po_id,)).fetchall()


def mark_payment_claimed(conn, order_id, method, claimed_at):
    conn.execute(
        "UPDATE orders SET payment_method = ?, paid_claimed_at = ? WHERE id = ?",
        (method, claimed_at, order_id),
    )


def mark_paid(conn, order_id, user_id, verified_at):
    conn.execute(
        "UPDATE orders SET status = 'PAID', verified_by = ?, verified_at = ? WHERE id = ?",
        (user_id, verified_at, order_id),
    )


def mark_cancelled(conn, order_id, user_id, cancelled_at):
    conn.execute(
        "UPDATE orders SET status = 'CANCELLED', cancelled_by = ?, cancelled_at = ? WHERE id = ?",
        (user_id, cancelled_at, order_id),
    )


def portions_per_menu(conn, po_id):
    return conn.execute(
        """SELECT mi.id AS menu_item_id, mi.name AS item_name,
                  SUM(oi.quantity) AS portions, SUM(oi.unit_price * oi.quantity) AS amount
           FROM order_items oi
           JOIN orders o ON o.id = oi.order_id
           JOIN menu_items mi ON mi.id = oi.menu_item_id
           WHERE o.po_session_id = ? AND o.status != 'CANCELLED'
           GROUP BY mi.id ORDER BY mi.name""",
        (po_id,),
    ).fetchall()


def totals_by_status(conn, po_id):
    return conn.execute(
        f"""SELECT o.status AS status, COUNT(*) AS orders,
                   SUM({_PORTIONS}) AS portions, SUM({_TOTAL}) AS amount
            FROM orders o WHERE o.po_session_id = ? GROUP BY o.status""",
        (po_id,),
    ).fetchall()
