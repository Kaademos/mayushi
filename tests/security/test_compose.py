"""C-CFG-01 / C-DATA-01: static checks on docker-compose.yml."""

from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture(scope="module")
def services(repo_root: Path) -> dict[str, Any]:
    compose = yaml.safe_load((repo_root / "docker-compose.yml").read_text())
    result: dict[str, Any] = compose["services"]
    return result


def test_published_ports_bind_to_localhost(services: dict[str, Any]) -> None:
    for name, service in services.items():
        for port in service.get("ports", []):
            assert isinstance(port, str) and port.startswith("127.0.0.1:"), (name, port)


def test_secrets_have_no_fallback_values(services: dict[str, Any]) -> None:
    for name, service in services.items():
        for key, value in (service.get("environment") or {}).items():
            if any(word in key for word in ("PASSWORD", "SECRET", "TOKEN")):
                assert ":?" in str(value) and ":-" not in str(value), (name, key)


@pytest.mark.parametrize(("runtime", "migrator"), [("orders", "orders"), ("gateway", "gateway")])
def test_runtime_services_never_receive_owner_credentials(
    services: dict[str, Any], runtime: str, migrator: str
) -> None:
    runtime_env = str(services[runtime]["environment"])
    assert f"{migrator}_migrator" not in runtime_env
    assert "MIGRATOR" not in runtime_env
    migrate_env = str(services[f"{runtime}-migrate"]["environment"])
    assert f"{migrator}_migrator" in migrate_env
    depends = services[runtime]["depends_on"][f"{runtime}-migrate"]
    assert depends["condition"] == "service_completed_successfully"


def test_dedicated_keycloak_admin_is_not_in_container_config(services: dict[str, Any]) -> None:
    keycloak_env = str(services["keycloak"]["environment"])
    assert "KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD" in keycloak_env
    for service in services.values():
        assert "${KEYCLOAK_ADMIN_PASSWORD" not in str(service.get("environment"))
