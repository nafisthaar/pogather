CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    phone         TEXT,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('owner', 'customer')),
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS menu_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    price       INTEGER NOT NULL CHECK (price > 0),      -- whole rupiah, never floats
    description TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS po_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    quota        INTEGER NOT NULL CHECK (quota > 0),     -- total portions across all menu items
    deadline     TEXT NOT NULL,                          -- local time, 'YYYY-MM-DDTHH:MM:SS'
    status       TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
    payment_info TEXT,
    created_by   INTEGER NOT NULL REFERENCES users(id),
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    po_session_id   INTEGER NOT NULL REFERENCES po_sessions(id),
    customer_id     INTEGER NOT NULL REFERENCES users(id),
    status          TEXT NOT NULL DEFAULT 'PENDING_PAYMENT'
                    CHECK (status IN ('PENDING_PAYMENT', 'PAID', 'CANCELLED')),
    note            TEXT,
    payment_method  TEXT CHECK (payment_method IN ('BANK_TRANSFER', 'E_WALLET', 'QRIS')),
    paid_claimed_at TEXT,                                -- when the customer said "I have paid"
    verified_at     TEXT,
    verified_by     INTEGER REFERENCES users(id),
    cancelled_at    TEXT,
    cancelled_by    INTEGER REFERENCES users(id),
    created_at      TEXT NOT NULL
);

-- Name and price are copied from the menu at order time, so later menu edits do not
-- change old orders.
CREATE TABLE IF NOT EXISTS order_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL REFERENCES orders(id),
    menu_item_id INTEGER NOT NULL REFERENCES menu_items(id),
    item_name    TEXT NOT NULL,
    unit_price   INTEGER NOT NULL CHECK (unit_price > 0),
    quantity     INTEGER NOT NULL CHECK (quantity > 0)
);

CREATE INDEX IF NOT EXISTS idx_orders_po ON orders(po_session_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
