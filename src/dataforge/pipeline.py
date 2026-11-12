"""CSV ingestion, validation, persistence, and quality artifacts."""

import csv
import io
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from dataforge.database import persist
from dataforge.validation import COLUMNS, Order


class PipelineError(Exception):
    """An input or output configuration prevents the import from running."""


def load_csv(source: Path) -> tuple[pd.DataFrame, list[int]]:
    """Preflight CSV structure, preserving physical starting line numbers."""
    try:
        with source.open(encoding="utf-8-sig", newline="") as handle:
            text = handle.read()
        if "\x00" in text:
            raise PipelineError("Malformed CSV: NUL bytes are not supported")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader, None)
        if header is None:
            raise PipelineError("CSV is empty; a header is required")
        missing = sorted(set(COLUMNS) - set(header))
        if missing:
            raise PipelineError(f"Missing required columns: {', '.join(missing)}")
        if len(header) != len(set(header)):
            raise PipelineError("Duplicate CSV column names are not allowed")
        if set(header) != set(COLUMNS):
            raise PipelineError("CSV must contain exactly the seven supported columns")
        row_numbers = []
        while True:
            start_line = reader.line_num + 1
            row = next(reader, None)
            if row is None:
                break
            if len(row) != len(header):
                raise PipelineError(
                    f"Malformed CSV at source row {start_line}: "
                    f"expected {len(header)} fields, found {len(row)}"
                )
            row_numbers.append(start_line)
        frame = pd.read_csv(
            io.StringIO(text), dtype=str, keep_default_na=False, skip_blank_lines=False
        )
        return frame, row_numbers
    except (csv.Error, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise PipelineError(f"Malformed CSV: {exc}") from exc


def run_pipeline(
    source: Path,
    database: Path = Path("artifacts/orders.db"),
    report: Path = Path("artifacts/quality_report.json"),
    rejected: Path = Path("artifacts/rejected_orders.csv"),
) -> dict:
    started = datetime.now(UTC)
    paths = [path.resolve() for path in (source, database, report, rejected)]
    if len(set(paths)) != len(paths):
        raise PipelineError("Input, database, report, and rejected paths must be distinct")
    frame, row_numbers = load_csv(source)
    candidates = []
    candidate_sources = []
    rejections = []
    seen = set()

    def reject(row_number: int, raw: dict, reasons: list[str]) -> None:
        rejections.append({"source_row": row_number, **raw, "rejection_reasons": reasons})

    for row_number, raw in zip(row_numbers, frame.to_dict(orient="records"), strict=True):
        try:
            order = Order.model_validate(raw)
        except ValidationError as exc:
            reasons = [
                f"{error['loc'][0]}: {error['msg'].removeprefix('Value error, ')}"
                for error in exc.errors(include_url=False)
            ]
            reject(row_number, raw, reasons)
            continue
        if order.order_id in seen:
            reject(row_number, raw, ["order_id: duplicate in input"])
            continue
        seen.add(order.order_id)
        candidates.append(order)
        candidate_sources.append((row_number, raw))

    outcomes = persist(database, candidates)
    for (row_number, raw), outcome in zip(candidate_sources, outcomes, strict=True):
        if outcome == "conflict":
            reject(row_number, raw, ["order_id: conflicts with stored order"])
    rejections.sort(key=lambda row: row["source_row"])
    reasons = Counter(reason for row in rejections for reason in row["rejection_reasons"])
    total = len(frame)
    accepted = outcomes.count("inserted") + outcomes.count("skipped")
    result = {
        "source": str(source),
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "total_rows": total,
        "valid_rows": accepted,
        "rejected_rows": len(rejections),
        "inserted_rows": outcomes.count("inserted"),
        "skipped_rows": outcomes.count("skipped"),
        "conflicting_rows": outcomes.count("conflict"),
        "duplicate_rows": reasons["order_id: duplicate in input"],
        "acceptance_rate": round(accepted / total, 6) if total else 0.0,
        "rejections_by_reason": dict(sorted(reasons.items())),
    }
    rejected.parent.mkdir(parents=True, exist_ok=True)
    with rejected.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_row", *COLUMNS, "rejection_reasons"])
        writer.writeheader()
        for row in rejections:
            writer.writerow({**row, "rejection_reasons": json.dumps(row["rejection_reasons"])})
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result
