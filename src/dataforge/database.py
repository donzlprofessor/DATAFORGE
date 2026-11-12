"""SQLite persistence; one transaction covers all order decisions and inserts."""

from pathlib import Path

from sqlalchemy import (
    URL,
    Column,
    Date,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
)

from dataforge.validation import Order, price_text

metadata = MetaData()
orders = Table(
    "orders",
    metadata,
    Column("order_id", String, primary_key=True),
    Column("customer_id", String, nullable=False),
    Column("order_date", Date, nullable=False),
    Column("product", String, nullable=False),
    Column("quantity", Integer, nullable=False),
    # SQLite NUMERIC affinity can silently round through binary floats.
    Column("unit_price", Text, nullable=False),
    Column("currency", String(3), nullable=False),
)


def persist(database: Path, records: list[Order]) -> list[str]:
    """Return inserted/skipped/conflict for each record; failures roll back all rows."""
    database.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create("sqlite", database=str(database)))
    try:
        metadata.create_all(engine)
        outcomes = []
        with engine.connect() as connection:
            # Serialize writers before reading existing IDs, including concurrent imports.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                for order in records:
                    values = order.model_dump()
                    values["unit_price"] = price_text(order.unit_price)
                    existing = (
                        connection.execute(
                            select(orders).where(orders.c.order_id == order.order_id)
                        )
                        .mappings()
                        .first()
                    )
                    if existing is None:
                        connection.execute(orders.insert().values(**values))
                        outcomes.append("inserted")
                    else:
                        outcomes.append("skipped" if dict(existing) == values else "conflict")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return outcomes
    finally:
        engine.dispose()
