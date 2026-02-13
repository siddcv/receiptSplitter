#!/usr/bin/env python3
"""
Test the vision node business persistence functionality.

This script actively exercises every persistence function with mock data,
verifies the rows landed in the database, then cleans up after itself.

Usage:
    python test_vision_persistence.py
"""

import sys
import os
import json
from datetime import datetime, timezone
from decimal import Decimal

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from psycopg import connect
from app.database import get_database_url
from app.graph.state import AuditEvent, Item, Totals
from app.persistence import (
    save_receipt_data,
    save_receipt_items,
    save_audit_events,
    save_vision_data,
    PersistenceError,
)

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------
TEST_THREAD_ID = "test-vision-persistence-001"

MOCK_TOTALS = {
    "subtotal": "37.00",
    "tax_total": "3.70",
    "tip_total": "6.00",
    "fees_total": "0.00",
    "grand_total": "46.70",
}

MOCK_ITEMS = [
    Item(name="Pizza Margherita", price=Decimal("18.50"), quantity=Decimal("1"),
         confidence={"name": 0.95, "price": 0.90, "quantity": 1.0}),
    Item(name="Caesar Salad", price=Decimal("12.00"), quantity=Decimal("1"),
         confidence={"name": 0.90, "price": 0.95, "quantity": 1.0}),
    Item(name="Garlic Bread", price=Decimal("6.50"), quantity=Decimal("1"),
         confidence={"name": 0.98, "price": 0.88, "quantity": 1.0}),
]

MOCK_AUDIT_EVENTS = [
    AuditEvent(
        node="vision",
        message="Extracted 3 items from receipt image",
        timestamp=datetime.now(timezone.utc),
        details={"item_count": 3, "has_totals": True},
    ),
    AuditEvent(
        node="vision",
        message="Business data persisted to PostgreSQL",
        timestamp=datetime.now(timezone.utc),
        details={"tables": ["receipts", "receipt_items", "audit_logs"]},
    ),
]

passed = 0
failed = 0


def _cleanup(dsn: str) -> None:
    """Remove all rows created by this test run."""
    with connect(dsn) as conn:
        with conn.cursor() as cur:
            # Children first (FK order)
            cur.execute("DELETE FROM audit_logs   WHERE receipt_id = %s", (TEST_THREAD_ID,))
            cur.execute("DELETE FROM assignments   WHERE item_id IN (SELECT id FROM receipt_items WHERE receipt_id = %s)", (TEST_THREAD_ID,))
            cur.execute("DELETE FROM receipt_items WHERE receipt_id = %s", (TEST_THREAD_ID,))
            cur.execute("DELETE FROM participants  WHERE receipt_id = %s", (TEST_THREAD_ID,))
            cur.execute("DELETE FROM receipts      WHERE id = %s", (TEST_THREAD_ID,))
            conn.commit()


def _assert(condition: bool, label: str) -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"   ✅ {label}")
    else:
        failed += 1
        print(f"   ❌ FAIL — {label}")


# ---------------------------------------------------------------------------
# Individual persistence-function tests
# ---------------------------------------------------------------------------

def test_db_connection():
    print("\n🔌 Test 1: Database connectivity")
    dsn = get_database_url()
    print(f"   📡 {dsn.split('@')[1] if '@' in dsn else dsn}")
    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            _assert(cur.fetchone()[0] == 1, "SELECT 1 returned 1")


def test_save_receipt_data():
    print("\n💾 Test 2: save_receipt_data()")
    dsn = get_database_url()
    save_receipt_data(TEST_THREAD_ID, MOCK_TOTALS)

    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT subtotal, tax_total, tip_total, fees_total, grand_total FROM receipts WHERE id = %s",
                        (TEST_THREAD_ID,))
            row = cur.fetchone()
            _assert(row is not None, "Receipt row exists")
            _assert(row[0] == Decimal("37.00"), f"subtotal = {row[0]}")
            _assert(row[1] == Decimal("3.70"),  f"tax_total = {row[1]}")
            _assert(row[2] == Decimal("6.00"),  f"tip_total = {row[2]}")
            _assert(row[3] == Decimal("0.00"),  f"fees_total = {row[3]}")
            _assert(row[4] == Decimal("46.70"), f"grand_total = {row[4]}")


def test_save_receipt_data_upsert():
    """Calling save_receipt_data twice should update, not duplicate."""
    print("\n🔄 Test 3: save_receipt_data() upsert (idempotency)")
    dsn = get_database_url()
    updated_totals = {**MOCK_TOTALS, "tip_total": "8.00", "grand_total": "48.70"}
    save_receipt_data(TEST_THREAD_ID, updated_totals)

    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM receipts WHERE id = %s", (TEST_THREAD_ID,))
            _assert(cur.fetchone()[0] == 1, "Still exactly 1 receipt row (upsert)")
            cur.execute("SELECT tip_total, grand_total FROM receipts WHERE id = %s", (TEST_THREAD_ID,))
            row = cur.fetchone()
            _assert(row[0] == Decimal("8.00"),  f"tip_total updated to {row[0]}")
            _assert(row[1] == Decimal("48.70"), f"grand_total updated to {row[1]}")

    # Reset back to original totals for downstream tests
    save_receipt_data(TEST_THREAD_ID, MOCK_TOTALS)


def test_save_receipt_items():
    print("\n🍕 Test 4: save_receipt_items()")
    dsn = get_database_url()
    item_ids = save_receipt_items(TEST_THREAD_ID, MOCK_ITEMS)

    _assert(len(item_ids) == 3, f"Returned {len(item_ids)} item UUIDs")

    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name, quantity, unit_price, line_total, confidence FROM receipt_items WHERE receipt_id = %s ORDER BY name",
                        (TEST_THREAD_ID,))
            rows = cur.fetchall()
            _assert(len(rows) == 3, f"{len(rows)} item rows in DB")

            # Rows sorted by name: Caesar Salad, Garlic Bread, Pizza Margherita
            caesar = rows[0]
            _assert(caesar[0] == "Caesar Salad", f"name = {caesar[0]}")
            _assert(caesar[2] == Decimal("12.00"), f"unit_price = {caesar[2]}")
            _assert(caesar[3] == Decimal("12.00"), f"line_total = {caesar[3]}")
            _assert(caesar[4] is not None, "confidence JSONB stored")

            pizza = rows[2]
            _assert(pizza[0] == "Pizza Margherita", f"name = {pizza[0]}")
            _assert(pizza[2] == Decimal("18.50"), f"unit_price = {pizza[2]}")


def test_save_receipt_items_idempotent():
    """Re-calling save_receipt_items should replace, not duplicate."""
    print("\n🔄 Test 5: save_receipt_items() idempotency (DELETE + re-INSERT)")
    dsn = get_database_url()
    save_receipt_items(TEST_THREAD_ID, MOCK_ITEMS)

    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM receipt_items WHERE receipt_id = %s", (TEST_THREAD_ID,))
            _assert(cur.fetchone()[0] == 3, "Still exactly 3 item rows after re-save")


def test_save_audit_events():
    print("\n📝 Test 6: save_audit_events()")
    dsn = get_database_url()
    save_audit_events(TEST_THREAD_ID, MOCK_AUDIT_EVENTS)

    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT node, message, details FROM audit_logs WHERE receipt_id = %s ORDER BY ts",
                        (TEST_THREAD_ID,))
            rows = cur.fetchall()
            _assert(len(rows) == 2, f"{len(rows)} audit rows in DB")
            _assert(rows[0][0] == "vision", f"node = {rows[0][0]}")
            _assert("3 items" in rows[0][1], f"message contains item count")
            _assert(rows[0][2] is not None, "details JSONB stored")


def test_save_vision_data_orchestrator():
    """Test the top-level save_vision_data() that calls all three sub-functions."""
    print("\n🚀 Test 7: save_vision_data() (full orchestrator)")
    dsn = get_database_url()

    # Clean slate for this test
    _cleanup(dsn)

    # Build a state dict like the vision node would produce
    mock_state = {
        "thread_id": TEST_THREAD_ID,
        "image_path": "uploads/test_receipt.jpg",
        "totals": MOCK_TOTALS,
        "items": MOCK_ITEMS,
        "audit_log": MOCK_AUDIT_EVENTS,
    }

    save_vision_data(mock_state)

    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM receipts WHERE id = %s", (TEST_THREAD_ID,))
            _assert(cur.fetchone()[0] == 1, "1 receipt via orchestrator")

            cur.execute("SELECT COUNT(*) FROM receipt_items WHERE receipt_id = %s", (TEST_THREAD_ID,))
            _assert(cur.fetchone()[0] == 3, "3 items via orchestrator")

            cur.execute("SELECT COUNT(*) FROM audit_logs WHERE receipt_id = %s", (TEST_THREAD_ID,))
            _assert(cur.fetchone()[0] == 2, "2 audit rows via orchestrator")


def test_edge_no_totals():
    """save_receipt_data should gracefully skip when totals is None."""
    print("\n⚠️  Test 8: Edge case — no totals")
    try:
        save_receipt_data(TEST_THREAD_ID, None)
        _assert(True, "No error when totals=None (skipped gracefully)")
    except Exception as e:
        _assert(False, f"Raised unexpected error: {e}")


def test_edge_no_items():
    """save_receipt_items should return [] when items list is empty."""
    print("\n⚠️  Test 9: Edge case — empty items list")
    ids = save_receipt_items(TEST_THREAD_ID, [])
    _assert(ids == [], f"Returned empty list: {ids}")


def test_edge_no_thread_id():
    """save_vision_data should skip when thread_id is missing."""
    print("\n⚠️  Test 10: Edge case — missing thread_id")
    try:
        save_vision_data({"items": MOCK_ITEMS})
        _assert(True, "No error when thread_id missing (skipped gracefully)")
    except Exception as e:
        _assert(False, f"Raised unexpected error: {e}")


# ---------------------------------------------------------------------------
# Display existing data (bonus info)
# ---------------------------------------------------------------------------

def show_existing_data():
    """Show what's in the DB right now (useful after a real upload)."""
    dsn = get_database_url()
    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM receipts")
            rc = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM receipt_items")
            ic = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM audit_logs")
            ac = cur.fetchone()[0]
            print(f"\n📊 Final DB state:  receipts={rc}  items={ic}  audit_logs={ac}")

            if rc > 0:
                cur.execute("""
                    SELECT id, subtotal, tax_total, tip_total, grand_total, created_at
                    FROM receipts ORDER BY created_at DESC LIMIT 3
                """)
                for r in cur.fetchall():
                    print(f"   📋 {r[0]}  total=${r[4]}  created={r[5]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("🧪 **TESTING VISION NODE BUSINESS PERSISTENCE**")
    print("=" * 60)

    dsn = get_database_url()

    # Clean up any leftovers from a previous run
    _cleanup(dsn)

    try:
        test_db_connection()
        test_save_receipt_data()
        test_save_receipt_data_upsert()
        test_save_receipt_items()
        test_save_receipt_items_idempotent()
        test_save_audit_events()
        test_save_vision_data_orchestrator()
        test_edge_no_totals()
        test_edge_no_items()
        test_edge_no_thread_id()
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Always clean up test data
        _cleanup(dsn)

    show_existing_data()

    print(f"\n{'=' * 60}")
    print(f"🏁 Results:  ✅ {passed} passed   ❌ {failed} failed")
    if failed == 0:
        print("🎉 All persistence tests passed!")
    else:
        print("⚠️  Some tests failed — check output above.")
    print()


if __name__ == "__main__":
    main()