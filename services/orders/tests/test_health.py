from collections.abc import Iterator
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from orders.db import get_session
from orders.main import app


def test_healthz() -> None:
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz_reports_database_failure() -> None:
    def broken_session() -> Iterator[MagicMock]:
        session = MagicMock()
        session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("down"))
        yield session

    app.dependency_overrides[get_session] = broken_session
    try:
        with TestClient(app) as client:
            response = client.get("/readyz")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
