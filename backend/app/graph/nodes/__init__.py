"""
LangGraph Execution Nodes Package.
Exports the 4 deterministic stages of the procurement pipeline:
1. input_guardrail_node  (Concept C5: Prompt injection & blacklisted vendor screen)
2. procurement_agent_node (Concept C3: ReAct agent loop with Qdrant RAG & FastMCP tools)
3. hitl_gate_node         (Concept E1: LangGraph interrupt() gate for orders > $500)
4. output_guardrail_node  (Concept C5 & PO Commit: PII redaction & final ERP write)
"""

from app.graph.nodes.hitl_gate import hitl_gate_node
from app.graph.nodes.input_guardrail import input_guardrail_node
from app.graph.nodes.output_guardrail import output_guardrail_node
from app.graph.nodes.procurement_agent import procurement_agent_node

__all__ = [
    "input_guardrail_node",
    "procurement_agent_node",
    "hitl_gate_node",
    "output_guardrail_node",
]
