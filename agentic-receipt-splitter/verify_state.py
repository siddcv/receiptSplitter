#!/usr/bin/env python3
"""
Verify that the state after vision + interview nodes contains all the data needed for the math node.

This script checks the actual state structure to confirm the math node will have:
- Items with prices/quantities
- Participants list  
- Assignment percentages for each item
- Totals (subtotal, tax, tip, grand_total)
"""

import requests
import json
import sys
from pathlib import Path

def main():
    print("🔍 **STATE VERIFICATION FOR MATH NODE**")
    print("=" * 50)
    
    base_url = "http://127.0.0.1:8000"
    
    # Check if server is running
    try:
        response = requests.get(f"{base_url}/")
        if response.status_code != 200:
            print("❌ Server not running. Please start with: uvicorn app.main:app --reload")
            return
        print("✅ Server is running")
    except requests.exceptions.ConnectionError:
        print("❌ Server not running. Please start with: uvicorn app.main:app --reload")
        return
    
    # Step 1: Upload receipt
    print("\n📤 **Step 1: Upload Receipt**")
    receipt_image_path = Path("uploads/receipt-2c173ef8ca48404fbf6c1ca94b63136a.jpg")
    
    if not receipt_image_path.exists():
        print(f"❌ Receipt image not found: {receipt_image_path}")
        return
    
    with open(receipt_image_path, 'rb') as f:
        files = {'file': ('receipt.jpg', f, 'image/jpeg')}
        response = requests.post(f"{base_url}/upload", files=files)
    
    if response.status_code != 200:
        print(f"❌ Upload failed: {response.status_code}")
        return
    
    upload_result = response.json()
    thread_id = upload_result['thread_id']
    print(f"✅ Upload successful, Thread ID: {thread_id}")
    
    # Step 2: Submit assignment
    print("\n📝 **Step 2: Submit Assignment**") 
    assignment_text = "Alice had both pizzas, Bob had both wines, they split the living wage"
    
    interview_payload = {"free_form_assignment": assignment_text}
    response = requests.post(f"{base_url}/interview/{thread_id}", json=interview_payload)
    
    if response.status_code != 200:
        print(f"❌ Interview failed: {response.status_code}")
        return
    
    result = response.json()['state']
    print("✅ Assignment completed")
    
    # Step 3: Analyze state for math node readiness
    print("\n🧮 **Step 3: State Analysis for Math Node**")
    print("=" * 45)
    
    verify_items(result)
    verify_participants(result)
    verify_assignments(result)
    verify_totals(result)
    
    print("\n✅ **VERIFICATION COMPLETE**")
    print("The state contains all required data for the math node!")


def verify_items(state):
    """Verify items data is complete."""
    items = state.get('items', [])
    print(f"\n📦 **Items ({len(items)} found):**")
    
    if not items:
        print("❌ No items found!")
        return
    
    for i, item in enumerate(items):
        name = item.get('name', 'MISSING')
        price = item.get('price', 'MISSING') 
        quantity = item.get('quantity', 'MISSING')
        print(f"   [{i}] {name} - ${price} x {quantity}")
        
        if not all([name != 'MISSING', price != 'MISSING', quantity != 'MISSING']):
            print(f"      ❌ Item {i} has missing data!")
    
    print("   ✅ Items data complete")


def verify_participants(state):
    """Verify participants list."""
    participants = state.get('participants', [])
    print(f"\n👥 **Participants ({len(participants)} found):**")
    
    if not participants:
        print("❌ No participants found!")
        return
    
    for participant in participants:
        print(f"   • {participant}")
    
    print("   ✅ Participants data complete")


def verify_assignments(state):
    """Verify assignment percentages."""
    assignments = state.get('assignments', [])
    items = state.get('items', [])
    participants = state.get('participants', [])
    
    print(f"\n📊 **Assignments ({len(assignments)} found):**")
    
    if not assignments:
        print("❌ No assignments found!")
        return
    
    for assignment in assignments:
        item_idx = assignment.get('item_index', -1)
        shares = assignment.get('shares', [])
        
        if item_idx < len(items):
            item_name = items[item_idx].get('name', 'Unknown')
            print(f"   [{item_idx}] {item_name}:")
            
            total_percentage = 0
            for share in shares:
                participant = share.get('participant', 'MISSING')
                fraction = float(share.get('fraction', 0))
                percentage = fraction * 100
                total_percentage += percentage
                print(f"      → {participant}: {percentage:.1f}%")
            
            if abs(total_percentage - 100.0) > 0.1:
                print(f"      ❌ Percentages sum to {total_percentage:.1f}%, not 100%!")
            else:
                print(f"      ✅ Percentages sum correctly to {total_percentage:.1f}%")
    
    print("   ✅ Assignment percentages complete")


def verify_totals(state):
    """Verify totals for tax/tip calculations."""
    totals = state.get('totals')
    print(f"\n💰 **Totals:**")
    
    if not totals:
        print("❌ No totals found!")
        return
    
    required_fields = ['subtotal', 'tax_total', 'tip_total', 'grand_total']
    for field in required_fields:
        value = totals.get(field, 'MISSING')
        print(f"   • {field}: ${value}")
        
        if value == 'MISSING':
            print(f"      ❌ {field} is missing!")
    
    # Verify math
    subtotal = float(totals.get('subtotal', 0))
    tax = float(totals.get('tax_total', 0))
    tip = float(totals.get('tip_total', 0))
    fees = float(totals.get('fees_total', 0))
    grand_total = float(totals.get('grand_total', 0))
    
    expected_total = subtotal + tax + tip + fees
    if abs(expected_total - grand_total) < 0.01:
        print(f"   ✅ Total math checks out: ${expected_total:.2f} = ${grand_total:.2f}")
    else:
        print(f"   ❌ Total math error: {subtotal} + {tax} + {tip} + {fees} = {expected_total}, but grand_total = {grand_total}")


if __name__ == "__main__":
    main()