"""CSV export of expenses."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path
from typing import TextIO

from expense_tracker.domain import Expense
from expense_tracker.storage import StorageError

CSV_COLUMNS = ("id", "date", "category", "amount", "description")

# A spreadsheet treats a cell that starts with one of these as a formula.
_FORMULA_STARTS = ("=", "+", "-", "@")


def _safe_text(value: str) -> str:
    """Stop a spreadsheet from running text as a formula, by putting a quote first."""
    return f"'{value}" if value.startswith(_FORMULA_STARTS) else value


def write_csv(expenses: Iterable[Expense], stream: TextIO) -> int:
    """Write the expenses to ``stream`` as CSV with a header row. Return the row count."""
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    count = 0
    for expense in expenses:
        writer.writerow(
            (
                expense.id,
                expense.spent_on.isoformat(),
                _safe_text(expense.category),
                str(expense.amount),
                _safe_text(expense.description),
            )
        )
        count += 1
    return count


def export_csv(expenses: Iterable[Expense], path: Path | str) -> int:
    """Write the expenses to a CSV file (UTF-8), replacing it. Return the row count."""
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as stream:
            return write_csv(expenses, stream)
    except OSError as error:
        raise StorageError(f"Cannot write {target}: {error.strerror or error}") from error
