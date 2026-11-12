"""Command-line entry point."""

from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy.exc import SQLAlchemyError

from dataforge.pipeline import PipelineError, run_pipeline

app = typer.Typer(help="Import e-commerce orders and report data quality.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """DATAFORGE offline ETL."""


@app.command()
def run(
    source: Annotated[Path, typer.Argument(help="UTF-8 orders CSV.")],
    database: Annotated[Path, typer.Option(help="SQLite database path.")] = Path(
        "artifacts/orders.db"
    ),
    report: Annotated[Path, typer.Option(help="JSON quality report.")] = Path(
        "artifacts/quality_report.json"
    ),
    rejected: Annotated[Path, typer.Option(help="Rejected source records CSV.")] = Path(
        "artifacts/rejected_orders.csv"
    ),
) -> None:
    """Validate, normalize, and import a CSV file."""
    try:
        result = run_pipeline(source, database, report, rejected)
    except (PipelineError, OSError, SQLAlchemyError) as exc:
        typer.echo(f"Import failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"Processed {result['total_rows']} rows: {result['inserted_rows']} inserted, "
        f"{result['skipped_rows']} skipped, {result['rejected_rows']} rejected "
        f"({result['conflicting_rows']} conflicts)."
    )
    typer.echo(f"Quality report: {report}\nRejected records: {rejected}")
