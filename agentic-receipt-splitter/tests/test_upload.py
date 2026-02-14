"""
Quick smoke test: upload a receipt image to the running FastAPI server
and print the extracted items + totals from the vision node.

Usage:
    python tests/test_upload.py <path_to_receipt_image>

Example:
    python tests/test_upload.py uploads/sample_receipt.jpg

Requires: pip install httpx  (already in requirements.txt)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"


def upload(image_path: str) -> dict:
    path = Path(image_path)
    if not path.exists():
        print(f"ERROR: file not found: {image_path}")
        sys.exit(1)

    # Guess MIME type from extension
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    mime = mime_map.get(path.suffix.lower(), "image/jpeg")

    with open(path, "rb") as f:
        files = {"file": (path.name, f, mime)}
        print(f"Uploading {path.name} ({mime}) to {BASE_URL}/upload ...")
        resp = httpx.post(f"{BASE_URL}/upload", files=files, timeout=120.0)

    resp.raise_for_status()
    return resp.json()


def main():
    if len(sys.argv) < 2:
        print("Usage: python tests/test_upload.py <path_to_receipt_image>")
        sys.exit(1)

    result = upload(sys.argv[1])
    print("\n=== RESPONSE ===")
    print(json.dumps(result, indent=2, default=str))

    # Pretty-print extracted items
    state = result.get("state", {})
    items = state.get("items", [])
    totals = state.get("totals")
    questions = state.get("pending_questions", [])

    print(f"\n--- Extracted {len(items)} item(s) ---")
    for i, item in enumerate(items):
        print(f"  {i+1}. {item['name']:30s}  qty={item['quantity']}  price=${item['price']}")
        if item.get("confidence"):
            low = {k: v for k, v in item["confidence"].items() if v < 0.8}
            if low:
                print(f"     ⚠ low confidence: {low}")

    if totals:
        print("\n--- Totals ---")
        print(f"  Subtotal:    ${totals['subtotal']}")
        print(f"  Tax:         ${totals['tax_total']}")
        print(f"  Tip:         ${totals['tip_total']}")
        print(f"  Fees:        ${totals['fees_total']}")
        print(f"  Grand Total: ${totals['grand_total']}")

    if questions:
        print(f"\n--- {len(questions)} question(s) flagged for review ---")
        for q in questions:
            print(f"  ❓ {q}")

    print(f"\nthread_id: {result.get('thread_id')}")


if __name__ == "__main__":
    main()
