from sqlalchemy import insert, text
from sqlalchemy.orm import Session

from orders.models import SCHEMA, Address, Base, Customer, Order, OrderItem, Payment
from orders.seed.generate import Dataset

_LOAD_ORDER: tuple[tuple[type[Base], str], ...] = (
    (Customer, "customers"),
    (Address, "addresses"),
    (Order, "orders"),
    (OrderItem, "order_items"),
    (Payment, "payments"),
)


def load_dataset(session: Session, data: Dataset) -> dict[str, int]:
    """Replace all rows in the orders schema with `data`, in one transaction."""
    tables = ", ".join(f"{SCHEMA}.{model.__tablename__}" for model, _ in reversed(_LOAD_ORDER))
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

    counts: dict[str, int] = {}
    for model, attr in _LOAD_ORDER:
        rows = getattr(data, attr)
        if rows:
            session.execute(insert(model), rows)
        table = f"{SCHEMA}.{model.__tablename__}"
        session.execute(
            text(
                "SELECT setval(pg_get_serial_sequence(:table, 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
            ),
            {"table": table},
        )
        counts[attr] = len(rows)
    session.commit()
    return counts
