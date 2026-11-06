#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=api_password="$REST_API_PASSWORD" <<'SQL'
CREATE ROLE rest_reader NOLOGIN;
CREATE ROLE rest_authenticator NOINHERIT LOGIN PASSWORD :'api_password';
GRANT rest_reader TO rest_authenticator;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA rest_probe;
-- Explicit smoke fixture, unrelated to application or household data.
CREATE TABLE rest_probe.health (status text PRIMARY KEY CHECK (status = 'ok'));
INSERT INTO rest_probe.health VALUES ('ok');
GRANT USAGE ON SCHEMA rest_probe TO rest_reader;
GRANT SELECT ON rest_probe.health TO rest_reader;
SQL
