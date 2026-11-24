"""
LangGraph Orchestration Package (Concept C7 & E1).
Contains the stateful procurement workflow, state schema, and execution nodes:
- input_guardrail: Prompt injection & blacklisted vendor screening
- procurement_agent: ReAct tool-calling & policy-grounded reasoning loop
- hitl_gate: Human-in-the-Loop interrupt() gate for orders > $500
- output_guardrail: PII/IBAN redaction & final ERP PO commitment
"""

from app.graph.state import ProcurementGraphState
from app.graph.workflow import close_compiled_graph, get_compiled_graph

__all__ = [
    "ProcurementGraphState",
    "close_compiled_graph",
    "get_compiled_graph",
]
