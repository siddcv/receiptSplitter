"""
Business data persistence layer for the Receipt Splitter.

This module handles persisting business domain data to PostgreSQL tables,
separate from the LangGraph checkpointer which handles workflow state.

The persistence functions extract structured business data from the workflow
state and save it to normalized database tables for historical records,
reporting, and analytics.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

from psycopg.errors import IntegrityError, OperationalError
from psycopg.types.json import Jsonb

from app.database import get_connection
from app.graph.state import AuditEvent, Item, ItemAssignment

logger = logging.getLogger(__name__)


class PersistenceError(Exception):
    """Raised when business data persistence fails."""
    pass


def save_receipt_data(thread_id: str, totals: Optional[Any], image_path: Optional[str] = None) -> None:
    """
    Save receipt summary data to the receipts table.
    
    Args:
        thread_id: Receipt identifier (used as primary key)
        totals: Totals Pydantic model or dict containing subtotal, tax_total, tip_total, etc.
        image_path: Optional path to the uploaded receipt image
    
    Raises:
        PersistenceError: If database operation fails
    """
    if not totals:
        logger.warning(f"No totals provided for receipt {thread_id}, skipping receipt save")
        return
    
    try:
        # Support both Totals Pydantic model and plain dict
        def _get(obj, key, default=0):
            if hasattr(obj, key):
                return getattr(obj, key)
            if isinstance(obj, dict):
                return obj.get(key, default)
            return default
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Extract totals with defaults
                subtotal = Decimal(str(_get(totals, 'subtotal')))
                tax_total = Decimal(str(_get(totals, 'tax_total')))
                tip_total = Decimal(str(_get(totals, 'tip_total')))
                fees_total = Decimal(str(_get(totals, 'fees_total')))
                grand_total = Decimal(str(_get(totals, 'grand_total')))
                
                # Insert or update receipt record (without image_path for now)
                cur.execute("""
                    INSERT INTO receipts (id, subtotal, tax_total, tip_total, fees_total, grand_total)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        subtotal = EXCLUDED.subtotal,
                        tax_total = EXCLUDED.tax_total,
                        tip_total = EXCLUDED.tip_total,
                        fees_total = EXCLUDED.fees_total,
                        grand_total = EXCLUDED.grand_total
                """, (
                    thread_id,
                    subtotal,
                    tax_total, 
                    tip_total,
                    fees_total,
                    grand_total
                ))
                
                conn.commit()
                logger.info(f"✅ Saved receipt data for {thread_id}: ${grand_total}")
                
    except (OperationalError, IntegrityError) as e:
        logger.error(f"❌ Database error saving receipt {thread_id}: {e}")
        raise PersistenceError(f"Failed to save receipt data: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error saving receipt {thread_id}: {e}")
        raise PersistenceError(f"Unexpected error saving receipt: {e}")


def save_receipt_items(thread_id: str, items: List[Item]) -> List[str]:
    """
    Save extracted receipt items to the receipt_items table.
    
    Args:
        thread_id: Receipt identifier 
        items: List of Item objects from vision extraction
        
    Returns:
        List of generated item UUIDs
        
    Raises:
        PersistenceError: If database operation fails
    """
    if not items:
        logger.warning(f"No items provided for receipt {thread_id}, skipping items save")
        return []
    
    try:
        item_ids = []
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                # First, clear any existing items for this receipt (in case of re-processing)
                cur.execute("DELETE FROM receipt_items WHERE receipt_id = %s", (thread_id,))
                
                # Insert new items with incrementing timestamps to preserve order
                base_ts = datetime.now(timezone.utc)
                for idx, item in enumerate(items):
                    item_id = str(uuid4())
                    item_ids.append(item_id)
                    
                    # Handle both dict and Item object formats
                    if isinstance(item, dict):
                        name = item.get('name', 'Unknown Item')
                        price = Decimal(str(item.get('price', 0)))
                        quantity = Decimal(str(item.get('quantity', 1)))
                        confidence = item.get('confidence')
                    else:
                        name = item.name
                        price = item.price
                        quantity = item.quantity
                        confidence = item.confidence
                    
                    line_total = price * quantity
                    item_ts = base_ts + timedelta(microseconds=idx)
                    
                    cur.execute("""
                        INSERT INTO receipt_items (id, receipt_id, name, quantity, unit_price, line_total, confidence, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        item_id,
                        thread_id,
                        name,
                        quantity,
                        price,
                        line_total,
                        Jsonb(confidence) if confidence else None,
                        item_ts,
                    ))
                
                conn.commit()
                logger.info(f"✅ Saved {len(items)} items for receipt {thread_id}")
                return item_ids
                
    except (OperationalError, IntegrityError) as e:
        logger.error(f"❌ Database error saving items for {thread_id}: {e}")
        raise PersistenceError(f"Failed to save receipt items: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error saving items for {thread_id}: {e}")
        raise PersistenceError(f"Unexpected error saving items: {e}")


def save_audit_events(thread_id: str, events: List[AuditEvent]) -> None:
    """
    Save audit events to the audit_logs table.
    
    Args:
        thread_id: Receipt identifier
        events: List of AuditEvent objects
        
    Raises:
        PersistenceError: If database operation fails
    """
    if not events:
        return
        
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                for event in events:
                    # Handle both dict and AuditEvent object formats
                    if isinstance(event, dict):
                        timestamp = event.get('timestamp')
                        node = event.get('node', 'unknown')
                        message = event.get('message', '')
                        details = event.get('details')
                    else:
                        timestamp = event.timestamp
                        node = event.node
                        message = event.message
                        details = event.details
                    
                    cur.execute("""
                        INSERT INTO audit_logs (receipt_id, ts, node, message, details)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        thread_id,
                        timestamp,
                        node,
                        message,
                        Jsonb(details) if details else None
                    ))
                
                conn.commit()
                logger.info(f"✅ Saved {len(events)} audit events for {thread_id}")
                
    except (OperationalError, IntegrityError) as e:
        logger.error(f"❌ Database error saving audit events for {thread_id}: {e}")
        raise PersistenceError(f"Failed to save audit events: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error saving audit events for {thread_id}: {e}")
        raise PersistenceError(f"Unexpected error saving audit events: {e}")


def save_vision_data(state: Dict[str, Any]) -> None:
    """
    Save all vision node data to business tables.
    
    This is the main function called after vision node completion.
    It orchestrates saving receipt data, items, and audit events.
    
    Args:
        state: The workflow state dict containing extracted data
        
    Raises:
        PersistenceError: If any persistence operation fails
    """
    thread_id = state.get('thread_id')
    if not thread_id:
        logger.warning("No thread_id in state, cannot save vision data")
        return
    
    logger.info(f"💾 Persisting vision data for {thread_id}")
    
    try:
        # Save receipt summary
        totals = state.get('totals')
        image_path = state.get('image_path')
        save_receipt_data(thread_id, totals, image_path)
        
        # Save extracted items
        items = state.get('items', [])
        save_receipt_items(thread_id, items)
        
        # Save audit events from this session
        audit_log = state.get('audit_log', [])
        if audit_log:
            save_audit_events(thread_id, audit_log)
            
        logger.info(f"✅ Successfully persisted all vision data for {thread_id}")
        
    except PersistenceError:
        # Re-raise persistence errors
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error persisting vision data for {thread_id}: {e}")
        raise PersistenceError(f"Failed to persist vision data: {e}")


# ---------------------------------------------------------------------------
# Interview node persistence
# ---------------------------------------------------------------------------

def save_participants(thread_id: str, participants: List[str]) -> Dict[str, str]:
    """
    Save participant names to the participants table.

    Uses ON CONFLICT to be idempotent — re-running with the same names
    simply returns the existing UUIDs.

    Args:
        thread_id: Receipt identifier (FK to receipts.id)
        participants: List of participant name strings

    Returns:
        Dict mapping participant name → participant UUID (str)

    Raises:
        PersistenceError: If database operation fails
    """
    if not participants:
        logger.warning(f"No participants for {thread_id}, skipping")
        return {}

    try:
        name_to_id: Dict[str, str] = {}

        with get_connection() as conn:
            with conn.cursor() as cur:
                for name in participants:
                    cur.execute(
                        """
                        INSERT INTO participants (receipt_id, name)
                        VALUES (%s, %s)
                        ON CONFLICT (receipt_id, name) DO UPDATE
                            SET name = EXCLUDED.name
                        RETURNING id
                        """,
                        (thread_id, name),
                    )
                    row = cur.fetchone()
                    name_to_id[name] = str(row[0])

                conn.commit()
                logger.info(
                    f"✅ Saved {len(name_to_id)} participants for {thread_id}"
                )
        return name_to_id

    except (OperationalError, IntegrityError) as e:
        logger.error(f"❌ DB error saving participants for {thread_id}: {e}")
        raise PersistenceError(f"Failed to save participants: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error saving participants for {thread_id}: {e}")
        raise PersistenceError(f"Unexpected error saving participants: {e}")


def save_assignments(
    thread_id: str,
    assignments: List[Any],
    participant_map: Dict[str, str],
) -> int:
    """
    Save item ↔ participant assignment fractions to the assignments table.

    Looks up receipt_items UUIDs by positional order (matching item_index)
    and maps participant names to their UUIDs via *participant_map*.

    Old assignment rows for the same receipt are deleted first so the
    function is idempotent.

    Args:
        thread_id: Receipt identifier
        assignments: List of ItemAssignment objects (or dicts with
                     item_index + shares)
        participant_map: name → UUID mapping returned by save_participants

    Returns:
        Number of assignment rows inserted

    Raises:
        PersistenceError: If database operation fails
    """
    if not assignments:
        logger.warning(f"No assignments for {thread_id}, skipping")
        return 0

    try:
        rows_inserted = 0

        with get_connection() as conn:
            with conn.cursor() as cur:
                # Fetch receipt_items ordered by creation so positional index
                # matches the item_index used by the interview node.
                cur.execute(
                    """
                    SELECT id FROM receipt_items
                    WHERE receipt_id = %s
                    ORDER BY created_at, id
                    """,
                    (thread_id,),
                )
                item_rows = cur.fetchall()
                item_id_list = [str(r[0]) for r in item_rows]

                if not item_id_list:
                    logger.warning(
                        f"No receipt_items found for {thread_id} — "
                        "cannot save assignments (vision data may not be persisted yet)"
                    )
                    return 0

                # Delete previous assignments for these items
                cur.execute(
                    """
                    DELETE FROM assignments
                    WHERE item_id IN (
                        SELECT id FROM receipt_items WHERE receipt_id = %s
                    )
                    """,
                    (thread_id,),
                )

                for asn in assignments:
                    # Support both ItemAssignment objects and dicts
                    if hasattr(asn, "item_index"):
                        item_index = asn.item_index
                        shares = asn.shares
                    else:
                        item_index = asn.get("item_index")
                        shares = asn.get("shares", [])

                    if item_index is None or item_index >= len(item_id_list):
                        logger.warning(
                            f"Skipping assignment with out-of-range item_index "
                            f"{item_index} (only {len(item_id_list)} items in DB)"
                        )
                        continue

                    db_item_id = item_id_list[item_index]

                    for share in shares:
                        if hasattr(share, "participant"):
                            name = share.participant
                            fraction = share.fraction
                        else:
                            name = share.get("participant", "")
                            fraction = Decimal(str(share.get("fraction", 0)))

                        participant_id = participant_map.get(name)
                        if not participant_id:
                            logger.warning(
                                f"Participant '{name}' not in map, skipping"
                            )
                            continue

                        cur.execute(
                            """
                            INSERT INTO assignments (item_id, participant_id, fraction)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (item_id, participant_id) DO UPDATE
                                SET fraction = EXCLUDED.fraction
                            """,
                            (db_item_id, participant_id, fraction),
                        )
                        rows_inserted += 1

                conn.commit()
                logger.info(
                    f"✅ Saved {rows_inserted} assignment rows for {thread_id}"
                )
        return rows_inserted

    except (OperationalError, IntegrityError) as e:
        logger.error(f"❌ DB error saving assignments for {thread_id}: {e}")
        raise PersistenceError(f"Failed to save assignments: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error saving assignments for {thread_id}: {e}")
        raise PersistenceError(f"Unexpected error saving assignments: {e}")


def save_interview_data(state: Dict[str, Any]) -> None:
    """
    Orchestrator: persist all interview-node data to business tables.

    Called after the interview node completes successfully (all items
    assigned).  Saves participants, assignments, and audit events.

    Args:
        state: Workflow state dict (or ReceiptState-like object)

    Raises:
        PersistenceError: If any persistence operation fails
    """
    # Support both dict and Pydantic state
    def _g(key, default=None):
        if isinstance(state, dict):
            return state.get(key, default)
        return getattr(state, key, default)

    thread_id = _g("thread_id")
    if not thread_id:
        logger.warning("No thread_id in state, cannot save interview data")
        return

    participants = _g("participants", [])
    assignments = _g("assignments", [])

    if not participants or not assignments:
        logger.warning(
            f"Interview data incomplete for {thread_id} "
            f"(participants={len(participants or [])}, "
            f"assignments={len(assignments or [])}), skipping"
        )
        return

    logger.info(f"💾 Persisting interview data for {thread_id}")

    try:
        # 1. Participants → participants table
        participant_map = save_participants(thread_id, participants)

        # 2. Assignments → assignments table
        save_assignments(thread_id, assignments, participant_map)

        # 3. Audit events (interview-specific ones)
        audit_log = _g("audit_log", [])
        if audit_log:
            save_audit_events(thread_id, audit_log)

        logger.info(
            f"✅ Successfully persisted all interview data for {thread_id}"
        )

    except PersistenceError:
        raise
    except Exception as e:
        logger.error(
            f"❌ Unexpected error persisting interview data for {thread_id}: {e}"
        )
        raise PersistenceError(f"Failed to persist interview data: {e}")


# ---------------------------------------------------------------------------
# Math node persistence
# ---------------------------------------------------------------------------

def save_final_costs(
    thread_id: str,
    participant_costs: List[Dict[str, Any]],
) -> int:
    """
    Save per-participant final cost rows to the final_costs table.

    Looks up participant UUIDs from the participants table by name.
    Old rows for the same receipt are deleted first (idempotent).

    Args:
        thread_id: Receipt identifier (FK to receipts.id)
        participant_costs: List of dicts with keys:
            participant, subtotal, tax_share, tip_share,
            fees_share, total_owed, item_costs

    Returns:
        Number of rows inserted

    Raises:
        PersistenceError: If database operation fails
    """
    if not participant_costs:
        logger.warning(f"No participant costs for {thread_id}, skipping")
        return 0

    try:
        rows_inserted = 0

        with get_connection() as conn:
            with conn.cursor() as cur:
                # Build a name → UUID lookup from the participants table
                cur.execute(
                    "SELECT id, name FROM participants WHERE receipt_id = %s",
                    (thread_id,),
                )
                name_to_id = {row[1]: str(row[0]) for row in cur.fetchall()}

                if not name_to_id:
                    logger.warning(
                        f"No participants found in DB for {thread_id} — "
                        "cannot save final costs (interview data may not be persisted yet)"
                    )
                    return 0

                # Delete previous final_costs for this receipt (idempotent)
                cur.execute(
                    "DELETE FROM final_costs WHERE receipt_id = %s",
                    (thread_id,),
                )

                for pc in participant_costs:
                    name = pc.get("participant", "")
                    participant_id = name_to_id.get(name)
                    if not participant_id:
                        logger.warning(
                            f"Participant '{name}' not in participants table, skipping"
                        )
                        continue

                    subtotal = Decimal(str(pc.get("subtotal", 0)))
                    tax_share = Decimal(str(pc.get("tax_share", 0)))
                    tip_share = Decimal(str(pc.get("tip_share", 0)))
                    fees_share = Decimal(str(pc.get("fees_share", 0)))
                    total_owed = Decimal(str(pc.get("total_owed", 0)))
                    item_costs = pc.get("item_costs")

                    cur.execute(
                        """
                        INSERT INTO final_costs
                            (receipt_id, participant_id, subtotal,
                             tax_share, tip_share, fees_share,
                             total_owed, item_costs)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (receipt_id, participant_id) DO UPDATE SET
                            subtotal   = EXCLUDED.subtotal,
                            tax_share  = EXCLUDED.tax_share,
                            tip_share  = EXCLUDED.tip_share,
                            fees_share = EXCLUDED.fees_share,
                            total_owed = EXCLUDED.total_owed,
                            item_costs = EXCLUDED.item_costs
                        """,
                        (
                            thread_id,
                            participant_id,
                            subtotal,
                            tax_share,
                            tip_share,
                            fees_share,
                            total_owed,
                            Jsonb(item_costs) if item_costs else None,
                        ),
                    )
                    rows_inserted += 1

                conn.commit()
                logger.info(
                    f"✅ Saved {rows_inserted} final_cost rows for {thread_id}"
                )
        return rows_inserted

    except (OperationalError, IntegrityError) as e:
        logger.error(f"❌ DB error saving final costs for {thread_id}: {e}")
        raise PersistenceError(f"Failed to save final costs: {e}"