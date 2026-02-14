from __future__ import annotations

"""
FastAPI backend for the Agentic Receipt Splitter.

Exposes:
- GET /                   : health/info
- POST /upload            : upload a receipt image → runs vision + interview phase 1
- POST /interview/{id}    : submit participant assignments → runs interview phase 2
- GET /state/{id}         : fetch latest state snapshot for a thread
- POST /test/mock-state   : create mock state for testing (in-memory mode only)
"""

import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.graph.state import AuditEvent, ReceiptState
from app.graph.workflow import build_graph
from app.database import ensure_db_ready

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
ALLOWED_CONTENT_TYPES = {
	"image/jpeg", "image/png", "image/webp", "image/gif",
	"image/bmp", "image/tiff",
}

# Load .env early so USE_IN_MEMORY and other settings are available
load_dotenv(override=False)

# Rate limiter — keyed by client IP
limiter = Limiter(key_func=get_remote_address)

# FastAPI app singleton
app = FastAPI(title="Agentic Receipt Splitter", version="0.1")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — allow the Next.js frontend (dev & production)
_allowed_origins = [
	"http://localhost:3000",   # Next.js dev server
	"http://127.0.0.1:3000",
]
# Allow a production frontend origin via env var
_prod_origin = os.getenv("FRONTEND_ORIGIN")
if _prod_origin:
	_allowed_origins.append(_prod_origin)

app.add_middleware(
	CORSMiddleware,
	allow_origins=_allowed_origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


# Security headers middleware
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
	async def dispatch(self, request, call_next):
		response = await call_next(request)
		response.headers["X-Content-Type-Options"] = "nosniff"
		response.headers["X-Frame-Options"] = "DENY"
		response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
		response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
		return response

app.add_middleware(SecurityHeadersMiddleware)

# Compiled graph singleton
_APP_GRAPH = None
_INMEM_STORE: Dict[str, Dict[str, Any]] = {}


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
@limiter.limit("3/hour")
async def upload_receipt(request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
	# --- Content-type guard ---
	ct = (file.content_type or "").lower()
	if ct not in ALLOWED_CONTENT_TYPES:
		raise HTTPException(
			status_code=400,
			detail=f"Unsupported file type '{ct}'. Please upload a JPEG, PNG, or WebP image.",
		)

	# --- Extension guard ---
	suffix = Path(file.filename or "").suffix.lower() or ".img"
	if suffix not in ALLOWED_EXTENSIONS:
		raise HTTPException(
			status_code=400,
			detail=f"Unsupported file extension '{suffix}'.",
		)

	# --- File size guard (read content once, check size) ---
	try:
		content = await file.read()
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Failed to read upload: {e}")

	if len(content) > MAX_UPLOAD_BYTES:
		raise HTTPException(
			status_code=413,
			detail=f"File too large ({len(content) / (1024*1024):.1f} MB). Maximum size is {MAX_UPLOAD_BYTES // (1024*1024)} MB.",
		)

	# --- Magic-byte sniff (reject non-images that lie about content-type) ---
	_IMAGE_SIGNATURES = {
		b"\xff\xd8\xff":       "JPEG",
		b"\x89PNG\r\n\x1a\n": "PNG",
		b"RIFF":               "WebP",  # WebP starts with RIFF....WEBP
		b"GIF87a":             "GIF",
		b"GIF89a":             "GIF",
		b"BM":                 "BMP",
	}
	head = content[:8]
	if not any(head.startswith(sig) for sig in _IMAGE_SIGNATURES):
		raise HTTPException(
			status_code=400,
			detail="File does not appear to be a valid image.",
		)

	thread_id = f"receipt-{uuid.uuid4().hex}"
	uploads = _uploads_dir()
	dest = uploads / f"{thread_id}{suffix}"

	try:
		dest.write_bytes(content)
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")

	# Persist initial state via the graph
	app_graph = _get_graph()
	# Sanitize original filename for audit logging (strip path traversal chars)
	safe_filename = Path(file.filename or "unknown").name.replace("..", "")
	initial = ReceiptState(
		thread_id=thread_id,
		image_path=str(dest),
		items=[],
		participants=[],
		assignments=[],
		totals=None,
		audit_log=[
			AuditEvent(
				node="upload",
				message="received image upload",
				details={"filename": safe_filename, "path": str(dest)}
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
	state_dict = _to_dict(result)

	# In in-memory mode, store the latest state so GET /state can retrieve it
	use_in_memory = (os.getenv("USE_IN_MEMORY", "").lower() in {"1", "true", "yes"})
	if use_in_memory:
		_INMEM_STORE[thread_id] = state_dict

	return {"thread_id": thread_id, "state": state_dict}


@app.get("/state/{thread_id}")
def get_state(thread_id: str) -> Dict[str, Any]:
	# If using in-memory mode, read from the local store
	use_in_memory = (os.getenv("USE_IN_MEMORY", "").lower() in {"1", "true", "yes"})
	if use_in_memory:
		saved = _INMEM_STORE.get(thread_id)
		if not saved:
			raise HTTPException(status_code=404, detail="No state found for thread_id (in-memory mode).")
		return saved

	# Otherwise, use the checkpointer-backed retrieval
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


# ---------------------------------------------------------------------------
# Interview endpoint — Phase 2: accept participant assignments
# ---------------------------------------------------------------------------

class ShareInput(BaseModel):
	"""A single participant's fractional share of an item."""
	participant: str
	fraction: float  # will be converted to Decimal in the node


class AssignmentInput(BaseModel):
	"""Assignment for one item by its index."""
	item_index: int
	shares: List[ShareInput]


class InterviewRequest(BaseModel):
	"""Payload for POST /interview/{thread_id}."""
	# New step-by-step flow
	participant_input: Optional[str] = None      # Step 1: Comma-separated participant names
	assignment_input: Optional[str] = None       # Step 2: Assignment descriptions
	
	# Legacy support for existing formats  
	free_form_assignment: Optional[str] = None   # Legacy free-form input
	participants: Optional[List[str]] = None     # Legacy structured input
	assignments: Optional[List[AssignmentInput]] = None  # Legacy structured input


@app.post("/interview/{thread_id}")
@limiter.limit("20/hour")
async def submit_interview(request: Request, thread_id: str, body: InterviewRequest) -> Dict[str, Any]:
	"""Accept participant assignments via free-form text or structured data.

	This re-invokes the interview node with the user's input.
	"""
	use_in_memory = (os.getenv("USE_IN_MEMORY", "").lower() in {"1", "true", "yes"})

	# Retrieve existing state
	if use_in_memory:
		existing = _INMEM_STORE.get(thread_id)
		if not existing:
			raise HTTPException(
				status_code=404,
				detail="No state found for thread_id (in-memory mode).",
			)
	else:
		# Postgres mode — retrieve state from LangGraph checkpointer
		app_graph = _get_graph()
		cfg = {"configurable": {"thread_id": thread_id}}
		try:
			snapshot = app_graph.get_state(cfg)
		except Exception as e:
			raise HTTPException(
				status_code=500,
				detail=f"Failed to retrieve state: {e}",
			)
		if snapshot is None:
			raise HTTPException(
				status_code=404,
				detail="No state found for thread_id.",
			)
		# snapshot.values is the state dict
		if hasattr(snapshot, "values"):
			existing = snapshot.values
		elif isinstance(snapshot, dict):
			existing = snapshot
		else:
			try:
				existing = snapshot.dict()
			except Exception:
				raise HTTPException(
					status_code=500,
					detail="Could not deserialise state from checkpointer.",
				)

	# Verify the graph is waiting for interview input
	if isinstance(existing, dict):
		current_node = existing.get("current_node", "")
	else:
		current_node = getattr(existing, "current_node", "")
	
	if current_node != "interview_pending":
		raise HTTPException(
			status_code=409,
			detail=f"Thread is at node '{current_node}', not 'interview_pending'. "
			"Cannot submit interview answers at this stage.",
		)

	# Build a state patch with the user's input and re-invoke the interview node
	from app.graph.nodes.interview import interview_node

	# Build a merged state dict for the interview node
	merged_state = dict(existing)

	# Handle new step-by-step input (preferred)
	if body.participant_input:
		merged_state["participant_input"] = body.participant_input.strip()
	elif body.assignment_input:
		merged_state["assignment_input"] = body.assignment_input.strip()
	# Handle legacy free-form text input
	elif body.free_form_assignment:
		merged_state["free_form_assignment"] = body.free_form_assignment.strip()
	# Handle legacy structured input
	elif body.participants and body.assignments:
		merged_state["participants"] = body.participants
		# Convert the request to plain dicts the interview node expects
		assignments_dicts = [
			{
				"item_index": a.item_index,
				"shares": [
					{"participant": s.participant, "fraction": str(s.fraction)}
					for s in a.shares
				],
			}
			for a in body.assignments
		]
		merged_state["assignments"] = assignments_dicts
	else:
		raise HTTPException(
			status_code=400,
			detail="Please provide participant_input, assignment_input, or legacy format input."
		)

	# Run interview phase 2 directly
	result = interview_node(merged_state)

	# Merge result back into state
	for key, value in result.items():
		if key == "audit_log":
			# Append, don't replace
			merged_state.setdefault("audit_log", [])
			merged_state["audit_log"] = merged_state["audit_log"] + value
		elif key == "pending_questions":
			# Replace (phase 2 clears or sets new questions)
			merged_state[key] = value
		else:
			merged_state[key] = value

	# If interview is complete (no pending questions), run the math node
	if not merged_state.get("pending_questions"):
		from app.graph.nodes.math import math_node
		math_result = math_node(merged_state)

		for key, value in math_result.items():
			if key == "audit_log":
				merged_state.setdefault("audit_log", [])
				merged_state["audit_log"] = merged_state["audit_log"] + value
			else:
				merged_state[key] = value

		# Normalize final_costs: math node returns {participant_costs: [...], ...}
		# but ReceiptState.final_costs expects a plain list of dicts.
		fc = merged_state.get("final_costs")
		if isinstance(fc, dict) and "participant_costs" in fc:
			merged_state["final_costs"] = fc["participant_costs"]

	# Serialize any Pydantic models for JSON storage
	merged_state = _serialize_state(merged_state)

	# Store updated state
	if use_in_memory:
		_INMEM_STORE[thread_id] = merged_state
	else:
		# Postgres mode — update state via graph invoke so the checkpointer persists it
		try:
			app_graph = _get_graph()
			cfg = {"configurable": {"thread_id": thread_id}}
			app_graph.update_state(cfg, merged_state)
		except Exception as e:
			# Log but don't fail — business persistence already happened in the node
			import logging
			logging.getLogger(__name__).error(f"Failed to update checkpointer state: {e}")

	return {"thread_id": thread_id, "state": merged_state}


def _serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Recursively convert Pydantic models and Decimals to JSON-safe dicts."""
	import json
	from decimal import Decimal
	from datetime import datetime

	def _default(obj: Any) -> Any:
		if isinstance(obj, Decimal):
			return str(obj)
		if isinstance(obj, datetime):
			# If timezone-aware, isoformat() already includes the offset — don't add Z
			# If naive, assume UTC and append Z
			if obj.tzinfo is not None:
				return obj.isoformat()
			return obj.isoformat() + "Z"
		if hasattr(obj, "model_dump"):
			return obj.model_dump()
		if hasattr(obj, "dict"):
			return obj.dict()
		raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

	# Round-trip through JSON to normalize everything
	raw = json.loads(json.dumps(state, default=_default))
	return raw


# ---------------------------------------------------------------------------
# Test endpoint — inject mock state for testing interview flow
# ---------------------------------------------------------------------------

class MockStateRequest(BaseModel):
	"""Request to create a mock state for testing."""
	thread_id: str
	items: List[Dict[str, Any]]
	totals: Optional[Dict[str, Any]] = None
	current_node: str = "interview_pending"


@app.post("/test/mock-state")
async def create_mock_state(body: MockStateRequest) -> Dict[str, Any]:
	"""Create a mock state for testing the interview flow (in-memory mode only)."""
	use_in_memory = (os.getenv("USE_IN_MEMORY", "").lower() in {"1", "true", "yes"})
	if not use_in_memory:
		raise HTTPException(
			status_code=501,
			detail="Mock state creation only available in in-memory mode."
		)

	from datetime import datetime, timezone

	# Build mock state
	mock_state = {
		"thread_id": body.thread_id,
		"image_path": f"test_{body.thread_id}.jpg",
		"items": body.items,
		"participants": [],
		"assignments": [],
		"totals": body.totals,
		"current_node": body.current_node,
		"audit_log": [
			{
				"timestamp": datetime.now(timezone.utc).isoformat(),
				"node": "test",
				"message": f"Created mock state with {len(body.items)} items",
				"details": {"mock": True, "item_count": len(body.items)},
			}
		],
		"pending_questions": [
			"Please provide the participants and assign each item.\n\n"
			"Extracted items:\n"
			+ "\n".join(f"  [{i}] {item['name']} — ${item.get('unit_price', item.get('price', '0.00'))}" for i, item in enumerate(body.items))
			+ "\n\nFor each item, specify which participant(s) share it and their "
			"fraction (fractions must sum to 1.00 per item)."
		] if body.current_node == "interview_pending" else [],
	}

	# Store in in-memory store
	_INMEM_STORE[body.thread_id] = _serialize_state(mock_state)

	return {"thread_id": body.thread_id, "state": _serialize_state(mock_state)}

