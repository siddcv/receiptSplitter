#!/usr/bin/env python3
"""
Complete end-to-end receipt splitter demo.

This script demonstrates the full workflow:
1. Upload receipt image to the API
2. Extract text using Gemini Vision API  
3. Start interactive interview process in terminal
4. Handle assignments with natural language input
5. Show final results with cost breakdown

Simulates the real user experience of the receipt splitter app.
"""

import requests
import json
import time
import sys
from pathlib import Path


def main():
    print("🍽️  **RECEIPT SPLITTER - COMPLETE DEMO**")
    print("=" * 50)
    print("Testing the full end-to-end workflow:")
    print("  1. Upload receipt image")
    print("  2. Extract items with Gemini Vision")
    print("  3. Interactive assignment interview")
    print("  4. Calculate final splits\n")
    
    base_url = "http://127.0.0.1:8000"
    
    # Check if server is running
    try:
        response = requests.get(f"{base_url}/")
        if response.status_code == 200:
            info = response.json()
            print(f"✅ Server running: {info.get('status')} (mode: {info.get('mode')})")
        else:
            print("❌ Server not responding properly")
            return
    except requests.exceptions.ConnectionError:
        print("❌ Server not running. Please start with: uvicorn app.main:app --reload")
        return
    
    # Step 1: Upload the receipt image
    print("\n📤 **STEP 1: Uploading Receipt Image**")
    print("-" * 30)
    
    receipt_image_path = Path("uploads/receipt-2c173ef8ca48404fbf6c1ca94b63136a.jpg")
    
    if not receipt_image_path.exists():
        print(f"❌ Receipt image not found: {receipt_image_path}")
        print("Please make sure you have run extract_receipt.py first")
        return
    
    try:
        with open(receipt_image_path, 'rb') as f:
            files = {'file': ('receipt.jpg', f, 'image/jpeg')}
            response = requests.post(f"{base_url}/upload", files=files)
        
        if response.status_code == 200:
            upload_result = response.json()
            thread_id = upload_result['thread_id']
            state = upload_result['state']
            
            print(f"✅ Upload successful!")
            print(f"   Thread ID: {thread_id}")
            
            # Check the extracted items
            items = state.get('items', [])
            totals = state.get('totals')
            
            if items:
                print(f"\n🔍 **STEP 2: Vision Extraction Results**")
                print("-" * 35)
                print(f"✅ Extracted {len(items)} items:")
                
                total_cost = 0
                for i, item in enumerate(items):
                    price = float(item.get('price', 0))
                    quantity = float(item.get('quantity', 1))
                    item_total = price * quantity
                    total_cost += item_total
                    print(f"   [{i}] {item.get('name', 'Unknown')} - ${price:.2f} x {quantity} = ${item_total:.2f}")
                
                if totals:
                    print(f"\n💰 **Totals:**")
                    print(f"   Subtotal: ${totals.get('subtotal', 0)}")
                    print(f"   Tax:      ${totals.get('tax_total', 0)}")
                    print(f"   Tip:      ${totals.get('tip_total', 0)}")
                    print(f"   TOTAL:    ${totals.get('grand_total', 0)}")
                
                # Step 3: Interactive Interview
                conduct_interactive_interview(base_url, thread_id, items, totals)
            else:
                print("❌ No items were extracted from the receipt")
                
        else:
            print(f"❌ Upload failed: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"❌ Upload error: {e}")


def conduct_interactive_interview(base_url, thread_id, items, totals):
    """Handle the interactive interview process."""
    
    print(f"\n🎤 **STEP 3: Interactive Assignment Interview**")
    print("-" * 45)
    
    # Show the items again for reference
    print("📋 **Items to assign:**")
    for i, item in enumerate(items):
        price = float(item.get('price', 0))
        print(f"   [{i}] {item.get('name', 'Unknown')} - ${price:.2f}")
    
    print("\n💡 **Assignment Tips:**")
    print("   • Use exact item names or numbers: '[0] Porky Pepperoni' or 'item 0'")
    print("   • Mention sharing: 'Alice and Bob split the wine'")
    print("   • Be specific: 'Alice had the pizza, Bob had the salad'")
    print("   • For equal splits: 'We shared everything equally'\n")
    
    # Get assignment input from user
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            print(f"📝 **Please describe who ordered what** (attempt {attempt + 1}/{max_attempts}):")
            
            if attempt == 0:
                print("   Example: 'Alice had the Porky Pepperoni pizza. Bob ordered the Za Matriciana.'")
            
            assignment_text = input("   👤 Your description: ").strip()
            
            if not assignment_text:
                print("   ⚠️  Please provide an assignment description\n")
                continue
            
            # Submit the assignment
            print(f"\n🤖 Processing assignment...")
            
            interview_payload = {
                "free_form_assignment": assignment_text
            }
            
            response = requests.post(f"{base_url}/interview/{thread_id}", json=interview_payload)
            
            if response.status_code == 200:
                result = response.json()['state']
                
                # Check if clarification is needed
                questions = result.get('pending_questions', [])
                if questions:
                    print("⚠️  **CLARIFICATION NEEDED:**")
                    for question in questions:
                        print(f"   {question}")
                    print()
                    continue  # Ask again
                else:
                    # Success! Show the results
                    show_final_results(result, items, totals)
                    return
            
            elif response.status_code == 409:
                print("⚠️  Thread state error. This might be a duplicate assignment.")
                break
            else:
                print(f"❌ Assignment failed: {response.status_code}")
                print(response.text)
                break
                
        except KeyboardInterrupt:
            print("\n\n👋 Assignment cancelled by user")
            return
        except Exception as e:
            print(f"❌ Error: {e}")
            break
    
    print(f"\n❌ Could not complete assignment after {max_attempts} attempts")


def show_final_results(result, items, totals):
    """Display the final assignment results and cost breakdown."""
    
    print("\n🎉 **STEP 4: ASSIGNMENT COMPLETE!**")
    print("=" * 40)
    
    participants = result.get('participants', [])
    assignments = result.get('assignments', [])
    
    print(f"👥 **Participants:** {', '.join(participants)}")
    
    # Calculate what each person owes
    participant_totals = {p: 0.0 for p in participants}
    
    print(f"\n📊 **Detailed Assignment:**")
    print("-" * 25)
    
    for assignment in assignments:
        item_idx = assignment['item_index']
        if item_idx < len(items):
            item = items[item_idx]
            item_name = item.get('name', 'Unknown')
            item_price = float(item.get('price', 0))
            
            print(f"\n[{item_idx}] {item_name} - ${item_price:.2f}")
            
            for share in assignment['shares']:
                participant = share['participant']
                fraction = float(share['fraction'])
                amount = item_price * fraction
                participant_totals[participant] += amount
                
                if fraction > 0:
                    print(f"    → {participant}: {fraction*100:.1f}% = ${amount:.2f}")
    
    # Show final cost breakdown
    print(f"\n💸 **FINAL COST BREAKDOWN:**")
    print("=" * 30)
    
    total_assigned = sum(participant_totals.values())
    
    for participant in participants:
        amount = participant_totals[participant]
        print(f"   {participant:20} ${amount:8.2f}")
    
    print(f"   {'-'*20} {'-'*8}")
    print(f"   {'TOTAL':20} ${total_assigned:8.2f}")
    
    if totals:
        receipt_total = float(totals.get('grand_total', 0))
        if abs(total_assigned - receipt_total) < 0.01:
            print(f"   ✅ Matches receipt total: ${receipt_total:.2f}")
        else:
            print(f"   ⚠️  Receipt total: ${receipt_total:.2f} (difference: ${abs(total_assigned - receipt_total):.2f})")
    
    print(f"\n🎊 **Receipt splitting complete!** 🎊")
    print("Each person now knows exactly what they owe.")


if __name__ == "__main__":
    main()