from __future__ import annotations

"""
FastAPI backend skeleton for Agentic Receipt Splitter.

Exposes:
- GET /            : health/info
- POST /upload     : upload a receipt image, create a thread_id, persist initial state
- GET /state/{id}  : fetch latest persisted state snapshot for a thread

The vision/math nodes will be added later; currently the graph includes a noop node
and uses the Postgres checkpointer to persist state per thread_id.
"""

import os
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, File, HTTPException, UploadFile
from dotenv import load_dotenv

from app.graph.state import AuditEvent, ReceiptState
from app.graph.workflow import build_graph
from app.database import ensure_db_ready


# Load .env early so USE_IN_MEMORY and other settings are available
load_dotenv(override=False)

# FastAPI app singleton
app = FastAPI(title="Agentic Receipt Splitter", version="0.1")

# Compiled graph singleton
_APP_GRAPH = None


def _uploads_dir() -> Path:
	# Allow override via env; default to ./uploads inside project folder
	configured = os.getenv("IMAGE_UPLOAD_DIR", "./uploads")
	base = Path(__file__).resolve().parent.parent  # agentic-receipt-splitter/
	# If configured is relative, resolve relative to project root
	upload_path = Path(configured)
	if not upload_path.is_absolute():
		upload_path = base / upload_path
	upload_path.mkdir(parents=True, exist_ok=True)
	return upload_path


def _get_graph():
	global _APP_GRAPH
	if _APP_GRAPH is None:
		# Honor in-memory toggle to develop without a running DB
		use_in_memory = (os.getenv("USE_IN_MEMORY", "").lower() in {"1", "true", "yes"})
		if not use_in_memory:
			# Verify DB connectivity early to surface clear errors
			ensure_db_ready()
		_APP_GRAPH = build_graph()
	return _APP_GRAPH


@app.get("/")
def info() -> Dict[str, Any]:
	use_in_memory = (os.getenv("USE_IN_MEMORY", "").lower() in {"1", "true", "yes"})
	return {
		"status": "ok",
		"version": app.version,
		"endpoints": ["/", "/upload", "/state/{thread_id}"],
		"mode": "in-memory" if use_in_memory else "postgres",
	}


@app.post("/upload")
async def upload_receipt(file: UploadFile = File(...)) -> Dict[str, Any]:
	# Basic content-type guard
	ct = (file.content_type or "").lower()
	if not ct.startswith("image/"):
		raise HTTPException(status_code=400, detail="Please upload an image file.")

	thread_id = f"receipt-{uuid.uuid4().hex}"
	uploads = _uploads_dir()

	# Preserve extension if present
	suffix = Path(file.filename or "").suffix or ".img"
	dest = uploads / f"{thread_id}{suffix}"

	try:
		content = await file.read()
		dest.write_bytes(content)
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")

	# Persist initial state via the graph
	app_graph = _get_graph()
	initial = ReceiptState(
		thread_id=thread_id,
		items=[],
		participants=[],
		assignments=[],
		totals=None,
		audit_log=[
			AuditEvent(
				node="upload",
				message="received image upload",
				details={"filename": file.filename, "path": str(dest)}
			)
		],
		current_node="upload",
		pending_questions=[],
	)

	cfg = {"configurable": {"thread_id": thread_id}}
	try:
		result = app_graph.invoke(initial, config=cfg)
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Failed to persist initial state: {e}")

	def _to_dict(obj: Any) -> Dict[str, Any]:
		if isinstance(obj, dict):
			return obj
		try:
			return obj.dict()
		except Exception:
			return {}

	return {"thread_id": thread_id, "state": _to_dict(result)}


@app.get("/state/{thread_id}")
def get_state(thread_id: str) -> Dict[str, Any]:
	app_graph = _get_graph()
	cfg = {"configurable": {"thread_id": thread_id}}
	get_state_fn = getattr(app_graph, "get_state", None)
	if not callable(get_state_fn):
		raise HTTPException(status_code=501, detail="State retrieval not supported by this graph version.")

	saved = get_state_fn(cfg)
	if saved is None:
		raise HTTPException(status_code=404, detail="No state found for thread_id.")
	if isinstance(saved, dict):
		return saved
	try:
		return saved.dict()
	except Exception:
		return {"thread_id": thread_id}

