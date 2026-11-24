import re
from typing import Any, Dict, List, Tuple

from langchain_core.messages import AIMessage

from app.graph.state import ProcurementGraphState

# ==============================================================================
# GUARDRAIL RULES & DEFINITIONS (Concept C5)
# ==============================================================================

# 1. Adversarial prompt-injection & budget-bypass patterns
INJECTION_PATTERNS: List[Tuple[str, str]] = [
    (
        r"ignore\s+(all\s+)?(previous\s+|prior\s+|budget\s+|policy\s+)?(instructions|rules|limits|guidelines)",
        "Prompt injection / policy override attempt detected.",
    ),
    (
        r"system\s*override|developer\s*mode|jailbreak|bypass\s+(approval|hitl|budget|limit)",
        "Unauthorized system override or HITL approval bypass attempt detected.",
    ),
    (
        r"approve\s+.*as\s+\$?\d+\s*(office\s+supplies|misc)",
        "Attempt to misclassify high-value spend to evade the $500 approval threshold.",
    ),
    (
        r"(reveal|print|dump|show)\s+(your\s+)?(system\s+prompt|hidden\s+instructions|api\s*key)",
        "Attempt to extract confidential system instructions or credentials.",
    ),
]

# 2. Explicitly Blacklisted / Sanctioned Vendors (Hard Block before LLM runs)
# Note: General unverified vendors like "ABC Tech" are handled by the agent so it can
# suggest approved catalog alternatives (e.g., Global IT Solutions) per Demo Scenario 1.
BLACKLISTED_VENDORS: Dict[str, str] = {
    "shadowsupply": "Sanctioned for counterfeit hardware components (Compliance Bulletin 2025-09).",
    "rogueit": "Blacklisted due to data-breach non-compliance (Security Manual Sec 6.1).",
    "apex grey market": "Prohibited grey-market reseller without OEM warranty.",
    "quickcash electronics": "Flagged for anti-fraud blacklist violation.",
}

# 3. Out-of-scope keywords (HR salaries, personal finance, unrelated tasks)
OUT_OF_SCOPE_PATTERNS: List[str] = [
    r"\b(salary|salaries|payroll|bonus|compensation\s+band)\b",
    r"\b(stock\s+market|crypto|bitcoin|personal\s+investment|tax\s+return)\b",
    r"\b(write\s+me\s+a\s+poem|tell\s+me\s+a\s+joke|recipe\s+for)\b",
]


def _extract_latest_user_text(state: ProcurementGraphState) -> str:
    """Extracts the plain text content of the most recent user message."""
    messages = state.get("messages", [])
    if not messages:
        return ""
    last_msg = messages[-1]
    content = getattr(last_msg, "content", "")
    if isinstance(content, list):
        return " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        ).strip()
    return str(content).strip()


def _check_input_safety(text: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Evaluates incoming text against injection, blacklist, and scope rules.
    Returns: (is_blocked, refusal_message, citations)
    """
    lowered = text.lower()

    # Check 1: Prompt Injection / Budget Bypass
    for pattern, reason in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            refusal = (
                "**Request Blocked by Security Guardrail (Policy Sec 1.4, p. 3)**\n\n"
                f"I cannot process this request because a policy-override or prompt-injection "
                f"pattern was detected (*{reason}*).\n\n"
                "All purchase requisitions must adhere strictly to Corporate Procurement Policy v2.4 "
                "and undergo automated budget and manager approval checks."
            )
            citations = [
                {
                    "doc_title": "Corporate_Procurement_Policy_v2.4.pdf",
                    "section": "Section 1.4 - System Integrity & Audit Controls",
                    "page": 3,
                    "snippet": "Attempts to circumvent spending thresholds, cost-center validations, or approval workflows are strictly prohibited and logged.",
                }
            ]
            return True, refusal, citations

    # Check 2: Explicitly Blacklisted Vendors
    for vendor_key, ban_reason in BLACKLISTED_VENDORS.items():
        if vendor_key in lowered:
            refusal = (
                f"**Blacklisted Vendor Refusal (Security Manual Sec 6.1, p. 10)**\n\n"
                f"Transactions with **{vendor_key.title()}** are strictly prohibited. "
                f"Reason: *{ban_reason}*\n\n"
                "Please specify an approved enterprise partner (such as **Apple Enterprise Partner**, "
                "**Dell Corporate**, or **Global IT Solutions**) or ask me to search our approved vendor catalog."
            )
            citations = [
                {
                    "doc_title": "Approved_Vendor_Security_Manual.pdf",
                    "section": "Section 6.1 - Sanctioned & Blacklisted Suppliers",
                    "page": 10,
                    "snippet": "Requisitions referencing entities on the Corporate Anti-Fraud & Security Blacklist must be rejected immediately prior to catalog lookup.",
                }
            ]
            return True, refusal, citations

    # Check 3: Out-of-Scope Queries (HR Payroll / Personal Advice)
    for pattern in OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, lowered):
            refusal = (
                "**Out-of-Scope Request**\n\n"
                "I am the **Enterprise Procurement & Vendor Management Assistant**. I can only assist "
                "with corporate hardware, cloud infrastructure, SaaS license requisitions, vendor "
                "catalog lookups, budget checks, and procurement policy compliance.\n\n"
                "For HR payroll or personal inquiries, please contact the People Operations portal."
            )
            return True, refusal, []

    return False, "", []


# ==============================================================================
# LANGGRAPH NODE FUNCTION
# ==============================================================================


async def input_guardrail_node(state: ProcurementGraphState) -> Dict[str, Any]:
    """
    Concept C5: Pre-execution Input Guardrail Node.
    Runs before `procurement_agent` to block prompt injections, blacklisted vendors,
    and out-of-scope requests without incurring LLM or MCP tool execution costs.
    """
    user_text = _extract_latest_user_text(state)
    is_blocked, refusal_message, citations = _check_input_safety(user_text)

    if is_blocked:
        return {
            "blocked": True,
            "block_reason": refusal_message,
            "status": "BLOCKED",
            "citations": citations,
            "messages": [AIMessage(content=refusal_message)],
            "visited_nodes": ["input_guardrail"],
        }

    return {
        "blocked": False,
        "block_reason": None,
        "status": "RUNNING",
        "visited_nodes": ["input_guardrail"],
    }
