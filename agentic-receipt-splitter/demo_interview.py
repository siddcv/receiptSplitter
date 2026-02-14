#!/usr/bin/env python3
"""
Simple demonstration of the interview functionality using HTTP requests.

This script shows how to:
1. Create a mock state with receipt items
2. Submit free-form assignment text
3. Handle clarification requests and ambiguity
"""

import requests
import json
import time


def test_interview_api():
    """Test the interview API with the extracted receipt data."""
    
    base_url = "http://127.0.0.1:8000"
    
    # Load the extracted receipt data
    try:
        with open("uploads/receipt-2c173ef8ca48404fbf6c1ca94b63136a.json", 'r') as f:
            receipt_data = json.load(f)
    except FileNotFoundError:
        print("❌ Please run extract_receipt.py first to generate receipt data")
        return
    
    items = receipt_data.get("items", [])
    totals = receipt_data.get("totals", {})
    
    print("🧾 **Receipt Items Available for Assignment:**")
    print("=" * 55)
    for i, item in enumerate(items):
        print(f"[{i}] {item['name']} - ${item['unit_price']}")
    
    print(f"\n📋 **Testing Interview Scenarios**")
    print("Each test creates a new thread to avoid state conflicts")
    
    # Test different assignment scenarios
    test_cases = [
        {
            "name": "Clear Assignment",
            "description": "Alice had the Porky Pepperoni pizza. Bob ordered the Za Matriciana. The wines (Scribe Rose and Tenuta Chianti) were shared equally between Alice and Bob. Alice also paid for the health fee."
        },
        {
            "name": "Fuzzy Matching",
            "description": "I had the pepperoni pizza and one wine. Sarah got the other pizza and the second wine. We split the fee equally."
        },
        {
            "name": "Item Numbers",
            "description": "Alice gets items 0 and 2. Bob gets items 1 and 3. Item 4 goes to Alice."
        },
        {
            "name": "Ambiguous (should need clarification)",
            "description": "I had some food and drinks. My friend had the rest."
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 **Test {i}: {test_case['name']}**")
        print(f"Input: \"{test_case['description']}\"")
        
        # Create a NEW thread for each test
        test_thread_id = f"interview_test_{int(time.time())}_{i}"
        
        # Create new mock state for this test
        mock_payload = {
            "thread_id": test_thread_id,
            "items": items,
            "totals": totals,
            "current_node": "interview_pending"
        }
        
        try:
            # Create the mock state
            response = requests.post(f"{base_url}/test/mock-state", json=mock_payload)
            if response.status_code != 200:
                print(f"❌ Failed to create test state: {response.status_code}")
                print(response.text)
                continue
            
            # Now submit the assignment
            interview_payload = {
                "free_form_assignment": test_case["description"]
            }
            
            response = requests.post(f"{base_url}/interview/{test_thread_id}", json=interview_payload)
            
            if response.status_code == 200:
                result = response.json()["state"]
                
                # Check if clarification is needed
                questions = result.get("pending_questions", [])
                if questions:
                    print("⚠️  **NEEDS CLARIFICATION:**")
                    for question in questions:
                        print(f"   {question}")
                else:
                    print("✅ **ASSIGNMENT SUCCESSFUL:**")
                    participants = result.get("participants", [])
                    assignments = result.get("assignments", [])
                    
                    print(f"   Participants: {', '.join(participants)}")
                    print("   Assignments:")
                    
                    for assignment in assignments:
                        item_idx = assignment["item_index"]
                        if item_idx < len(items):
                            item_name = items[item_idx]['name']
                            print(f"     [{item_idx}] {item_name}:")
                            for share in assignment["shares"]:
                                percentage = float(share["fraction"]) * 100
                                print(f"       - {share['participant']}: {percentage:.1f}%")
            else:
                print(f"❌ Request failed: {response.status_code}")
                print(response.text)
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("-" * 50)
    
    print("\n💡 **Key Features Demonstrated:**")
    print("• Natural language processing for item assignments")
    print("• Fuzzy matching (pepperoni pizza → Porky Pepperoni)")
    print("• Support for item references by number [0], [1], etc.")
    print("• Automatic detection of incomplete or ambiguous assignments")
    print("• Request for clarification when needed")
    print("• Validation that all items are properly assigned")


if __name__ == "__main__":
    print("🤖 **Interview API Testing**")
    print("Testing enhanced ambiguity handling and assignment validation\n")
    test_interview_api()