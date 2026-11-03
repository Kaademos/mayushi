import json
import os
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REALM_EXPORT = REPO_ROOT / "infra" / "keycloak" / "realm-northwind.json"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def realm() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(REALM_EXPORT.read_text())
    return data


def require_env(*names: str) -> dict[str, str]:
    values = {name: os.environ.get(name, "") for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        pytest.skip(f"{', '.join(missing)} not set (run via `make test-integration`)")
    return values
