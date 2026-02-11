"""
Interview node: processes participant assignments via natural language or structured input.

This is a human-in-the-loop node that operates in two phases:

Phase 1 (automatic, runs after vision):
  - Reads the extracted items from state.
  - Sets pending_questions with a structured prompt listing items
    so the frontend can present an assignment UI.
  - Sets current_node = "interview_pending" to signal the frontend.

Phase 2 (triggered by POST /interview/{thread_id}):
  - Receives FREE-FORM TEXT describing who ordered what items
  - Uses Gemini LLM to parse natural language and extract participants/assignments
  - Handles synonyms, complex sharing scenarios, and natural language variations
  - Validates the assignments (shares must sum to 1.00 per item, participants
    must exist, item indices must be valid).
  - Populates state.participants and state.assignments.
  - Clears pending_questions and advances the graph.

Uses Gemini 2.0 Flash for natural language understanding with minimal API cost.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.graph.state import (
    AssignmentShare,
    AuditEvent,
    ItemAssignment,
    ReceiptState,
)

load_dotenv(override=False)

logger = logging.getLogger(__name__)

TWO_DP = Decimal("0.01")


def _get_interview_model() -> ChatGoogleGenerativeAI:
    """Get Gemini model for interview processing with fallback."""
    model_name = os.getenv("INTERVIEW_MODEL", "models/gemini-2.5-flash")
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set in environment/.env")

    max_retries = int(os.getenv("INTERVIEW_MAX_RETRIES", "2"))

    # Try the specified model first
    try:
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0.0,
            max_retries=max_retries,
        )
    except Exception as e:
        logger.warning(f"Failed to create interview model {model_name}: {e}")
        
        # Try fallback models
        fallback_models = [
            "models/gemini-2.5-flash",
            "models/gemini-2.0-flash", 
            "models/gemini-2.5-pro"
        ]
        
        for fallback_model in fallback_models:
            if fallback_model == model_name:
                continue  # Skip the one we already tried
            try:
                logger.info(f"Trying fallback interview model: {fallback_model}")
                return ChatGoogleGenerativeAI(
                    model=fallback_model,
                    google_api_key=api_key,
                    temperature=0.0,
                    max_retries=max_retries,
                )
            except Exception as fallback_e:
                logger.warning(f"Fallback model {fallback_model} also failed: {fallback_e}")
        
        # If all models fail, raise the original error
        raise RuntimeError(f"All interview models failed. Last error: {e}")


def _generate_participant_questions(items: List) -> List[str]:
    """Generate questions to collect participants for the bill."""
    
    item_summary = []
    for i, item in enumerate(items):
        if hasattr(item, 'name'):  # Pydantic Item object
            name = item.name
            price = item.price
        else:  # Plain dict
            name = item.get("name", "Unknown")
            price = item.get("price", "0.00")
        item_summary.append(f"  [{i}] {name} - ${price}")
    
    question = (
        "🧾 **Receipt Items:**\n"
        + "\n".join(item_summary)
        + "\n\n"
        "👥 **Step 1: Who was part of this bill?**\n"
        "Please enter the names of everyone who shared this meal/bill.\n\n"
        "📝 **Enter names separated by commas:**\n"
        "Example: 'Alice, Bob, Charlie' or 'Me, Sarah, John'\n\n"
        "💡 Tip: Use simple first names or nicknames for easier assignment later."
    )
    
    return [question]


def _generate_assignment_questions(items: List, participants: List[str]) -> List[str]:
    """Generate questions for assigning items to participants."""
    
    item_summary = []
    for i, item in enumerate(items):
        if hasattr(item, 'name'):  # Pydantic Item object
            name = item.name
            price = item.price
        else:  # Plain dict
            name = item.get("name", "Unknown")
            price = item.get("price", "0.00")
        item_summary.append(f"  [{i}] {name} - ${price}")
    
    participant_list = ", ".join(participants)
    
    question = (
        f"👥 **Participants:** {participant_list}\n\n"
        "🧾 **Items to assign:**\n"
        + "\n".join(item_summary)
        + "\n\n"
        "📝 **Step 2: How should we assign these items?**\n"
        "Please describe who ordered what using a simple format.\n\n"
        "💡 **Assignment Examples:**\n"
        "• 'Alice: 0, 2 | Bob: 1, 3 | Charlie: 4' (by item numbers)\n"
        "• 'Alice had the pizza. Bob got the salad. We split the appetizer.'\n"
        "• '0: Alice | 1: Bob, Charlie (split) | 2: Alice'\n\n"
        "🤝 **For shared items:** Use 'split', 'shared', or list multiple names\n"
        "📊 **For specific splits:** Add percentages like 'Alice 70%, Bob 30%'"
    )
    
    return [question]


def _process_structured_assignment(items: List, participants: List[str], assignment_input: str) -> Dict[str, Any]:
    """Process structured assignment input without complex LLM parsing."""
    
    try:
        # Simple parsing logic for common patterns
        assignments = []
        assignment_input = assignment_input.strip()
        
        # Try to parse simple patterns first
        if _is_simple_pattern(assignment_input):
            assignments = _parse_simple_assignment(items, participants, assignment_input)
        else:
            # Fallback to basic validation and user clarification
            return {
                "current_node": "interview_pending",
                "pending_questions": [
                    f"Please use a simpler format for assignments.\n\n"
                    f"Try one of these patterns:\n"
                    f"• 'Alice: 0, 1 | Bob: 2, 3' (assign items by number)\n"
                    f"• 'Alice had items 0 and 1. Bob had items 2 and 3.'\n"
                    f"• '0: Alice | 1: Bob | 2: split between Alice, Bob'\n\n"
                    f"Your input: '{assignment_input}'"
                ],
                "audit_log": [
                    AuditEvent(
                        node="interview",
                        message="Assignment format not recognized, requesting clarification",
                        timestamp=datetime.now(timezone.utc),
                    )
                ],
            }
        
        # Validate that all items are assigned
        assigned_items = set()
        for assignment in assignments:
            assigned_items.add(assignment.item_index)
        
        missing_items = []
        for i in range(len(items)):
            if i not in assigned_items:
                missing_items.append(i)
        
        if missing_items:
            item_names = []
            for i in missing_items:
                if hasattr(items[i], 'name'):
                    item_names.append(f"[{i}] {items[i].name}")
                else:
                    item_names.append(f"[{i}] {items[i].get('name', 'Unknown')}")
            
            return {
                "current_node": "interview_pending",
                "pending_questions": [
                    f"Some items are not assigned yet:\n"
                    + "\n".join(f"  • {name}" for name in item_names)
                    + "\n\nPlease assign these remaining items."
                ],
                "audit_log": [
                    AuditEvent(
                        node="interview",
                        message=f"Assignment incomplete - {len(missing_items)} items unassigned",
                        timestamp=datetime.now(timezone.utc),
                    )
                ],
            }
        
        # Success - all items assigned
        return {
            "participants": participants,
            "assignments": assignments,
            "current_node": "interview",
            "pending_questions": [],
            "audit_log": [
                AuditEvent(
                    node="interview",
                    message=f"Assignment complete - {len(participants)} participants, {len(assignments)} items",
                    timestamp=datetime.now(timezone.utc),
                    details={
                        "participant_count": len(participants),
                        "assignment_count": len(assignments),
                        "participants": participants,
                    },
                )
            ],
        }
        
    except Exception as e:
        return {
            "current_node": "interview_pending",
            "pending_questions": [
                f"Error processing assignment: {str(e)}\n"
                f"Please try a simpler format or contact support."
            ],
            "audit_log": [
                AuditEvent(
                    node="interview",
                    message=f"Assignment processing error: {str(e)}",
                    timestamp=datetime.now(timezone.utc),
                )
            ],
        }


def _is_simple_pattern(text: str) -> bool:
    """Check if the text matches simple assignment patterns."""
    text_lower = text.lower().strip()
    
    # Pattern: "Alice: 0, 1 | Bob: 2, 3" or "0,1: Alice | 2,3: Bob"
    if "|" in text and ":" in text:
        return True
    
    # Pattern: "0: Alice | 1: Bob"
    if text.count("|") > 0 and all(":" in part for part in text.split("|")):
        return True
    
    # Pattern: "Alice had items 0 and 1. Bob had items 2 and 3."
    if any(keyword in text_lower for keyword in ["had items", "got items", "had item", "got item"]):
        return True
    
    # Pattern: "alice got the pizza" with item references
    if any(keyword in text_lower for keyword in ["got", "had", "ordered"]) and any(char.isdigit() for char in text):
        return True
    
    return False


def _parse_simple_assignment(items: List, participants: List[str], assignment_input: str) -> List[ItemAssignment]:
    """Parse simple assignment patterns into ItemAssignment objects."""
    assignments = []
    assignment_lower = assignment_input.lower()
    
    # Handle "Alice: 0, 1 | Bob: 2, 3" or "0,1: Alice | 2,3: Bob" patterns
    if "|" in assignment_input:
        parts = assignment_input.split("|")
        for part in parts:
            part = part.strip()
            if ":" not in part:
                continue
                
            left_part, right_part = part.split(":", 1)
            left_part = left_part.strip()
            right_part = right_part.strip()
            
            # Determine if it's "person: items" or "items: person"
            item_numbers = []
            person_names = []
            
            # Check if left part contains numbers (items: person format)
            if any(char.isdigit() for char in left_part):
                # Parse item numbers from left side
                for item_str in left_part.replace(",", " ").split():
                    item_str = item_str.strip()
                    try:
                        item_num = int(item_str)
                        if 0 <= item_num < len(items):
                            item_numbers.append(item_num)
                    except ValueError:
                        continue
                
                # Parse person names from right side
                if "split" in right_part.lower():
                    # Extract names from split description
                    split_text = right_part.lower()
                    for participant in participants:
                        if participant.lower() in split_text:
                            person_names.append(participant)
                else:
                    # Single person assignment
                    # Match participant name (case insensitive)
                    for participant in participants:
                        if participant.lower() in right_part.lower():
                            person_names = [participant]
                            break
            else:
                # Parse person name from left side (person: items format)
                for participant in participants:
                    if participant.lower() in left_part.lower():
                        person_names = [participant]
                        break
                
                # Parse item numbers from right side
                for item_str in right_part.replace(",", " ").split():
                    item_str = item_str.strip()
                    try:
                        item_num = int(item_str)
                        if 0 <= item_num < len(items):
                            item_numbers.append(item_num)
                    except ValueError:
                        continue
            
            # Create assignments for each item
            for item_idx in item_numbers:
                if person_names:
                    # Calculate equal shares for all people
                    share_fraction = (Decimal("1.0") / len(person_names)).quantize(TWO_DP, rounding=ROUND_HALF_UP)
                    shares = [
                        AssignmentShare(participant=person, fraction=share_fraction)
                        for person in person_names
                    ]
                    
                    assignments.append(
                        ItemAssignment(
                            item_index=item_idx,
                            shares=shares
                        )
                    )
    
    # Handle natural language patterns like "Alice had items 0 and 1"
    elif any(keyword in assignment_lower for keyword in ["had items", "got items", "had item", "got item", "split"]):
        # Split by periods or "and" to get separate statements
        statements = []
        for delimiter in ['.', ';']:
            if delimiter in assignment_input:
                statements = [s.strip() for s in assignment_input.split(delimiter) if s.strip()]
                break
        if not statements:
            statements = [assignment_input]
        
        for statement in statements:
            statement_lower = statement.lower()
            
            # Handle split statements like "harry and sidd split 4"
            if "split" in statement_lower:
                # Find item numbers
                item_numbers = []
                for word in statement.split():
                    try:
                        item_num = int(word)
                        if 0 <= item_num < len(items):
                            item_numbers.append(item_num)
                    except ValueError:
                        continue
                
                # Find participants mentioned
                person_names = []
                for participant in participants:
                    if participant.lower() in statement_lower:
                        person_names.append(participant)
                
                # Create shared assignments
                for item_idx in item_numbers:
                    if person_names:
                        share_fraction = (Decimal("1.0") / len(person_names)).quantize(TWO_DP, rounding=ROUND_HALF_UP)
                        shares = [
                            AssignmentShare(participant=person, fraction=share_fraction)
                            for person in person_names
                        ]
                        assignments.append(
                            ItemAssignment(
                                item_index=item_idx,
                                shares=shares
                            )
                        )
            
            # Handle individual assignments like "sidd had items 0 and 1"
            else:
                # Find the person
                person_name = None
                for participant in participants:
                    if participant.lower() in statement_lower:
                        person_name = participant
                        break
                
                if person_name:
                    # Find item numbers
                    item_numbers = []
                    for word in statement.split():
                        try:
                            item_num = int(word)
                            if 0 <= item_num < len(items):
                                item_numbers.append(item_num)
                        except ValueError:
                            continue
                    
                    # Create assignments
                    for item_idx in item_numbers:
                        assignments.append(
                            ItemAssignment(
                                item_index=item_idx,
                                shares=[AssignmentShare(participant=person_name, fraction=Decimal("1.0"))]
                            )
                        )
    
    return assignments
    """Build a human-readable list of items for the interview prompt."""
    # Handle both ReceiptState objects and plain dicts
    if hasattr(state, 'items'):  # ReceiptState object
        items = state.items
    else:  # Plain dict
        items = state.get("items", [])
        
    item_lines = []
    for i, item in enumerate(items):
        # Handle both Pydantic Item objects and plain dicts
        if hasattr(item, 'name'):  # Pydantic Item object
            name = item.name
            price = item.price
            quantity = item.quantity
        else:  # Plain dict
            name = item.get("name", "Unknown")
            price = item.get("price", "0.00")
            quantity = item.get("quantity", "1")
        item_lines.append(f"  [{i}] {name} — ${price} x {quantity}")
    return item_lines


def _parse_free_form_input(state: Dict[str, Any], items: List, free_form_text: str) -> Dict[str, Any]:
    """Parse free-form text into structured assignments using LLM."""
    
    if not items:
        return {
            "audit_log": [
                AuditEvent(
                    node="interview",
                    message="Cannot parse assignments - no items available",
                    timestamp=datetime.now(timezone.utc),
                )
            ],
            "pending_questions": ["No items found to assign. Please upload a receipt first."]
        }
    
    # Build context for the LLM
    items_text = "\n".join([
        f"Item {i}: {item.name if hasattr(item, 'name') else item.get('name', 'Unknown')} - ${item.price if hasattr(item, 'price') else item.get('price', '0.00')}"
        for i, item in enumerate(items)
    ])
    
    system_prompt = """You are an expert at parsing receipt assignment descriptions with excellent fuzzy matching capabilities.
    
Given a list of items and a natural language description of who ordered what,
extract the participants and their share percentages for each item.

Return ONLY a valid JSON object with this structure:
{
  "participants": ["Name1", "Name2", ...],
  "assignments": [
    {
      "item_index": 0,
      "shares": [
        {"participant": "Name1", "percentage": 100.0},
        {"participant": "Name2", "percentage": 0.0}
      ]
    }
  ],
  "unassigned_items": [0, 1, 2],
  "ambiguous_assignments": [
    {
      "item_index": 1,
      "reason": "Could not determine who ordered the 'Za Matriciana' pizza"
    }
  ]
}

CRITICAL RULES:
1. Percentages must sum to exactly 100.0 for each item
2. Handle fuzzy matching: "pizza" can match "Porky Pepperoni", "wine" can match "Scribe Rose GL"
3. Handle abbreviations and partial matches intelligently
4. If someone "shared" equally between N people, use (100/N)% for each
5. ALL items must be assigned - if unclear, ask for clarification via ambiguous_assignments
6. Include all item indices in assignments array, even if 0% for some participants
7. Extract participant names as they appear in text (capitalize first letter)
8. If multiple items could match a description, list them in ambiguous_assignments"""

    user_prompt = f"""Items from receipt:
{items_text}

Assignment description:
{free_form_text}

Parse this into JSON format showing who pays what percentage of each item."""

    try:
        model = _get_interview_model()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        
        response = model.invoke(messages)
        raw_text = response.content if isinstance(response.content, str) else str(response.content)
        logger.debug(f"Interview model raw response: {raw_text}")
        
        # Extract JSON from response
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.replace("{{", "{").replace("}}", "}")
        
        parsed = json.loads(cleaned)
        
        participants = parsed.get("participants", [])
        assignments = parsed.get("assignments", [])
        unassigned_items = parsed.get("unassigned_items", [])
        ambiguous_assignments = parsed.get("ambiguous_assignments", [])
        
        # Check if there are unassigned items or ambiguous assignments
        if unassigned_items or ambiguous_assignments:
            clarification_questions = []
            
            if unassigned_items:
                unassigned_names = []
                for i in unassigned_items:
                    if i < len(items):
                        item = items[i]
                        if hasattr(item, 'name'):
                            unassigned_names.append(item.name)
                        else:
                            unassigned_names.append(item.get("name", f"Item {i}"))
                clarification_questions.append(
                    f"These items were not assigned to anyone: {', '.join(unassigned_names)}. "
                    f"Please specify who should pay for them."
                )
            
            if ambiguous_assignments:
                for ambig in ambiguous_assignments:
                    item_idx = ambig.get("item_index")
                    reason = ambig.get("reason", "Assignment unclear")
                    if item_idx is not None and item_idx < len(items):
                        item = items[item_idx]
                        if hasattr(item, 'name'):
                            item_name = item.name
                        else:
                            item_name = item.get("name", f"Item {item_idx}")
                        clarification_questions.append(f"{item_name}: {reason}")
            
            return {
                "audit_log": [
                    AuditEvent(
                        node="interview",
                        message="Assignment needs clarification",
                        timestamp=datetime.now(timezone.utc),
                        details={
                            "unassigned_count": len(unassigned_items),
                            "ambiguous_count": len(ambiguous_assignments)
                        }
                    )
                ],
                "pending_questions": [
                    "Please clarify the following assignments:\n\n" + 
                    "\n• ".join(clarification_questions) + 
                    "\n\nYou can provide more details or rephrase your assignment description."
                ],
            }
        
        # Convert to expected format and validate
        return _validate_and_accept(items, participants, assignments)
        
    except Exception as e:
        error_msg = f"Failed to parse assignment description: {str(e)}. Please try again or rephrase your description."
        logger.warning(f"LLM parsing failed: {e}")
        
        return {
            "audit_log": [
                AuditEvent(
                    node="interview",
                    message="Assignment validation failed with error",
                    timestamp=datetime.now(timezone.utc),
                    details={"errors": [error_msg]},
                )
            ],
            "pending_questions": [f"Some assignments were invalid:\n• {error_msg}"],
        }


def _validate_and_accept(items: List, participants: List[str], assignments: List[Dict]) -> Dict[str, Any]:
    """Validate assignments and convert to internal format."""
    
    errors = []
    
    # Validate participants
    if not participants:
        errors.append("No participants found in the assignment.")
    
    # Convert assignments to internal format
    validated_assignments = []
    
    for assignment in assignments:
        item_index = assignment.get("item_index")
        shares = assignment.get("shares", [])
        
        if item_index is None or item_index < 0 or item_index >= len(items):
            errors.append(f"Invalid item index: {item_index}")
            continue
        
        # Convert percentage shares to decimal fractions
        assignment_shares = []
        total_percentage = 0.0
        
        for share in shares:
            participant = share.get("participant", "")
            percentage = float(share.get("percentage", 0.0))
            
            if not participant:
                errors.append(f"Empty participant name in assignment for item {item_index}")
                continue
            
            if participant not in participants:
                errors.append(f"Participant '{participant}' not found in participant list")
                continue
            
            total_percentage += percentage
            fraction = Decimal(str(percentage / 100.0)).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            
            assignment_shares.append(AssignmentShare(
                participant=participant,
                fraction=fraction
            ))
        
        # Validate total percentage
        if abs(total_percentage - 100.0) > 0.01:
            errors.append(f"Item {item_index} shares sum to {total_percentage}%, not 100%")
            continue
        
        validated_assignments.append(ItemAssignment(
            item_index=item_index,
            shares=assignment_shares
        ))
    
    if errors:
        error_list = "\n• ".join(errors)
        return {
            "audit_log": [
                AuditEvent(
                    node="interview",
                    message=f"Assignment validation failed with {len(errors)} error(s)",
                    timestamp=datetime.now(timezone.utc),
                    details={"errors": errors},
                )
            ],
            "pending_questions": [f"Some assignments were invalid:\n• {error_list}"],
        }
    
    # Success - accept the assignments
    return {
        "participants": participants,
        "assignments": validated_assignments,
        "current_node": "interview",
        "pending_questions": [],
        "audit_log": [
            AuditEvent(
                node="interview",
                message=f"Accepted assignments for {len(participants)} participants across {len(validated_assignments)} items",
                timestamp=datetime.now(timezone.utc),
                details={
                    "participant_count": len(participants),
                    "assignment_count": len(validated_assignments),
                    "participants": participants,
                },
            )
        ],
    }


def interview_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node: handle participant collection and assignments via structured steps."""
    
    # Handle both ReceiptState objects and plain dicts
    if hasattr(state, 'items') and hasattr(state, 'model_dump'):  # ReceiptState object
        items = getattr(state, 'items', [])
        participants = getattr(state, 'participants', [])
        participant_input = getattr(state, 'participant_input', "") or ""
        assignment_input = getattr(state, 'assignment_input', "") or ""
    else:  # Plain dict
        items = state.get("items", [])
        participants = state.get("participants", [])
        participant_input = state.get("participant_input", "") or ""
        assignment_input = state.get("assignment_input", "") or ""
    
    # Step 1: Collect participants first
    if not participants and participant_input.strip():
        # Parse participant names from input
        participant_names = [name.strip().title() for name in participant_input.split(',') if name.strip()]
        if participant_names:
            return {
                "participants": participant_names,
                "current_node": "interview_pending",
                "pending_questions": _generate_assignment_questions(items, participant_names),
                "audit_log": [
                    AuditEvent(
                        node="interview",
                        message=f"Added {len(participant_names)} participants: {', '.join(participant_names)}",
                        timestamp=datetime.now(timezone.utc),
                    )
                ],
            }
        else:
            return {
                "current_node": "interview_pending",
                "pending_questions": ["Please provide valid participant names separated by commas."],
                "audit_log": [
                    AuditEvent(
                        node="interview",
                        message="Invalid participant input",
                        timestamp=datetime.now(timezone.utc),
                    )
                ],
            }
    
    # Step 2: Handle assignments (if participants already exist)
    if participants and assignment_input.strip():
        return _process_structured_assignment(items, participants, assignment_input)
    
    # Phase 1: Ask for participants first
    if not participants:
        if not items:
            return {
                "current_node": "interview_pending",
                "audit_log": [
                    AuditEvent(
                        node="interview",
                        message="No items found — nothing to assign",
                        timestamp=datetime.now(timezone.utc),
                    )
                ],
                "pending_questions": [
                    "No items were extracted from the receipt. "
                    "Please go back and re-upload a clearer image."
                ],
            }
        
        return {
            "current_node": "interview_pending",
            "pending_questions": _generate_participant_questions(items),
            "audit_log": [
                AuditEvent(
                    node="interview",
                    message=f"Requesting participants for {len(items)} items",
                    timestamp=datetime.now(timezone.utc),
                    details={"item_count": len(items)},
                )
            ],
        }
    
    # Phase 2: Ask for assignments (participants already collected)
    return {
        "current_node": "interview_pending",
        "pending_questions": _generate_assignment_questions(items, participants),
        "audit_log": [
            AuditEvent(
                node="interview",
                message=f"Requesting assignments for {len(participants)} participants",
                timestamp=datetime.now(timezone.utc),
                details={"participant_count": len(participants)},
            )
        ],
    }