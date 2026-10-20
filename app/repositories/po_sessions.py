_SELECT = """
SELECT p.*,
       COALESCE((SELECT SUM(oi.quantity)
                 FROM order_items oi JOIN orders o ON o.id = oi.order_id
                 WHERE o.po_session_id = p.id AND o.status != 'CANCELLED'), 0) AS used
FROM po_sessions p
"""


def create(conn, name, quota, deadline, payment_info, created_by, created_at):
    cursor = conn.execute(
        """INSERT INTO po_sessions (name, quota, deadline, payment_info, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, quota, deadline, payment_info, created_by, created_at),
    )
    return cursor.lastrowid


def get(conn, po_id):
    return conn.execute(_SELECT + " WHERE p.id = ?", (po_id,)).fetchone()


def list_all(conn):
    return conn.execute(_SELECT + " ORDER BY p.id DESC").fetchall()


def list_open(conn):
    return conn.execute(_SELECT + " WHERE p.status = 'OPEN' ORDER BY p.deadline, p.id").fetchall()


def update(conn, po_id, name, quota, deadline, payment_info):
    conn.execute(
        "UPDATE po_sessions SET name = ?, quota = ?, deadline = ?, payment_info = ? WHERE id = ?",
        (name, quota, deadline, payment_info, po_id),
    )


def set_status(conn, po_id, status):
    conn.execute("UPDATE po_sessions SET status = ? WHERE id = ?", (status, po_id))


def close_expired(conn, now_iso):
    cursor = conn.execute(
        "UPDATE po_sessions SET status = 'CLOSED' WHERE status = 'OPEN' AND deadline <= ?",
        (now_iso,),
    )
    return cursor.rowcount
