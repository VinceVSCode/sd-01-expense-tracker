"""Unit tests for the domain layer. They use an in-memory repository: no files."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from expense_tracker.domain import (
    Expense,
    ExpenseFilter,
    ExpenseTracker,
    ValidationError,
    filter_expenses,
    normalise_category,
    normalise_description,
    parse_amount,
    summarise_month,
)


class InMemoryRepository:
    """A repository that keeps expenses in a list and counts the saves."""

    def __init__(self, expenses: list[Expense] | None = None) -> None:
        self.expenses = list(expenses or [])
        self.saves = 0

    def load(self) -> list[Expense]:
        return list(self.expenses)

    def save(self, expenses: list[Expense]) -> None:
        self.expenses = list(expenses)
        self.saves += 1


def expense(
    id: int, day: str, category: str, amount: str, description: str = ""
) -> Expense:
    return Expense(id, date.fromisoformat(day), category, Decimal(amount), description)


SAMPLE = [
    expense(1, "2026-10-30", "rent", "650.00"),
    expense(2, "2026-11-03", "food", "12.50", "lunch"),
    expense(3, "2026-11-03", "transport", "2.40"),
    expense(4, "2026-11-15", "food", "30.10"),
    expense(5, "2026-12-01", "food", "8.00"),
]


# --- amounts ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12.5", "12.50"),
        (" 3 ", "3.00"),
        ("12.", "12.00"),
        (".5", "0.50"),
        (7, "7.00"),
        (Decimal("0.01"), "0.01"),
        ("999999999.99", "999999999.99"),
    ],
)
def test_parse_amount_accepts_valid_values(raw: object, expected: str) -> None:
    amount = parse_amount(raw)  # type: ignore[arg-type]
    assert amount == Decimal(expected)
    assert str(amount) == expected


@pytest.mark.parametrize(
    "raw",
    ["abc", "", "0", "-5", "1.999", "NaN", "Infinity", Decimal("NaN"), Decimal("Infinity"),
     12.5, True, None],
)
def test_parse_amount_rejects_invalid_values(raw: object) -> None:
    with pytest.raises(ValidationError):
        parse_amount(raw)  # type: ignore[arg-type]


@pytest.mark.parametrize("raw", ["1e2", "1E2", "1,000.50", "1_000", "\u0661\u0662", "12 50", "."])
def test_parse_amount_accepts_only_plain_digits(raw: str) -> None:
    with pytest.raises(ValidationError, match="Use digits and an optional decimal point"):
        parse_amount(raw)


@pytest.mark.parametrize(
    "raw",
    ["1000000000", "1e30", "99999999999999999999999999999", 10**40, Decimal("1E+40")],
)
def test_parse_amount_refuses_amounts_that_are_too_large(raw: object) -> None:
    # Before 1.0.1 these raised decimal.InvalidOperation, a crash with a traceback.
    with pytest.raises(ValidationError):
        parse_amount(raw)  # type: ignore[arg-type]


def test_the_largest_amounts_still_add_up_exactly() -> None:
    largest = parse_amount("999999999.99")
    assert sum([largest] * 1000, Decimal("0.00")) == Decimal("999999999990.00")


def test_amounts_add_up_exactly() -> None:
    assert parse_amount("0.10") + parse_amount("0.20") == Decimal("0.30")


# --- categories and descriptions --------------------------------------------


def test_category_is_trimmed_and_lower_cased() -> None:
    assert normalise_category("  Eating   Out ") == "eating out"


@pytest.mark.parametrize("raw", ["", "   ", "x" * 31, 5])
def test_category_rejects_invalid_values(raw: object) -> None:
    with pytest.raises(ValidationError):
        normalise_category(raw)  # type: ignore[arg-type]


def test_description_is_put_on_one_line() -> None:
    assert normalise_description("  weekly\nshop  ") == "weekly shop"


@pytest.mark.parametrize("raw", ["x" * 201, None])
def test_description_rejects_invalid_values(raw: object) -> None:
    with pytest.raises(ValidationError):
        normalise_description(raw)  # type: ignore[arg-type]


# --- the expense -------------------------------------------------------------


def test_expense_normalises_its_values() -> None:
    created = Expense(1, date(2026, 11, 3), " Food ", Decimal("12.5"), " lunch ")
    assert (created.category, str(created.amount), created.description) == (
        "food",
        "12.50",
        "lunch",
    )


@pytest.mark.parametrize("bad_id", [0, -1, True, "1"])
def test_expense_rejects_a_bad_id(bad_id: object) -> None:
    with pytest.raises(ValidationError):
        Expense(bad_id, date(2026, 11, 3), "food", Decimal("1"))  # type: ignore[arg-type]


def test_expense_rejects_a_date_given_as_text() -> None:
    with pytest.raises(ValidationError):
        Expense(1, "2026-11-03", "food", Decimal("1"))  # type: ignore[arg-type]


def test_expense_cannot_be_changed() -> None:
    with pytest.raises(AttributeError):
        SAMPLE[0].amount = Decimal("1.00")  # type: ignore[misc]


# --- filtering ---------------------------------------------------------------


def ids(expenses: list[Expense]) -> list[int]:
    return [item.id for item in expenses]


def test_empty_filter_returns_everything_oldest_first() -> None:
    assert ids(filter_expenses(reversed(SAMPLE), ExpenseFilter())) == [1, 2, 3, 4, 5]


def test_filter_by_category_ignores_case() -> None:
    assert ids(filter_expenses(SAMPLE, ExpenseFilter(category="FOOD"))) == [2, 4, 5]


def test_filter_by_date_range_includes_both_ends() -> None:
    criteria = ExpenseFilter(start=date(2026, 11, 3), end=date(2026, 11, 15))
    assert ids(filter_expenses(SAMPLE, criteria)) == [2, 3, 4]


def test_filter_with_only_a_start_date() -> None:
    assert ids(filter_expenses(SAMPLE, ExpenseFilter(start=date(2026, 11, 15)))) == [4, 5]


def test_filter_with_only_an_end_date() -> None:
    assert ids(filter_expenses(SAMPLE, ExpenseFilter(end=date(2026, 11, 2)))) == [1]


def test_filter_by_category_and_date_together() -> None:
    criteria = ExpenseFilter(category="food", start=date(2026, 11, 1), end=date(2026, 11, 30))
    assert ids(filter_expenses(SAMPLE, criteria)) == [2, 4]


def test_filter_that_matches_nothing() -> None:
    assert filter_expenses(SAMPLE, ExpenseFilter(category="travel")) == []


def test_filter_rejects_a_start_after_the_end() -> None:
    with pytest.raises(ValidationError):
        ExpenseFilter(start=date(2026, 11, 2), end=date(2026, 11, 1))


def test_filter_rejects_an_empty_category() -> None:
    with pytest.raises(ValidationError):
        ExpenseFilter(category=" ")


# --- monthly summary ---------------------------------------------------------


def test_summary_totals_one_month_only() -> None:
    summary = summarise_month(SAMPLE, 2026, 11)
    assert (summary.year, summary.month, summary.count) == (2026, 11, 3)
    assert summary.total == Decimal("45.00")


def test_summary_orders_categories_by_largest_total() -> None:
    summary = summarise_month(SAMPLE, 2026, 11)
    assert list(summary.by_category.items()) == [
        ("food", Decimal("42.60")),
        ("transport", Decimal("2.40")),
    ]


def test_summary_orders_equal_totals_by_name() -> None:
    tied = [expense(1, "2026-11-01", "b", "5"), expense(2, "2026-11-02", "a", "5")]
    assert list(summarise_month(tied, 2026, 11).by_category) == ["a", "b"]


def test_summary_of_an_empty_month() -> None:
    summary = summarise_month(SAMPLE, 2025, 1)
    assert (summary.count, summary.total, summary.by_category) == (0, Decimal("0.00"), {})


@pytest.mark.parametrize("month", [0, 13])
def test_summary_rejects_a_bad_month(month: int) -> None:
    with pytest.raises(ValidationError):
        summarise_month(SAMPLE, 2026, month)


# --- the tracker -------------------------------------------------------------


def test_add_saves_and_returns_the_expense() -> None:
    repository = InMemoryRepository()
    added = ExpenseTracker(repository).add("12.50", "Food", date(2026, 11, 3), "lunch")
    assert added == expense(1, "2026-11-03", "food", "12.50", "lunch")
    assert repository.expenses == [added]


def test_add_gives_the_next_free_id() -> None:
    repository = InMemoryRepository([expense(7, "2026-11-01", "food", "1")])
    assert ExpenseTracker(repository).add("2", "food", date(2026, 11, 2)).id == 8


@pytest.mark.parametrize(("amount", "category"), [("-1", "food"), ("1", ""), ("abc", "food")])
def test_add_saves_nothing_when_a_value_is_invalid(amount: str, category: str) -> None:
    repository = InMemoryRepository(SAMPLE)
    with pytest.raises(ValidationError):
        ExpenseTracker(repository).add(amount, category, date(2026, 11, 3))
    assert repository.saves == 0
    assert repository.expenses == SAMPLE


def test_list_returns_everything_by_default() -> None:
    assert ids(ExpenseTracker(InMemoryRepository(SAMPLE)).list()) == [1, 2, 3, 4, 5]


def test_list_applies_the_filter() -> None:
    tracker = ExpenseTracker(InMemoryRepository(SAMPLE))
    assert ids(tracker.list(ExpenseFilter(category="transport"))) == [3]


def test_monthly_summary_reads_from_the_repository() -> None:
    tracker = ExpenseTracker(InMemoryRepository(SAMPLE))
    assert tracker.monthly_summary(2026, 12).total == Decimal("8.00")
