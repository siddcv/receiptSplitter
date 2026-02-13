r"""
Test interview node persistence: participants + assignments tables.

Run:  .\rSplit\Scripts\python.exe test_interview_persistence.py

Prerequisites: vision persistence test must pass first (receipts + receipt_items
must be insertable) because assignments FK-reference receipt_items and
participants FK-reference receipts.
"""
from __future__ import annotations

import sys, os
from decimal import Decimal
from datetime import datetime, timezone

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
from dotenv import load_dotenv
load_dotenv(override=False)

from psycopg import connect
from app.database import get_database_url
from app.persistence import (
    PersistenceError,
    save_receipt_data,
    save_receipt_items,
    save_audit_events,
    save_participants,
    save_assignments,
    save_interview_data,
)
from app.graph.state import AuditEvent, Item, ItemAssignment, AssignmentShare

# ---------------------------------------------------------------------------
TEST_THREAD = "test-interview-persist-001"
passed = 0
failed = 0


def ok(msg: str):
    global passed
    passed += 1
    print(f"   ✅ {msg}")


def fail(msg: str):
    global failed
    failed += 1
    print(f"   ❌ {msg}")


def check(condition: bool, msg: str):
    if condition:
        ok(msg)
    else:
        fail(msg)


def cleanup():
    """Remove all test data for TEST_THREAD."""
    dsn = get_database_url()
    with connect(dsn) as conn:
        with conn.cursor() as cur:
            # FK order: assignments → receipt_items / participants → receipts
            cur.execute(
                "DELETE FROM assignments WHERE item_id IN "
                "(SELECT id FROM receipt_items WHERE receipt_id = %s)", (TEST_THREAD,))
            cur.execute("DELETE FROM audit_logs WHERE receipt_id = %s", (TEST_THREAD,))
            cur.execute("DELETE FROM receipt_items WHERE receipt_id = %s", (TEST_THREAD,))
            cur.execute("DELETE FROM participants WHERE receipt_id = %s", (TEST_THREAD,))
            cur.execute("DELETE FROM receipts WHERE id = %s", (TEST_THREAD,))
            conn.commit()


# ===========================================================================
print("🧪 **TESTING INTERVIEW NODE PERSISTENCE**")
print("=" * 60)

# ---- Seed prerequisite data (receipt + items) from vision layer ----------
print("\n🔧 Setup: seeding receipt + items (vision prerequisite)")
cleanup()

totals = {
    "subtotal": "37.00", "tax_total": "3.70", "tip_total": "6.00",
    "fees_total": "0.00", "grand_total": "46.70",
}
save_receipt_data(TEST_THREAD, totals)

mock_items = [
    Item(name="Caesar Salad", price=Decimal("12.00"), quantity=Decimal("1"),
         confidence={"name": 0.95, "quantity": 1.0, "unit_price": 0.90}),
    Item(name="Pizza Margherita", price=Decimal("18.50"), quantity=Decimal("1"),
         confidence={"name": 0.98, "quantity": 1.0, "unit_price": 0.97}),
    Item(name="Tiramisu", price=Decimal("6.50"), quantity=Decimal("1"),
         confidence={"name": 0.92, "quantity": 1.0, "unit_price": 0.88}),
]
item_ids = save_receipt_items(TEST_THREAD, mock_items)
check(len(item_ids) == 3, f"Seeded {len(item_ids)} receipt_items")
print()

# ===========================================================================
# Test 1: save_participants
# ===========================================================================
print("👥 Test 1: save_participants()")
participants = ["Alice", "Bob"]
pmap = save_participants(TEST_THREAD, participants)
check(len(pmap) == 2, f"Returned map with {len(pmap)} entries")
check("Alice" in pmap and "Bob" in pmap, "Both names present in map")

# Verify DB
dsn = get_database_url()
with connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM participants WHERE receipt_id = %s ORDER BY name",
                    (TEST_THREAD,))
        rows = cur.fetchall()
        db_names = [r[0] for r in rows]
check(db_names == ["Alice", "Bob"], f"DB names = {db_names}")
print()

# ===========================================================================
# Test 2: save_participants idempotency
# ===========================================================================
print("🔄 Test 2: save_participants() idempotency")
pmap2 = save_participants(TEST_THREAD, ["Alice", "Bob", "Charlie"])
check(len(pmap2) == 3, f"Map now has {len(pmap2)} entries after adding Charlie")
# Alice & Bob UUIDs should be the same
check(pmap2["Alice"] == pmap["Alice"], "Alice UUID unchanged")
check(pmap2["Bob"] == pmap["Bob"], "Bob UUID unchanged")

with connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM participants WHERE receipt_id = %s",
                    (TEST_THREAD,))
        cnt = cur.fetchone()[0]
check(cnt == 3, f"Exactly 3 participant rows (got {cnt})")
print()

# ===========================================================================
# Test 3: save_assignments
# ===========================================================================
print("📋 Test 3: save_assignments()")
assignments = [
    ItemAssignment(item_index=0, shares=[
        AssignmentShare(participant="Alice", fraction=Decimal("1.00")),
    ]),
    ItemAssignment(item_index=1, shares=[
        AssignmentShare(participant="Bob", fraction=Decimal("1.00")),
    ]),
    ItemAssignment(item_index=2, shares=[
        AssignmentShare(participant="Alice", fraction=Decimal("0.50")),
        AssignmentShare(participant="Bob", fraction=Decimal("0.50")),
    ]),
]
rows_inserted = save_assignments(TEST_THREAD, assignments, pmap2)
check(rows_inserted == 4, f"Inserted {rows_inserted} assignment rows (expected 4)")

with connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ri.name, p.name, a.fraction
            FROM assignments a
            JOIN receipt_items ri ON ri.id = a.item_id
            JOIN participants  p  ON p.id  = a.participant_id
            WHERE ri.receipt_id = %s
            ORDER BY ri.name, p.name
            """,
            (TEST_THREAD,),
        )
        rows = cur.fetchall()

check(len(rows) == 4, f"4 assignment rows in DB (got {len(rows)})")
# Expect: Caesar→Alice(1.00), Pizza→Bob(1.00), Tiramisu→Alice(0.50), Tiramisu→Bob(0.50)
expected = [
    ("Caesar Salad", "Alice", Decimal("1.00000")),
    ("Pizza Margherita", "Bob", Decimal("1.00000")),
    ("Tiramisu", "Alice", Decimal("0.50000")),
    ("Tiramisu", "Bob", Decimal("0.50000")),
]
for exp, got in zip(expected, rows):
    item_ok = exp[0] == got[0] and exp[1] == got[1]
    frac_ok = abs(got[2] - exp[2]) < Decimal("0.001")
    check(item_ok and frac_ok, f"{got[0]} → {got[1]} = {got[2]}")
print()

# ===========================================================================
# Test 4: save_assignments idempotency (re-run replaces)
# ===========================================================================
print("🔄 Test 4: save_assignments() idempotency")
rows2 = save_assignments(TEST_THREAD, assignments, pmap2)
check(rows2 == 4, f"Re-insert still 4 rows (got {rows2})")

with connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM assignments WHERE item_id IN "
            "(SELECT id FROM receipt_items WHERE receipt_id = %s)",
            (TEST_THREAD,),
        )
        total = cur.fetchone()[0]
check(total == 4, f"DB still has exactly 4 rows (got {total})")
print()

# ===========================================================================
# Test 5: save_interview_data orchestrator
# ===========================================================================
print("🚀 Test 5: save_interview_data() orchestrator")
# Clean participants + assignments first to test orchestrator from scratch
with connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM assignments WHERE item_id IN "
            "(SELECT id FROM receipt_items WHERE receipt_id = %s)", (TEST_THREAD,))
        cur.execute("DELETE FROM participants WHERE receipt_id = %s", (TEST_THREAD,))
        cur.execute("DELETE FROM audit_logs WHERE receipt_id = %s", (TEST_THREAD,))
        conn.commit()

interview_state = {
    "thread_id": TEST_THREAD,
    "participants": ["Alice", "Bob"],
    "assignments": assignments,
    "audit_log": [
        AuditEvent(
            node="interview",
            message="Assignment complete via orchestrator test",
            timestamp=datetime.now(timezone.utc),
            details={"test": True},
        )
    ],
}
save_interview_data(interview_state)

with connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM participants WHERE receipt_id = %s", (TEST_THREAD,))
        p_cnt = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM assignments WHERE item_id IN "
            "(SELECT id FROM receipt_items WHERE receipt_id = %s)", (TEST_THREAD,))
        a_cnt = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM audit_logs WHERE receipt_id = %s AND node = 'interview'",
            (TEST_THREAD,))
        audit_cnt = cur.fetchone()[0]

check(p_cnt == 2, f"Orchestrator: {p_cnt} participants")
check(a_cnt == 4, f"Orchestrator: {a_cnt} assignment rows")
check(audit_cnt >= 1, f"Orchestrator: {audit_cnt} audit log(s)")
print()

# ===========================================================================
# Test 6: Edge case — empty participants
# ===========================================================================
print("⚠️  Test 6: Edge case — empty participants")
empty_map = save_participants(TEST_THREAD, [])
check(empty_map == {}, f"Returned empty map: {empty_map}")
print()

# ===========================================================================
# Test 7: Edge case — empty assignments
# ===========================================================================
print("⚠️  Test 7: Edge case — empty assignments")
cnt = save_assignments(TEST_THREAD, [], {})
check(cnt == 0, f"Returned 0 rows: {cnt}")
print()

# ===========================================================================
# Test 8: Edge case — no receipt_items in DB
# ===========================================================================
print("⚠️  Test 8: Edge case — assignments with no items in DB")
cnt = save_assignments("nonexistent-thread-xyz", assignments, pmap2)
check(cnt == 0, f"Returned 0 (no items found): {cnt}")
print()

# ===========================================================================
# Cleanup
# ===========================================================================
print("🧹 Cleanup…")
cleanup()

with connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM receipts WHERE id = %s", (TEST_THREAD,))
        r = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM participants WHERE receipt_id = %s", (TEST_THREAD,))
        p = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM receipt_items WHERE receipt_id = %s", (TEST_THREAD,))
        i = cur.fetchone()[0]

print(f"\n📊 Final DB state:  receipts={r}  participants={p}  items={i}")

print("\n" + "=" * 60)
print(f"🏁 Results:  ✅ {passed} passed   ❌ {failed} failed")
if failed == 0:
    print("🎉 All interview persistence tests passed!")
else:
    print("⚠️  Some tests failed — review output above")
    sys.exit(1)
