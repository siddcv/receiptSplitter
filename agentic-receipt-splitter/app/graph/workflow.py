"""
LangGraph workflow wiring for the Agentic Receipt Splitter.

Current graph: START → vision → interview → math → END
- vision node: extracts items + totals from receipt image via Gemini 2.0 Flash
- interview node: handles participant assignments via natural language processing
- math node: calculates final costs including tax/tip distribution
"""

from __future__ import annotations

import operator
import os
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from app.database import get_checkpointer
from app.graph.state import AuditEvent, ReceiptState
from app.graph.nodes.vision import vision_node
from app.graph.nodes.interview import interview_node
from app.graph.nodes.math import math_node


def should_proceed_to_math(state: Dict[str, Any]) -> str:
	"""Conditional edge: only proceed to math if interview is complete."""
	
	# Handle both ReceiptState objects and plain dicts
	if hasattr(state, 'pending_questions'):
		pending_questions = getattr(state, 'pending_questions', [])
	else:
		pending_questions = state.get("pending_questions", [])
	
	# If there are pending questions, stay at interview (end workflow for now)
	if pending_questions:
		return END
	
	# If no pending questions, proceed to math
	return "math"


def build_graph() -> Any:
	"""Build and compile the receipt-processing graph.

	Honors env toggle USE_IN_MEMORY:
	- If set to '1'/'true', compiles WITHOUT a checkpointer (no DB required).
	- Otherwise, compiles with Postgres checkpointer for persistence.
	"""
	reducers = {"audit_log": operator.add}
	graph = StateGraph(ReceiptState, reducers=reducers)

	graph.add_node("vision", vision_node)
	graph.add_node("interview", interview_node)
	graph.add_node("math", math_node)

	graph.add_edge(START, "vision")
	graph.add_edge("vision", "interview")
	
	# Conditional edge: only proceed to math if interview is complete
	graph.add_conditional_edges(
		"interview",
		should_proceed_to_math,
		{
			"math": "math",
			END: END
		}
	)
	
	graph.add_edge("math", END)

	use_in_memory = (os.getenv("USE_IN_MEMORY", "").lower() in {"1", "true", "yes"})
	if use_in_memory:
		app_graph = graph.compile()
	else:
		checkpointer = get_checkpointer()
		app_graph = graph.compile(checkpointer=checkpointer)
	return app_graph

