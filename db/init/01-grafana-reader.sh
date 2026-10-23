#!/bin/sh
# Runs once, when the PostgreSQL volume is first created.
# Grafana connects as a read-only user so a dashboard can never change data.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE grafana_reader WITH LOGIN PASSWORD '${GRAFANA_DB_PASSWORD}';
GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO grafana_reader;
GRANT USAGE ON SCHEMA public TO grafana_reader;
-- Tables and views Django creates later are readable automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE "${POSTGRES_USER}" IN SCHEMA public GRANT SELECT ON TABLES TO grafana_reader;
ALTER ROLE grafana_reader SET default_transaction_read_only = on;
ALTER ROLE grafana_reader SET statement_timeout = '15s';
SQL
