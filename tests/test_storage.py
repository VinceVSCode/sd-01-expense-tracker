"""Tests for the JSON storage layer. Every test works in a temporary folder."""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from expense_tracker.domain import Expense
from expense_tracker.storage import JsonExpenseRepository, StorageError

EXPENSES = [
    Expense(1, date(2026, 11, 3), "food", Decimal("12.50"), "lunch"),
    Expense(2, date(2026, 11, 4), "transport", Decimal("2.40")),
]


def write(path: Path, document: object) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def record(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": 1,
        "date": "2026-11-03",
        "category": "food",
        "amount": "12.50",
        "description": "",
    }
    return {**base, **changes}


def test_a_missing_file_means_no_expenses(tmp_path: Path) -> None:
    assert JsonExpenseRepository(tmp_path / "none.json").load() == []


def test_saved_expenses_load_back_unchanged(tmp_path: Path) -> None:
    repository = JsonExpenseRepository(tmp_path / "expenses.json")
    repository.save(EXPENSES)
    assert repository.load() == EXPENSES


def test_the_path_can_be_given_as_text(tmp_path: Path) -> None:
    repository = JsonExpenseRepository(str(tmp_path / "expenses.json"))
    repository.save(EXPENSES)
    assert repository.path.is_file()


def test_amounts_are_stored_as_text(tmp_path: Path) -> None:
    path = tmp_path / "expenses.json"
    JsonExpenseRepository(path).save(EXPENSES)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["version"] == 1
    assert document["expenses"][0] == record(description="lunch")


def test_text_outside_ascii_survives(tmp_path: Path) -> None:
    repository = JsonExpenseRepository(tmp_path / "expenses.json")
    expense = Expense(1, date(2026, 11, 3), "καφές", Decimal("3.00"), "café ☕")
    repository.save([expense])
    assert repository.load() == [expense]


def test_save_creates_missing_folders(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "expenses.json"
    JsonExpenseRepository(path).save(EXPENSES)
    assert path.is_file()


def test_save_leaves_no_temporary_file(tmp_path: Path) -> None:
    JsonExpenseRepository(tmp_path / "expenses.json").save(EXPENSES)
    assert [item.name for item in tmp_path.iterdir()] == ["expenses.json"]


def test_a_failed_save_keeps_the_old_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "expenses.json"
    repository = JsonExpenseRepository(path)
    repository.save(EXPENSES[:1])
    before = path.read_bytes()

    def fail(source: object, target: object) -> None:
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(StorageError, match="Cannot write"):
        repository.save(EXPENSES)

    assert path.read_bytes() == before
    assert [item.name for item in tmp_path.iterdir()] == ["expenses.json"]


def test_a_path_that_is_a_folder_cannot_be_read(tmp_path: Path) -> None:
    with pytest.raises(StorageError, match="Cannot read"):
        JsonExpenseRepository(tmp_path).load()


def test_a_folder_that_cannot_be_created_is_reported(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    with pytest.raises(StorageError, match="Cannot write"):
        JsonExpenseRepository(blocker / "expenses.json").save(EXPENSES)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("{ not json", "not valid JSON"),
        ("", "not valid JSON"),
        ("[]", 'no "expenses" list'),
        ('{"version": 1}', 'no "expenses" list'),
        ('{"version": 1, "expenses": {}}', 'no "expenses" list'),
        ('{"version": 2, "expenses": []}', "format version"),
        ('{"expenses": []}', "format version"),
    ],
)
def test_a_damaged_file_gives_a_clear_error(tmp_path: Path, text: str, reason: str) -> None:
    path = tmp_path / "expenses.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(StorageError) as caught:
        JsonExpenseRepository(path).load()
    assert reason in str(caught.value)
    assert str(path) in str(caught.value)
    assert path.read_text(encoding="utf-8") == text


def test_a_file_that_is_not_utf8_gives_a_clear_error(tmp_path: Path) -> None:
    # Before 1.0.1 this raised UnicodeDecodeError, a crash with a traceback.
    path = tmp_path / "expenses.json"
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(StorageError, match="not UTF-8 text") as caught:
        JsonExpenseRepository(path).load()
    assert ".." not in str(caught.value)
    assert isinstance(caught.value.__cause__, UnicodeDecodeError)
    assert path.read_bytes() == b"\xff\xfe\x00"


@pytest.mark.parametrize(
    "bad_record",
    [
        "text",
        {"id": 1},
        record(id=0),
        record(id="1"),
        record(date="03/11/2026"),
        record(date=20261103),
        record(category=""),
        record(category=None),
        record(amount="abc"),
        record(amount="-1.00"),
        record(amount=12.5),
        record(amount="1e30"),
        record(amount="99999999999999999999999999999"),
        record(description=5),
    ],
)
def test_an_invalid_expense_gives_a_clear_error(tmp_path: Path, bad_record: object) -> None:
    path = tmp_path / "expenses.json"
    write(path, {"version": 1, "expenses": [record(id=7), bad_record]})
    with pytest.raises(StorageError, match="expense number 2 is invalid"):
        JsonExpenseRepository(path).load()


def test_a_repeated_id_gives_a_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "expenses.json"
    write(path, {"version": 1, "expenses": [record(), record()]})
    with pytest.raises(StorageError, match="the id 1 is used twice"):
        JsonExpenseRepository(path).load()


def test_a_record_without_a_description_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "expenses.json"
    without = record()
    del without["description"]
    write(path, {"version": 1, "expenses": [without]})
    assert JsonExpenseRepository(path).load()[0].description == ""


def test_a_reason_ending_in_a_full_stop_is_not_doubled(tmp_path: Path) -> None:
    path = tmp_path / "expenses.json"
    write(path, {"version": 1, "expenses": [record(amount="0")]})
    with pytest.raises(StorageError) as caught:
        JsonExpenseRepository(path).load()
    assert "greater than zero. Fix or move the file" in str(caught.value)
