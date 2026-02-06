"""
Minimal LangGraph wiring for Step 1: persistence smoke test.

This constructs a trivial graph that simply echoes the input state, compiled
with the PostgresSaver checkpointer so we can save and retrieve by thread_id.
"""

from __future__ import annotations

import operator
import os
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from app.database import get_checkpointer
from app.graph.state import AuditEvent, ReceiptState


def _noop_node(state: ReceiptState) -> ReceiptState:
	"""A pass-through node that returns the state unchanged."""
	return state


def build_graph() -> Any:
	"""Build and compile the trivial graph.

	Honors env toggle USE_IN_MEMORY:
	- If set to '1'/'true', compiles WITHOUT a checkpointer (no DB required).
	- Otherwise, compiles with Postgres checkpointer for persistence.
	"""
	reducers = {"audit_log": operator.add}
	graph = StateGraph(ReceiptState, reducers=reducers)
	graph.add_node("noop", _noop_node)
	graph.add_edge(START, "noop")
	graph.add_edge("noop", END)

	use_in_memory = (os.getenv("USE_IN_MEMORY", "").lower() in {"1", "true", "yes"})
	if use_in_memory:
		# Compile without a checkpointer; state persists only in-process
		app_graph = graph.compile()
	else:
		checkpointer = get_checkpointer()
		app_graph = graph.compile(checkpointer=checkpointer)
	return app_graph


def run_dummy(thread_id: str = "demo-thread-1") -> Dict[str, Any]:
	"""Invoke the graph with a minimal state and return the final state snapshot.

	This provides a simple smoke test that verifies:
	- we can compile with a Postgres checkpointer
	- we can invoke with a given thread_id
	- we can retrieve saved state after invocation
	"""
	app_graph = build_graph()

	initial = ReceiptState(
		thread_id=thread_id,
		items=[],
		participants=[],
		assignments=[],
		totals=None,
		audit_log=[
			AuditEvent(node="noop", message="initialized dummy state for smoke test")
		],
		current_node="noop",
		pending_questions=[],
	)

	cfg = {"configurable": {"thread_id": thread_id}}
	result = app_graph.invoke(initial, config=cfg)

	# Attempt to retrieve the latest saved state for this thread
	# Some versions expose get_state; if unavailable, return the result of invoke
	get_state = getattr(app_graph, "get_state", None)
	if callable(get_state):
		saved = get_state(cfg)
		# saved may be a dict or a model; normalize to dict for display
		try:
			return saved if isinstance(saved, dict) else saved.dict()
		except Exception:
			# Fallback if .dict() isn't available
			return result if isinstance(result, dict) else {}
	return result if isinstance(result, dict) else {}

