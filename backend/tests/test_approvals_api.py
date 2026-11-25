from types import SimpleNamespace

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.api.approvals import router


class FakeCheckpointer:
    async def alist(self, config: object, *, limit: int | None = None) -> object:
        raise NotImplementedError


class FakeGraph:
    checkpointer = FakeCheckpointer()

    def __init__(self) -> None:
        self.resume_value: dict[str, str] | None = None

    async def aget_state(self, config: dict[str, object]) -> SimpleNamespace:
        return SimpleNamespace(
            values={"status": "AWAITING_APPROVAL"},
            next=("hitl_gate",),
            tasks=(),
            created_at=None,
        )

    async def ainvoke(
        self,
        command: object,
        config: dict[str, object],
    ) -> dict[str, str]:
        self.resume_value = command.resume
        return {"approval_decision": self.resume_value["decision"]}


def test_approval_route_maps_api_action_to_hitl_resume_contract() -> None:
    app = FastAPI()
    app.include_router(router)
    graph = FakeGraph()
    app.state.procurement_graph = graph

    response = TestClient(app).post(
        "/approvals/thread-1",
        json={
            "decision": "approve",
            "comment": "  Reviewed  ",
            "approver_id": " manager-1 ",
        },
    )

    assert response.status_code == 200, response.text
    assert graph.resume_value == {
        "decision": "approved",
        "notes": "Reviewed",
        "approver_id": "manager-1",
    }


class _PendingState(TypedDict, total=False):
    status: str
    draft_po: dict[str, object]


@pytest.mark.asyncio
async def test_list_pending_approvals_does_not_deadlock_sqlite_checkpointer(
    tmp_path,
) -> None:
    import asyncio
    from httpx import ASGITransport, AsyncClient

    builder = StateGraph(_PendingState)
    builder.add_node(
        "wait",
        lambda state: {
            "status": "AWAITING_APPROVAL",
            "draft_po": {
                "items": [{"product_id": "ITEM-1", "quantity": 1}],
                "total_amount": 900.0,
            },
        },
    )
    builder.add_edge(START, "wait")
    builder.add_edge("wait", END)

    async with aiosqlite.connect(str(tmp_path / "checkpoints.sqlite")) as conn:
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        compiled = builder.compile(checkpointer=saver)
        await compiled.ainvoke(
            {"status": "RUNNING"},
            {"configurable": {"thread_id": "pending-thread-1"}},
        )

        app = FastAPI()
        app.include_router(router)
        app.state.procurement_graph = compiled

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await asyncio.wait_for(client.get("/approvals"), timeout=5.0)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["thread_id"] == "pending-thread-1"
    assert payload[0]["details"]["draft_po"]["total_amount"] == 900.0
