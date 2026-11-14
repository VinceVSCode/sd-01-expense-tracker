"""Tests for the CSV export."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from expense_tracker.domain import Expense
from expense_tracker.export import export_csv, write_csv
from expense_tracker.storage import StorageError

EXPENSES = [
    Expense(1, date(2026, 11, 3), "food", Decimal("12.50"), 'lunch, with "extras"'),
    Expense(2, date(2026, 11, 4), "transport", Decimal("2.40")),
]


def test_write_csv_has_a_header_and_one_row_per_expense() -> None:
    stream = io.StringIO()
    assert write_csv(EXPENSES, stream) == 2
    assert stream.getvalue().splitlines() == [
        "id,date,category,amount,description",
        '1,2026-11-03,food,12.50,"lunch, with ""extras"""',
        "2,2026-11-04,transport,2.40,",
    ]


def test_write_csv_with_no_expenses_writes_only_the_header() -> None:
    stream = io.StringIO()
    assert write_csv([], stream) == 0
    assert stream.getvalue() == "id,date,category,amount,description\n"


def test_csv_reads_back_with_the_standard_reader(tmp_path: Path) -> None:
    path = tmp_path / "out" / "expenses.csv"
    assert export_csv(EXPENSES, path) == 2
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0] == {
        "id": "1",
        "date": "2026-11-03",
        "category": "food",
        "amount": "12.50",
        "description": 'lunch, with "extras"',
    }
    assert len(rows) == 2


def test_export_replaces_an_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "expenses.csv"
    path.write_text("old contents", encoding="utf-8")
    export_csv(EXPENSES[:1], str(path))
    assert "old contents" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("text", ["=1+1", "+1", "-1", "@SUM(A1)"])
def test_text_that_looks_like_a_formula_is_neutralised(text: str) -> None:
    stream = io.StringIO()
    write_csv([Expense(1, date(2026, 11, 3), text, Decimal("1"), text)], stream)
    row = next(csv.DictReader(io.StringIO(stream.getvalue())))
    assert row["category"] == f"'{text.lower()}"
    assert row["description"] == f"'{text}"


def test_export_to_a_folder_is_reported(tmp_path: Path) -> None:
    with pytest.raises(StorageError, match="Cannot write"):
        export_csv(EXPENSES, tmp_path)
