#!/usr/bin/env python3
"""
Script to extract text from receipt images using the existing vision prompt and Gemini API.

This script leverages the existing vision.py module to extract structured data
from the receipt image in the uploads folder.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the app directory to the Python path
import sys
sys.path.append(str(Path(__file__).parent))

from app.graph.nodes.vision import _call_vision_model, _parse_items, _parse_totals


def main():
    # Get the uploads directory
    uploads_dir = Path(__file__).parent / "uploads"
    
    # Find receipt images in uploads folder
    receipt_files = list(uploads_dir.glob("*.jpg")) + list(uploads_dir.glob("*.jpeg")) + list(uploads_dir.glob("*.png"))
    
    if not receipt_files:
        print("No receipt images found in uploads folder!")
        return
    
    for receipt_path in receipt_files:
        print(f"\n🧾 Processing receipt: {receipt_path.name}")
        print("=" * 50)
        
        try:
            # Use the existing vision model to extract data
            raw_data = _call_vision_model(str(receipt_path))
            
            # Parse the raw data using existing parsers
            raw_items = raw_data.get("items", [])
            items = _parse_items(raw_items)
            
            raw_totals = raw_data.get("totals", {})
            totals_confidence = raw_totals.pop("confidence", None) if "confidence" in raw_totals else None
            
            try:
                totals = _parse_totals(raw_totals)
            except Exception as e:
                print(f"⚠️  Warning: Could not parse totals - {e}")
                totals = None
            
            # Display extracted information
            print("\n📋 EXTRACTED ITEMS:")
            print("-" * 30)
            for i, item in enumerate(items, 1):
                confidence_str = ""
                if item.confidence:
                    conf_values = [f"{k}: {v:.1%}" for k, v in item.confidence.items()]
                    confidence_str = f" (Confidence: {', '.join(conf_values)})"
                
                print(f"{i:2d}. {item.name}")
                print(f"    Qty: {item.quantity} × ${item.price} = ${item.quantity * item.price}{confidence_str}")
            
            if totals:
                print("\n💰 TOTALS:")
                print("-" * 20)
                print(f"Subtotal: ${totals.subtotal}")
                print(f"Tax:      ${totals.tax_total}")
                print(f"Tip:      ${totals.tip_total}")
                print(f"Fees:     ${totals.fees_total}")
                print(f"TOTAL:    ${totals.grand_total}")
                
                if totals_confidence:
                    print("\nTotals Confidence:")
                    for field, confidence in totals_confidence.items():
                        print(f"  {field}: {confidence:.1%}")
            
            # Save raw JSON for inspection
            output_file = receipt_path.with_suffix('.json')
            with open(output_file, 'w') as f:
                json.dump(raw_data, f, indent=2, default=str)
            print(f"\n📄 Raw JSON saved to: {output_file}")
            
        except Exception as e:
            print(f"❌ Error processing {receipt_path.name}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    # Check if API key is set
    if not os.getenv("GOOGLE_API_KEY"):
        print("❌ Error: GOOGLE_API_KEY not found in environment!")
        print("Please set your Google API key in the .env file")
        exit(1)
    
    main()