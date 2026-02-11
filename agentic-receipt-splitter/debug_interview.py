#!/usr/bin/env python3
"""
Direct test of the interview node function to debug the 500 error.
"""

import sys
import os
from pathlib import Path

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent))

from app.graph.nodes.interview import interview_node


def test_interview_node_directly():
    """Test the interview node function directly to see the error."""
    
    # Create a simple test state
    test_state = {
        "thread_id": "test123",
        "items": [
            {"name": "Pizza", "unit_price": 20.0, "quantity": 1},
            {"name": "Salad", "unit_price": 10.0, "quantity": 1}
        ],
        "participants": [],
        "assignments": [],
        "free_form_assignment": "I had the pizza. Alice had the salad.",
        "current_node": "interview_pending",
        "audit_log": [],
        "pending_questions": []
    }
    
    print("🧪 Testing interview node directly...")
    print(f"Input state: {test_state}")
    
    try:
        result = interview_node(test_state)
        print("✅ Interview node succeeded!")
        print(f"Result: {result}")
        return True
    except Exception as e:
        print(f"❌ Interview node failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_interview_node_directly()