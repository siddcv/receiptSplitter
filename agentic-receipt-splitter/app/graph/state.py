"""
State schema for the Agentic Receipt Splitter.

This file defines strict Pydantic models for the core state objects used by the
LangGraph workflow. The audit log is modeled as a list which will be configured
in the graph to use an additive reducer (operator.add) so each node can append
entries without overwriting prior logs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---- Utility ----
TWO_DP = Decimal("0.01")


class AuditEvent(BaseModel):
	"""An entry describing a node's thought process or action.

	Intended to be accumulated via an additive reducer in the graph
	(e.g., reducers={"audit_log": operator.add}).
	"""

	timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
	node: str = Field(..., description="Graph node that produced this event")
	message: str = Field(..., description="Human-readable description")
	details: Optional[Dict] = Field(
		default=None, description="Optional structured payload for debugging"
	)


class Item(BaseModel):
	"""A single line item extracted from the receipt.

	- name: Item name/description as seen on the receipt.
	- price: Unit price in USD (quantized to 2 decimal places).
	- quantity: Number of units (strictly positive).
	- confidence: Per-field confidence scores from the vision model (0.0–1.0).
	"""

	name: str = Field(..., min_length=1)
	price: Decimal = Field(..., description="Unit price, USD")
	quantity: Decimal = Field(..., description="Units purchased, > 0")
	confidence: Optional[Dict[str, float]] = Field(
		default=None,
		description="Per-field confidence scores, e.g. {'name': 0.95, 'price': 0.90, 'quantity': 0.85}",
	)

	@field_validator("price")
	@classmethod
	def _validate_price(cls, v: Decimal) -> Decimal:
		if v is None:
			raise ValueError("price is required")
		if v < Decimal("0"):
			raise ValueError("price must be non-negative")
		# Quantize to 2 decimal places using ROUND_HALF_UP to match receipts
		return v.quantize(TWO_DP, rounding=ROUND_HALF_UP)

	@field_validator("quantity")
	@classmethod
	def _validate_quantity(cls, v: Decimal) -> Decimal:
		if v is None:
			raise ValueError("quantity is required")
		if v <= Decimal("0"):
			raise ValueError("quantity must be strictly positive")
		return v


class Totals(BaseModel):
	"""All totals present on the receipt (USD).

	grand_total must equal subtotal + tax_total + tip_total + fees_total.
	"""

	subtotal: Decimal = Field(...)
	tax_total: Decimal = Field(default=Decimal("0.00"))
	tip_total: Decimal = Field(default=Decimal("0.00"))
	fees_total: Decimal = Field(default=Decimal("0.00"))
	grand_total: Decimal = Field(...)

	@field_validator("subtotal", "tax_total", "tip_total", "fees_total", "grand_total")
	@classmethod
	def _quantize_totals(cls, v: Decimal) -> Decimal:
		if v is None:
			raise ValueError("total values must be provided")
		if v < Decimal("0"):
			raise ValueError("total values must be non-negative")
		return v.quantize(TWO_DP, rounding=ROUND_HALF_UP)

	@model_validator(mode="after")
	def _validate_grand_total(self) -> "Totals":
		expected = (self.subtotal + self.tax_total + self.tip_total + self.fees_total).quantize(
			TWO_DP, rounding=ROUND_HALF_UP
		)
		if self.grand_total != expected:
			raise ValueError(
				f"grand_total ({self.grand_total}) must equal subtotal + tax_total + tip_total + fees_total ({expected})"
			)
		return self


class AssignmentShare(BaseModel):
	"""A fractional share of an item assigned to a participant."""

	participant: str = Field(..., min_length=1)
	fraction: Decimal = Field(..., description="Between 0 and 1 inclusive")

	@field_validator("fraction")
	@classmethod
	def _validate_fraction(cls, v: Decimal) -> Decimal:
		if v is None:
			raise ValueError("fraction is required")
		if v < Decimal("0") or v > Decimal("1"):
			raise ValueError("fraction must be between 0 and 1 inclusive")
		return v


class ItemAssignment(BaseModel):
	"""Assignment for a specific item by index in the items list."""

	item_index: int = Field(..., ge=0)
	shares: List[AssignmentShare] = Field(default_factory=list)

	@model_validator(mode="after")
	def _validate_shares_sum(self) -> "ItemAssignment":
		total = sum((s.fraction for s in self.shares), Decimal("0"))
		# Allow exact 1.00 only
		if total.quantize(TWO_DP, rounding=ROUND_HALF_UP) != Decimal("1.00"):
			raise ValueError("sum of shares.fraction must equal 1.00 for each item")
		return self


class ReceiptState(BaseModel):
	"""Global state tracked across the LangGraph workflow for a single receipt.

	Notes:
	- audit_log is intended to use operator.add as a reducer in the graph.
	- participants must be unique, non-empty names.
	- assignments reference items by positional index to avoid ambiguous names.
	"""

	thread_id: str = Field(..., description="Unique ID for this receipt session")
	image_path: Optional[str] = Field(
		default=None, description="Absolute path to the uploaded receipt image"
	)
	items: List[Item] = Field(default_factory=list)
	participants: List[str] = Field(default_factory=list)
	assignments: List[ItemAssignment] = Field(default_factory=list)
	totals: Optional[Totals] = Field(default=None)
	confidence: Optional[Dict[str, float]] = Field(
		default=None,
		description="Overall extraction confidence scores from the vision model",
	)
	audit_log: List[AuditEvent] = Field(default_factory=list)
	current_node: Optional[str] = Field(
		default=None, description="Current graph node name (for status APIs)"
	)
	pending_questions: List[str] = Field(
		default_factory=list, description="Questions to present to the user"
	)
	final_costs: Optional[List[Dict[str, Any]]] = Field(
		default=None, description="Final calculated costs for each participant from math node"
	)

	@field_validator("participants")
	@classmethod
	def _validate_participants(cls, v: List[str]) -> List[str]:
		cleaned = [p.strip() for p in v if isinstance(p, str)]
		if any(len(p) == 0 for p in cleaned):
			raise ValueError("participant names must be non-empty")
		if len(set(cleaned)) != len(cleaned):
			raise ValueError("participant names must be unique")
		return cleaned

