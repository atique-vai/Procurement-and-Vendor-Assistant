import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage

from app.config import get_settings
from app.graph.state import ProcurementGraphState

settings = get_settings()

# ==============================================================================
# OUTPUT PII & FINANCIAL IDENTIFIER REDACTION RULES (Concept C5)
# ==============================================================================

REDACTION_PATTERNS: List[Tuple[str, str]] = [
    # US/Corporate EIN / Tax IDs (e.g., 12-3456789)
    (r"\b\d{2}-\d{7}\b", "[REDACTED-CORPORATE-EIN]"),
    # International Bank Account Numbers (IBAN)
    (r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", "[REDACTED-VENDOR-IBAN]"),
    # Bank Routing / SWIFT / Account references
    (
        r"(?i)(routing|account|swift)\s*(number|no|#|:)?\s*[:#]?\s*\d{6,17}",
        "[REDACTED-BANK-DETAIL]",
    ),
    # Social Security Numbers
    (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED-SSN]"),
    # API Keys / Bearer Tokens
    (r"\b(AIza[0-9A-Za-z\-_]{35}|sk-[a-zA-Z0-9]{20,})\b", "[REDACTED-API-KEY]"),
]


def _redact_sensitive_text(text: str) -> str:
    """Scrubs sensitive tax, banking, and credential strings from LLM outputs."""
    scrubbed = text
    for pattern, replacement in REDACTION_PATTERNS:
        scrubbed = re.sub(pattern, replacement, scrubbed)
    return scrubbed


def _commit_final_po_to_erp(
    state: ProcurementGraphState,
    draft_po: Dict[str, Any],
) -> Optional[str]:
    """
    Commits an approved (or <= $500 auto-approved) Purchase Order to the SQLite ERP
    `purchase_orders` ledger and deducts the total from `department_budgets`.
    """
    total_amount = float(draft_po.get("total_amount", 0.0))
    items = draft_po.get("items", [])

    # Only commit if there is an actual requisition with items and positive spend
    if not items or total_amount <= 0:
        return None

    thread_id = state.get("thread_id", "unknown-thread")
    po_id = draft_po.get("po_id") or f"PO-2026-{abs(hash(thread_id)) % 900 + 100}"
    cost_center_id = draft_po.get("cost_center_id", "CC-ENG-402")
    approver_id = state.get("approver_id") or "AUTO-POLICY-SEC-2.1"
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(settings.erp_db_path())
    try:
        cursor = conn.cursor()

        # Ensure purchase_orders table exists
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

        # Check if this PO was already committed to prevent double budget deduction
        cursor.execute(
            "SELECT status FROM purchase_orders WHERE po_id = ?",
            (po_id,),
        )
        existing = cursor.fetchone()
        already_committed = existing is not None and existing[0] == "COMMITTED"

        # Upsert PO as COMMITTED
        cursor.execute(
            """
            INSERT INTO purchase_orders (
                po_id, thread_id, requester_name, department, cost_center_id,
                total_amount, items_json, citations_json, status, approver_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'COMMITTED', ?, ?, ?)
            ON CONFLICT(po_id) DO UPDATE SET
                total_amount = excluded.total_amount,
                items_json = excluded.items_json,
                citations_json = excluded.citations_json,
                status = 'COMMITTED',
                approver_id = excluded.approver_id,
                updated_at = excluded.updated_at
            """,
            (
                po_id,
                thread_id,
                state.get("user_name", "Engineering Lead"),
                draft_po.get("department", "Engineering"),
                cost_center_id,
                total_amount,
                json.dumps(items),
                json.dumps(state.get("citations", [])),
                approver_id,
                now_iso,
                now_iso,
            ),
        )

        # Deduct from department Q4 remaining budget if not already deducted
        if not already_committed:
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='department_budgets'
                """
            )
            if cursor.fetchone():
                cursor.execute(
                    """
                    UPDATE department_budgets
                    SET remaining_budget = MAX(0, remaining_budget - ?),
                        spent_budget = spent_budget + ?
                    WHERE cost_center_id = ?
                    """,
                    (total_amount, total_amount, cost_center_id),
                )

        conn.commit()
        return po_id
    finally:
        conn.close()


# ==============================================================================
# LANGGRAPH NODE FUNCTION
# ==============================================================================


async def output_guardrail_node(state: ProcurementGraphState) -> Dict[str, Any]:
    """
    Concept C5 & Final PO Commit Node:
    1. Commits approved requisitions (<= $500 auto-approved or manager-approved via HITL)
       to the SQLite ERP database and updates remaining Q4 department budgets.
    2. Redacts sensitive corporate EINs, vendor IBANs, or API keys from responses.
    3. Emits the final confirmation receipt when resuming from manager approval.
    """
    draft_po = dict(state.get("draft_po") or {})
    approval_decision = (state.get("approval_decision") or "").lower()
    final_po_id: Optional[str] = state.get("final_po_id")

    # Commit PO if a valid draft exists (either <= $500 auto-approved or HITL approved)
    if draft_po and draft_po.get("items") and draft_po.get("status") != "REJECTED":
        committed_id = _commit_final_po_to_erp(state, draft_po)
        if committed_id:
            final_po_id = committed_id
            draft_po["po_id"] = committed_id
            draft_po["status"] = "COMMITTED"

    # Extract latest message and scrub any sensitive patterns
    messages = state.get("messages", [])
    latest_text = ""
    if messages and hasattr(messages[-1], "content"):
        raw = messages[-1].content
        if isinstance(raw, list):
            latest_text = "\n".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in raw
            )
        else:
            latest_text = str(raw)

    # If resuming directly from Manager HITL approval, generate the final PO receipt message
    if approval_decision == "approved" and final_po_id:
        approver_name = state.get("approver_name", "Tanvir Ahmed")
        notes = state.get("manager_notes", "")
        note_line = f"\n* **Manager Notes:** {notes}" if notes else ""

        receipt_msg = (
            f"**Purchase Order `{final_po_id}` Approved & Committed!**\n\n"
            f"* **Approved By:** {approver_name}\n"
            f"* **Cost Center:** `{draft_po.get('cost_center_id', 'CC-ENG-402')}`\n"
            f"* **Total Committed Amount:** **${float(draft_po.get('total_amount', 0)):,.2f}**"
            f"{note_line}\n\n"
            "The requisition has been dispatched to the ERP ledger and deducted from your Q4 department budget."
        )
        scrubbed_reply = _redact_sensitive_text(receipt_msg)
        return {
            "draft_po": draft_po,
            "final_po_id": final_po_id,
            "status": "COMPLETED",
            "messages": [AIMessage(content=scrubbed_reply)],
            "visited_nodes": ["output_guardrail"],
        }

    # Otherwise scrub the agent's existing response message in place if needed
    scrubbed_reply = _redact_sensitive_text(latest_text)
    updated_messages = []
    if scrubbed_reply and scrubbed_reply != latest_text:
        updated_messages = [AIMessage(content=scrubbed_reply)]

    return {
        "draft_po": draft_po if draft_po else None,
        "final_po_id": final_po_id,
        "status": "COMPLETED",
        "messages": updated_messages,
        "visited_nodes": ["output_guardrail"],
    }
