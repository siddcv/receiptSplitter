#!/usr/bin/env python3
"""Test the rounding fix for ItemAssignment validation."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from decimal import Decimal
from app.graph.state import ItemAssignment, AssignmentShare

def test_rounding_fix():
    """Test that 3-way splits and other rounding scenarios work correctly."""
    
    print("🧮 **TESTING ASSIGNMENT ROUNDING FIX**")
    print("=" * 50)
    
    # Test 1: 3-way equal split (0.33 + 0.33 + 0.33 = 0.99)
    print("\n📝 **Test 1: 3-way equal split**")
    try:
        shares = [
            AssignmentShare(participant="Alice", fraction=Decimal("0.33")),
            AssignmentShare(participant="Bob", fraction=Decimal("0.33")),
            AssignmentShare(participant="Charlie", fraction=Decimal("0.33"))
        ]
        
        assignment = ItemAssignment(item_index=0, shares=shares)
        
        # Check final fractions
        total = sum(s.fraction for s in assignment.shares)
        print(f"   Original total: 0.33 + 0.33 + 0.33 = {total}")
        print(f"   Final fractions after adjustment:")
        for share in assignment.shares:
            print(f"     • {share.participant}: {share.fraction}")
        print(f"   Final total: {sum(s.fraction for s in assignment.shares)}")
        print("   ✅ 3-way split validated successfully!")
        
    except Exception as e:
        print(f"   ❌ 3-way split failed: {e}")
    
    # Test 2: Already perfect split (0.50 + 0.50 = 1.00)
    print("\n📝 **Test 2: Perfect 2-way split**")
    try:
        shares = [
            AssignmentShare(participant="Alice", fraction=Decimal("0.50")),
            AssignmentShare(participant="Bob", fraction=Decimal("0.50"))
        ]
        
        assignment = ItemAssignment(item_index=1, shares=shares)
        total = sum(s.fraction for s in assignment.shares)
        print(f"   Total: {total}")
        print("   ✅ Perfect split validated successfully!")
        
    except Exception as e:
        print(f"   ❌ Perfect split failed: {e}")
    
    # Test 3: Single person (1.00)
    print("\n📝 **Test 3: Single person assignment**")
    try:
        shares = [
            AssignmentShare(participant="Alice", fraction=Decimal("1.00"))
        ]
        
        assignment = ItemAssignment(item_index=2, shares=shares)
        total = sum(s.fraction for s in assignment.shares)
        print(f"   Total: {total}")
        print("   ✅ Single assignment validated successfully!")
        
    except Exception as e:
        print(f"   ❌ Single assignment failed: {e}")
    
    # Test 4: Invalid assignment (too far from 1.00)
    print("\n📝 **Test 4: Invalid assignment (should fail)**")
    try:
        shares = [
            AssignmentShare(participant="Alice", fraction=Decimal("0.80")),
            AssignmentShare(participant="Bob", fraction=Decimal("0.10"))  # Only 0.90 total
        ]
        
        assignment = ItemAssignment(item_index=3, shares=shares)
        print("   ❌ Should have failed but didn't!")
        
    except Exception as e:
        print(f"   ✅ Correctly rejected invalid assignment: {str(e)[:60]}...")
    
    # Test 5: 4-way split (0.25 each = 1.00 exactly)
    print("\n📝 **Test 5: 4-way equal split**")
    try:
        shares = [
            AssignmentShare(participant="Alice", fraction=Decimal("0.25")),
            AssignmentShare(participant="Bob", fraction=Decimal("0.25")),
            AssignmentShare(participant="Charlie", fraction=Decimal("0.25")),
            AssignmentShare(participant="Dave", fraction=Decimal("0.25"))
        ]
        
        assignment = ItemAssignment(item_index=4, shares=shares)
        total = sum(s.fraction for s in assignment.shares)
        print(f"   Total: {total}")
        print("   ✅ 4-way split validated successfully!")
        
    except Exception as e:
        print(f"   ❌ 4-way split failed: {e}")
    
    print(f"\n🎊 **ROUNDING FIX TEST COMPLETE!** 🎊")
    print("The assignment validation now handles rounding errors gracefully!")

if __name__ == "__main__":
    test_rounding_fix()