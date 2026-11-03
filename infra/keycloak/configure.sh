#!/usr/bin/env bash
# Post-start Keycloak configuration, run inside the keycloak container by `make seed`:
#   docker compose exec -T -e KEYCLOAK_ADMIN_USER -e KEYCLOAK_ADMIN_PASSWORD \
#     -e DEMO_USER_PASSWORD -e WEB_CLIENT_SECRET keycloak bash /opt/mayushi/configure.sh
#
# 1. Ensures a dedicated, permanent master-realm admin exists and removes the temporary
#    bootstrap admin, so the KC_BOOTSTRAP_ADMIN_* values in the container environment no
#    longer grant access. The dedicated admin's password is only ever passed to this exec.
# 2. Applies credentials that must not live in the realm export.
# Secrets are passed to kcadm on stdin where possible. Safe to run repeatedly.
set -euo pipefail

: "${KC_BOOTSTRAP_ADMIN_USERNAME:?}" "${KC_BOOTSTRAP_ADMIN_PASSWORD:?}"
: "${KEYCLOAK_ADMIN_USER:?KEYCLOAK_ADMIN_USER is required (make bootstrap)}"
: "${KEYCLOAK_ADMIN_PASSWORD:?KEYCLOAK_ADMIN_PASSWORD is required (make bootstrap)}"
: "${DEMO_USER_PASSWORD:?DEMO_USER_PASSWORD is required (make bootstrap)}"
: "${WEB_CLIENT_SECRET:?WEB_CLIENT_SECRET is required (make bootstrap)}"

if [[ "$KEYCLOAK_ADMIN_USER" == "$KC_BOOTSTRAP_ADMIN_USERNAME" ]]; then
  echo "error: dedicated admin must differ from the bootstrap admin" >&2
  exit 1
fi

REALM=northwind
KCADM=/opt/keycloak/bin/kcadm.sh
CONFIG=$(mktemp)
trap 'rm -f "$CONFIG"' EXIT

kcadm() { "$KCADM" "$@" --config "$CONFIG"; }

login() {
  "$KCADM" config credentials \
    --config "$CONFIG" \
    --server http://localhost:8080 \
    --realm master \
    --user "$1" \
    --password "$2" >/dev/null 2>&1
}

find_user_id() {
  kcadm get users -r master -q exact=true -q "username=$1" --fields id --format csv --noquotes
}

if login "$KEYCLOAK_ADMIN_USER" "$KEYCLOAK_ADMIN_PASSWORD"; then
  echo "Authenticated as dedicated admin"
elif login "$KC_BOOTSTRAP_ADMIN_USERNAME" "$KC_BOOTSTRAP_ADMIN_PASSWORD"; then
  if [[ -z "$(find_user_id "$KEYCLOAK_ADMIN_USER")" ]]; then
    printf '{"username":"%s","enabled":true}' "$KEYCLOAK_ADMIN_USER" | kcadm create users -r master -f -
  fi
  admin_id=$(find_user_id "$KEYCLOAK_ADMIN_USER")
  printf '{"type":"password","temporary":false,"value":"%s"}' "$KEYCLOAK_ADMIN_PASSWORD" |
    kcadm update "users/$admin_id/reset-password" -r master -f -
  kcadm add-roles -r master --uid "$admin_id" --rolename admin
  login "$KEYCLOAK_ADMIN_USER" "$KEYCLOAK_ADMIN_PASSWORD"
  echo "Created dedicated admin"
else
  echo "error: neither the dedicated nor the bootstrap admin can authenticate" >&2
  exit 1
fi

bootstrap_id=$(find_user_id "$KC_BOOTSTRAP_ADMIN_USERNAME")
if [[ -n "$bootstrap_id" ]]; then
  kcadm delete "users/$bootstrap_id" -r master
  echo "Removed temporary bootstrap admin"
fi

client_id=$(kcadm get clients -r "$REALM" -q clientId=mayushi-web --fields id --format csv --noquotes)
printf '{"secret":"%s"}' "$WEB_CLIENT_SECRET" | kcadm update "clients/$client_id" -r "$REALM" -f -
echo "Applied mayushi-web client secret"

count=0
while IFS=, read -r user_id username; do
  [[ -n "$user_id" ]] || continue
  printf '{"type":"password","temporary":false,"value":"%s"}' "$DEMO_USER_PASSWORD" |
    kcadm update "users/$user_id/reset-password" -r "$REALM" -f -
  count=$((count + 1))
done < <(kcadm get users -r "$REALM" --fields id,username --format csv --noquotes)
echo "Applied demo password to $count users"
