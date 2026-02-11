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


def _build_item_summary(state: Dict[str, Any]) -> List[str]:
    """Build a human-readable list of items for the interview prompt."""
    items = state.get("items", [])
    item_lines = []
    for i, item in enumerate(items):
        name = item.get("name", "Unknown")
        price = item.get("price", "0.00")
        quantity = item.get("quantity", "1")
        item_lines.append(f"  [{i}] {name} — ${price} x {quantity}")
    return item_lines


def _parse_free_form_input(state: Dict[str, Any], items: List[Dict], free_form_text: str) -> Dict[str, Any]:
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
        f"Item {i}: {item.get('name', 'Unknown')} - ${item.get('price', '0.00')}"
        for i, item in enumerate(items)
    ])
    
    system_prompt = """You are an expert at parsing receipt assignment descriptions.
    
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
  ]
}

Rules:
- Percentages must sum to exactly 100.0 for each item
- Use exact names as they appear in the text
- If someone "shared" equally, use 50%/50% or 33.3%/33.3%/33.3%
- Be precise with percentage splits based on context
- If unclear, make reasonable assumptions"""

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
        
        # Convert to expected format and validate
        return _validate_and_accept(state, items, participants, assignments)
        
    except Exception as e:
        error_msg = f"Failed to parse assignment description: {str(e)}. Please try again or rephrase your description."
        logger.warning(f"LLM parsing failed: {e}")
        
        return {
            "audit_log": [
                AuditEvent(
                    node="interview",
                    message=f"Assignment validation failed with 1 error(s)",
                    timestamp=datetime.now(timezone.utc),
                    details={"errors": [error_msg]},
                )
            ],
            "pending_questions": [f"Some assignments were invalid:\n• {error_msg}"],
        }


def _validate_and_accept(state: Dict[str, Any], items: List[Dict], participants: List[str], assignments: List[Dict]) -> Dict[str, Any]:
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
    """LangGraph node: handle participant assignments via free-form text or structured input."""
    
    items = state.get("items", [])
    free_form_text = state.get("free_form_assignment", "")
    participants = state.get("participants", [])
    assignments = state.get("assignments", [])
    
    # Phase 2 re-entry: free-form text provided
    if free_form_text.strip():
        return _parse_free_form_input(state, items, free_form_text)
    
    # Legacy support for structured assignments
    if participants and assignments:
        return _validate_and_accept(state, items, participants, assignments)
    
    # Phase 1: no assignments yet — generate questions
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
    
    item_lines = _build_item_summary(state)
    question = (
        "Please describe who ordered what items in your own words.\n\n"
        "Extracted items:\n"
        + "\n".join(item_lines)
        + "\n\n"
        "Example responses:\n"
        "• 'Alice had the pizza and Caesar salad. Bob had the garlic bread. We split the appetizer.'\n"
        "• 'I ordered items 0 and 2. Sarah got item 1. The wine was shared between all three of us.'\n"
        "• 'Pizza: Alice and Bob split it. Salad: Alice only. Bread: everyone shared equally.'\n\n"
        "You can reference items by name or by their number [0], [1], etc. "
        "Mention if items are shared and how they should be split."
    )
    
    audit = AuditEvent(
        node="interview",
        message=f"Awaiting free-form assignment description for {len(items)} items",
        timestamp=datetime.now(timezone.utc),
        details={"item_count": len(items)},
    )
    
    return {
        "current_node": "interview_pending",
        "pending_questions": [question],
        "audit_log": [audit],
    }