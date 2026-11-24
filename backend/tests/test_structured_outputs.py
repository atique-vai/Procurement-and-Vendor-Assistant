import pytest
from pydantic import ValidationError

from app.schemas import (
    ApprovalDecision,
    ChatRequest,
    PurchaseOrder,
    PurchaseOrderItem,
)


def _purchase_order(total_amount: float) -> PurchaseOrder:
    return PurchaseOrder(
        items=[
            PurchaseOrderItem(
                product_id="laptop-01",
                item_name="Business Laptop",
                vendor_id="vendor-01",
                vendor_name="Approved Computers",
                quantity=2,
                unit_price=400,
                currency="USD",
                line_total=800,
            )
        ],
        total_amount=total_amount,
    )


def test_chat_request_normalizes_input() -> None:
    request = ChatRequest(message="  Find a vendor  ", thread_id=" thread-1 ")

    assert request.message == "Find a vendor"
    assert request.thread_id == "thread-1"


def test_approval_decision_normalizes_optional_fields() -> None:
    decision = ApprovalDecision(
        decision="approve",
        comment="  Looks good  ",
        approver_id=" manager-1 ",
    )

    assert decision.comment == "Looks good"
    assert decision.approver_id == "manager-1"


def test_purchase_order_rejects_inconsistent_totals() -> None:
    with pytest.raises(ValidationError, match="total_amount"):
        _purchase_order(799)