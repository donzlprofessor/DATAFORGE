# DATAFORGE

A small, offline Python ETL pipeline for synthetic e-commerce orders. DATAFORGE validates CSV records, explains rejected rows, normalizes accepted orders, and imports them into SQLite without duplicating or overwriting existing orders.

Built as a junior backend/data engineering portfolio project with Pandas, Pydantic, SQLAlchemy 2, Typer, Pytest, and Ruff. All sample identifiers and transactions are fictional; no personal data or credentials are included.

## Installation

Requires Python 3.12 or newer. From this directory, create a virtual environment and install the project with development tools:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

On macOS/Linux, use `python3 -m venv .venv` followed by `source .venv/bin/activate`. Installation needs access to the Python package index; imports and tests run offline after installation.

## Usage

```console
dataforge run data/sample_orders.csv
```

Default outputs, with parent directories created automatically:

| Path | Purpose |
| --- | --- |
| `artifacts/orders.db` | Accepted orders in the SQLite `orders` table |
| `artifacts/quality_report.json` | Import counts, acceptance rate, rejection reasons, UTC timestamps |
| `artifacts/rejected_orders.csv` | Original field values, source row numbers, and rejection reasons |

Override the paths when needed:

```console
dataforge run data/sample_orders.csv --database artifacts/demo.db --report artifacts/demo.json --rejected artifacts/demo_rejected.csv
dataforge run --help
```

The sample contains 19 records: 8 valid orders and 11 rejected rows, including one duplicate. First import:

```text
Processed 19 rows: 8 inserted, 0 skipped, 11 rejected (0 conflicts).
Quality report: artifacts/quality_report.json
Rejected records: artifacts/rejected_orders.csv
```

Running the command again against the same database:

```text
Processed 19 rows: 0 inserted, 8 skipped, 11 rejected (0 conflicts).
```

Selected first-import report fields:

```json
{
  "total_rows": 19,
  "valid_rows": 8,
  "rejected_rows": 11,
  "inserted_rows": 8,
  "skipped_rows": 0,
  "conflicting_rows": 0,
  "duplicate_rows": 1,
  "acceptance_rate": 0.421053
}
```

The full report also contains the source path, start/finish timestamps, and `rejections_by_reason`. Counts and reason ordering are deterministic for the same input and database state; timestamps change on each run. `valid_rows = inserted_rows + skipped_rows`, and `total_rows = valid_rows + rejected_rows`. Conflicts and duplicates are subsets of rejected rows. A row can have several validation errors, so reason counts can exceed the rejected-row count. A header-only CSV has acceptance rate `0.0`.

Rejected CSV rows preserve original field text rather than normalized values. `source_row` is the physical starting line in the input, counting the header as line 1, including when a quoted field spans lines. `rejection_reasons` is a JSON array encoded as a CSV field, for example `["unit_price: unit_price must be finite"]`.

Row rejections are a normal successful import (exit code 0). Missing files, malformed CSV, schema errors, database failures, or output errors return exit code 1 with an explanatory message.

## Data contract

The UTF-8 CSV (optionally with a BOM) must contain exactly these columns, in any order, with no duplicate headers:

| Column | Rules |
| --- | --- |
| `order_id` | Required, trimmed, case-sensitive string |
| `customer_id` | Required, trimmed string; fictional IDs in sample data |
| `order_date` | Required valid calendar date in `YYYY-MM-DD` format |
| `product` | Required, trimmed string |
| `quantity` | Positive integer, at most SQLite's signed 64-bit maximum |
| `unit_price` | Finite, nonnegative `Decimal` in plain decimal notation; zero is allowed |
| `currency` | Three ASCII letters, normalized to uppercase |

Whitespace-only values are missing. Literal strings such as `NA` remain strings. Scientific notation, fractional quantities, NaN, and infinite prices are rejected. Prices are never converted to floats or rounded; equivalent decimal representations such as `24.99` and `24.990` compare identically. Currency validation checks syntax, not membership in an ISO currency registry.

The first **valid** occurrence of an order ID in a file claims that ID. Later valid occurrences are rejected as input duplicates, even if their values match. Invalid earlier rows do not claim the ID. Rows that fail validation report all field errors before duplicate detection.

For IDs already in SQLite, all normalized fields must match to skip the row. Any difference rejects the new row as a conflict and preserves the stored order. Orders are not updated or deleted by imports.

## Architecture

```text
CSV -> structural checks -> Pandas strings -> Pydantic orders
                                             |
                                    input duplicate checks
                                             |
                                 SQLite transaction and comparison
                                             |
                                  JSON report + rejected CSV
```

`src/dataforge/validation.py` defines the record model and normalization rules. `pipeline.py` checks CSV structure, reads string columns with Pandas, coordinates validation and persistence, and writes artifacts. `database.py` owns the SQLAlchemy table and transactional insert/skip/conflict decisions. `cli.py` exposes the workflow through Typer. The project uses functions and a single record model without repository/service abstraction layers.

CSV structural checks run before database access, rejecting inconsistent field counts, broken quoting, blank physical records, missing/extra columns, and duplicate headers. SQLite uses `order_id` as the primary key. `BEGIN IMMEDIATE` serializes writers before checking existing IDs; any database failure rolls back the entire batch of order inserts. The table may still exist after a failed first import because schema creation is separate from the row transaction.

Monetary values are stored as canonical decimal **TEXT** to avoid SQLite's numeric affinity converting them to binary floats. Use Python `Decimal` when reading prices for calculations.

## Tests and checks

```console
pytest
ruff check .
ruff format --check .
```

On Windows, if the default test run fails with `WinError 5` because temporary or cache directories are inaccessible, keep temporary files inside the project and disable Pytest's cache plugin:

```powershell
python -m pytest -q --basetemp=".test-tmp" -p no:cacheprovider
```

The `.test-tmp/` directory is ignored by Git. Use the full `-p no:cacheprovider` option; `-p no` does not disable the cache plugin.

Tests use temporary CSV files and SQLite databases with no network calls. Coverage includes schema failures, missing values, dates, quantity bounds, exact monetary values, nonfinite prices, normalization, duplicates, conflicts, idempotency, multiline source positions, report reconciliation, CLI errors/defaults, and a database trigger that verifies full batch rollback on failure.

GitHub Actions runs these checks on Python 3.12, 3.13, and 3.14. Generated databases, virtual environments, caches, and default artifacts are excluded by `.gitignore`.

## Limitations

- The full CSV and validated records are held in memory; this implementation targets small portfolio datasets rather than large streaming imports.
- JSON and rejected CSV files are overwritten on each successful run. Archive them or use different output paths when retaining import history.
- Database commits and filesystem outputs are separate operations. If writing an artifact fails after commit, the CLI reports failure but stored orders remain committed; rerunning safely skips them and regenerates artifacts.
- SQLite permits one writer at a time and uses its default lock timeout. This project has no schema migration system, retry service, or import history table.
- There is no currency conversion, customer/product reference validation, business calendar policy, or fixed currency-specific decimal scale.
- Rejected values are preserved verbatim. Treat the rejected CSV as data; spreadsheet applications may interpret formula-like cell contents.
