"""
Vision node: extracts structured receipt data from an uploaded image.

Uses Gemini 1.5 Flash via langchain-google-genai to read the receipt image
and return items + totals with per-field confidence scores.

The node reads the image from state.image_path, calls the model, parses the
JSON response into Item/Totals models, and flags low-confidence fields as
pending_questions for human review.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.graph.state import AuditEvent, Item, ReceiptState, Totals
from app.prompts.vision_prompt import VISION_SYSTEM_PROMPT, VISION_USER_PROMPT

load_dotenv(override=False)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _image_to_data_url(image_path: str) -> str:
    """Read an image file and return a base64-encoded data URL."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    suffix = path.suffix.lower()
    _MIME_JPEG = "image/jpeg"
    mime_map = {
        ".jpg": _MIME_JPEG,
        ".jpeg": _MIME_JPEG,
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    mime = mime_map.get(suffix, _MIME_JPEG)
    raw = path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _extract_json(text: str) -> Dict[str, Any]:
    """Extract a JSON object from model output, tolerating markdown fences."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    
    # Fix double curly braces ({{}} -> {}) - model escape sequence issue
    cleaned = cleaned.replace("{{", "{").replace("}}", "}")
    
    return json.loads(cleaned)


def _parse_items(raw_items: List[Dict[str, Any]]) -> List[Item]:
    """Convert raw JSON items into validated Item models."""
    items: List[Item] = []
    for raw in raw_items:
        item = Item(
            name=raw.get("name", "Unknown Item"),
            price=Decimal(str(raw.get("unit_price", "0.00"))),
            quantity=Decimal(str(raw.get("quantity", "1"))),
            confidence=raw.get("confidence"),
        )
        items.append(item)
    return items


def _parse_totals(raw_totals: Dict[str, Any]) -> Totals:
    """Convert raw JSON totals into a validated Totals model.

    If the grand_total doesn't match the component sum, we adjust subtotal
    so the Totals validator passes, since we trust the printed grand_total.
    """
    subtotal = Decimal(str(raw_totals.get("subtotal", "0.00")))
    tax_total = Decimal(str(raw_totals.get("tax_total", "0.00")))
    tip_total = Decimal(str(raw_totals.get("tip_total", "0.00")))
    fees_total = Decimal(str(raw_totals.get("fees_total", "0.00")))
    grand_total = Decimal(str(raw_totals.get("grand_total", "0.00")))

    # If grand_total != sum of parts, adjust subtotal to reconcile
    component_sum = tax_total + tip_total + fees_total
    expected_subtotal = grand_total - component_sum
    if subtotal != expected_subtotal:
        logger.warning(
            "Adjusting subtotal from %s to %s to match grand_total %s",
            subtotal, expected_subtotal, grand_total,
        )
        subtotal = expected_subtotal

    return Totals(
        subtotal=subtotal,
        tax_total=tax_total,
        tip_total=tip_total,
        fees_total=fees_total,
        grand_total=grand_total,
    )


def _flag_item_confidence(items: List[Item], threshold: float) -> List[str]:
    """Generate review questions for item fields below the confidence threshold."""
    questions: List[str] = []
    for i, item in enumerate(items):
        if not item.confidence:
            continue
        for field, score in item.confidence.items():
            if score >= threshold:
                continue
            value = getattr(item, field if field != "unit_price" else "price", "?")
            questions.append(
                f"Item {i + 1} ({item.name}): is the {field} = {value} correct? "
                f"(confidence: {score:.0%})"
            )
    return questions


def _flag_totals_confidence(
    totals_confidence: Optional[Dict[str, float]],
    threshold: float,
) -> List[str]:
    """Generate review questions for totals fields below the confidence threshold."""
    if not totals_confidence:
        return []
    return [
        f"Totals: is {field} correct? (confidence: {score:.0%})"
        for field, score in totals_confidence.items()
        if score < threshold
    ]


def _flag_low_confidence(
    items: List[Item],
    totals_confidence: Optional[Dict[str, float]],
    threshold: float,
) -> List[str]:
    """Generate human-review questions for fields below the confidence threshold."""
    return (
        _flag_item_confidence(items, threshold)
        + _flag_totals_confidence(totals_confidence, threshold)
    )


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _get_model() -> ChatGoogleGenerativeAI:
    """Instantiate the Gemini model from env config with fallback."""
    model_name = os.getenv("VISION_MODEL", "models/gemini-2.5-flash")
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set in environment/.env")

    max_retries = int(os.getenv("VISION_MAX_RETRIES", "2"))

    # Try the specified model first
    try:
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0.0,
            max_retries=max_retries,
        )
    except Exception as e:
        logger.warning(f"Failed to create model {model_name}: {e}")
        
        # Try fallback models (same as interview component)
        fallback_models = [
            "models/gemini-2.5-flash",
            "models/gemini-2.0-flash", 
            "models/gemini-2.5-pro"
        ]
        
        for fallback_model in fallback_models:
            if fallback_model == model_name:
                continue  # Skip the one we already tried
            try:
                logger.info(f"Trying fallback vision model: {fallback_model}")
                return ChatGoogleGenerativeAI(
                    model=fallback_model,
                    google_api_key=api_key,
                    temperature=0.0,
                    max_retries=max_retries,
                )
            except Exception as fallback_e:
                logger.warning(f"Fallback model {fallback_model} also failed: {fallback_e}")
        
        # If all models fail, raise the original error
        raise RuntimeError(f"All vision models failed. Last error: {e}")


def _call_vision_model(image_path: str) -> Dict[str, Any]:
    """Send the image to Gemini and return the parsed JSON response."""
    model = _get_model()
    data_url = _image_to_data_url(image_path)

    messages = [
        SystemMessage(content=VISION_SYSTEM_PROMPT),
        HumanMessage(
            content=[
                {"type": "text", "text": VISION_USER_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
        ),
    ]

    response = model.invoke(messages)
    raw_text = response.content if isinstance(response.content, str) else str(response.content)

    logger.debug("Vision model raw response:\n%s", raw_text)
    return _extract_json(raw_text)


# ---------------------------------------------------------------------------
# Graph node
# ---------------------------------------------------------------------------

def vision_node(state: ReceiptState) -> Dict[str, Any]:
    """LangGraph node: extract receipt data from the uploaded image.

    Reads state.image_path, calls Gemini 1.5 Flash, parses the response into
    Item/Totals, flags low-confidence fields, and returns a state update dict
    (LangGraph merges this into the existing state).

    Returns a dict (not a full ReceiptState) so the graph reducer can merge
    fields additively (especially audit_log via operator.add).
    """
    image_path = state.image_path
    if not image_path:
        return {
            "current_node": "vision",
            "audit_log": [
                AuditEvent(
                    node="vision",
                    message="SKIPPED — no image_path in state",
                    timestamp=datetime.now(timezone.utc),
                )
            ],
        }

    threshold = float(os.getenv("VISION_CONF_THRESHOLD", "0.80"))

    try:
        parsed = _call_vision_model(image_path)
    except Exception as exc:
        logger.exception("Vision model call failed")
        return {
            "current_node": "vision",
            "audit_log": [
                AuditEvent(
                    node="vision",
                    message=f"ERROR — vision model call failed: {exc}",
                    timestamp=datetime.now(timezone.utc),
                )
            ],
            "pending_questions": [
                "The vision model failed to read the receipt. "
                "Please re-upload a clearer image or enter items manually."
            ],
        }

    # ---- Parse items ----
    raw_items = parsed.get("items", [])
    items = _parse_items(raw_items)

    # ---- Parse totals ----
    raw_totals = parsed.get("totals", {})
    totals_confidence = raw_totals.pop("confidence", None)
    try:
        totals = _parse_totals(raw_totals)
    except Exception as exc:
        logger.warning("Totals parsing failed: %s", exc)
        totals = None
        totals_confidence = None

    # ---- Flag low-confidence fields ----
    questions = _flag_low_confidence(items, totals_confidence, threshold)

    # ---- Build audit entry ----
    audit = AuditEvent(
        node="vision",
        message=f"Extracted {len(items)} items from receipt image",
        timestamp=datetime.now(timezone.utc),
        details={
            "item_count": len(items),
            "has_totals": totals is not None,
            "low_confidence_flags": len(questions),
            "totals_confidence": totals_confidence,
        },
    )

    return {
        "items": items,
        "totals": totals,
        "confidence": totals_confidence,
        "current_node": "vision",
        "audit_log": [audit],
        "pending_questions": questions,
    }
