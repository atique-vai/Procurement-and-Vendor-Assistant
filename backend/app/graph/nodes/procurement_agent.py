"""LLM-backed procurement conversation and purchase-order drafting node."""

import math
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import get_settings
from app.graph.state import ProcurementGraphState
from app.llm import get_structured_chat_model
from app.mcp import lookup_procurement_context
from app.prompts import build_cpo_agent_system_message
from app.rag import retrieve_policy_context
from app.schemas.po import (
    PurchaseOrderItem,
    PurchaseOrderProposal as PurchaseOrderDraft,
)


class ProcurementAgentResponse(BaseModel):
    """Validated response returned by the procurement model."""

    model_config = ConfigDict(extra="forbid")

    response: str = Field(min_length=1)
    draft_po: PurchaseOrderDraft | None = None

    @field_validator("response")
    @classmethod
    def normalize_response(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("response must not be blank")
        return normalized


_UNGROUNDED_DRAFT_MESSAGE = (
    "I can't prepare a purchase-order draft until the requested items, vendors, and "
    "current prices are verified against the approved procurement catalog."
)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
        return "\n".join(
            str(block.get("text", "")) if isinstance(block, Mapping) else str(block)
            for block in content
        ).strip()
    return str(content).strip()


def _latest_user_message(messages: Sequence[BaseMessage]) -> HumanMessage | None:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message
    return None


def _verified_catalog_entry(
    item: PurchaseOrderItem,
    procurement_context: Mapping[str, Any],
) -> bool:
    catalog_items = procurement_context.get("catalog_items")
    if not isinstance(catalog_items, list):
        return False

    for entry in catalog_items:
        if not isinstance(entry, Mapping):
            continue
        if (
            entry.get("approved") is not True
            or entry.get("product_id") != item.product_id
            or entry.get("vendor_id") != item.vendor_id
            or str(entry.get("currency", "")).upper() != item.currency
        ):
            continue
        catalog_name = entry.get("item_name", entry.get("name"))
        vendor_name = entry.get("vendor_name")
        if (
            not isinstance(catalog_name, str)
            or catalog_name.strip().casefold() != item.item_name.strip().casefold()
            or not isinstance(vendor_name, str)
            or vendor_name.strip().casefold() != item.vendor_name.strip().casefold()
        ):
            continue
        try:
            catalog_price = float(entry["unit_price"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(catalog_price) and math.isclose(
            catalog_price, item.unit_price, rel_tol=0, abs_tol=0.005
        ):
            return True
    return False


def _draft_is_grounded(
    draft: PurchaseOrderDraft,
    procurement_context: Any,
) -> bool:
    if not isinstance(procurement_context, Mapping):
        return False
    return all(
        _verified_catalog_entry(item, procurement_context)
        for item in draft.items
    )


def _draft_po_dict(
    draft: PurchaseOrderDraft,
    state: ProcurementGraphState,
) -> dict[str, Any]:
    items = []
    total_amount = 0.0
    for item in draft.items:
        line_total = round(item.quantity * item.unit_price, 2)
        total_amount += line_total
        items.append({**item.model_dump(), "line_total": line_total})

    return {
        "items": items,
        "total_amount": round(total_amount, 2),
        "currency": "USD",
        "department": draft.department,
        "cost_center_id": state.get("default_cost_center") or draft.cost_center_id,
        "status": "DRAFT",
    }


def _build_model() -> Any:
    return get_structured_chat_model(ProcurementAgentResponse)


def _merge_catalog_entries(
    existing: Any,
    fresh: Any,
    *,
    key_field: str,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    fallback: list[dict[str, Any]] = []
    for source in (existing, fresh):
        if not isinstance(source, list):
            continue
        for entry in source:
            if not isinstance(entry, Mapping):
                continue
            item = dict(entry)
            key = item.get(key_field)
            if isinstance(key, str) and key.strip():
                merged[key] = item
            elif item not in fallback:
                fallback.append(item)
    return [*merged.values(), *fallback]


def _merge_procurement_context(
    existing: Mapping[str, Any],
    fresh: Mapping[str, Any],
) -> dict[str, Any]:
    merged = {**dict(existing), **dict(fresh)}
    merged["catalog_items"] = _merge_catalog_entries(
        existing.get("catalog_items"),
        fresh.get("catalog_items"),
        key_field="product_id",
    )
    merged["approved_vendors"] = _merge_catalog_entries(
        existing.get("approved_vendors"),
        fresh.get("approved_vendors"),
        key_field="vendor_id",
    )
    if fresh.get("budget") is None and existing.get("budget") is not None:
        merged["budget"] = existing.get("budget")
    return merged


def _normalize_model_messages(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Ensure Gemini never sees trailing SystemMessages or ends on an AIMessage."""
    normalized: list[BaseMessage] = []
    for message in messages:
        if isinstance(message, SystemMessage):
            text = _content_text(message.content)
            if text:
                normalized.append(HumanMessage(content=f"[Workflow Notice]\n{text}"))
        else:
            normalized.append(message)
    if normalized and isinstance(normalized[-1], AIMessage):
        normalized.append(
            HumanMessage(content="Please respond to the latest workflow update.")
        )
    return normalized


async def procurement_agent_node(
    state: ProcurementGraphState,
) -> dict[str, Any]:
    """Answer the latest procurement message and produce only grounded PO drafts."""
    messages = state.get("messages", [])
    if state.get("blocked", False):
        return {"visited_nodes": ["procurement_agent"]}

    latest_user_message = _latest_user_message(messages)
    if latest_user_message is None or not _content_text(latest_user_message.content):
        raise ValueError("The procurement agent requires a non-empty user message.")

    existing_procurement_context = state.get("procurement_context", {})
    if not isinstance(existing_procurement_context, Mapping):
        raise TypeError("Procurement context must be a mapping.")
    erp_context = await lookup_procurement_context(
        _content_text(latest_user_message.content),
        cost_center_id=state.get("default_cost_center"),
    )
    if not isinstance(erp_context, Mapping):
        raise TypeError("The ERP MCP client must return a mapping.")
    procurement_context = _merge_procurement_context(
        existing_procurement_context,
        erp_context,
    )
    citations = state.get("citations", [])
    if not isinstance(citations, list):
        raise TypeError("Procurement state citations must be a list.")
    policy_result = await retrieve_policy_context(
        _content_text(latest_user_message.content)
    )
    combined_citations: list[dict[str, Any]] = []
    for citation in [*citations, *policy_result.citations]:
        if not isinstance(citation, Mapping):
            raise TypeError("Procurement citations must be mappings.")
        citation_dict = dict(citation)
        if citation_dict not in combined_citations:
            combined_citations.append(citation_dict)

    context = {
        "procurement_context": procurement_context,
        "policy_context": policy_result.context,
        "policy_citations": combined_citations,
        "requester": {
            "name": state.get("user_name"),
            "user_id": state.get("user_id"),
            "default_cost_center": state.get("default_cost_center"),
        },
        "approval_threshold_usd": get_settings().hitl_approval_threshold,
    }
    system_message = build_cpo_agent_system_message(context)
    model_messages = [system_message, *_normalize_model_messages(messages)]
    model = _build_model()
    model_result = await model.ainvoke(model_messages)
    agent_response = ProcurementAgentResponse.model_validate(model_result)

    draft_po: dict[str, Any] | None = None
    response_text = agent_response.response.strip()
    if agent_response.draft_po is not None:
        if _draft_is_grounded(agent_response.draft_po, procurement_context):
            draft_po = _draft_po_dict(agent_response.draft_po, state)
        else:
            response_text = _UNGROUNDED_DRAFT_MESSAGE

    requires_approval = bool(
        draft_po
        and draft_po["total_amount"] > get_settings().hitl_approval_threshold
    )
    return {
        "messages": [AIMessage(content=response_text)],
        "draft_po": draft_po,
        "procurement_context": procurement_context,
        "citations": combined_citations,
        "requires_approval": requires_approval,
        "status": "AWAITING_APPROVAL" if requires_approval else "RUNNING",
        "visited_nodes": ["procurement_agent"],
    }