import csv
import json
from pathlib import Path

import pytest

from dataforge.pipeline import PipelineError, load_csv, run_pipeline


def read_rejected(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_quality_artifacts_and_idempotency(raw_order, write_csv, outputs):
    source = write_csv(
        [
            raw_order,
            {**raw_order, "order_id": " ORD-1 "},
            {**raw_order, "order_id": "ORD-2", "quantity": "0", "unit_price": "-1"},
        ]
    )
    first = run_pipeline(source, **outputs)
    assert (first["total_rows"], first["valid_rows"], first["rejected_rows"]) == (3, 1, 2)
    assert first["inserted_rows"] == 1
    assert first["duplicate_rows"] == 1
    assert first["acceptance_rate"] == 0.333333
    rejected = read_rejected(outputs["rejected"])
    assert [row["source_row"] for row in rejected] == ["3", "4"]
    assert rejected[0]["order_id"] == " ORD-1 "
    assert len(json.loads(rejected[1]["rejection_reasons"])) == 2
    assert sum(first["rejections_by_reason"].values()) == 3
    assert json.loads(outputs["report"].read_text()) == first
    second = run_pipeline(source, **outputs)
    assert second["inserted_rows"] == 0
    assert second["skipped_rows"] == 1
    assert second["rejections_by_reason"] == first["rejections_by_reason"]


def test_invalid_first_occurrence_does_not_claim_id(raw_order, write_csv, outputs):
    source = write_csv([{**raw_order, "quantity": "0"}, raw_order])
    report = run_pipeline(source, **outputs)
    assert report["inserted_rows"] == 1
    assert report["duplicate_rows"] == 0


def test_database_conflict(raw_order, write_csv, outputs):
    run_pipeline(write_csv([raw_order]), **outputs)
    report = run_pipeline(write_csv([{**raw_order, "product": "Changed"}]), **outputs)
    assert report["conflicting_rows"] == report["rejected_rows"] == 1
    assert report["valid_rows"] == report["inserted_rows"] == 0
    assert json.loads(read_rejected(outputs["rejected"])[0]["rejection_reasons"]) == [
        "order_id: conflicts with stored order"
    ]
    assert run_pipeline(write_csv([raw_order]), **outputs)["skipped_rows"] == 1


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("order_id,product\n1,Lamp\n", "Missing required columns"),
        ("order_id,customer_id,order_date,product,quantity,unit_price,currency\n1,2\n", "fields"),
        (
            'order_id,customer_id,order_date,product,quantity,unit_price,currency\n"unclosed',
            "Malformed",
        ),
        (
            "order_id,customer_id,order_date,product,quantity,unit_price,currency,order_id\n",
            "Duplicate",
        ),
        ("order_id,customer_id,order_date,product,quantity,unit_price,currency,extra\n", "exactly"),
        ("order_id,customer_id,order_date,product,quantity,unit_price,currency\n\n", "fields"),
        ("order_id,customer_id,order_date,product,quantity,unit_price,currency\x00\n", "NUL"),
    ],
)
def test_bad_csv_does_not_create_database(tmp_path, outputs, text, message):
    source = tmp_path / "bad.csv"
    source.write_text(text)
    with pytest.raises(PipelineError, match=message):
        run_pipeline(source, **outputs)
    assert not outputs["database"].exists()


def test_header_only(write_csv, outputs):
    report = run_pipeline(write_csv([]), **outputs)
    assert report["total_rows"] == report["inserted_rows"] == 0
    assert report["acceptance_rate"] == 0
    assert read_rejected(outputs["rejected"]) == []


def test_multiline_rows_and_bom(raw_order, write_csv, outputs):
    source = write_csv(
        [
            {**raw_order, "product": "Desk\nLamp"},
            {**raw_order, "order_id": "ORD-2", "unit_price": "NaN"},
        ]
    )
    source.write_bytes(b"\xef\xbb\xbf" + source.read_bytes())
    report = run_pipeline(source, **outputs)
    assert report["inserted_rows"] == 1
    assert read_rejected(outputs["rejected"])[0]["source_row"] == "4"


def test_invalid_encoding(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_bytes(b"\xff")
    with pytest.raises(PipelineError, match="Malformed CSV"):
        load_csv(source)


def test_literal_na_is_not_missing(raw_order, write_csv, outputs):
    assert (
        run_pipeline(write_csv([{**raw_order, "product": "NA"}]), **outputs)["inserted_rows"] == 1
    )


def test_path_collision(raw_order, write_csv, outputs):
    source = write_csv([raw_order])
    original = source.read_bytes()
    with pytest.raises(PipelineError, match="distinct"):
        run_pipeline(source, **{**outputs, "report": source})
    assert source.read_bytes() == original


def test_sample_data(outputs):
    result = run_pipeline(Path(__file__).parents[1] / "data" / "sample_orders.csv", **outputs)
    assert (result["total_rows"], result["inserted_rows"], result["rejected_rows"]) == (19, 8, 11)
    assert result["duplicate_rows"] == 1
