from pathlib import Path

import pytest

from app.memory import (
    delete_department_preferences,
    get_department_preferences,
    initialize_memory_database,
    save_department_preferences,
    update_department_preferences,
)


def test_department_preferences_persist_and_merge(tmp_path: Path) -> None:
    database_path = tmp_path / "memory.sqlite"

    assert get_department_preferences("Engineering", database_path=database_path) == {}
    saved = save_department_preferences(
        "Engineering",
        {"preferred_currency": "USD", "default_cost_center": "CC-ENG"},
        database_path=database_path,
    )
    updated = update_department_preferences(
        " Engineering ",
        {"default_cost_center": "CC-ENG-2", "preferred_vendors": ["vendor-1"]},
        database_path=database_path,
    )

    assert saved["default_cost_center"] == "CC-ENG"
    assert updated == {
        "preferred_currency": "USD",
        "default_cost_center": "CC-ENG-2",
        "preferred_vendors": ["vendor-1"],
    }
    assert get_department_preferences("Engineering", database_path=database_path) == updated


def test_memory_database_initialization_and_delete_are_idempotent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "nested" / "memory.sqlite"

    assert initialize_memory_database(database_path) == database_path.resolve()
    assert initialize_memory_database(database_path) == database_path.resolve()
    save_department_preferences("Finance", {"approval_limit": 1000}, database_path=database_path)

    assert delete_department_preferences("Finance", database_path=database_path)
    assert not delete_department_preferences("Finance", database_path=database_path)
    assert get_department_preferences("Finance", database_path=database_path) == {}


@pytest.mark.parametrize(
    ("department", "preferences", "error"),
    [
        ("  ", {}, ValueError),
        ("Engineering", {"": "invalid"}, ValueError),
        ("Engineering", {"unsupported": object()}, ValueError),
    ],
)
def test_invalid_department_preferences_are_rejected(
    tmp_path: Path,
    department: str,
    preferences: dict[str, object],
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        save_department_preferences(
            department,
            preferences,
            database_path=tmp_path / "memory.sqlite",
        )