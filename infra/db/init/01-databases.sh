#!/usr/bin/env bash
# Runs once, on first start of an empty Postgres data volume.
#
# Per service there are two login roles:
#   <svc>_migrator  owns the service schema; used only by the one-shot migrate job
#   <svc>_svc       runtime role; no DDL, only the privileges its migrations grant
set -euo pipefail

: "${KEYCLOAK_DB_PASSWORD:?}" "${GATEWAY_DB_PASSWORD:?}" "${GATEWAY_MIGRATOR_DB_PASSWORD:?}"
: "${ORDERS_DB_PASSWORD:?}" "${ORDERS_MIGRATOR_DB_PASSWORD:?}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v keycloak_pw="$KEYCLOAK_DB_PASSWORD" \
  -v gateway_pw="$GATEWAY_DB_PASSWORD" \
  -v gateway_migrator_pw="$GATEWAY_MIGRATOR_DB_PASSWORD" \
  -v orders_pw="$ORDERS_DB_PASSWORD" \
  -v orders_migrator_pw="$ORDERS_MIGRATOR_DB_PASSWORD" <<-'SQL'
  CREATE ROLE keycloak LOGIN PASSWORD :'keycloak_pw';
  CREATE ROLE gateway_migrator LOGIN PASSWORD :'gateway_migrator_pw';
  CREATE ROLE gateway_svc LOGIN PASSWORD :'gateway_pw';
  CREATE ROLE orders_migrator LOGIN PASSWORD :'orders_migrator_pw';
  CREATE ROLE orders_svc LOGIN PASSWORD :'orders_pw';

  CREATE DATABASE keycloak OWNER keycloak;
  CREATE DATABASE mayushi;

  REVOKE ALL ON DATABASE postgres FROM PUBLIC;
  REVOKE ALL ON DATABASE keycloak FROM PUBLIC;
  REVOKE ALL ON DATABASE mayushi FROM PUBLIC;
  GRANT CONNECT ON DATABASE keycloak TO keycloak;
  GRANT CONNECT ON DATABASE mayushi TO gateway_migrator, gateway_svc, orders_migrator, orders_svc;
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname mayushi <<-'SQL'
  REVOKE ALL ON SCHEMA public FROM PUBLIC;
  CREATE EXTENSION IF NOT EXISTS vector;

  CREATE SCHEMA app AUTHORIZATION gateway_migrator;
  CREATE SCHEMA orders AUTHORIZATION orders_migrator;
  REVOKE ALL ON SCHEMA app FROM PUBLIC;
  REVOKE ALL ON SCHEMA orders FROM PUBLIC;
SQL
