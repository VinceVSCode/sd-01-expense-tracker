"""Run a short demo of the expense tracker and print what it shows.

The demo uses a temporary data file, so it never touches your own expenses.
Each command really runs; the output below it is what the application printed.

Usage: python scripts/demo.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SETUP = [
    ["add", "650", "rent", "--date", "2026-11-01"],
    ["add", "42.80", "groceries", "--date", "2026-11-03", "--note", "weekly shop"],
    ["add", "2.40", "transport", "--date", "2026-11-03", "--note", "bus"],
    ["add", "18.50", "eating out", "--date", "2026-11-07", "--note", "lunch"],
    ["add", "37.15", "groceries", "--date", "2026-11-10"],
]
SHOWN = [
    ["add", "12.99", "books", "--date", "2026-11-12", "--note", "paperback"],
    ["list", "--from", "2026-11-03"],
    ["summary", "--month", "2026-11"],
    ["export", "november.csv", "--category", "groceries"],
]


def run(arguments: list[str], folder: Path) -> str:
    """Run one command in ``folder`` and return everything it printed."""
    result = subprocess.run(
        [sys.executable, "-m", "expense_tracker", "--file", "expenses.json", *arguments],
        cwd=folder,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def quote(argument: str) -> str:
    return f'"{argument}"' if " " in argument else argument


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        for arguments in SETUP:
            run(arguments, folder)
        for arguments in SHOWN:
            print("$ python -m expense_tracker " + " ".join(quote(item) for item in arguments))
            print(run(arguments, folder))
        print("$ cat november.csv")
        print((folder / "november.csv").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
