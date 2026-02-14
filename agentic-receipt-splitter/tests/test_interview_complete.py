"""
Test the interview workflow with mock data via test endpoint.

This test:
1. Creates mock state via POST /test/mock-state 
2. Submits interview assignments via POST /interview/{thread_id}
3. Shows the complete interview flow without API calls

Usage:
    python tests/test_interview_complete.py

Requires server running: uvicorn app.main:app --reload --port 8000
"""

import json
import httpx

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 30.0


def test_complete_interview_flow():
    """Test the full interview workflow with mock data."""
    
    print("🧪 Testing Complete Interview Flow")
    print("=" * 50)
    
    # --- Step 1: Create mock state ---
    thread_id = "test-interview-flow"
    mock_items = [
        {
            "name": "Pizza Margherita",
            "price": "18.50",
            "quantity": "1"
        },
        {
            "name": "Caesar Salad", 
            "price": "12.00",
            "quantity": "1"
        },
        {
            "name": "Garlic Bread",
            "price": "6.50", 
            "quantity": "1"
        }
    ]
    
    mock_totals = {
        "subtotal": "37.00",
        "tax_total": "3.70",
        "tip_total": "6.00", 
        "fees_total": "0.00",
        "grand_total": "46.70"
    }
    
    print("📋 Creating mock state...")
    mock_payload = {
        "thread_id": thread_id,
        "items": mock_items,
        "totals": mock_totals,
        "current_node": "interview_pending"
    }
    
    try:
        resp = httpx.post(f"{BASE_URL}/test/mock-state", json=mock_payload, timeout=TIMEOUT)
        resp.raise_for_status()
        mock_result = resp.json()
        print(f"✅ Mock state created: {thread_id}")
        
        state = mock_result.get("state", {})
        print(f"   Items: {len(state.get('items', []))}")
        print(f"   Current node: {state.get('current_node')}")
        
        # Show pending questions
        questions = state.get("pending_questions", [])
        if questions:
            print("\n❓ Pending questions:")
            for q in questions:
                print(f"   {q[:150]}...")
        
    except Exception as e:
        print(f"❌ Failed to create mock state: {e}")
        return
    
    # --- Step 2: Submit interview assignments ---
    participants = ["Alice", "Bob", "Charlie"]
    assignments = [
        {
            "item_index": 0,  # Pizza - Alice and Bob split 50/50
            "shares": [
                {"participant": "Alice", "fraction": 0.5},
                {"participant": "Bob", "fraction": 0.5}
            ]
        },
        {
            "item_index": 1,  # Caesar Salad - Alice only
            "shares": [
                {"participant": "Alice", "fraction": 1.0}
            ]
        },
        {
            "item_index": 2,  # Garlic Bread - all three split equally
            "shares": [
                {"participant": "Alice", "fraction": 0.3334},
                {"participant": "Bob", "fraction": 0.3333}, 
                {"participant": "Charlie", "fraction": 0.3333}
            ]
        }
    ]
    
    print(f"\n📝 Submitting interview assignments...")
    print(f"   Participants: {participants}")
    print(f"   Assignments: {len(assignments)} items")
    
    interview_payload = {
        "participants": participants,
        "assignments": assignments
    }
    
    try:
        resp = httpx.post(
            f"{BASE_URL}/interview/{thread_id}",
            json=interview_payload,
            timeout=TIMEOUT
        )
        resp.raise_for_status()
        interview_result = resp.json()
        
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error {e.response.status_code}: {e.response.text}")
        return
    except Exception as e:
        print(f"❌ Interview submission failed: {e}")
        return
    
    print("✅ Interview submission successful!")
    
    # --- Step 3: Analyze results ---
    final_state = interview_result.get("state", {})
    print(f"\n📊 Final State Analysis:")
    print(f"   Thread ID: {final_state.get('thread_id')}")
    print(f"   Current node: {final_state.get('current_node')}")
    print(f"   Participants: {final_state.get('participants')}")
    
    # Show final assignments
    final_assignments = final_state.get("assignments", [])
    print(f"\n--- Final Assignments ({len(final_assignments)} items) ---")
    
    items = final_state.get("items", [])
    for assignment in final_assignments:
        idx = assignment.get("item_index")
        if idx < len(items):
            item_name = items[idx]["name"]
            item_price = items[idx]["price"]
        else:
            item_name = f"Item {idx}"
            item_price = "?"
            
        shares = assignment.get("shares", [])
        shares_str = ", ".join(f"{s['participant']}={s['fraction']}" for s in shares)
        print(f"  [{idx}] {item_name} (${item_price}): {shares_str}")
    
    # Check for any remaining questions
    remaining_questions = final_state.get("pending_questions", [])
    if remaining_questions:
        print(f"\n⚠️ Still pending ({len(remaining_questions)}) questions:")
        for q in remaining_questions:
            print(f"  ❓ {q[:100]}...")
    else:
        print("\n✅ No pending questions — interview complete!")
    
    # Show recent audit trail
    audit_log = final_state.get("audit_log", [])
    print(f"\n--- Recent Audit Log (last 3 of {len(audit_log)}) ---")
    for entry in audit_log[-3:]:  
        node = entry.get("node", "?")
        msg = entry.get("message", "")
        timestamp = entry.get("timestamp", "")[:19]  # truncate microseconds
        print(f"  [{timestamp}] [{node}] {msg}")
    
    print(f"\n🎉 Interview test completed successfully!")
    print(f"   Ready to implement the math node next!")


if __name__ == "__main__":
    test_complete_interview_flow()