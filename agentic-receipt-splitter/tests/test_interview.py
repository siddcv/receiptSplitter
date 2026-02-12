#!/usr/bin/env python3
"""
Test script to demonstrate the enhanced interview functionality.

This script simulates the interview process with different types of free-form input
to show how it handles ambiguity and ensures all items are assigned.
"""

import os
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the parent directory to the Python path so we can import from app
sys.path.append(str(Path(__file__).parent.parent))

from app.graph.nodes.interview import interview_node


def test_interview_with_receipt_data():
    """Test the interview node with real receipt data and various input scenarios."""
    
    # Load the extracted receipt data
    receipt_json_path = Path(__file__).parent.parent / "uploads" / "receipt-2c173ef8ca48404fbf6c1ca94b63136a.json"
    print(f"Looking for receipt JSON at: {receipt_json_path}")
    print(f"File exists: {receipt_json_path.exists()}")
    
    if not receipt_json_path.exists():
        print("❌ Receipt JSON file not found. Please run extract_receipt.py first.")
        return
    
    with open(receipt_json_path, 'r') as f:
        receipt_data = json.load(f)
    
    # Create a mock state with the extracted items
    items = receipt_data.get("items", [])
    
    print("🍕 **Receipt Items for Assignment:**")
    print("=" * 50)
    for i, item in enumerate(items):
        print(f"[{i}] {item['name']} - ${item['unit_price']}")
    
    print(f"\n📊 **Testing Interview Node with Various Inputs**")
    print("=" * 60)
    
    # Test scenarios
    test_scenarios = [
        {
            "name": "Clear Assignment",
            "input": "Alice had the Porky Pepperoni pizza. Bob ordered the Za Matriciana. The wine (Scribe Rose and Tenuta Chianti) were shared equally between Alice and Bob. Alice also paid for the health & living wage fee.",
            "description": "Clear assignment with exact item names"
        },
        {
            "name": "Fuzzy Matching",
            "input": "I had the pepperoni pizza and the red wine. Sarah got the other pizza and the white wine. We split the fee.",
            "description": "Uses approximate item descriptions (pepperoni pizza, red wine, etc.)"
        },
        {
            "name": "Item Numbers",
            "input": "Alice: items 0 and 2. Bob: item 1 and 3. The fee (item 4) goes to Alice.",
            "description": "References items by their index numbers"
        },
        {
            "name": "Ambiguous Input",
            "input": "I had a pizza. My friend had the other stuff.",
            "description": "Vague assignment that should trigger clarification"
        },
        {
            "name": "Incomplete Assignment",
            "input": "Alice had the Porky Pepperoni. Bob had some wine.",
            "description": "Not all items are assigned"
        }
    ]
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n🧪 **Test {i}: {scenario['name']}**")
        print(f"Description: {scenario['description']}")
        print(f"Input: \"{scenario['input']}\"\n")
        
        # Create test state
        test_state = {
            "thread_id": f"test_{i}",
            "items": items,
            "participants": [],
            "assignments": [],
            "totals": receipt_data.get("totals"),
            "current_node": "interview_pending",
            "free_form_assignment": scenario["input"],
            "audit_log": [],
            "pending_questions": []
        }
        
        try:
            # Run the interview node
            result = interview_node(test_state)
            
            # Display results
            if result.get("pending_questions"):
                print("⚠️  **NEEDS CLARIFICATION:**")
                for question in result["pending_questions"]:
                    print(f"   {question}")
            else:
                print("✅ **ASSIGNMENT SUCCESSFUL:**")
                participants = result.get("participants", [])
                assignments = result.get("assignments", [])
                
                print(f"   Participants: {', '.join(participants)}")
                print("   Assignments:")
                
                for assignment in assignments:
                    item_idx = assignment.item_index
                    if item_idx < len(items):
                        item_name = items[item_idx]['name']
                        print(f"     [{item_idx}] {item_name}:")
                        for share in assignment.shares:
                            percentage = float(share.fraction) * 100
                            print(f"       - {share.participant}: {percentage:.1f}%")
            
            # Show audit information
            audit_entries = result.get("audit_log", [])
            if audit_entries:
                latest_audit = audit_entries[-1]
                print(f"   📝 Status: {latest_audit.message}")
                
        except Exception as e:
            print(f"❌ **ERROR:** {e}")
        
        print("-" * 60)


def main():
    # Check if API key is set
    if not os.getenv("GOOGLE_API_KEY"):
        print("❌ Error: GOOGLE_API_KEY not found in environment!")
        print("Please set your Google API key in the .env file")
        return
    
    print("🤖 **Enhanced Interview Node Testing**")
    print("Testing improved ambiguity handling and assignment validation\n")
    
    test_interview_with_receipt_data()
    
    print("\n💡 **Key Improvements:**")
    print("• Fuzzy matching for item names (pizza → Porky Pepperoni)")
    print("• Handles item references by number [0], [1], etc.")
    print("• Detects unassigned items and asks for clarification")
    print("• Identifies ambiguous assignments and requests specifics")
    print("• Validates that all items are fully assigned")
    print("• Supports complex sharing scenarios")


if __name__ == "__main__":
    main()