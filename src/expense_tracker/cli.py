"""Command-line layer: reads the arguments, calls the domain, prints the result.

It holds no rules of its own. Exit codes: 0 for success, 1 for an invalid value
or a file problem, 2 for a wrong command line (set by ``argparse``).
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import date

from expense_tracker import __version__
from expense_tracker.config import DATA_FILE_VARIABLE, DEFAULT_DATA_FILE, resolve_data_file
from expense_tracker.domain import (
    Expense,
    ExpenseFilter,
    ExpenseTracker,
    MonthlySummary,
    ValidationError,
)
from expense_tracker.export import export_csv
from expense_tracker.storage import JsonExpenseRepository, StorageError

MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def parse_day(text: str) -> date:
    """Turn ``YYYY-MM-DD`` into a date, for ``argparse``."""
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a date. Use YYYY-MM-DD, for example 2026-11-03."
        ) from None


def parse_month(text: str) -> tuple[int, int]:
    """Turn ``YYYY-MM`` into (year, month), for ``argparse``."""
    try:
        year_text, month_text = text.split("-")
        if len(year_text) != 4 or len(month_text) != 2:
            raise ValueError(text)
        first_day = date(int(year_text), int(month_text), 1)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a month. Use YYYY-MM, for example 2026-11."
        ) from None
    return first_day.year, first_day.month


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser with its four commands."""
    parser = argparse.ArgumentParser(
        prog="expense_tracker",
        description="Record expenses and report on them. The data is kept in one JSON file.",
        epilog=(
            f"Data file: the --file option, else the {DATA_FILE_VARIABLE} environment "
            f"variable, else {DEFAULT_DATA_FILE.as_posix()}."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--file", metavar="PATH", help="the JSON data file to use")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    add = commands.add_parser("add", help="record an expense")
    add.add_argument("amount", help="the amount, for example 12.50")
    add.add_argument("category", help="the category, for example food")
    add.add_argument(
        "--date", type=parse_day, metavar="YYYY-MM-DD", help="the day it was spent (default: today)"
    )
    add.add_argument("--note", default="", metavar="TEXT", help="a short description")

    listing = commands.add_parser("list", help="show expenses, oldest first")
    export = commands.add_parser("export", help="write expenses to a CSV file")
    export.add_argument("output", metavar="CSV_FILE", help="the CSV file to write")
    for command in (listing, export):
        command.add_argument("--category", help="only this category")
        command.add_argument(
            "--from", dest="start", type=parse_day, metavar="YYYY-MM-DD", help="from this day on"
        )
        command.add_argument(
            "--to", dest="end", type=parse_day, metavar="YYYY-MM-DD", help="up to this day"
        )

    summary = commands.add_parser("summary", help="show the totals for one month")
    summary.add_argument(
        "--month", type=parse_month, metavar="YYYY-MM", help="the month (default: this month)"
    )
    return parser


def format_expenses(expenses: Sequence[Expense]) -> str:
    """Return the expenses as an aligned text table with a total line."""
    if not expenses:
        return "No expenses found."
    category_width = max(len("Category"), *(len(expense.category) for expense in expenses))
    total = sum(expense.amount for expense in expenses)
    amount_width = max(len("Amount"), len(f"{total:,}"))
    id_width = max(len("ID"), len(str(max(expense.id for expense in expenses))))

    def row(id_text: str, day: str, category: str, amount: str, note: str) -> str:
        line = (
            f"{id_text:>{id_width}}  {day:<10}  {category:<{category_width}}  "
            f"{amount:>{amount_width}}  {note}"
        )
        return line.rstrip()

    header = row("ID", "Date", "Category", "Amount", "Note")
    lines = [header, "-" * len(header)]
    lines += [
        row(
            str(expense.id),
            expense.spent_on.isoformat(),
            expense.category,
            f"{expense.amount:,}",
            expense.description,
        )
        for expense in expenses
    ]
    count = f"{len(expenses)} expense" + ("" if len(expenses) == 1 else "s")
    lines += ["", f"{count}, total {total:,}"]
    return "\n".join(lines)


def format_summary(summary: MonthlySummary) -> str:
    """Return the monthly summary as text, with each category's share of the total."""
    title = f"{MONTH_NAMES[summary.month - 1]} {summary.year}"
    if summary.count == 0:
        return f"{title}: no expenses."
    name_width = max(len("Total"), *(len(name) for name in summary.by_category))
    amount_width = len(f"{summary.total:,}")
    lines = [title, "-" * len(title)]
    for name, amount in summary.by_category.items():
        share = amount / summary.total * 100
        lines.append(f"{name:<{name_width}}  {amount:>{amount_width},}  {share:5.1f}%")
    lines.append(f"{'Total':<{name_width}}  {summary.total:>{amount_width},}")
    count = f"{summary.count} expense" + ("" if summary.count == 1 else "s")
    lines += ["", count]
    return "\n".join(lines)


def _criteria(arguments: argparse.Namespace) -> ExpenseFilter:
    return ExpenseFilter(category=arguments.category, start=arguments.start, end=arguments.end)


def run(arguments: argparse.Namespace, tracker: ExpenseTracker, today: date) -> str:
    """Carry out one command and return the text to print."""
    if arguments.command == "add":
        expense = tracker.add(
            arguments.amount, arguments.category, arguments.date or today, arguments.note
        )
        return (
            f"Added expense {expense.id}: {expense.amount:,} "
            f"for {expense.category} on {expense.spent_on.isoformat()}."
        )
    if arguments.command == "list":
        return format_expenses(tracker.list(_criteria(arguments)))
    if arguments.command == "summary":
        year, month = arguments.month or (today.year, today.month)
        return format_summary(tracker.monthly_summary(year, month))
    count = export_csv(tracker.list(_criteria(arguments)), arguments.output)
    plural = "" if count == 1 else "s"
    return f"Wrote {count} expense{plural} to {arguments.output}."


def use_utf8_output() -> None:
    """Print UTF-8 text even when the output is redirected to a file or a pipe.

    On Windows, redirected output uses the system's legacy code page, which
    cannot hold Greek or most other non-Latin text. Printing such text would
    then raise ``UnicodeEncodeError`` after the command had already done its work.
    The data and CSV files are UTF-8, so the printed output matches them.
    """
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and stream.encoding.lower() != "utf-8":
            stream.reconfigure(encoding="utf-8")


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    today: Callable[[], date] = date.today,
) -> int:
    """Run the command line and return the exit code."""
    use_utf8_output()
    arguments = build_parser().parse_args(argv)
    data_file = resolve_data_file(
        arguments.file, os.environ if environment is None else environment
    )
    tracker = ExpenseTracker(JsonExpenseRepository(data_file))
    try:
        print(run(arguments, tracker, today()))
    except (ValidationError, StorageError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0
