"""
Math node: calculates final costs for each participant based on assignments.

This node processes the assignments from the interview node and calculates:
1. Individual item costs based on assignment percentages
2. Proportional distribution of taxes, tips, and fees
3. Final amount each participant owes

The math node only runs after interview completion (no pending questions).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List

from app.graph.state import AuditEvent, ReceiptState

logger = logging.getLogger(__name__)

TWO_DP = Decimal("0.01")


class ParticipantCost(dict):
    """Structure to hold calculated costs for a participant."""
    
    def __init__(self, participant: str):
        super().__init__()
        self['participant'] = participant
        self['item_costs'] = []  # List of individual item costs
        self['subtotal'] = Decimal("0.00")
        self['tax_share'] = Decimal("0.00")
        self['tip_share'] = Decimal("0.00")
        self['fees_share'] = Decimal("0.00")
        self['total_owed'] = Decimal("0.00")


def _calculate_item_costs(items: List, assignments: List, participants: List[str]) -> List[ParticipantCost]:
    """Calculate individual item costs for each participant."""
    
    # Initialize participant cost tracking
    participant_costs = [ParticipantCost(p) for p in participants]
    participant_lookup = {p: i for i, p in enumerate(participants)}
    
    # Calculate item costs for each assignment
    for assignment in assignments:
        item_idx = assignment.get('item_index') if isinstance(assignment, dict) else assignment.item_index
        shares = assignment.get('shares', []) if isinstance(assignment, dict) else assignment.shares
        
        if item_idx < len(items):
            item = items[item_idx]
            
            # Get item details
            if hasattr(item, 'name'):  # Pydantic Item object
                item_name = item.name
                item_price = item.price
                item_quantity = item.quantity
            else:  # Plain dict
                item_name = item.get('name', 'Unknown')
                item_price = Decimal(str(item.get('price', item.get('unit_price', 0))))
                item_quantity = Decimal(str(item.get('quantity', 1)))
            
            # Calculate total cost for this item
            total_item_cost = (item_price * item_quantity).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            
            # Distribute cost among participants based on shares
            for share in shares:
                if isinstance(share, dict):
                    participant = share.get('participant')
                    fraction = Decimal(str(share.get('fraction', 0)))
                else:
                    participant = share.participant
                    fraction = share.fraction
                
                if participant in participant_lookup:
                    participant_idx = participant_lookup[participant]
                    participant_cost = (total_item_cost * fraction).quantize(TWO_DP, rounding=ROUND_HALF_UP)
                    
                    # Record individual item cost
                    participant_costs[participant_idx]['item_costs'].append({
                        'item_index': item_idx,
                        'item_name': item_name,
                        'item_price': float(item_price),
                        'quantity': float(item_quantity),
                        'share_percentage': float(fraction * 100),
                        'cost': float(participant_cost)
                    })
                    
                    # Add to subtotal
                    participant_costs[participant_idx]['subtotal'] += participant_cost
    
    return participant_costs


def _distribute_taxes_tips_fees(participant_costs: List[ParticipantCost], totals: Dict) -> List[ParticipantCost]:
    """Distribute taxes, tips, and fees proportionally based on subtotal shares."""
    
    if not totals:
        logger.warning("No totals found - cannot distribute taxes/tips/fees")
        return participant_costs
    
    # Get totals
    tax_total = Decimal(str(totals.get('tax_total', 0)))
    tip_total = Decimal(str(totals.get('tip_total', 0)))
    fees_total = Decimal(str(totals.get('fees_total', 0)))
    
    # Calculate total subtotal across all participants
    total_subtotal = sum(pc['subtotal'] for pc in participant_costs)
    
    if total_subtotal <= 0:
        logger.warning("Total subtotal is zero - cannot distribute taxes/tips/fees proportionally")
        return participant_costs
    
    # First pass: calculate proportional shares
    for participant_cost in participant_costs:
        participant_subtotal = participant_cost['subtotal']
        proportion = participant_subtotal / total_subtotal
        
        # Calculate shares (rounded down initially)
        tax_share = (tax_total * proportion).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        tip_share = (tip_total * proportion).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        fees_share = (fees_total * proportion).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        
        participant_cost['tax_share'] = tax_share
        participant_cost['tip_share'] = tip_share
        participant_cost['fees_share'] = fees_share
        participant_cost['proportion'] = float(proportion)  # Store for rounding adjustment
    
    # Ensure exact totals by adjusting for rounding errors
    _adjust_for_rounding_errors(participant_costs, tax_total, tip_total, fees_total)
    
    # Calculate final totals
    for participant_cost in participant_costs:
        participant_cost['total_owed'] = (
            participant_cost['subtotal'] + 
            participant_cost['tax_share'] + 
            participant_cost['tip_share'] + 
            participant_cost['fees_share']
        ).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        
        # Remove temporary proportion field
        participant_cost.pop('proportion', None)
    
    return participant_costs


def _adjust_for_rounding_errors(participant_costs: List[ParticipantCost], tax_total: Decimal, tip_total: Decimal, fees_total: Decimal):
    """Adjust for rounding errors to ensure totals match exactly."""
    
    # Calculate current totals after rounding
    current_tax = sum(pc['tax_share'] for pc in participant_costs)
    current_tip = sum(pc['tip_share'] for pc in participant_costs)
    current_fees = sum(pc['fees_share'] for pc in participant_costs)
    
    # Calculate differences (should be small rounding errors)
    tax_diff = tax_total - current_tax
    tip_diff = tip_total - current_tip  
    fees_diff = fees_total - current_fees
    
    # Find participant with largest subtotal to absorb rounding differences
    largest_participant_idx = max(range(len(participant_costs)), 
                                key=lambda i: participant_costs[i]['subtotal'])
    
    # Adjust the largest participant's shares to make totals exact
    participant_costs[largest_participant_idx]['tax_share'] += tax_diff
    participant_costs[largest_participant_idx]['tip_share'] += tip_diff
    participant_costs[largest_participant_idx]['fees_share'] += fees_diff


def _validate_total_matches_receipt(participant_costs: List[ParticipantCost], totals: Dict) -> Dict:
    """Validate that calculated total matches receipt total within tolerance."""
    
    if not totals:
        return {'valid': False, 'message': 'No receipt totals found for validation'}
    
    # Calculate our total
    calculated_total = sum(pc['total_owed'] for pc in participant_costs)
    
    # Get receipt total
    receipt_total = Decimal(str(totals.get('grand_total', 0)))
    
    # Check if they match (allowing for minimal rounding differences)
    difference = abs(calculated_total - receipt_total)
    tolerance = Decimal('0.05')  # 5 cent tolerance
    
    if difference <= tolerance:
        return {
            'valid': True, 
            'message': 'Totals match within tolerance',
            'calculated_total': str(calculated_total),
            'receipt_total': str(receipt_total),
            'difference': str(difference)
        }
    else:
        return {
            'valid': False,
            'message': f'Significant discrepancy: calculated ${calculated_total}, receipt ${receipt_total} (difference: ${difference})',
            'calculated_total': str(calculated_total),
            'receipt_total': str(receipt_total), 
            'difference': str(difference)
        }


def _generate_cost_breakdown(participant_costs: List[ParticipantCost], totals: Dict) -> Dict:
    """Generate detailed cost breakdown showing how taxes/tips were distributed."""
    
    breakdown = {
        'summary': {
            'total_participants': len(participant_costs),
            'receipt_totals': {
                'subtotal': str(totals.get('subtotal', 0)) if totals else '0.00',
                'tax': str(totals.get('tax_total', 0)) if totals else '0.00', 
                'tip': str(totals.get('tip_total', 0)) if totals else '0.00',
                'fees': str(totals.get('fees_total', 0)) if totals else '0.00',
                'grand_total': str(totals.get('grand_total', 0)) if totals else '0.00'
            },
            'calculated_totals': {
                'subtotal': str(sum(pc['subtotal'] for pc in participant_costs)),
                'tax': str(sum(pc['tax_share'] for pc in participant_costs)),
                'tip': str(sum(pc['tip_share'] for pc in participant_costs)),
                'fees': str(sum(pc['fees_share'] for pc in participant_costs)),
                'grand_total': str(sum(pc['total_owed'] for pc in participant_costs))
            }
        },
        'participant_details': []
    }
    
    for pc in participant_costs:
        participant_detail = {
            'participant': pc['participant'],
            'subtotal_percentage': float((pc['subtotal'] / sum(p['subtotal'] for p in participant_costs)) * 100) if sum(p['subtotal'] for p in participant_costs) > 0 else 0,
            'costs': {
                'subtotal': str(pc['subtotal']),
                'tax_share': str(pc['tax_share']),
                'tip_share': str(pc['tip_share']),
                'fees_share': str(pc['fees_share']),
                'total_owed': str(pc['total_owed'])
            },
            'items': pc['item_costs']
        }
        breakdown['participant_details'].append(participant_detail)
    
    return breakdown


def math_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node: calculate final costs for each participant."""
    
    # Handle both ReceiptState objects and plain dicts
    if hasattr(state, 'items') and hasattr(state, 'model_dump'):  # ReceiptState object
        items = getattr(state, 'items', [])
        participants = getattr(state, 'participants', [])
        assignments = getattr(state, 'assignments', [])
        totals = getattr(state, 'totals', None)
        pending_questions = getattr(state, 'pending_questions', [])
    else:  # Plain dict
        items = state.get("items", [])
        participants = state.get("participants", [])
        assignments = state.get("assignments", [])
        totals = state.get("totals")
        pending_questions = state.get("pending_questions", [])
    
    # Check prerequisites
    if pending_questions:
        return {
            "audit_log": [
                AuditEvent(
                    node="math",
                    message="Cannot calculate costs - interview has pending questions",
                    timestamp=datetime.now(timezone.utc),
                    details={"pending_questions": pending_questions}
                )
            ],
        }
    
    if not participants:
        return {
            "audit_log": [
                AuditEvent(
                    node="math",
                    message="Cannot calculate costs - no participants found",
                    timestamp=datetime.now(timezone.utc),
                )
            ],
        }
    
    if not assignments:
        return {
            "audit_log": [
                AuditEvent(
                    node="math",
                    message="Cannot calculate costs - no assignments found",
                    timestamp=datetime.now(timezone.utc),
                )
            ],
        }
    
    if not items:
        return {
            "audit_log": [
                AuditEvent(
                    node="math",
                    message="Cannot calculate costs - no items found",
                    timestamp=datetime.now(timezone.utc),
                )
            ],
        }
    
    try:
        # Calculate individual item costs
        participant_costs = _calculate_item_costs(items, assignments, participants)
        
        # Distribute taxes, tips, and fees proportionally
        if totals:
            participant_costs = _distribute_taxes_tips_fees(participant_costs, totals)
        
        # Validate total matches receipt
        validation_result = _validate_total_matches_receipt(participant_costs, totals) if totals else {'valid': True, 'message': 'No totals to validate'}
        
        # If validation fails with significant discrepancy, return to interview
        if not validation_result['valid'] and Decimal(validation_result.get('difference', '0')) > Decimal('1.00'):
            return {
                "error_message": f"Cost calculation error: {validation_result['message']}. Please verify item assignments.",
                "needs_interview": True,
                "audit_log": [
                    AuditEvent(
                        node="math",
                        message=f"Validation failed: {validation_result['message']}",
                        timestamp=datetime.now(timezone.utc),
                        details=validation_result
                    )
                ],
            }
        
        # Generate detailed breakdown
        breakdown = _generate_cost_breakdown(participant_costs, totals) if totals else {}
        
        # Convert to serializable format
        final_costs = []
        for pc in participant_costs:
            cost_dict = {
                'participant': pc['participant'],
                'subtotal': str(pc['subtotal']),
                'tax_share': str(pc['tax_share']),
                'tip_share': str(pc['tip_share']),
                'fees_share': str(pc['fees_share']),
                'total_owed': str(pc['total_owed']),
                'item_costs': pc['item_costs']
            }
            final_costs.append(cost_dict)
        
        return {
            "final_costs": {
                'participant_costs': final_costs,
                'breakdown': breakdown,
                'validation': validation_result,
                'calculated_at': str(datetime.now())
            },
            "current_node": "math",
            "pending_questions": [],
            "needs_interview": False,
            "error_message": None,
            "audit_log": [
                AuditEvent(
                    node="math",
                    message=f"Cost calculation complete for {len(participants)} participants",
                    timestamp=datetime.now(timezone.utc),
                    details={
                        "participant_count": len(participants),
                        "validation_status": "passed" if validation_result['valid'] else "failed_but_within_tolerance",
                        "calculated_total": validation_result.get('calculated_total', '0.00'),
                        "receipt_total": validation_result.get('receipt_total', '0.00'),
                        "difference": validation_result.get('difference', '0.00')
                    },
                )
            ],
        }
        
    except Exception as e:
        return {
            "audit_log": [
                AuditEvent(
                    node="math",
                    message=f"Cost calculation failed: {str(e)}",
                    timestamp=datetime.now(timezone.utc),
                    details={"error": str(e)},
                )
            ],
        }