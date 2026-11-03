"""C-CFG-01: `make bootstrap` generates strong credentials and refuses weak ones."""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

MANAGED = [
    "POSTGRES_PASSWORD",
    "KEYCLOAK_DB_PASSWORD",
    "GATEWAY_DB_PASSWORD",
    "GATEWAY_MIGRATOR_DB_PASSWORD",
    "ORDERS_DB_PASSWORD",
    "ORDERS_MIGRATOR_DB_PASSWORD",
    "KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD",
    "KEYCLOAK_ADMIN_PASSWORD",
    "WEB_CLIENT_SECRET",
    "DEMO_USER_PASSWORD",
]


@pytest.fixture
def workdir(tmp_path: Path, repo_root: Path) -> Path:
    shutil.copy(repo_root / ".env.example", tmp_path / ".env.example")
    return tmp_path


def run_bootstrap(
    repo_root: Path, workdir: Path, rotate: bool = False
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "ROTATE": "1" if rotate else "0"}
    return subprocess.run(
        [str(repo_root / "scripts" / "bootstrap.sh")],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
    )


def read_env(path: Path) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return {k: v for k, v in pairs if not k.startswith("#")}


def test_generates_every_credential(repo_root: Path, workdir: Path) -> None:
    result = run_bootstrap(repo_root, workdir)
    assert result.returncode == 0, result.stderr
    values = read_env(workdir / ".env")
    for key in MANAGED:
        assert re.fullmatch(r"[0-9a-f]{64}", values[key]), key
    for key in ("KEYCLOAK_ADMIN_USER", "KEYCLOAK_BOOTSTRAP_ADMIN_USER"):
        assert re.fullmatch(r"admin-[0-9a-f]{8}", values[key]), key
    assert values["KEYCLOAK_ADMIN_USER"] != values["KEYCLOAK_BOOTSTRAP_ADMIN_USER"]
    assert len({values[k] for k in MANAGED}) == len(MANAGED), "values must be distinct"


def test_never_prints_values(repo_root: Path, workdir: Path) -> None:
    result = run_bootstrap(repo_root, workdir)
    values = read_env(workdir / ".env")
    for key in MANAGED:
        assert values[key] not in result.stdout + result.stderr


def test_env_file_is_private(repo_root: Path, workdir: Path) -> None:
    run_bootstrap(repo_root, workdir)
    mode = stat.S_IMODE((workdir / ".env").stat().st_mode)
    assert mode == 0o600


def test_is_idempotent(repo_root: Path, workdir: Path) -> None:
    run_bootstrap(repo_root, workdir)
    first = (workdir / ".env").read_text()
    assert run_bootstrap(repo_root, workdir).returncode == 0
    assert (workdir / ".env").read_text() == first


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("KEYCLOAK_ADMIN_PASSWORD", "admin"),
        ("KEYCLOAK_ADMIN_USER", "admin"),
        ("POSTGRES_PASSWORD", "postgres-local-dev"),
        ("KEYCLOAK_BOOTSTRAP_ADMIN_USER", "Admin"),
    ],
)
def test_refuses_weak_existing_values(repo_root: Path, workdir: Path, key: str, value: str) -> None:
    run_bootstrap(repo_root, workdir)
    env_file = workdir / ".env"
    text = re.sub(rf"(?m)^{key}=.*$", f"{key}={value}", env_file.read_text())
    env_file.write_text(text)
    result = run_bootstrap(repo_root, workdir)
    assert result.returncode != 0
    assert key in result.stderr
    assert read_env(env_file)[key] == value, "must not silently overwrite"


def test_rotate_replaces_all_values(repo_root: Path, workdir: Path) -> None:
    run_bootstrap(repo_root, workdir)
    before = read_env(workdir / ".env")
    assert run_bootstrap(repo_root, workdir, rotate=True).returncode == 0
    after = read_env(workdir / ".env")
    for key in [*MANAGED, "KEYCLOAK_ADMIN_USER", "KEYCLOAK_BOOTSTRAP_ADMIN_USER"]:
        assert after[key] != before[key], key


def test_refuses_dedicated_admin_equal_to_bootstrap_admin(repo_root: Path, workdir: Path) -> None:
    run_bootstrap(repo_root, workdir)
    env_file = workdir / ".env"
    bootstrap_user = read_env(env_file)["KEYCLOAK_BOOTSTRAP_ADMIN_USER"]
    text = re.sub(
        r"(?m)^KEYCLOAK_ADMIN_USER=.*$",
        f"KEYCLOAK_ADMIN_USER={bootstrap_user}",
        env_file.read_text(),
    )
    env_file.write_text(text)
    result = run_bootstrap(repo_root, workdir)
    assert result.returncode != 0
    assert "KEYCLOAK_ADMIN_USER" in result.stderr
