"""Configuration: the one place that decides where the data file is."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

DATA_FILE_VARIABLE = "EXPENSE_TRACKER_FILE"
DEFAULT_DATA_FILE = Path("~/.expense_tracker/expenses.json")


def resolve_data_file(option: str | None, environment: Mapping[str, str]) -> Path:
    """Return the data file path.

    Order of preference: the ``--file`` option, then the ``EXPENSE_TRACKER_FILE``
    environment variable, then ``~/.expense_tracker/expenses.json``.
    """
    chosen = option or environment.get(DATA_FILE_VARIABLE) or str(DEFAULT_DATA_FILE)
    return Path(chosen).expanduser()
