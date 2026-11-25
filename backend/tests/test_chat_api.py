import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.api.chat import router


class SlowGraph:
    async def ainvoke(self, input: object, config: dict[str, object]) -> object:
        await asyncio.sleep(1)
        return {"response": "This should not be reached."}


def test_chat_times_out_when_workflow_does_not_respond(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_api, "_WORKFLOW_TIMEOUT_SECONDS", 0.01)
    app = FastAPI()
    app.include_router(router)
    app.state.procurement_graph = SlowGraph()

    response = TestClient(app).post("/chat", json={"message": "Find a vendor"})

    assert response.status_code == 504
    assert response.json()["detail"] == (
        "The procurement workflow timed out. Please try again."
    )


def test_chat_passes_thread_id_into_workflow_input_state() -> None:
    captured_inputs: list[dict[str, object]] = []

    class CapturingGraph:
        async def ainvoke(
            self, input: dict[str, object], config: dict[str, object]
        ) -> dict[str, object]:
            captured_inputs.append(input)
            return {"response": "OK", "citations": [], "draft_po": None}

    app = FastAPI()
    app.include_router(router)
    app.state.procurement_graph = CapturingGraph()

    response = TestClient(app).post(
        "/chat",
        json={"message": "Find a vendor", "thread_id": "thread-xyz"},
    )

    assert response.status_code == 200
    assert captured_inputs[0]["thread_id"] == "thread-xyz"
