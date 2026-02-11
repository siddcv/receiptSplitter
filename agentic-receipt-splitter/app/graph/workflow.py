"""
LangGraph workflow wiring for the Agentic Receipt Splitter.

Current graph: START → vision → END
The vision node extracts items + totals from a receipt image via Gemini 1.5 Flash.
Future nodes (math, interview) will be inserted between vision and END.
"""

from __future__ import annotations

import operator
import os
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from app.database import get_checkpointer
from app.graph.state import AuditEvent, ReceiptState
from app.graph.nodes.vision import vision_node


def build_graph() -> Any:
	"""Build and compile the receipt-processing graph.

	Honors env toggle USE_IN_MEMORY:
	- If set to '1'/'true', compiles WITHOUT a checkpointer (no DB required).
	- Otherwise, compiles with Postgres checkpointer for persistence.
	"""
	reducers = {"audit_log": operator.add}
	graph = StateGraph(ReceiptState, reducers=reducers)

	graph.add_node("vision", vision_node)

	graph.add_edge(START, "vision")
	graph.add_edge("vision", END)

	use_in_memory = (os.getenv("USE_IN_MEMORY", "").lower() in {"1", "true", "yes"})
	if use_in_memory:
		app_graph = graph.compile()
	else:
		checkpointer = get_checkpointer()
		app_graph = graph.compile(checkpointer=checkpointer)
	return app_graph

