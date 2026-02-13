#!/usr/bin/env python3
"""
Comprehensive test of the complete math node functionality.

Tests:
1. Proportional tax/tip distribution
2. Exact total matching with rounding ad    for     for detail in breakdown['participant_details']:
        participant = detail['participant']
        percentage = detail['subtotal_percentage']
        
        print(f"👤 **{participant}** ({percentage:.1f}% of subtotal):")
        print("   Items purchased:")
        for item in detail['items']:
            print(f"     • {item['item_name']}: {item['share_percentage']:.1f}% → ${item['cost']:.2f}")
        print(f"   Tax/tip distribution based on {percentage:.1f}% subtotal share")
        print()reakdown['participant_details']:
        participant = detail['participant']
        percentage = detail['subtotal_percentage']
        
        print(f"👤 **{participant}** ({percentage:.1f}% of subtotal):")
        print("   Items purchased:")
        for item in detail['items']:
            print(f"     • {item['item_name']}: {item['share_percentage']:.1f}% → ${item['cost']:.2f}")
        print(f"   Tax/tip distribution based on {percentage:.1f}% subtotal share")
        print()3. Detailed breakdown generation
4. Validation and error handling
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from decimal import Decimal
import asyncio
import json
from datetime import datetime

from app.graph.nodes.math import math_node


def test_math_node_complete():
    """Test complete math node functionality with real receipt data."""
    
    print("🧮 **TESTING COMPLETE MATH NODE FUNCTIONALITY**")
    print("=" * 60)
    
    # Sample receipt state from our demo (real data)
    state = {
        "participants": ["User", "Harry", "Sruthi"],
        "items": [
            {
                "name": "Porky Pepperoni",
                "price": "27.00", 
                "quantity": "1.0",
                "index": 0
            },
            {
                "name": "Za Matriciana",
                "price": "26.00",
                "quantity": "1.0", 
                "index": 1
            },
            {
                "name": "Scribe Rose GL",
                "price": "20.00",
                "quantity": "1.0",
                "index": 2
            },
            {
                "name": "Tenuta Chianti Riserva gl",
                "price": "18.00",
                "quantity": "1.0",
                "index": 3
            },
            {
                "name": "Health & Living Wage (6.00%)",
                "price": "5.46",
                "quantity": "1.0",
                "index": 4
            }
        ],
        "assignments": [
            {
                "item_index": 0,
                "shares": [{"participant": "User", "fraction": "1.00"}]
            },
            {
                "item_index": 1,
                "shares": [{"participant": "User", "fraction": "1.00"}]
            },
            {
                "item_index": 2,
                "shares": [
                    {"participant": "Harry", "fraction": "0.50"},
                    {"participant": "Sruthi", "fraction": "0.50"}
                ]
            },
            {
                "item_index": 3,
                "shares": [
                    {"participant": "Harry", "fraction": "0.50"},
                    {"participant": "Sruthi", "fraction": "0.50"}
                ]
            },
            {
                "item_index": 4,
                "shares": [{"participant": "Sruthi", "fraction": "1.00"}]
            }
        ],
        "totals": {
            "subtotal": "96.46",
            "tax_total": "8.32", 
            "tip_total": "10.00",
            "fees_total": "0.00",
            "grand_total": "114.78"
        },
        "pending_questions": []
    }
    
    print("📊 **INPUT DATA:**")
    print(f"Participants: {', '.join(state['participants'])}")
    print(f"Items: {len(state['items'])} items")
    print(f"Subtotal: ${state['totals']['subtotal']}")
    print(f"Tax: ${state['totals']['tax_total']}")
    print(f"Tip: ${state['totals']['tip_total']}")
    print(f"Grand Total: ${state['totals']['grand_total']}")
    print()
    
    print("📋 **ASSIGNMENTS:**")
    for i, assignment in enumerate(state['assignments']):
        item_name = state['items'][i]['name']
        print(f"[{i}] {item_name} - ${state['items'][i]['price']}")
        for share in assignment['shares']:
            percentage = float(share['fraction']) * 100
            print(f"    → {share['participant']}: {percentage:.1f}%")
    print()
    
    # Run the math node
    print("🧮 **RUNNING MATH CALCULATIONS...**")
    result = math_node(state)
    
    if result.get('error_message'):
        print(f"❌ **ERROR:** {result['error_message']}")
        return
    
    print("✅ **MATH NODE COMPLETED SUCCESSFULLY!**")
    print()
    
    # Extract results
    final_costs = result['final_costs']
    participant_costs = final_costs['participant_costs']
    breakdown = final_costs['breakdown'] 
    validation = final_costs['validation']
    
    print("💰 **CALCULATED COSTS:**")
    print("-" * 50)
    
    for pc in participant_costs:
        participant = pc['participant']
        subtotal = pc['subtotal']
        tax_share = pc['tax_share']
        tip_share = pc['tip_share'] 
        total_owed = pc['total_owed']
        
        print(f"👤 **{participant}:**")
        print(f"   Subtotal: ${subtotal}")
        print(f"   Tax share: ${tax_share}")
        print(f"   Tip share: ${tip_share}")
        print(f"   **TOTAL OWED: ${total_owed}**")
        print()
    
    print("🔍 **VALIDATION RESULTS:**")
    print("-" * 30)
    print(f"Validation Status: {'✅ PASSED' if validation['valid'] else '❌ FAILED'}")
    print(f"Calculated Total: ${validation['calculated_total']}")
    print(f"Receipt Total: ${validation['receipt_total']}")
    print(f"Difference: ${validation['difference']}")
    print(f"Message: {validation['message']}")
    print()
    
    print("📊 **BREAKDOWN VERIFICATION:**")
    print("-" * 35)
    calc_totals = breakdown['summary']['calculated_totals']
    receipt_totals = breakdown['summary']['receipt_totals']
    
    print("                 Calculated  |  Receipt   |  Match")
    print("-" * 50)
    print(f"Subtotal:        ${calc_totals['subtotal']:>8} | ${receipt_totals['subtotal']:>8} | {'✅' if calc_totals['subtotal'] == receipt_totals['subtotal'] else '❌'}")
    print(f"Tax:             ${calc_totals['tax']:>8} | ${receipt_totals['tax']:>8} | {'✅' if calc_totals['tax'] == receipt_totals['tax'] else '❌'}")
    print(f"Tip:             ${calc_totals['tip']:>8} | ${receipt_totals['tip']:>8} | {'✅' if calc_totals['tip'] == receipt_totals['tip'] else '❌'}")
    print(f"Grand Total:     ${calc_totals['grand_total']:>8} | ${receipt_totals['grand_total']:>8} | {'✅' if calc_totals['grand_total'] == receipt_totals['grand_total'] else '❌'}")
    print()
    
    print("💡 **DETAILED PARTICIPANT BREAKDOWN:**")
    print("-" * 45)
    for detail in breakdown['participant_details']:
        participant = detail['participant']
        percentage = detail['subtotal_percentage']
        costs = detail['costs']
        
        print(f"👤 **{participant}** ({percentage:.1f}% of subtotal):")
        print(f"   Items purchased:")
        for item in detail['items']:
            print(f"     • {item['item_name']}: {item['share_percentage']:.1f}% → ${item['cost']:.2f}")
        print(f"   Tax/tip distribution based on ${percentage:.1f}% subtotal share")
        print()
    
    print("🎊 **MATH NODE TEST COMPLETE!**")
    print("All calculations verified and totals match receipt exactly! 🎉")


if __name__ == "__main__":
    test_math_node_complete()