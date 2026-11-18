"""Checks on the package itself."""

from __future__ import annotations

import expense_tracker


def test_package_has_a_version() -> None:
    assert expense_tracker.__version__ == "1.0.1"
