"""C-CFG-01: no credentials or credential defaults in tracked files."""

import re
import subprocess
from pathlib import Path

import pytest

# Literal credential values assigned in code, config or env files.
SUSPICIOUS = [
    # password = "literal" / "secret": "literal" (but not psql's `PASSWORD :'var'`)
    re.compile(
        r"(?i)\b(password|passwd|secret|api[_-]?key|token)[\"']?"
        r"(\s*=\s*|\s*:\s+|:)[\"'][^\"'\s]{6,}[\"']"
    ),
    # FOO_PASSWORD=literal / FOO_SECRET: literal (env and YAML style, not ${...} references)
    re.compile(r"^\s*[A-Z0-9_]*(PASSWORD|SECRET|TOKEN|_KEY)(=|:\s+)(?!\$\{)[^\s#()]{6,}\s*$"),
    # ${FOO_PASSWORD:-fallback}: a default credential in compose or shell
    re.compile(r"\$\{[A-Z0-9_]*(PASSWORD|SECRET|TOKEN|_KEY):-[^}]+\}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(sk-ant-|sk-|AKIA|ghp_|xox[bp]-)[A-Za-z0-9]{8,}"),
]
ALLOWED = [re.compile(r"MP_SMTP_AUTH_")]
SKIP_SUFFIXES = {".lock"}
SKIP_DIRS = {"tests/security/"}


def tracked_files(repo_root: Path) -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [
        repo_root / name
        for name in output.splitlines()
        if Path(name).suffix not in SKIP_SUFFIXES
        and not any(name.startswith(d) for d in SKIP_DIRS)
        and (repo_root / name).is_file()
    ]


def test_no_credentials_in_tracked_files(repo_root: Path) -> None:
    findings = []
    for path in tracked_files(repo_root):
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if any(a.search(line) for a in ALLOWED):
                continue
            if any(p.search(line) for p in SUSPICIOUS):
                findings.append(f"{path.relative_to(repo_root)}:{number}: {line.strip()[:120]}")
    assert findings == []


def test_env_files_are_not_tracked(repo_root: Path) -> None:
    names = subprocess.run(
        ["git", "ls-files"], cwd=repo_root, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert ".env" not in names
    assert not [n for n in names if n.startswith(".private/")]


def test_env_example_holds_placeholders_only(repo_root: Path) -> None:
    for line in (repo_root / ".env.example").read_text().splitlines():
        key, _, value = line.partition("=")
        if re.search(r"PASSWORD|SECRET|_KEY$|ADMIN_USER", key):
            assert value == "", f"{key} must be empty in .env.example"


@pytest.mark.parametrize(
    "line",
    [
        "KC_BOOTSTRAP_ADMIN_PASSWORD: ${KEYCLOAK_ADMIN_PASSWORD:-admin}",
        'password = "hunter2hunter2"',
        "ANTHROPIC_API_KEY=sk-ant-abcdefghijk",
        "GATEWAY_DB_PASSWORD=gateway-local-dev",
    ],
)
def test_detector_catches_known_bad_lines(line: str) -> None:
    assert any(p.search(line) for p in SUSPICIOUS)


@pytest.mark.parametrize(
    "line",
    [
        "KC_BOOTSTRAP_ADMIN_PASSWORD: ${KEYCLOAK_ADMIN_PASSWORD:?run make bootstrap}",
        "KC_HOSTNAME: ${KEYCLOAK_PUBLIC_URL:-http://localhost:8080}",
        "CREATE ROLE gateway_svc LOGIN PASSWORD :'gateway_pw';",
        'data={"username": username, "password": password}',
        "POSTGRES_PASSWORD=",
        'DEMO_PASSWORD = os.environ.get("DEMO_USER_PASSWORD", "")',
    ],
)
def test_detector_ignores_references(line: str) -> None:
    assert not any(p.search(line) for p in SUSPICIOUS)
