#!/usr/bin/env bash
# Create .env from .env.example and generate every credential the stack needs.
#
#   scripts/bootstrap.sh              fill missing/empty values, refuse weak existing ones
#   ROTATE=1 scripts/bootstrap.sh     regenerate all managed values (then: make reset)
#
# Values are never printed. Existing strong values are never overwritten unless ROTATE=1.
set -euo pipefail

ENV_FILE=${ENV_FILE:-.env}
EXAMPLE_FILE=${EXAMPLE_FILE:-.env.example}
ROTATE=${ROTATE:-0}
MIN_SECRET_LENGTH=32

SECRET_KEYS=(
  POSTGRES_PASSWORD
  KEYCLOAK_DB_PASSWORD
  GATEWAY_DB_PASSWORD
  GATEWAY_MIGRATOR_DB_PASSWORD
  ORDERS_DB_PASSWORD
  ORDERS_MIGRATOR_DB_PASSWORD
  KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD
  KEYCLOAK_ADMIN_PASSWORD
  WEB_CLIENT_SECRET
  DEMO_USER_PASSWORD
)
WEAK_ADMIN_USERS=(admin administrator root keycloak)

umask 077

random_hex() {
  od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'
}

get_value() {
  grep -E "^$1=" "$ENV_FILE" | head -n 1 | cut -d= -f2- || true
}

set_value() {
  local key=$1 value=$2 tmp
  tmp=$(mktemp)
  awk -v key="$key" -v value="$value" '
    index($0, key "=") == 1 { print key "=" value; next }
    { print }
  ' "$ENV_FILE" >"$tmp"
  cat "$tmp" >"$ENV_FILE"
  rm -f "$tmp"
}

if [[ ! -f "$EXAMPLE_FILE" ]]; then
  echo "error: $EXAMPLE_FILE not found" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$EXAMPLE_FILE" "$ENV_FILE"
  echo "Created $ENV_FILE from $EXAMPLE_FILE"
fi
chmod 600 "$ENV_FILE"

while IFS= read -r line; do
  key=${line%%=*}
  if ! grep -qE "^${key}=" "$ENV_FILE"; then
    printf '%s\n' "$line" >>"$ENV_FILE"
    echo "Added $key"
  fi
done < <(grep -E '^[A-Z][A-Z0-9_]*=' "$EXAMPLE_FILE")

weak=()

for key in "${SECRET_KEYS[@]}"; do
  current=$(get_value "$key")
  if [[ -z "$current" || "$ROTATE" == "1" ]]; then
    set_value "$key" "$(random_hex 32)"
    echo "Generated $key"
  elif ((${#current} < MIN_SECRET_LENGTH)); then
    weak+=("$key")
  fi
done

for key in KEYCLOAK_BOOTSTRAP_ADMIN_USER KEYCLOAK_ADMIN_USER; do
  current=$(get_value "$key")
  if [[ -z "$current" || "$ROTATE" == "1" ]]; then
    set_value "$key" "admin-$(random_hex 4)"
    echo "Generated $key"
  else
    for name in "${WEAK_ADMIN_USERS[@]}"; do
      [[ "${current,,}" == "$name" ]] && weak+=("$key")
    done
  fi
done

if [[ "$(get_value KEYCLOAK_BOOTSTRAP_ADMIN_USER)" == "$(get_value KEYCLOAK_ADMIN_USER)" ]]; then
  weak+=(KEYCLOAK_ADMIN_USER)
fi

if ((${#weak[@]} > 0)); then
  echo "error: weak or default values in $ENV_FILE: ${weak[*]}" >&2
  echo "       run 'make bootstrap ROTATE=1' and then 'make reset'" >&2
  exit 1
fi

echo "$ENV_FILE is ready"
