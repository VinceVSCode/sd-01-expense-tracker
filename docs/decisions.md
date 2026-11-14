# Design decisions

One page on the choices made in this project and their trade-offs.

| Date | Decision | Options considered | Why this one |
|---|---|---|---|
| 2026-11-14 | Command-line library: `argparse` | `argparse`, Typer, Click | It is part of Python, so the application has no run-time dependencies and a clean clone runs at once. Four commands do not need more. |
| 2026-11-14 | Money type: `Decimal`, two decimal places | `Decimal`, whole cents as integers, `float` | Sums are exact (`0.10 + 0.20` is `0.30`) and the code reads like the amounts a person types. `float` was ruled out because it cannot hold most decimal amounts exactly. |
| 2026-11-14 | Amounts are stored as text in the JSON file (`"12.50"`) | text, JSON number | A JSON number is read back as a `float`, which would lose the exactness. |
| 2026-11-14 | Three layers: `cli`, `domain`, `storage` (plus `export` and `config`) | one module, or layers | Each layer has one job and is tested alone. The domain never reads a file or prints. |
| 2026-11-14 | The domain defines the `ExpenseRepository` interface; storage implements it | the domain importing the JSON class directly | The domain does not depend on the file format. Tests use an in-memory repository, and another storage could replace JSON. |
| 2026-11-14 | `Expense` is an immutable dataclass that validates itself | a plain dictionary, or a mutable class | An invalid expense cannot exist, whether it comes from the command line or from the file. |
| 2026-11-14 | Categories are free text, stored trimmed and in lower case | a fixed list of categories | The user needs no setup step, and `Food` and `food` are the same category. |
| 2026-11-14 | Safe write: write a temporary file, then replace the real one | writing the file directly | If writing fails halfway, the old file is still complete. |
| 2026-11-14 | A damaged data file stops the command with a clear error | starting again with an empty list | Starting empty would overwrite the user's data on the next `add`. |
| 2026-11-14 | Data file path: `--file`, then `EXPENSE_TRACKER_FILE`, then `~/.expense_tracker/expenses.json` | a fixed path, or a file in the current folder | The path is configurable in two ways, and the default does not depend on the folder the command is run from. |
| 2026-11-14 | CSV export puts a quote before text that starts with `=`, `+`, `-` or `@` | writing the text as it is | A spreadsheet would otherwise run such a note as a formula. |
| 2026-11-14 | Coverage is measured with `pytest-cov` and `pytest` fails below 90% | `coverage` run by hand, or no threshold | The requirement (80% on the domain logic) is then enforced on every run, also in CI. |
| 2026-11-14 | The images in `docs/media/` are drawn from the captured text output of `scripts/demo.py` | a screenshot of a terminal window | The capture can be repeated exactly. The text in the images is the application's real output; only the window frame is drawn. |

## Trade-offs

- **Standard library only.** No dependencies to install or keep up to date. In exchange, the help text and the tables are plainer than Typer or Rich would give.
- **One JSON file, rewritten on every command.** Simple, readable, and easy to back up. It would be slow with a very large number of expenses, and it does not protect against two commands writing at the same moment.
- **No currency.** The model stays small. Mixed currencies would need a currency on every amount and exchange rules.
- **`Decimal` rather than integer cents.** Easier to read and to format. It needs care at the edges: amounts are checked and rounded to two places in one function (`parse_amount`), and floats are refused.
