#!/bin/bash
set -euo pipefail

POSTGRES_BIN="$(command -v postgres)"
ENTRYPOINT_BIN="/usr/local/bin/docker-entrypoint.sh"
PGDATA_DIR="${PGDATA:-/var/lib/postgresql/data}"
BOOTSTRAP_USER="${POSTGRES_USER:-postgres}"
APP_DB="${HERMES_TIMESCALE_DB:-hermes_trading}"
APP_USER="${HERMES_TIMESCALE_USER:-hermes}"
APP_PASSWORD="${HERMES_TIMESCALE_PASSWORD:-hermes}"

_escape_sql_literal() {
    printf "%s" "$1" | sed "s/'/''/g"
}

APP_DB_ESCAPED="$(_escape_sql_literal "$APP_DB")"
APP_USER_ESCAPED="$(_escape_sql_literal "$APP_USER")"
APP_PASSWORD_ESCAPED="$(_escape_sql_literal "$APP_PASSWORD")"

_ensure_app_role_single_user() {
    echo "Timescale role/db bootstrap: ensuring role=$APP_USER via single-user mode"
    su postgres -c "\"$POSTGRES_BIN\" --single -D \"$PGDATA_DIR\" postgres" <<SQL >/dev/null
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${APP_USER_ESCAPED}') THEN
        EXECUTE format('CREATE ROLE %I SUPERUSER LOGIN PASSWORD %L', '${APP_USER_ESCAPED}', '${APP_PASSWORD_ESCAPED}');
    ELSE
        EXECUTE format('ALTER ROLE %I WITH SUPERUSER LOGIN PASSWORD %L', '${APP_USER_ESCAPED}', '${APP_PASSWORD_ESCAPED}');
    END IF;
END
\$\$;
SQL
}

_provision_app_db() {
    local sql
    read -r -d '' sql <<SQL || true
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${APP_USER_ESCAPED}') THEN
        EXECUTE format('CREATE ROLE %I SUPERUSER LOGIN PASSWORD %L', '${APP_USER_ESCAPED}', '${APP_PASSWORD_ESCAPED}');
    ELSE
        EXECUTE format('ALTER ROLE %I WITH SUPERUSER LOGIN PASSWORD %L', '${APP_USER_ESCAPED}', '${APP_PASSWORD_ESCAPED}');
    END IF;
END
\$\$;

SELECT format('CREATE DATABASE %I OWNER %I', '${APP_DB_ESCAPED}', '${APP_USER_ESCAPED}')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '${APP_DB_ESCAPED}')
\gexec

GRANT ALL PRIVILEGES ON DATABASE "${APP_DB}" TO "${APP_USER}";
SQL

    if su postgres -c "psql -U \"$BOOTSTRAP_USER\" --dbname postgres -v ON_ERROR_STOP=1" <<<"$sql" >/dev/null 2>&1; then
        return 0
    fi

    if su postgres -c "psql -U \"$APP_USER\" --dbname postgres -v ON_ERROR_STOP=1" <<<"$sql" >/dev/null 2>&1; then
        return 0
    fi

    return 1
}

if [ -f "$PGDATA_DIR/PG_VERSION" ]; then
    _ensure_app_role_single_user
fi

"$ENTRYPOINT_BIN" postgres &
db_pid=$!

cleanup() {
    kill -TERM "$db_pid" 2>/dev/null || true
    wait "$db_pid"
}

trap cleanup SIGINT SIGTERM

echo "Timescale role/db bootstrap: waiting for PostgreSQL ..."
until su postgres -c "pg_isready -h /var/run/postgresql -p 5432 -U \"$APP_USER\"" >/dev/null 2>&1 || \
      su postgres -c "pg_isready -h /var/run/postgresql -p 5432 -U \"$BOOTSTRAP_USER\"" >/dev/null 2>&1; do
    sleep 1
done

echo "Timescale role/db bootstrap: ensuring role=$APP_USER db=$APP_DB"
if ! _provision_app_db; then
    echo "Timescale role/db bootstrap: failed to provision role/database" >&2
    exit 1
fi

echo "Timescale role/db bootstrap: complete"
wait "$db_pid"
