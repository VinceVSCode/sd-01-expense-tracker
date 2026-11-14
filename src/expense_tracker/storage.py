"""Storage layer: keeps the expenses in one JSON file.

The file looks like this::

    {
      "version": 1,
      "expenses": [
        {"id": 1, "date": "2026-11-03", "category": "food",
         "amount": "12.50", "description": "lunch"}
      ]
    }

Amounts are stored as text so that no precision is lost.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from expense_tracker.domain import Expense, ValidationError, parse_amount

FORMAT_VERSION = 1


class StorageError(Exception):
    """Raised when the data file cannot be read or written."""


def expense_to_record(expense: Expense) -> dict[str, Any]:
    """Return the JSON form of one expense."""
    return {
        "id": expense.id,
        "date": expense.spent_on.isoformat(),
        "category": expense.category,
        "amount": str(expense.amount),
        "description": expense.description,
    }


def expense_from_record(record: Any) -> Expense:
    """Build an expense from its JSON form. Raises ``ValueError`` on bad data."""
    if not isinstance(record, dict):
        raise ValueError("an expense must be an object")
    try:
        raw_date, raw_amount = record["date"], record["amount"]
        if not isinstance(raw_date, str) or not isinstance(raw_amount, str):
            raise ValueError("the date and the amount must be text")
        return Expense(
            id=record["id"],
            spent_on=date.fromisoformat(raw_date),
            category=record["category"],
            amount=parse_amount(raw_amount),
            description=record.get("description", ""),
        )
    except KeyError as missing:
        raise ValueError(f"an expense has no {missing.args[0]!r} value") from None


class JsonExpenseRepository:
    """Reads and writes every expense in one JSON file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> list[Expense]:
        """Return the stored expenses. A file that does not exist yet means none."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as error:
            raise StorageError(f"Cannot read {self.path}: {error.strerror or error}") from error

        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise self._corrupt(f"it is not valid JSON (line {error.lineno})") from error
        if not isinstance(document, dict) or not isinstance(document.get("expenses"), list):
            raise self._corrupt('it has no "expenses" list')
        if document.get("version") != FORMAT_VERSION:
            raise self._corrupt(f"its format version is not {FORMAT_VERSION}")

        expenses: list[Expense] = []
        seen: set[int] = set()
        for number, record in enumerate(document["expenses"], start=1):
            try:
                expense = expense_from_record(record)
            except (ValidationError, ValueError, TypeError) as error:
                raise self._corrupt(f"expense number {number} is invalid: {error}") from error
            if expense.id in seen:
                raise self._corrupt(f"the id {expense.id} is used twice")
            seen.add(expense.id)
            expenses.append(expense)
        return expenses

    def save(self, expenses: list[Expense]) -> None:
        """Replace the file's contents.

        The data goes to a temporary file in the same folder first, and that file
        then replaces the real one in a single step. If writing fails halfway, the
        old file is still complete.
        """
        document = {
            "version": FORMAT_VERSION,
            "expenses": [expense_to_record(expense) for expense in expenses],
        }
        temporary: str | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(
                dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
            )
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(document, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
            os.replace(temporary, self.path)
        except OSError as error:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
            raise StorageError(f"Cannot write {self.path}: {error.strerror or error}") from error

    def _corrupt(self, reason: str) -> StorageError:
        return StorageError(
            f"The data file {self.path} is damaged: {reason}. "
            "Fix or move the file, then try again. It was not changed."
        )
