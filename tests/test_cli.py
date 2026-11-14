"""Tests for the command-line layer and the configuration."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from expense_tracker import __version__
from expense_tracker.cli import main
from expense_tracker.config import resolve_data_file

TODAY = date(2026, 11, 14)


class Cli:
    """Runs commands against one data file and captures what they print."""

    def __init__(self, data_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
        self.data_file = data_file
        self._capsys = capsys

    def __call__(self, *argv: str) -> tuple[int, str, str]:
        code = main(
            ["--file", str(self.data_file), *argv], environment={}, today=lambda: TODAY
        )
        captured = self._capsys.readouterr()
        return code, captured.out, captured.err


@pytest.fixture
def cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Cli:
    return Cli(tmp_path / "expenses.json", capsys)


@pytest.fixture
def filled(cli: Cli) -> Cli:
    cli("add", "650", "rent", "--date", "2026-10-30")
    cli("add", "12.50", "food", "--date", "2026-11-03", "--note", "lunch")
    cli("add", "2.40", "transport", "--date", "2026-11-03")
    cli("add", "30.10", "Food")
    return cli


# --- add ---------------------------------------------------------------------


def test_add_reports_what_was_saved(cli: Cli) -> None:
    code, out, err = cli("add", "12.5", "Food", "--date", "2026-11-03", "--note", "lunch")
    assert (code, err) == (0, "")
    assert out == "Added expense 1: 12.50 for food on 2026-11-03.\n"
    stored = json.loads(cli.data_file.read_text(encoding="utf-8"))["expenses"]
    assert stored == [
        {
            "id": 1,
            "date": "2026-11-03",
            "category": "food",
            "amount": "12.50",
            "description": "lunch",
        }
    ]


def test_add_uses_today_when_no_date_is_given(cli: Cli) -> None:
    assert "on 2026-11-14." in cli("add", "5", "food")[1]


@pytest.mark.parametrize(
    ("amount", "message"),
    [
        ("abc", "is not a number"),
        ("0", "greater than zero"),
        ("-5", "greater than zero"),
        ("1.234", "two decimal places"),
    ],
)
def test_add_rejects_a_bad_amount(cli: Cli, amount: str, message: str) -> None:
    code, out, err = cli("add", amount, "food")
    assert (code, out) == (1, "")
    assert err.startswith("Error: ") and message in err
    assert not cli.data_file.exists()


def test_add_rejects_a_bad_date(cli: Cli, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli("add", "5", "food", "--date", "03/11/2026")
    assert stopped.value.code == 2
    assert "is not a date. Use YYYY-MM-DD" in capsys.readouterr().err


# --- list --------------------------------------------------------------------


def test_list_with_no_data(cli: Cli) -> None:
    assert cli("list") == (0, "No expenses found.\n", "")


def test_list_shows_a_table_and_a_total(filled: Cli) -> None:
    code, out, _ = filled("list")
    assert code == 0
    assert out.splitlines() == [
        "ID  Date        Category   Amount  Note",
        "---------------------------------------",
        " 1  2026-10-30  rent       650.00",
        " 2  2026-11-03  food        12.50  lunch",
        " 3  2026-11-03  transport    2.40",
        " 4  2026-11-14  food        30.10",
        "",
        "4 expenses, total 695.00",
    ]


def test_list_filters_by_category(filled: Cli) -> None:
    out = filled("list", "--category", "FOOD")[1]
    assert "2 expenses, total 42.60" in out
    assert "rent" not in out


def test_list_filters_by_date_range(filled: Cli) -> None:
    out = filled("list", "--from", "2026-11-01", "--to", "2026-11-03")[1]
    assert "2 expenses, total 14.90" in out


def test_list_of_one_expense_uses_the_singular(filled: Cli) -> None:
    assert "1 expense, total 2.40" in filled("list", "--category", "transport")[1]


def test_list_rejects_a_range_that_ends_before_it_starts(filled: Cli) -> None:
    code, _, err = filled("list", "--from", "2026-11-05", "--to", "2026-11-01")
    assert code == 1
    assert "start date must not be after the end date" in err


def test_large_totals_get_thousands_separators(cli: Cli) -> None:
    cli("add", "1200", "rent")
    cli("add", "300", "rent")
    assert "total 1,500.00" in cli("list")[1]


# --- summary -----------------------------------------------------------------


def test_summary_of_a_given_month(filled: Cli) -> None:
    code, out, _ = filled("summary", "--month", "2026-11")
    assert code == 0
    assert out.splitlines() == [
        "November 2026",
        "-------------",
        "food       42.60   94.7%",
        "transport   2.40    5.3%",
        "Total      45.00",
        "",
        "3 expenses",
    ]


def test_summary_defaults_to_this_month(filled: Cli) -> None:
    assert filled("summary")[1].startswith("November 2026\n")


def test_summary_of_a_month_with_no_expenses(filled: Cli) -> None:
    assert filled("summary", "--month", "2025-01")[1] == "January 2025: no expenses.\n"


@pytest.mark.parametrize("month", ["2026-13", "2026", "26-11", "2026-1", "november"])
def test_summary_rejects_a_bad_month(
    cli: Cli, capsys: pytest.CaptureFixture[str], month: str
) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli("summary", "--month", month)
    assert stopped.value.code == 2
    assert "is not a month. Use YYYY-MM" in capsys.readouterr().err


# --- export ------------------------------------------------------------------


def test_export_writes_a_csv_file(filled: Cli, tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    code, out, _ = filled("export", str(target))
    assert (code, out) == (0, f"Wrote 4 expenses to {target}.\n")
    with target.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["amount"] for row in rows] == ["650.00", "12.50", "2.40", "30.10"]


def test_export_applies_the_filters(filled: Cli, tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    out = filled("export", str(target), "--category", "transport")[1]
    assert out == f"Wrote 1 expense to {target}.\n"


def test_export_to_a_folder_fails_cleanly(filled: Cli, tmp_path: Path) -> None:
    code, _, err = filled("export", str(tmp_path))
    assert code == 1
    assert err.startswith("Error: Cannot write")


# --- errors and configuration ------------------------------------------------


def test_a_damaged_data_file_is_reported_and_left_alone(cli: Cli) -> None:
    cli.data_file.write_text("{ not json", encoding="utf-8")
    code, out, err = cli("add", "5", "food")
    assert (code, out) == (1, "")
    assert "is damaged" in err
    assert cli.data_file.read_text(encoding="utf-8") == "{ not json"


def test_a_command_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        main([], environment={})
    assert stopped.value.code == 2


def test_the_file_option_wins_over_the_environment(tmp_path: Path) -> None:
    environment = {"EXPENSE_TRACKER_FILE": str(tmp_path / "from-env.json")}
    chosen = resolve_data_file(str(tmp_path / "from-option.json"), environment)
    assert chosen == tmp_path / "from-option.json"


def test_the_environment_variable_sets_the_data_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_file = tmp_path / "from-env.json"
    code = main(
        ["add", "5", "food"],
        environment={"EXPENSE_TRACKER_FILE": str(data_file)},
        today=lambda: TODAY,
    )
    assert code == 0
    assert data_file.is_file()


def test_the_default_data_file_is_in_the_home_folder() -> None:
    assert resolve_data_file(None, {}) == Path.home() / ".expense_tracker" / "expenses.json"


# --- the real entry point ----------------------------------------------------


def run_module(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "expense_tracker", *argv],
        capture_output=True,
        text=True,
        check=False,
    )


def test_python_m_help_lists_the_commands() -> None:
    result = run_module("--help")
    assert result.returncode == 0
    for command in ("add", "list", "summary", "export"):
        assert command in result.stdout


def test_python_m_version() -> None:
    assert run_module("--version").stdout.strip() == f"expense_tracker {__version__}"


def test_python_m_runs_a_command_end_to_end(tmp_path: Path) -> None:
    data_file = str(tmp_path / "expenses.json")
    added = run_module("--file", data_file, "add", "9.99", "books", "--date", "2026-11-01")
    assert added.returncode == 0
    listed = run_module("--file", data_file, "list")
    assert "books" in listed.stdout and "total 9.99" in listed.stdout
