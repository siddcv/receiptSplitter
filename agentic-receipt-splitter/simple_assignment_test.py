#!/usr/bin/env python3
"""
Quick test to isolate the assignment processing issue.
"""

import requests
import json
import time


def test_simple_assignment():
    """Test a simple assignment to isolate the 500 error."""
    
    base_url = "http://127.0.0.1:8000"
    
    # Create a simple mock state first
    thread_id = f"simple_test_{int(time.time())}"
    
    # Simple items for testing
    items = [
        {"name": "Pizza", "unit_price": 20.0, "quantity": 1},
        {"name": "Salad", "unit_price": 10.0, "quantity": 1}
    ]
    
    # Create mock state
    payload = {
        "thread_id": thread_id,
        "items": items,
        "current_node": "interview_pending"
    }
    
    print("📋 Creating simple test state...")
    response = requests.post(f"{base_url}/test/mock-state", json=payload)
    
    if response.status_code != 200:
        print(f"❌ Failed to create state: {response.status_code}")
        print(response.text)
        return
    
    print("✅ Mock state created")
    
    # Test simple assignment
    assignment_payload = {
        "free_form_assignment": "I had the pizza. Alice had the salad."
    }
    
    print("📝 Testing simple assignment...")
    response = requests.post(f"{base_url}/interview/{thread_id}", json=assignment_payload)
    
    if response.status_code == 200:
        print("✅ Assignment successful!")
        result = response.json()
        print(json.dumps(result, indent=2))
    else:
        print(f"❌ Assignment failed: {response.status_code}")
        print(response.text)


if __name__ == "__main__":
    test_simple_assignment()