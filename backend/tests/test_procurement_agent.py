from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.graph.nodes import procurement_agent


class FakeModel:
    def __init__(self, response: procurement_agent.ProcurementAgentResponse) -> None:
        self.response = response

    async def ainvoke(self, messages: list[object]) -> procurement_agent.ProcurementAgentResponse:
        assert messages[0].type == "system"
        return self.response


async def _empty_policy_result(query: str) -> SimpleNamespace:
    return SimpleNamespace(context="", citations=[])


async def _lookup_context(
    query: str,
    *,
    cost_center_id: str | None = None,
) -> dict[str, object]:
    return {
        **_catalog_context(),
        "approved_vendors": [],
        "budget": None,
    }


def _catalog_context() -> dict[str, object]:
    return {
        "catalog_items": [
            {
                "approved": True,
                "product_id": "laptop-01",
                "item_name": "Business Laptop",
                "vendor_id": "vendor-01",
                "vendor_name": "Approved Computers",
                "unit_price": 400.0,
                "currency": "USD",
            }
        ]
    }


def _state() -> dict[str, object]:
    return {
        "messages": [HumanMessage(content="Draft an order for two business laptops.")],
        "procurement_context": _catalog_context(),
        "citations": [],
        "default_cost_center": "CC-IT-01",
    }


@pytest.mark.asyncio
async def test_procurement_agent_builds_grounded_order_and_flags_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = procurement_agent.PurchaseOrderDraft(
        items=[
            procurement_agent.PurchaseOrderItem(
                product_id="laptop-01",
                item_name="Business Laptop",
                vendor_id="vendor-01",
                vendor_name="Approved Computers",
                quantity=2,
                unit_price=400,
                currency="USD",
            )
        ]
    )
    model_response = procurement_agent.ProcurementAgentResponse(
        response="I prepared the purchase-order draft.",
        draft_po=draft,
    )
    monkeypatch.setattr(
        procurement_agent, "_build_model", lambda: FakeModel(model_response)
    )
    monkeypatch.setattr(
        procurement_agent, "retrieve_policy_context", _empty_policy_result
    )
    monkeypatch.setattr(
        procurement_agent, "lookup_procurement_context", _lookup_context
    )
    monkeypatch.setattr(
        procurement_agent,
        "get_settings",
        lambda: SimpleNamespace(hitl_approval_threshold=500),
    )

    result = await procurement_agent.procurement_agent_node(_state())

    assert result["draft_po"]["total_amount"] == 800
    assert result["draft_po"]["cost_center_id"] == "CC-IT-01"
    assert result["requires_approval"] is True
    assert result["status"] == "AWAITING_APPROVAL"


@pytest.mark.asyncio
async def test_procurement_agent_rejects_order_not_in_approved_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = procurement_agent.PurchaseOrderDraft(
        items=[
            procurement_agent.PurchaseOrderItem(
                product_id="unlisted-item",
                item_name="Business Laptop",
                vendor_id="vendor-01",
                vendor_name="Approved Computers",
                quantity=1,
                unit_price=400,
                currency="USD",
            )
        ]
    )
    model_response = procurement_agent.ProcurementAgentResponse(
        response="I prepared the purchase-order draft.",
        draft_po=draft,
    )
    monkeypatch.setattr(
        procurement_agent, "_build_model", lambda: FakeModel(model_response)
    )
    monkeypatch.setattr(
        procurement_agent, "retrieve_policy_context", _empty_policy_result
    )
    monkeypatch.setattr(
        procurement_agent, "lookup_procurement_context", _lookup_context
    )
    monkeypatch.setattr(
        procurement_agent,
        "get_settings",
        lambda: SimpleNamespace(hitl_approval_threshold=500),
    )

    result = await procurement_agent.procurement_agent_node(_state())

    assert result["draft_po"] is None
    assert "verified against the approved procurement catalog" in result["messages"][0].content
    assert result["requires_approval"] is False


@pytest.mark.asyncio
async def test_procurement_agent_normalizes_rejection_system_messages_and_preserves_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_messages: list[object] = []

    class CapturingModel:
        async def ainvoke(
            self, messages: list[object]
        ) -> procurement_agent.ProcurementAgentResponse:
            captured_messages.extend(messages)
            return procurement_agent.ProcurementAgentResponse(
                response="Your request was rejected by the manager.",
                draft_po=None,
            )

    async def _empty_lookup(query: str, *, cost_center_id: str | None = None) -> dict[str, object]:
        return {"catalog_items": [], "approved_vendors": [], "budget": None}

    monkeypatch.setattr(procurement_agent, "_build_model", lambda: CapturingModel())
    monkeypatch.setattr(procurement_agent, "retrieve_policy_context", _empty_policy_result)
    monkeypatch.setattr(procurement_agent, "lookup_procurement_context", _empty_lookup)
    monkeypatch.setattr(
        procurement_agent,
        "get_settings",
        lambda: SimpleNamespace(hitl_approval_threshold=500),
    )

    state = {
        "messages": [
            HumanMessage(content="Draft an order for two business laptops."),
            AIMessage(content="Drafted PO."),
            SystemMessage(content="[HITL MANAGER DECISION: REJECTED] Over budget."),
        ],
        "procurement_context": _catalog_context(),
        "citations": [],
        "default_cost_center": "CC-IT-01",
    }

    result = await procurement_agent.procurement_agent_node(state)

    assert captured_messages[0].type == "system"
    assert all(msg.type != "system" for msg in captured_messages[1:])
    assert captured_messages[-1].type == "human"
    assert "[HITL MANAGER DECISION: REJECTED]" in captured_messages[-1].content
    assert len(result["procurement_context"]["catalog_items"]) == 1
