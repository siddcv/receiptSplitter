#!/usr/bin/env python3
"""
Enhanced End-to-End Receipt Splitter Demo with Step-by-Step Interview

This script demonstrates the improved workflow:
1. Upload receipt image via API  
2. Extract text using Gemini Vision API
3. Step-by-step interview process:
   - First: Collect participants 
   - Second: Assign items to participants
4. Display final results with cost breakdown
"""

import requests
import json
import time
import os
from pathlib import Path


class StepByStepReceiptDemo:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url
        self.thread_id = None
        
    def check_server(self):
        """Check if the server is running."""
        try:
            response = requests.get(f"{self.base_url}/")
            if response.status_code == 200:
                print("✅ Server is running")
                return True
            else:
                print(f"❌ Server responded with {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ Could not connect to server")
            print("Please start the server with: uvicorn app.main:app --reload")
            return False
    
    def upload_receipt(self, image_path):
        """Upload receipt image and extract text."""
        print(f"\n📤 **STEP 1: Uploading Receipt**")
        print("=" * 40)
        
        if not Path(image_path).exists():
            print(f"❌ Image file not found: {image_path}")
            return False
        
        try:
            with open(image_path, 'rb') as f:
                files = {'file': (Path(image_path).name, f, 'image/jpeg')}
                response = requests.post(f"{self.base_url}/upload", files=files)
            
            if response.status_code == 200:
                result = response.json()
                self.thread_id = result.get("thread_id")
                state = result.get("state", {})
                
                print(f"✅ Upload successful!")
                print(f"Thread ID: {self.thread_id}")
                
                # Display extracted items
                items = state.get("items", [])
                totals = state.get("totals", {})
                
                if items:
                    print(f"\n🧾 **Extracted Items:**")
                    for i, item in enumerate(items):
                        name = item.get("name", "Unknown")
                        price = item.get("price", item.get("unit_price", "0.00"))
                        print(f"  [{i}] {name} - ${price}")
                
                if totals:
                    grand_total = totals.get("grand_total", 0)
                    print(f"\n💰 **Total: ${grand_total}**")
                
                return True
            else:
                print(f"❌ Upload failed: {response.status_code}")
                print(response.text)
                return False
                
        except Exception as e:
            print(f"❌ Upload error: {e}")
            return False
    
    def collect_participants(self):
        """Step 2: Collect participants interactively."""
        print(f"\n👥 **STEP 2: Collect Participants**")
        print("=" * 40)
        
        # Get current state to show the participant question
        try:
            response = requests.get(f"{self.base_url}/state/{self.thread_id}")
            if response.status_code != 200:
                print(f"❌ Could not get state: {response.status_code}")
                return False
            
            state = response.json()
            questions = state.get("pending_questions", [])
            if questions:
                print(questions[0])
            
            # Get participant input from user
            while True:
                participant_input = input("\n👤 Enter participant names (comma-separated): ").strip()
                
                if not participant_input:
                    print("⚠️  Please enter at least one participant name.")
                    continue
                
                if participant_input.lower() in ['quit', 'exit']:
                    print("👋 Demo cancelled.")
                    return False
                
                # Submit participants
                payload = {"participant_input": participant_input}
                response = requests.post(f"{self.base_url}/interview/{self.thread_id}", json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    new_state = result.get("state", {})
                    participants = new_state.get("participants", [])
                    
                    if participants:
                        print(f"✅ Participants added: {', '.join(participants)}")
                        return True
                    else:
                        questions = new_state.get("pending_questions", [])
                        if questions:
                            print(f"⚠️  {questions[0]}")
                            continue
                else:
                    print(f"❌ Error: {response.status_code}")
                    print(response.text)
                    return False
                    
        except Exception as e:
            print(f"❌ Error collecting participants: {e}")
            return False
    
    def assign_items(self):
        """Step 3: Assign items to participants."""
        print(f"\n📝 **STEP 3: Assign Items**")
        print("=" * 30)
        
        # Get current state to show assignment question
        try:
            response = requests.get(f"{self.base_url}/state/{self.thread_id}")
            if response.status_code != 200:
                print(f"❌ Could not get state: {response.status_code}")
                return False
            
            state = response.json()
            questions = state.get("pending_questions", [])
            if questions:
                print(questions[0])
            
            # Get assignment input from user
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                print(f"\n📋 **Assignment Attempt {attempt}/{max_attempts}:**")
                assignment_input = input("👤 Enter your assignment: ").strip()
                
                if not assignment_input:
                    print("⚠️  Please provide an assignment description.")
                    continue
                
                if assignment_input.lower() in ['quit', 'exit']:
                    print("👋 Demo cancelled.")
                    return False
                
                # Submit assignment
                payload = {"assignment_input": assignment_input}
                response = requests.post(f"{self.base_url}/interview/{self.thread_id}", json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    new_state = result.get("state", {})
                    questions = new_state.get("pending_questions", [])
                    
                    if not questions:  # No more questions = success
                        print("✅ Assignment successful!")
                        return True
                    else:  # Need clarification
                        print(f"\n⚠️  **Clarification needed:**")
                        print(questions[0])
                        print(f"\nPlease try again with more specific details.")
                else:
                    print(f"❌ Assignment error: {response.status_code}")
                    if attempt < max_attempts:
                        print("Please try again with a different format.")
                    
            print(f"❌ Could not complete assignment after {max_attempts} attempts")
            return False
                    
        except Exception as e:
            print(f"❌ Error in assignment: {e}")
            return False
    
    def show_final_results(self):
        """Display the final assignment results."""
        print(f"\n🎉 **FINAL RESULTS**")
        print("=" * 30)
        
        try:
            response = requests.get(f"{self.base_url}/state/{self.thread_id}")
            if response.status_code != 200:
                print("❌ Could not get final state")
                return False
            
            state = response.json()
            participants = state.get("participants", [])
            assignments = state.get("assignments", [])
            items = state.get("items", [])
            totals = state.get("totals", {})
            
            print(f"👥 **Participants:** {', '.join(participants)}")
            
            print(f"\n📋 **Item Assignments:**")
            participant_totals = {p: 0.0 for p in participants}
            
            for assignment in assignments:
                item_idx = assignment.get("item_index")
                shares = assignment.get("shares", [])
                
                if item_idx < len(items):
                    item = items[item_idx]
                    item_name = item.get("name", f"Item {item_idx}")
                    item_price = float(item.get("price", item.get("unit_price", 0)))
                    
                    print(f"\n  [{item_idx}] {item_name} (${item_price:.2f}):")
                    for share in shares:
                        participant = share.get("participant")
                        fraction = float(share.get("fraction", 0))
                        percentage = fraction * 100
                        amount = item_price * fraction
                        
                        if fraction > 0:
                            print(f"    • {participant}: {percentage:.1f}% = ${amount:.2f}")
                            participant_totals[participant] += amount
            
            print(f"\n💰 **Cost Breakdown:**")
            grand_total = float(totals.get("grand_total", 0))
            total_assigned = sum(participant_totals.values())
            
            for participant in participants:
                amount = participant_totals[participant]
                percentage = (amount / grand_total * 100) if grand_total > 0 else 0
                print(f"  {participant}: ${amount:.2f} ({percentage:.1f}%)")
            
            print(f"\n📊 **Summary:**")
            print(f"  Total Receipt: ${grand_total:.2f}")
            print(f"  Total Assigned: ${total_assigned:.2f}")
            
            if abs(total_assigned - grand_total) <= 0.01:
                print(f"  ✅ Perfect match!")
            else:
                print(f"  ⚠️  Difference: ${abs(total_assigned - grand_total):.2f}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error showing results: {e}")
            return False
    
    def run_full_demo(self, image_path):
        """Run the complete step-by-step demo."""
        print("🍕 **STEP-BY-STEP RECEIPT SPLITTER**")
        print("=" * 45)
        print("Enhanced workflow:")
        print("  1. Upload receipt image")
        print("  2. Collect participants")  
        print("  3. Assign items")
        print("  4. Show final breakdown")
        
        # Step 1: Check server and upload
        if not self.check_server():
            return False
        
        if not self.upload_receipt(image_path):
            return False
        
        # Wait for processing
        print(f"\n⏰ Processing receipt...")
        time.sleep(2)
        
        # Step 2: Collect participants
        if not self.collect_participants():
            return False
        
        # Step 3: Assign items
        if not self.assign_items():
            return False
        
        # Step 4: Show results
        if not self.show_final_results():
            return False
        
        print(f"\n🎉 **DEMO COMPLETE!**")
        print("Receipt successfully processed and split!")
        return True


def main():
    # Find the receipt image
    script_dir = Path(__file__).parent
    uploads_dir = script_dir / "uploads"
    
    receipt_images = list(uploads_dir.glob("*.jpg")) + list(uploads_dir.glob("*.jpeg"))
    
    if not receipt_images:
        print("❌ No receipt images found in uploads/ folder")
        print("Please run extract_receipt.py first or add a receipt image")
        return
    
    receipt_path = receipt_images[0]
    
    # Run the demo
    demo = StepByStepReceiptDemo()
    demo.run_full_demo(str(receipt_path))


if __name__ == "__main__":
    main()