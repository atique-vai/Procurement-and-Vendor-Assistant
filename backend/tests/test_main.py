from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main
from app.graph import workflow


def test_app_starts_workflow_and_serves_graph_definition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        workflow,
        "settings",
        SimpleNamespace(checkpoint_db_path=lambda: tmp_path / "checkpoints.sqlite"),
    )

    with TestClient(main.app) as client:
        assert client.get("/health").json() == {"status": "ok"}

        response = client.get("/graph/definition")

    assert response.status_code == 200
    assert response.json()["mermaid"]
