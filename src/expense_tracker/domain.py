"""Domain layer: the expense model and the rules that apply to it.

Nothing in this module reads a file, prints, or looks at the clock. That keeps
the rules easy to test and lets the storage and the interface change freely.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol

CENT = Decimal("0.01")
MAX_CATEGORY_LENGTH = 30
MAX_DESCRIPTION_LENGTH = 200


class ValidationError(ValueError):
    """Raised when a value breaks a rule of the domain."""


def parse_amount(value: Decimal | str | int) -> Decimal:
    """Return ``value`` as a positive amount with exactly two decimal places.

    Floats are refused, because they cannot hold most decimal amounts exactly.
    """
    if isinstance(value, bool) or not isinstance(value, Decimal | str | int):
        raise ValidationError(f"Amount must be a decimal number, not {type(value).__name__}.")
    try:
        amount = Decimal(value.strip()) if isinstance(value, str) else Decimal(value)
    except InvalidOperation:
        raise ValidationError(f"Amount {value!r} is not a number.") from None
    if not amount.is_finite():
        raise ValidationError(f"Amount {value!r} is not a number.")
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero.")
    if amount != amount.quantize(CENT):
        raise ValidationError("Amount can have at most two decimal places.")
    return amount.quantize(CENT)


def normalise_category(value: str) -> str:
    """Return the category in its stored form: trimmed and in lower case."""
    if not isinstance(value, str):
        raise ValidationError("Category must be text.")
    category = " ".join(value.split()).lower()
    if not category:
        raise ValidationError("Category must not be empty.")
    if len(category) > MAX_CATEGORY_LENGTH:
        raise ValidationError(f"Category can have at most {MAX_CATEGORY_LENGTH} characters.")
    return category


def normalise_description(value: str) -> str:
    """Return the description on one line, without surrounding spaces."""
    if not isinstance(value, str):
        raise ValidationError("Description must be text.")
    description = " ".join(value.split())
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValidationError(
            f"Description can have at most {MAX_DESCRIPTION_LENGTH} characters."
        )
    return description


@dataclass(frozen=True, slots=True)
class Expense:
    """One expense. It is always valid: bad values are refused when it is created."""

    id: int
    spent_on: date
    category: str
    amount: Decimal
    description: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.id, bool) or not isinstance(self.id, int) or self.id < 1:
            raise ValidationError("Expense id must be a whole number, 1 or greater.")
        if not isinstance(self.spent_on, date):
            raise ValidationError("Expense date must be a date.")
        object.__setattr__(self, "category", normalise_category(self.category))
        object.__setattr__(self, "amount", parse_amount(self.amount))
        object.__setattr__(self, "description", normalise_description(self.description))


@dataclass(frozen=True, slots=True)
class ExpenseFilter:
    """Which expenses to select. A value of ``None`` means "do not filter on this"."""

    category: str | None = None
    start: date | None = None
    end: date | None = None

    def __post_init__(self) -> None:
        if self.category is not None:
            object.__setattr__(self, "category", normalise_category(self.category))
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValidationError("The start date must not be after the end date.")

    def matches(self, expense: Expense) -> bool:
        """Return whether ``expense`` passes every part of the filter."""
        if self.category is not None and expense.category != self.category:
            return False
        if self.start is not None and expense.spent_on < self.start:
            return False
        return self.end is None or expense.spent_on <= self.end


@dataclass(frozen=True, slots=True)
class MonthlySummary:
    """Totals for one calendar month."""

    year: int
    month: int
    count: int
    total: Decimal
    by_category: dict[str, Decimal] = field(default_factory=dict)


def filter_expenses(expenses: Iterable[Expense], criteria: ExpenseFilter) -> list[Expense]:
    """Return the matching expenses, oldest first (then by id)."""
    selected = [expense for expense in expenses if criteria.matches(expense)]
    return sorted(selected, key=lambda expense: (expense.spent_on, expense.id))


def summarise_month(expenses: Iterable[Expense], year: int, month: int) -> MonthlySummary:
    """Return the totals for one month. Categories are ordered by largest total first."""
    if not 1 <= month <= 12:
        raise ValidationError("Month must be between 1 and 12.")
    in_month = [
        expense
        for expense in expenses
        if expense.spent_on.year == year and expense.spent_on.month == month
    ]
    totals: dict[str, Decimal] = {}
    for expense in in_month:
        totals[expense.category] = totals.get(expense.category, Decimal("0.00")) + expense.amount
    ordered = dict(sorted(totals.items(), key=lambda item: (-item[1], item[0])))
    return MonthlySummary(
        year=year,
        month=month,
        count=len(in_month),
        total=sum(totals.values(), Decimal("0.00")),
        by_category=ordered,
    )


class ExpenseRepository(Protocol):
    """What the domain needs from storage. The storage layer provides it."""

    def load(self) -> list[Expense]:
        """Return every stored expense."""
        ...

    def save(self, expenses: list[Expense]) -> None:
        """Replace the stored expenses with ``expenses``."""
        ...


class ExpenseTracker:
    """The operations of the application, on top of any repository."""

    def __init__(self, repository: ExpenseRepository) -> None:
        self._repository = repository

    def add(
        self,
        amount: Decimal | str | int,
        category: str,
        spent_on: date,
        description: str = "",
    ) -> Expense:
        """Record a new expense and return it. Nothing is saved if a value is invalid."""
        expenses = self._repository.load()
        next_id = max((expense.id for expense in expenses), default=0) + 1
        expense = Expense(
            id=next_id,
            spent_on=spent_on,
            category=category,
            amount=parse_amount(amount),
            description=description,
        )
        self._repository.save([*expenses, expense])
        return expense

    def list(self, criteria: ExpenseFilter | None = None) -> list[Expense]:
        """Return the expenses that match ``criteria`` (all of them by default)."""
        return filter_expenses(self._repository.load(), criteria or ExpenseFilter())

    def monthly_summary(self, year: int, month: int) -> MonthlySummary:
        """Return the totals for one calendar month."""
        return summarise_month(self._repository.load(), year, month)
