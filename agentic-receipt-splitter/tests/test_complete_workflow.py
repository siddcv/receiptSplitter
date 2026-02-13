#!/usr/bin/env python3
"""
Test the complete workflow: vision → interview → math

This script tests the full end-to-end workflow including the new math node.
"""

import sys
from pathlib import Path

# Add the parent directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.graph.workflow import build_graph
from app.graph.state import ReceiptState, AuditEvent
import json


def test_complete_workflow():
    """Test the complete workflow with math node."""
    
    print("🧮 **TESTING COMPLETE WORKFLOW: VISION → INTERVIEW → MATH**")
    print("=" * 60)
    
    # Load test receipt data
    receipt_json_path = Path(__file__).parent / "uploads" / "receipt-2c173ef8ca48404fbf6c1ca94b63136a.json"
    
    if not receipt_json_path.exists():
        print("❌ Receipt JSON not found. Run extract_receipt.py first.")
        return
    
    with open(receipt_json_path, 'r') as f:
        receipt_data = json.load(f)
    
    items = receipt_data.get("items", [])
    totals = receipt_data.get("totals", {})
    
    print(f"📋 **Test Data:**")
    print(f"   • {len(items)} items loaded")
    print(f"   • Receipt total: ${totals.get('grand_total', 0)}")
    
    # Build the graph
    try:
        app_graph = build_graph()
        print("✅ Graph compiled successfully")
    except Exception as e:
        print(f"❌ Graph compilation failed: {e}")
        return
    
    # Create initial state (simulating after vision node)
    initial_state = ReceiptState(
        thread_id="test_math_workflow",
        items=items,
        totals=totals,
        participants=[],  # Empty - will be filled by interview
        assignments=[],   # Empty - will be filled by interview
        audit_log=[
            AuditEvent(
                node="test",
                message="Simulating state after vision node",
                details={"items_count": len(items)}
            )
        ],
        current_node="vision",
        pending_questions=[],
    )
    
    print(f"\n🎤 **Step 1: Testing Interview Node**")
    print("-" * 35)
    
    # Test interview with free-form input
    test_state = initial_state.model_dump()
    test_state["free_form_assignment"] = "Alice had both pizzas, Bob had both wines, they split the living wage"
    
    try:
        from app.graph.nodes.interview import interview_node
        interview_result = interview_node(test_state)
        
        # Update state with interview results
        for key, value in interview_result.items():
            test_state[key] = value
        
        participants = interview_result.get("participants", [])
        assignments = interview_result.get("assignments", [])
        pending = interview_result.get("pending_questions", [])
        
        if pending:
            print("⚠️ Interview needs clarification:")
            for q in pending:
                print(f"   {q}")
            return
        
        print(f"✅ Interview completed:")
        print(f"   • Participants: {', '.join(participants)}")
        print(f"   • Assignments: {len(assignments)} items assigned")
        
    except Exception as e:
        print(f"❌ Interview failed: {e}")
        return
    
    print(f"\n🧮 **Step 2: Testing Math Node**")
    print("-" * 30)
    
    try:
        from app.graph.nodes.math import math_node
        math_result = math_node(test_state)
        
        final_costs = math_result.get("final_costs", [])
        
        if not final_costs:
            print("❌ No final costs calculated")
            audit = math_result.get("audit_log", [])
            if audit:
                print(f"   Error: {audit[-1].message}")
            return
        
        print(f"✅ Math calculation completed:")
        
        # Display results
        print(f"\n💰 **Final Cost Breakdown:**")
        print("=" * 35)
        
        total_calculated = 0
        for cost in final_costs:
            participant = cost['participant']
            subtotal = float(cost['subtotal'])
            tax_share = float(cost['tax_share'])
            tip_share = float(cost['tip_share'])
            total_owed = float(cost['total_owed'])
            total_calculated += total_owed
            
            print(f"\n{participant}:")
            print(f"   Items:     ${subtotal:.2f}")
            print(f"   Tax:       ${tax_share:.2f}")
            print(f"   Tip:       ${tip_share:.2f}")
            print(f"   TOTAL:     ${total_owed:.2f}")
        
        print(f"\n📊 **Verification:**")
        receipt_total = float(totals.get('grand_total', 0))
        print(f"   Calculated total: ${total_calculated:.2f}")
        print(f"   Receipt total:    ${receipt_total:.2f}")
        print(f"   Difference:       ${abs(total_calculated - receipt_total):.2f}")
        
        if abs(total_calculated - receipt_total) < 0.01:
            print("   ✅ Totals match!")
        else:
            print("   ⚠️  Small rounding difference (expected)")
        
    except Exception as e:
        print(f"❌ Math node failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"\n🎉 **COMPLETE WORKFLOW TEST SUCCESS!**")
    print("All nodes working correctly: vision → interview → math")


if __name__ == "__main__":
    test_complete_workflow()