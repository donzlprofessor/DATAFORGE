from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError

from dataforge.database import metadata, orders, persist
from dataforge.validation import Order


def test_exact_storage_and_equivalent_prices(raw_order, tmp_path):
    database = tmp_path / "orders.db"
    precise = "12345678901234567890.12345678901234567890"
    order = Order.model_validate({**raw_order, "unit_price": precise})
    assert persist(database, [order]) == ["inserted"]
    equivalent = Order.model_validate({**raw_order, "unit_price": precise + "0"})
    assert persist(database, [equivalent]) == ["skipped"]
    engine = create_engine(f"sqlite:///{database}")
    try:
        with engine.connect() as connection:
            stored = connection.execute(select(orders.c.unit_price)).scalar_one()
            assert isinstance(stored, str)
            assert Decimal(stored) == Decimal(precise)
    finally:
        engine.dispose()


def test_failure_rolls_back_whole_batch(raw_order, tmp_path):
    database = tmp_path / "orders.db"
    engine = create_engine(f"sqlite:///{database}")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER fail_second BEFORE INSERT ON orders "
                "WHEN NEW.order_id = 'ORD-2' "
                "BEGIN SELECT RAISE(ABORT, 'simulated database failure'); END"
            )
        records = [
            Order.model_validate(raw_order),
            Order.model_validate({**raw_order, "order_id": "ORD-2"}),
        ]
        with pytest.raises(IntegrityError, match="simulated database failure"):
            persist(database, records)
        with engine.connect() as connection:
            assert connection.execute(select(orders)).all() == []
    finally:
        engine.dispose()
