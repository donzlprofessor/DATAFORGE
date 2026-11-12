import csv

import pytest

from dataforge.validation import COLUMNS


@pytest.fixture
def raw_order():
    return dict(
        zip(
            COLUMNS,
            ["ORD-1", "CUST-1", "2026-10-01", "Desk Lamp", "2", "19.90", "EUR"],
            strict=True,
        )
    )


@pytest.fixture
def write_csv(tmp_path):
    def write(rows, name="input.csv", columns=COLUMNS):
        path = tmp_path / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        return path

    return write


@pytest.fixture
def outputs(tmp_path):
    return {
        "database": tmp_path / "nested" / "orders.db",
        "report": tmp_path / "reports" / "quality.json",
        "rejected": tmp_path / "rejections" / "rows.csv",
    }
