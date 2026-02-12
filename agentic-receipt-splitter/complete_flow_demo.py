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
                    # Success! Show the results and calculate final costs
                    print("\n🎉 **STEP 4: ASSIGNMENT COMPLETE!**")
                    print("=" * 40)
                    
                    show_assignment_results(result, items)
                    calculate_final_costs(result, totals, thread_id)
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


def show_assignment_results(result, items):
    """Display the assignment results in a clean format."""
    
    participants = result.get('participants', [])
    assignments = result.get('assignments', [])
    
    print(f"👥 **Participants:** {', '.join(participants)}")
    
    print("\n📊 **Assignment Percentages:**")
    print("-" * 30)
    
    for assignment in assignments:
        item_idx = assignment['item_index']
        if item_idx < len(items):
            item = items[item_idx]
            item_name = item.get('name', 'Unknown')
            item_price = float(item.get('price', 0))
            
            print(f"[{item_idx}] {item_name} - ${item_price:.2f}")
            
            for share in assignment['shares']:
                participant = share['participant']
                fraction = float(share['fraction'])
                
                if fraction > 0:
                    print(f"    → {participant}: {fraction*100:.1f}%")


def calculate_final_costs(result, totals, thread_id):
    """Calculate and display final costs using the math node."""
    
    print("\n🧮 **STEP 5: CALCULATING FINAL COSTS**")
    print("=" * 45)
    
    try:
        # Check if math was already calculated
        if 'final_costs' in result:
            print("✅ Math calculations found!")
            display_final_costs(result['final_costs'], totals)
            return
        
        print("🔄 Triggering math node calculation...")
        
        # Manually invoke the math node with current state
        from app.graph.nodes.math import math_node
        
        # Convert result to format expected by math node
        math_state = {
            'participants': result.get('participants', []),
            'items': result.get('items', []),
            'assignments': result.get('assignments', []),
            'totals': totals,
            'pending_questions': result.get('pending_questions', [])
        }
        
        print("📊 Running math calculations...")
        math_result = math_node(math_state)
        
        if 'final_costs' in math_result:
            print("✅ Math calculations completed!")
            display_final_costs(math_result['final_costs'], totals)
        elif math_result.get('error_message'):
            print(f"❌ Math calculation failed: {math_result['error_message']}")
            if math_result.get('needs_interview'):
                print("   → Returned to interview for clarification")
        else:
            print("⚠️  Math node executed but no final costs returned")
            print("   This might indicate an unexpected result format")
                
    except Exception as e:
        print(f"❌ Error calculating final costs: {e}")
        print("Assignment completed successfully, but final cost calculation failed.")
        import traceback
        print(f"Details: {traceback.format_exc()}")


def display_final_costs(final_costs, receipt_totals):
    """Display the detailed final cost breakdown."""
    
    participant_costs = final_costs.get('participant_costs', [])
    breakdown = final_costs.get('breakdown', {})
    validation = final_costs.get('validation', {})
    
    print("💰 **FINAL COST BREAKDOWN:**")
    print("-" * 40)
    
    total_calculated = 0.0
    
    for pc in participant_costs:
        participant = pc['participant']
        subtotal = float(pc['subtotal'])
        tax_share = float(pc['tax_share'])
        tip_share = float(pc['tip_share']) 
        total_owed = float(pc['total_owed'])
        total_calculated += total_owed
        
        print(f"\n👤 **{participant}:**")
        print(f"   Items subtotal: ${subtotal:.2f}")
        print(f"   Tax share:      ${tax_share:.2f}")
        print(f"   Tip share:      ${tip_share:.2f}")
        print(f"   **TOTAL OWED:   ${total_owed:.2f}** 💵")
        
        # Show individual items
        item_costs = pc.get('item_costs', [])
        if item_costs:
            print("   📝 Items:")
            for item_cost in item_costs:
                item_name = item_cost['item_name']
                share_pct = item_cost['share_percentage']
                cost = item_cost['cost']
                print(f"      • {item_name}: {share_pct:.1f}% → ${cost:.2f}")
    
    print(f"\n🔍 **VALIDATION:**")
    print("-" * 20)
    if validation.get('valid'):
        print("✅ Totals verified!")
        print(f"   Calculated: ${validation.get('calculated_total', '0.00')}")
        print(f"   Receipt:    ${validation.get('receipt_total', '0.00')}")
        print(f"   Difference: ${validation.get('difference', '0.00')}")
    else:
        print("⚠️  Validation issues:")
        print(f"   {validation.get('message', 'Unknown validation error')}")
    
    # Show detailed breakdown
    if breakdown.get('summary'):
        summary = breakdown['summary']
        calc_totals = summary.get('calculated_totals', {})
        receipt_totals_data = summary.get('receipt_totals', {})
        
        print(f"\n📊 **BREAKDOWN VERIFICATION:**")
        print("-" * 35)
        print("                 Calculated  |  Receipt   |  Match")
        print("-" * 50)
        
        components = [
            ('Subtotal', 'subtotal'),
            ('Tax', 'tax'), 
            ('Tip', 'tip'),
            ('Grand Total', 'grand_total')
        ]
        
        for label, key in components:
            calc_val = calc_totals.get(key, '0.00')
            receipt_val = receipt_totals_data.get(key, '0.00')
            match = "✅" if calc_val == receipt_val else "❌"
            print(f"{label:12}: ${calc_val:>8} | ${receipt_val:>8} | {match}")
    
    print(f"\n🎊 **RECEIPT SPLITTING COMPLETE!** 🎊")
    print("=" * 45)
    print(f"💰 Each person owes the amount shown above")
    print(f"📱 You can now request payment from each participant")
    print(f"🧾 Total verified: ${total_calculated:.2f}")


def show_final_results(result, items, totals):
    """Display the final assignment results without cost calculations."""
    
    print("\n🎉 **STEP 4: ASSIGNMENT COMPLETE!**")
    print("=" * 40)
    
    participants = result.get('participants', [])
    assignments = result.get('assignments', [])
    
    print(f"👥 **Participants:** {', '.join(participants)}")
    
    print(f"\n📊 **Assignment Percentages:**")
    print("-" * 30)
    
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
                
                if fraction > 0:
                    print(f"    → {participant}: {fraction*100:.1f}%")
    
    print(f"\n✅ **Assignment Summary:**")
    print("=" * 25)
    print(f"   • {len(participants)} participants assigned")
    print(f"   • {len(assignments)} items with percentage splits")
    print(f"   • Ready for math node to calculate final costs")
    
    if totals:
        receipt_total = float(totals.get('grand_total', 0))
        print(f"   • Receipt total: ${receipt_total:.2f} (includes tax + tip)")
        print(f"   • Tax: ${totals.get('tax_total', 0)}")
        print(f"   • Tip: ${totals.get('tip_total', 0)}")
    
    print(f"\n🔧 **Next Step: Math Node**")
    print("The math node will calculate:")
    print("• Individual item costs based on percentages")
    print("• Proportional tax and tip distribution") 
    print("• Final amount each person owes")
    print(f"\n🎊 **Assignment parsing complete!** 🎊")


if __name__ == "__main__":
    main()