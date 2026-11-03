"""C-DATA-01: least-privilege database roles (live; needs `make up && make seed`)."""

import os
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import errors

from conftest import require_env

pytestmark = pytest.mark.integration

HOST = os.environ.get("POSTGRES_HOST", "127.0.0.1")
PORT = int(os.environ.get("POSTGRES_PORT", "5432"))

ROLE_PASSWORDS = {
    "gateway_svc": "GATEWAY_DB_PASSWORD",
    "gateway_migrator": "GATEWAY_MIGRATOR_DB_PASSWORD",
    "orders_svc": "ORDERS_DB_PASSWORD",
    "orders_migrator": "ORDERS_MIGRATOR_DB_PASSWORD",
}


def connect(role: str, dbname: str = "mayushi") -> psycopg.Connection[tuple[object, ...]]:
    password = require_env(ROLE_PASSWORDS[role])[ROLE_PASSWORDS[role]]
    return psycopg.connect(
        host=HOST, port=PORT, user=role, password=password, dbname=dbname, connect_timeout=5
    )


@pytest.fixture
def db(request: pytest.FixtureRequest) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    with connect(request.param) as conn:
        yield conn
        conn.rollback()


def assert_denied(conn: psycopg.Connection[tuple[object, ...]], sql: str) -> None:
    with pytest.raises(errors.InsufficientPrivilege):
        conn.execute(sql)
    conn.rollback()


@pytest.mark.parametrize("role", list(ROLE_PASSWORDS))
def test_no_role_has_elevated_attributes(role: str) -> None:
    with connect(role) as conn:
        row = conn.execute(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication "
            "FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
    assert row == (False, False, False, False, False)


@pytest.mark.parametrize("db", ["gateway_svc"], indirect=True)
class TestGatewayRuntimeRole:
    def test_reads_tenants(self, db: psycopg.Connection[tuple[object, ...]]) -> None:
        count = db.execute("SELECT count(*) FROM app.tenants").fetchone()
        assert count is not None and count[0] == 2

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO app.tenants (slug, display_name, is_active) VALUES ('x', 'x', true)",
            "UPDATE app.tenants SET is_active = false",
            "DELETE FROM app.tenants",
            "SELECT * FROM app.alembic_version",
            "SELECT * FROM orders.customers",
            "CREATE TABLE app.scratch (id int)",
            "CREATE TABLE public.scratch (id int)",
            "DROP TABLE app.tenants",
        ],
    )
    def test_denied(self, db: psycopg.Connection[tuple[object, ...]], sql: str) -> None:
        assert_denied(db, sql)


@pytest.mark.parametrize("db", ["orders_svc"], indirect=True)
class TestOrdersRuntimeRole:
    def test_dml_on_business_tables(self, db: psycopg.Connection[tuple[object, ...]]) -> None:
        db.execute("UPDATE orders.orders SET status = status WHERE id = 1")
        row = db.execute("SELECT count(*) FROM orders.orders").fetchone()
        assert row is not None and row[0] == 200

    @pytest.mark.parametrize(
        "sql",
        [
            "TRUNCATE orders.payments",
            "SELECT * FROM orders.alembic_version",
            "SELECT * FROM app.tenants",
            "CREATE TABLE orders.scratch (id int)",
            "ALTER TABLE orders.orders ADD COLUMN note text",
            "DROP TABLE orders.payments",
            "CREATE TABLE public.scratch (id int)",
        ],
    )
    def test_denied(self, db: psycopg.Connection[tuple[object, ...]], sql: str) -> None:
        assert_denied(db, sql)


@pytest.mark.parametrize(
    ("role", "foreign_table"),
    [("gateway_migrator", "orders.customers"), ("orders_migrator", "app.tenants")],
)
def test_migrators_cannot_read_other_service_schemas(role: str, foreign_table: str) -> None:
    with connect(role) as conn:
        assert_denied(conn, f"SELECT * FROM {foreign_table}")


@pytest.mark.parametrize("role", list(ROLE_PASSWORDS))
def test_service_roles_cannot_connect_to_keycloak_database(role: str) -> None:
    with pytest.raises(psycopg.OperationalError, match="permission denied"):
        connect(role, dbname="keycloak").close()
