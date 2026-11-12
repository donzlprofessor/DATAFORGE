from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from dataforge.validation import COLUMNS, Order, price_text


def test_normalization(raw_order):
    order = Order.model_validate({key: f" {value} " for key, value in raw_order.items()})
    assert order.order_id == "ORD-1"
    assert order.order_date == date(2026, 10, 1)
    assert order.quantity == 2
    assert order.unit_price == Decimal("19.90")
    assert Order.model_validate({**raw_order, "currency": " eur "}).currency == "EUR"


@pytest.mark.parametrize("field", COLUMNS)
@pytest.mark.parametrize("value", ["", "   ", None])
def test_missing_values(raw_order, field, value):
    with pytest.raises(ValidationError, match="required value is missing"):
        Order.model_validate({**raw_order, field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("order_date", "2026-02-30"),
        ("order_date", "10/01/2026"),
        ("order_date", "2026-1-1"),
        ("order_date", "2026-01-01T00:00:00"),
        ("quantity", "0"),
        ("quantity", "-2"),
        ("quantity", "1.5"),
        ("quantity", "NaN"),
        ("quantity", "9223372036854775808"),
        ("unit_price", "-0.01"),
        ("unit_price", "NaN"),
        ("unit_price", "sNaN"),
        ("unit_price", "Infinity"),
        ("unit_price", "-Infinity"),
        ("unit_price", "abc"),
        ("unit_price", "1e3"),
        ("currency", "EURO"),
        ("currency", "12A"),
    ],
)
def test_invalid_values(raw_order, field, value):
    with pytest.raises(ValidationError):
        Order.model_validate({**raw_order, field: value})


@pytest.mark.parametrize(
    "value", ["0", "-0.00", "0.10", "12345678901234567890.12345678901234567890"]
)
def test_exact_decimal(raw_order, value):
    order = Order.model_validate({**raw_order, "unit_price": value})
    assert order.unit_price == Decimal(value)
    assert Decimal(price_text(order.unit_price)) == Decimal(value)


def test_all_reasons_are_returned_in_field_order(raw_order):
    with pytest.raises(ValidationError) as error:
        Order.model_validate({**raw_order, "quantity": "-1", "unit_price": "NaN"})
    assert [item["loc"][0] for item in error.value.errors()] == ["quantity", "unit_price"]
