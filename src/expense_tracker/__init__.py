"""Expense Tracker: a command-line tool that records and reports expenses.

The package has three layers:

- ``domain``: the expense model and the rules (no file or terminal access)
- ``storage``: reading and writing the JSON data file
- ``cli``: the command-line interface
"""

__version__ = "1.0.1"
