def create(conn, username, full_name, phone, password_hash, role):
    cursor = conn.execute(
        "INSERT INTO users (username, full_name, phone, password_hash, role) VALUES (?, ?, ?, ?, ?)",
        (username, full_name, phone, password_hash, role),
    )
    return cursor.lastrowid


def get(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_by_username(conn, username):
    return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
