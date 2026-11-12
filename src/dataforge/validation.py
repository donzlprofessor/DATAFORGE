"""Validate and normalize the seven source order fields."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, field_validator

COLUMNS = (
    "order_id",
    "customer_id",
    "order_date",
    "product",
    "quantity",
    "unit_price",
    "currency",
)


class Order(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    order_id: str
    customer_id: str
    order_date: date
    product: str
    quantity: int
    unit_price: Decimal
    currency: str

    @field_validator("order_date", mode="before")
    @classmethod
    def valid_date(cls, value: object) -> date:
        if isinstance(value, date):
            return value
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("expected date in YYYY-MM-DD format")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("invalid calendar date") from exc

    @field_validator("quantity", mode="before")
    @classmethod
    def valid_quantity(cls, value: object) -> int:
        if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
            raise ValueError("quantity must be a positive integer")
        quantity = int(str(value))
        if not 1 <= quantity <= 2**63 - 1:
            raise ValueError("quantity must be between 1 and 9223372036854775807")
        return quantity

    @field_validator("unit_price", mode="before")
    @classmethod
    def valid_price(cls, value: object) -> Decimal:
        # Plain decimal notation prevents exponent expansion and float conversion.
        text = str(value)
        try:
            price = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("unit_price must be a decimal number") from exc
        if not price.is_finite():
            raise ValueError("unit_price must be finite")
        if price < 0:
            raise ValueError("unit_price must be nonnegative")
        if not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", text):
            raise ValueError("unit_price must use plain decimal notation")
        return abs(price) if price.is_zero() else price

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str) -> str:
        value = value.upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("currency must contain three ASCII letters")
        return value

    @field_validator("*", mode="before")
    @classmethod
    def trim_required(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
        if value is None or value == "":
            raise ValueError("required value is missing")
        return value


def price_text(price: Decimal) -> str:
    """Canonical exact decimal text without using the Decimal context precision."""
    text = format(price, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
