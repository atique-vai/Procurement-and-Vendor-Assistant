"""Endpoints for listing and resolving human approval interrupts."""

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol, cast

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from langgraph.types import Command

from app.schemas.api_models import (
    ApprovalDecision,
    ApprovalDecisionResult,
    ApprovalItem,
)


router = APIRouter(prefix="/approvals", tags=["approvals"])
logger = logging.getLogger(__name__)
_APPROVAL_TIMEOUT_SECONDS = 120

_APPROVAL_DETAIL_KEYS = (
    "approval",
    "approval_request",
    "purchase_order",
    "po_draft",
    "draft_po",
    "request",
)
_APPROVAL_STATUSES = {
    "awaiting_approval",
    "approval_pending",
    "pending",
    "requires_approval",
}


class ApprovalSnapshot(Protocol):
    """Portion of a LangGraph state snapshot used by these endpoints."""

    values: Mapping[str, Any]
    next: tuple[str, ...]
    tasks: tuple[Any, ...]
    created_at: Any


class Checkpointer(Protocol):
    def alist(
        self, config: Any, *, limit: int | None = None
    ) -> AsyncIterator[Any]: ...


class ApprovalGraph(Protocol):
    checkpointer: Checkpointer | None

    async def aget_state(self, config: dict[str, Any]) -> ApprovalSnapshot: ...

    async def ainvoke(
        self, input: Any, config: dict[str, Any]
    ) -> Mapping[str, Any]: ...


def _get_graph(request: Request) -> ApprovalGraph:
    graph = getattr(request.app.state, "procurement_graph", None)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The procurement workflow is not initialized.",
        )

    checkpointer = getattr(graph, "checkpointer", None)
    if (
        not callable(getattr(graph, "aget_state", None))
        or not callable(getattr(graph, "ainvoke", None))
        or not callable(getattr(checkpointer, "alist", None))
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The procurement workflow does not support approval operations.",
        )
    return cast(ApprovalGraph, graph)


def _thread_id(config: Any) -> str | None:
    if not isinstance(config, Mapping):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, Mapping):
        return None
    thread_id = configurable.get("thread_id")
    return str(thread_id) if thread_id is not None else None


def _is_pending_approval(snapshot: ApprovalSnapshot) -> bool:
    values = snapshot.values
    state_status = values.get("approval_status", values.get("status", ""))
    if str(state_status).strip().lower() in _APPROVAL_STATUSES:
        return True
    if values.get("approval_required") is True or values.get("requires_approval") is True:
        return True

    for task in snapshot.tasks:
        task_name = str(getattr(task, "name", "")).lower()
        if "approval" in task_name or "hitl" in task_name:
            return True

        for interrupt in getattr(task, "interrupts", ()):
            interrupt_value = getattr(interrupt, "value", None)
            if isinstance(interrupt_value, Mapping):
                interrupt_type = str(
                    interrupt_value.get("type", interrupt_value.get("kind", ""))
                ).lower()
                if "approval" in interrupt_type or "hitl" in interrupt_type:
                    return True
    return False


def _approval_details(
    values: Mapping[str, Any],
    snapshot: ApprovalSnapshot | None = None,
) -> dict[str, Any]:
    details = {
        key: values[key]
        for key in _APPROVAL_DETAIL_KEYS
        if key in values and values[key] is not None
    }
    if snapshot is not None and "approval_request" not in details:
        for task in snapshot.tasks:
            for interrupt in getattr(task, "interrupts", ()):
                interrupt_value = getattr(interrupt, "value", None)
                if isinstance(interrupt_value, Mapping):
                    details["approval_request"] = dict(interrupt_value)
                    return details
    return details


@router.get(
    "",
    response_model=list[ApprovalItem],
    summary="List pending approvals",
)
async def list_pending_approvals(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ApprovalItem]:
    """List the most recent checkpoint threads paused at an approval gate."""
    graph = _get_graph(request)
    checkpointer = graph.checkpointer
    if checkpointer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The procurement workflow has no checkpoint store.",
        )

    thread_configs: list[tuple[str, Any]] = []
    seen_thread_ids: set[str] = set()
    async for checkpoint in checkpointer.alist(None, limit=limit * 10):
        config = getattr(checkpoint, "config", None)
        thread_id = _thread_id(config)
        if thread_id is None or thread_id in seen_thread_ids:
            continue
        seen_thread_ids.add(thread_id)
        thread_configs.append((thread_id, config))

    pending: list[ApprovalItem] = []
    for thread_id, config in thread_configs:
        snapshot = await graph.aget_state(config)
        if not _is_pending_approval(snapshot):
            continue

        values = snapshot.values
        pending.append(
            ApprovalItem(
                thread_id=thread_id,
                status=str(values.get("approval_status", "pending")),
                next=list(snapshot.next),
                created_at=snapshot.created_at,
                details=jsonable_encoder(_approval_details(values, snapshot)),
            )
        )
        if len(pending) >= limit:
            break
    return pending


@router.post(
    "/{thread_id}",
    response_model=ApprovalDecisionResult,
    summary="Approve or reject a pending request",
)
async def resolve_approval(
    thread_id: str,
    decision: ApprovalDecision,
    request: Request,
) -> ApprovalDecisionResult:
    """Resume a pending workflow with the submitted human decision."""
    graph = _get_graph(request)
    config = {
        "configurable": {"thread_id": thread_id},
        "tags": ["procurement-approval"],
        "metadata": {
            "thread_id": thread_id,
            "workflow": "procurement",
            "approval_decision": decision.decision,
        },
        "run_name": "procurement_approval",
    }
    snapshot = await graph.aget_state(config)
    if not _is_pending_approval(snapshot):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This workflow is not waiting for an approval decision.",
        )

    resume_value: dict[str, str] = {
        "decision": "approved" if decision.decision == "approve" else "rejected"
    }
    if decision.comment is not None:
        resume_value["notes"] = decision.comment
    if decision.approver_id is not None:
        resume_value["approver_id"] = decision.approver_id
    if decision.approver_name is not None:
        resume_value["approver_name"] = decision.approver_name

    try:
        result = await asyncio.wait_for(
            graph.ainvoke(Command(resume=resume_value), config=config),
            timeout=_APPROVAL_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        logger.error("Approval resume timed out for thread %s", thread_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Resolving the approval timed out. Please try again.",
        ) from exc
    except (RuntimeError, ValueError, TypeError) as exc:
        logger.exception("Approval resume failed for thread %s", thread_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The procurement workflow could not resume after the decision. Check backend logs.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected approval resume failure for thread %s", thread_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The procurement workflow or an external AI service is unavailable. Please try again.",
        ) from exc
    return ApprovalDecisionResult(
        thread_id=thread_id,
        decision=decision.decision,
        state=jsonable_encoder(dict(result)),
    )