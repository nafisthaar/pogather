def create(conn, name, price, description):
    cursor = conn.execute(
        "INSERT INTO menu_items (name, price, description) VALUES (?, ?, ?)",
        (name, price, description),
    )
    return cursor.lastrowid


def get(conn, item_id):
    return conn.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()


def update(conn, item_id, name, price, description, is_active):
    conn.execute(
        "UPDATE menu_items SET name = ?, price = ?, description = ?, is_active = ? WHERE id = ?",
        (name, price, description, 1 if is_active else 0, item_id),
    )


def list_items(conn, active_only=False):
    where = "WHERE is_active = 1" if active_only else ""
    return conn.execute(f"SELECT * FROM menu_items {where} ORDER BY name").fetchall()
