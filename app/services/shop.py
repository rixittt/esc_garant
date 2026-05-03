from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.services.notifications import safe_send


SHOP_FEE_KEY = "shop_seller_fee_percent"


def _dict_rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    columns = [d[0] for d in cursor.description or []]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _one_dict(cursor: sqlite3.Cursor) -> dict[str, Any] | None:
    columns = [d[0] for d in cursor.description or []]
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(zip(columns, row))


def _get_setting_percent(conn: sqlite3.Connection, key: str, default: float = 0.0) -> float:
    cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    if row is None:
        return default
    return float(row[0])


def list_categories(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT id, name, description, is_active, created_at, updated_at FROM categories ORDER BY id DESC"
    )
    return _dict_rows(cur)


def list_products_by_category(conn: sqlite3.Connection, category_id: int) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT id, category_id, seller_id, title, description, price_usd, is_active, created_at, updated_at
        FROM products
        WHERE category_id = ? AND is_active = 1
        ORDER BY id DESC
        """,
        (category_id,),
    )
    return _dict_rows(cur)


def get_product(conn: sqlite3.Connection, product_id: int) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        SELECT id, category_id, seller_id, title, description, price_usd, is_active, created_at, updated_at
        FROM products
        WHERE id = ?
        """,
        (product_id,),
    )
    return _one_dict(cur)


def create_order_and_deliver(conn: sqlite3.Connection, buyer_id: int, product_id: int) -> dict[str, Any]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        product_cur = conn.execute(
            "SELECT id, seller_id, title, price_usd, is_active FROM products WHERE id = ?",
            (product_id,),
        )
        product = _one_dict(product_cur)
        if not product or int(product["is_active"]) != 1:
            raise ValueError("Product not found or inactive")

        buyer_cur = conn.execute("SELECT id, balance_usd FROM users WHERE id = ?", (buyer_id,))
        buyer = _one_dict(buyer_cur)
        if not buyer:
            raise ValueError("Buyer not found")

        price = float(product["price_usd"])
        buyer_balance = float(buyer["balance_usd"])
        if buyer_balance < price:
            raise ValueError("Insufficient balance")

        item_cur = conn.execute(
            """
            SELECT id, seller_id, payload
            FROM product_items
            WHERE product_id = ? AND status = 'AVAILABLE'
            ORDER BY id ASC
            LIMIT 1
            """,
            (product_id,),
        )
        item = _one_dict(item_cur)
        if not item:
            raise ValueError("No available items")

        update_item = conn.execute(
            "UPDATE product_items SET status = 'RESERVED' WHERE id = ? AND status = 'AVAILABLE'",
            (item["id"],),
        )
        if update_item.rowcount != 1:
            raise RuntimeError("Race condition detected: item already sold")

        fee_percent = _get_setting_percent(conn, SHOP_FEE_KEY, 0.0)
        commission_amount = round(price * fee_percent / 100.0, 2)
        seller_net_amount = round(price - commission_amount, 2)

        conn.execute("UPDATE users SET balance_usd = balance_usd - ? WHERE id = ?", (price, buyer_id))
        conn.execute(
            "UPDATE users SET balance_usd = balance_usd + ? WHERE id = ?",
            (seller_net_amount, int(product["seller_id"])),
        )

        delivered_payload = item["payload"]
        if not isinstance(delivered_payload, str):
            delivered_payload = json.dumps(delivered_payload)

        order_cur = conn.execute(
            """
            INSERT INTO orders (
                buyer_id, seller_id, product_id, item_id, amount_usd,
                commission_amount, seller_net_amount, delivered_payload, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'DELIVERED')
            """,
            (
                buyer_id,
                int(product["seller_id"]),
                product_id,
                int(item["id"]),
                price,
                commission_amount,
                seller_net_amount,
                delivered_payload,
            ),
        )
        order_id = order_cur.lastrowid

        conn.execute(
            "UPDATE product_items SET status = 'SOLD', order_id = ? WHERE id = ?",
            (order_id, int(item["id"])),
        )

        conn.commit()

        safe_send(
            int(product["seller_id"]),
            f"💸 Sold: {product['title']} for ${price:.2f}. Net: ${seller_net_amount:.2f}.",
        )
        admin_cur = conn.execute("SELECT id FROM users WHERE role = 'SUPER_ADMIN' LIMIT 1")
        admin = admin_cur.fetchone()
        if admin:
            safe_send(
                int(admin[0]),
                f"📦 Order #{order_id} delivered. Product #{product_id}, buyer #{buyer_id}.",
            )

        return {
            "order_id": order_id,
            "buyer_id": buyer_id,
            "product_id": product_id,
            "item_id": int(item["id"]),
            "commission_amount": commission_amount,
            "seller_net_amount": seller_net_amount,
            "delivered_payload": delivered_payload,
            "status": "DELIVERED",
        }
    except Exception:
        conn.rollback()
        raise


def list_user_orders(conn: sqlite3.Connection, user_id: int, page: int, page_size: int) -> list[dict[str, Any]]:
    offset = max(page - 1, 0) * page_size
    cur = conn.execute(
        """
        SELECT id, buyer_id, seller_id, product_id, item_id, amount_usd,
               commission_amount, seller_net_amount, delivered_payload, status, created_at
        FROM orders
        WHERE buyer_id = ? OR seller_id = ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, user_id, page_size, offset),
    )
    return _dict_rows(cur)


def create_category(conn: sqlite3.Connection, name: str, description: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO categories (name, description, is_active) VALUES (?, ?, 1)",
        (name, description),
    )
    product_id = int(cur.lastrowid)
    conn.commit()
    admin_cur = conn.execute("SELECT id FROM users WHERE role = 'SUPER_ADMIN' LIMIT 1")
    admin = admin_cur.fetchone()
    if admin:
        safe_send(int(admin[0]), f"🆕 Product #{product_id} created by seller #{seller_id}.")
    return product_id


def update_category(conn: sqlite3.Connection, category_id: int, name: str, description: str | None, is_active: int) -> None:
    conn.execute(
        "UPDATE categories SET name = ?, description = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (name, description, is_active, category_id),
    )
    conn.commit()


def delete_category(conn: sqlite3.Connection, category_id: int) -> None:
    conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()


def create_product(
    conn: sqlite3.Connection,
    category_id: int,
    seller_id: int,
    title: str,
    description: str,
    price_usd: float,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO products (category_id, seller_id, title, description, price_usd, is_active)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (category_id, seller_id, title, description, price_usd),
    )
    product_id = int(cur.lastrowid)
    conn.commit()
    admin_cur = conn.execute("SELECT id FROM users WHERE role = 'SUPER_ADMIN' LIMIT 1")
    admin = admin_cur.fetchone()
    if admin:
        safe_send(int(admin[0]), f"🆕 Product #{product_id} created by seller #{seller_id}.")
    return product_id


def update_product(
    conn: sqlite3.Connection,
    product_id: int,
    title: str,
    description: str,
    price_usd: float,
    is_active: int,
) -> None:
    conn.execute(
        """
        UPDATE products
        SET title = ?, description = ?, price_usd = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (title, description, price_usd, is_active, product_id),
    )
    conn.commit()


def delete_product(conn: sqlite3.Connection, product_id: int) -> None:
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
