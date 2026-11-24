import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict

from langchain_core.messages import SystemMessage
from langgraph.types import interrupt

from app.config import get_settings
from app.graph.state import ProcurementGraphState

settings = get_settings()


def _upsert_pending_po_in_erp(state: ProcurementGraphState) -> str:
    """
    Ensures the draft requisition is persisted in the SQLite ERP `purchase_orders`
    table with status='PENDING_APPROVAL' so the React.js Manager Dashboard can display it.
    """
    draft_po: Dict[str, Any] = state.get("draft_po") or {}
    thread_id = state.get("thread_id", "unknown-thread")
    po_id = draft_po.get("po_id") or f"PO-2026-{abs(hash(thread_id)) % 900 + 100}"

    conn = sqlite3.connect(settings.erp_db_path())
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS purchase_orders (
                po_id TEXT PRIMARY KEY,
                thread_id TEXT,
                requester_name TEXT,
                department TEXT,
                cost_center_id TEXT,
                total_amount REAL,
                items_json TEXT,
                citations_json TEXT,
                status TEXT,
                approver_id TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO purchase_orders (
                po_id, thread_id, requester_name, department, cost_center_id,
                total_amount, items_json, citations_json, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL', ?, ?)
            ON CONFLICT(po_id) DO UPDATE SET
                total_amount = excluded.total_amount,
                items_json = excluded.items_json,
                citations_json = excluded.citations_json,
                status = 'PENDING_APPROVAL',
                updated_at = excluded.updated_at
            """,
            (
                po_id,
                thread_id,
                state.get("user_name", "Engineering Lead"),
                draft_po.get("department", "Engineering"),
                draft_po.get("cost_center_id", "CC-ENG-402"),
                float(draft_po.get("total_amount", 0.0)),
                json.dumps(draft_po.get("items", [])),
                json.dumps(state.get("citations", [])),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        return po_id
    finally:
        conn.close()


def _mark_po_rejected_in_erp(po_id: str, approver_id: str) -> None:
    """Updates the ERP record to REJECTED if the manager declines the requisition."""
    conn = sqlite3.connect(settings.erp_db_path())
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE purchase_orders
            SET status = 'REJECTED',
                approver_id = ?,
                updated_at = ?
            WHERE po_id = ?
            """,
            (approver_id, datetime.now(timezone.utc).isoformat(), po_id),
        )
        conn.commit()
    finally:
        conn.close()


async def hitl_gate_node(state: ProcurementGraphState) -> Dict[str, Any]:
    """
    Concept E1: Human-in-the-Loop (HITL) Approval Gate.
    Triggered whenever `total_amount > $500` (Policy Sec 2.1, p. 5).

    1. Writes/updates the `PENDING_APPROVAL` requisition in SQLite for the React Dashboard.
    2. Invokes LangGraph `interrupt()` to halt execution until `Command(resume=...)` is sent
       from `POST /approvals/{thread_id}`.
    3. Routes approved orders to `output_guardrail` or rejected orders back to `procurement_agent`.
    """
    draft_po = dict(state.get("draft_po") or {})
    po_id = _upsert_pending_po_in_erp(state)
    draft_po["po_id"] = po_id
    draft_po["status"] = "PENDING_APPROVAL"

    # Suspend execution and surface approval card payload to the checkpoint
    manager_response: Dict[str, Any] = interrupt(
        {
            "event": "HITL_APPROVAL_REQUIRED",
            "po_id": po_id,
            "thread_id": state.get("thread_id"),
            "requester_name": state.get("user_name", "Engineering Lead"),
            "cost_center_id": draft_po.get("cost_center_id", "CC-ENG-402"),
            "total_amount": draft_po.get("total_amount", 0.0),
            "threshold_usd": settings.hitl_approval_threshold,
            "items": draft_po.get("items", []),
            "citations": state.get("citations", []),
            "message": (
                f"Requisition {po_id} (${draft_po.get('total_amount', 0):,.2f}) exceeds "
                f"the ${settings.hitl_approval_threshold:,.2f} automated threshold "
                f"(Policy Sec 2.1, p. 5) and requires Department Manager sign-off."
            ),
        }
    )

    # --- Execution resumes here when Manager submits Approve/Reject in React ---
    decision = (manager_response.get("decision") or "rejected").lower()
    approver_id = manager_response.get("approver_id", "MGR-TANVIR-01")
    approver_name = manager_response.get("approver_name", "Tanvir Ahmed")
    notes = manager_response.get("notes", "").strip()

    if decision == "approved":
        draft_po["status"] = "APPROVED"
        return {
            "draft_po": draft_po,
            "requires_approval": False,
            "approval_decision": "approved",
            "approver_id": approver_id,
            "approver_name": approver_name,
            "manager_notes": notes,
            "status": "APPROVED",
            "visited_nodes": ["hitl_gate"],
        }

    # Handle rejection: update ERP status and notify the agent to inform the requester
    _mark_po_rejected_in_erp(po_id, approver_id)
    draft_po["status"] = "REJECTED"

    rejection_context = (
        f"[HITL MANAGER DECISION: REJECTED] Department Manager {approver_name} ({approver_id}) "
        f"rejected Purchase Requisition {po_id} (${draft_po.get('total_amount', 0):,.2f}). "
        f"Manager Notes: '{notes or 'No specific notes provided.'}'. "
        "Inform the user politely about the rejection, include the manager's notes, and ask "
        "if they would like to modify the quantities/specifications or cancel the request."
    )

    return {
        "draft_po": draft_po,
        "requires_approval": False,
        "approval_decision": "rejected",
        "approver_id": approver_id,
        "approver_name": approver_name,
        "manager_notes": notes,
        "status": "REJECTED",
        "messages": [SystemMessage(content=rejection_context)],
        "visited_nodes": ["hitl_gate"],
    }
