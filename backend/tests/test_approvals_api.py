from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

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
