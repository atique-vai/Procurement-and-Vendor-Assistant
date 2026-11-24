from typing import Literal, Optional

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.graph.nodes.hitl_gate import hitl_gate_node
from app.graph.nodes.input_guardrail import input_guardrail_node
from app.graph.nodes.output_guardrail import output_guardrail_node
from app.graph.nodes.procurement_agent import procurement_agent_node
from app.graph.state import ProcurementGraphState

settings = get_settings()

# Singleton compiled graph instance
_compiled_graph = None
_sqlite_conn: Optional[aiosqlite.Connection] = None


# ==============================================================================
# CONDITIONAL ROUTING FUNCTIONS
# ==============================================================================


def route_after_input_guardrail(
    state: ProcurementGraphState,
) -> Literal["procurement_agent", "__end__"]:
    """
    Concept C5: If the input guardrail detected a prompt injection, out-of-scope
    query, or blacklisted vendor, short-circuit immediately to END.
    """
    if state.get("blocked", False):
        return END
    return "procurement_agent"


def route_after_agent(
    state: ProcurementGraphState,
) -> Literal["hitl_gate", "output_guardrail"]:
    """
    Concept E1: Checks whether a draft Purchase Requisition exists and exceeds
    the $500 automated approval threshold.
    - > $500  -> Route to `hitl_gate` (pauses via interrupt() for manager sign-off)
    - <= $500 -> Route directly to `output_guardrail` for auto-approval & PO commit
    """
    draft_po = state.get("draft_po") or {}
    total_amount = float(draft_po.get("total_amount", 0.0))

    if draft_po and total_amount > settings.hitl_approval_threshold:
        return "hitl_gate"

    return "output_guardrail"


def route_after_hitl_gate(
    state: ProcurementGraphState,
) -> Literal["output_guardrail", "procurement_agent"]:
    """
    Section 8 (Risks & Fallbacks): Handles the manager's HITL decision.
    - 'approved' -> Proceed to `output_guardrail` to scrub PII and commit final PO.
    - 'rejected' -> Route back to `procurement_agent` with the manager's rejection
                    notes so the requester can adjust quantities or cancel cleanly.
    """
    decision = (state.get("approval_decision") or "").lower()
    if decision == "approved":
        return "output_guardrail"
    return "procurement_agent"


# ==============================================================================
# GRAPH BUILDER & CHECKPOINTER INITIALIZATION
# ==============================================================================


def build_procurement_state_graph() -> StateGraph:
    """Constructs the deterministic LangGraph StateGraph topology."""
    workflow = StateGraph(ProcurementGraphState)

    # 1. Register Nodes
    workflow.add_node("input_guardrail", input_guardrail_node)
    workflow.add_node("procurement_agent", procurement_agent_node)
    workflow.add_node("hitl_gate", hitl_gate_node)
    workflow.add_node("output_guardrail", output_guardrail_node)

    # 2. Define Entry Point
    workflow.add_edge(START, "input_guardrail")

    # 3. Conditional Edge after Input Guardrail (Safe vs. Blocked)
    workflow.add_conditional_edges(
        "input_guardrail",
        route_after_input_guardrail,
        {
            "procurement_agent": "procurement_agent",
            END: END,
        },
    )

    # 4. Conditional Edge after Procurement Agent (>$500 HITL vs. <=$500 Auto-Commit)
    workflow.add_conditional_edges(
        "procurement_agent",
        route_after_agent,
        {
            "hitl_gate": "hitl_gate",
            "output_guardrail": "output_guardrail",
        },
    )

    # 5. Conditional Edge after HITL Gate (Manager Approved vs. Rejected)
    workflow.add_conditional_edges(
        "hitl_gate",
        route_after_hitl_gate,
        {
            "output_guardrail": "output_guardrail",
            "procurement_agent": "procurement_agent",
        },
    )

    # 6. Exit Edge after Output Guardrail & PO Commit
    workflow.add_edge("output_guardrail", END)

    return workflow


async def get_compiled_graph():
    """
    Returns a singleton compiled LangGraph instance backed by AsyncSqliteSaver
    for multi-turn conversation memory and HITL interrupt persistence (Concept C4).
    """
    global _compiled_graph, _sqlite_conn

    if _compiled_graph is None:
        db_path = settings.checkpoint_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        _sqlite_conn = await aiosqlite.connect(str(db_path))
        checkpointer = AsyncSqliteSaver(_sqlite_conn)
        await checkpointer.setup()

        workflow = build_procurement_state_graph()
        _compiled_graph = workflow.compile(checkpointer=checkpointer)

    return _compiled_graph


async def close_compiled_graph() -> None:
    """Close the checkpoint connection and allow the graph to be rebuilt."""
    global _compiled_graph, _sqlite_conn

    if _sqlite_conn is None:
        return

    await _sqlite_conn.close()
    _sqlite_conn = None
    _compiled_graph = None
