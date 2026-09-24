import sqlite3
from datetime import datetime
from contextlib import contextmanager

import os
DB_PATH = os.environ.get("DB_PATH", "ledger.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier TEXT NOT NULL,
                invoice_number TEXT,
                invoice_date TEXT,
                total_cost REAL,
                paid INTEGER NOT NULL DEFAULT 0,
                paid_date TEXT,
                due_date TEXT,
                date_logged TEXT NOT NULL,
                notes TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS line_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                part_name TEXT NOT NULL,
                part_number TEXT,
                cost REAL,
                fits TEXT,
                notes TEXT,
                FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
            )
        """)


def _to_float(val):
    try:
        return float(str(val).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def insert_invoice(header, items):
    """header: dict with supplier, invoice_number, invoice_date, due_date, notes
       items: list of dicts with part_name, part_number, cost, fits, notes"""
    with get_db() as conn:
        total = sum(_to_float(i.get("cost")) or 0 for i in items)
        cur = conn.execute("""
            INSERT INTO invoices (supplier, invoice_number, invoice_date, total_cost, paid, paid_date, due_date, date_logged, notes)
            VALUES (?, ?, ?, ?, 0, NULL, ?, ?, ?)
        """, (
            header.get("supplier", "").strip(),
            header.get("invoice_number", "").strip(),
            header.get("invoice_date", "").strip(),
            total,
            header.get("due_date", "").strip(),
            datetime.now().isoformat(timespec="seconds"),
            header.get("notes", "").strip(),
        ))
        invoice_id = cur.lastrowid
        for item in items:
            conn.execute("""
                INSERT INTO line_items (invoice_id, part_name, part_number, cost, fits, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                invoice_id,
                item.get("part_name", "").strip(),
                item.get("part_number", "").strip(),
                _to_float(item.get("cost")),
                item.get("fits", "").strip(),
                item.get("notes", "").strip(),
            ))
        return invoice_id


def get_invoices(supplier=None, paid=None, search=None):
    query = "SELECT * FROM invoices WHERE 1=1"
    params = []
    if supplier:
        query += " AND supplier LIKE ?"
        params.append(f"%{supplier}%")
    if paid is not None:
        query += " AND paid = ?"
        params.append(1 if paid else 0)
    if search:
        query += " AND (invoice_number LIKE ? OR supplier LIKE ?)"
        params.extend([f"%{search}%"] * 2)
    query += " ORDER BY paid ASC, date_logged DESC"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        invoices = [dict(r) for r in rows]
        for inv in invoices:
            items = conn.execute("SELECT * FROM line_items WHERE invoice_id = ?", (inv["id"],)).fetchall()
            inv["items"] = [dict(i) for i in items]
        return invoices


def get_invoice(invoice_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not row:
            return None
        inv = dict(row)
        items = conn.execute("SELECT * FROM line_items WHERE invoice_id = ?", (invoice_id,)).fetchall()
        inv["items"] = [dict(i) for i in items]
        return inv


def set_paid(invoice_id, paid, paid_date=None):
    with get_db() as conn:
        conn.execute(
            "UPDATE invoices SET paid = ?, paid_date = ? WHERE id = ?",
            (1 if paid else 0, paid_date or (datetime.now().isoformat(timespec="seconds") if paid else None), invoice_id),
        )


def update_invoice(invoice_id, header):
    with get_db() as conn:
        conn.execute("""
            UPDATE invoices SET supplier=?, invoice_number=?, invoice_date=?, due_date=?, notes=?
            WHERE id=?
        """, (
            header.get("supplier", "").strip(),
            header.get("invoice_number", "").strip(),
            header.get("invoice_date", "").strip(),
            header.get("due_date", "").strip(),
            header.get("notes", "").strip(),
            invoice_id,
        ))


def update_line_item(item_id, data):
    with get_db() as conn:
        conn.execute("""
            UPDATE line_items SET part_name=?, part_number=?, cost=?, fits=?, notes=?
            WHERE id=?
        """, (
            data.get("part_name", "").strip(),
            data.get("part_number", "").strip(),
            _to_float(data.get("cost")),
            data.get("fits", "").strip(),
            data.get("notes", "").strip(),
            item_id,
        ))
        item = conn.execute("SELECT invoice_id FROM line_items WHERE id = ?", (item_id,)).fetchone()
        if item:
            _recalc_total(conn, item["invoice_id"])


def delete_line_item(item_id):
    with get_db() as conn:
        row = conn.execute("SELECT invoice_id FROM line_items WHERE id = ?", (item_id,)).fetchone()
        conn.execute("DELETE FROM line_items WHERE id = ?", (item_id,))
        if row:
            _recalc_total(conn, row["invoice_id"])


def _recalc_total(conn, invoice_id):
    total = conn.execute("SELECT COALESCE(SUM(cost), 0) FROM line_items WHERE invoice_id = ?", (invoice_id,)).fetchone()[0]
    conn.execute("UPDATE invoices SET total_cost = ? WHERE id = ?", (total, invoice_id))


def delete_invoice(invoice_id):
    with get_db() as conn:
        conn.execute("DELETE FROM line_items WHERE invoice_id = ?", (invoice_id,))
        conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))


def get_balances():
    """Total owed per supplier, unpaid only."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT supplier, COUNT(*) as invoice_count, SUM(total_cost) as owed
            FROM invoices WHERE paid = 0
            GROUP BY supplier ORDER BY owed DESC
        """).fetchall()
        return [dict(r) for r in rows]
