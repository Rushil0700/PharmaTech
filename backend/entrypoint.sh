#!/bin/sh
set -e

echo "Waiting for PostgreSQL at ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
python - <<'PY'
import os, time, psycopg
for attempt in range(60):
    try:
        psycopg.connect(
            host=os.environ.get("POSTGRES_HOST", "db"), port=os.environ.get("POSTGRES_PORT", "5432"),
            dbname=os.environ.get("POSTGRES_DB", "pharmatrack"), user=os.environ.get("POSTGRES_USER", "pharmatrack"),
            password=os.environ.get("POSTGRES_PASSWORD", ""), connect_timeout=3,
        ).close()
        break
    except psycopg.OperationalError:
        time.sleep(2)
else:
    raise SystemExit("Database never became available")
PY

python manage.py migrate --noinput

if [ "${SEED_DEMO_DATA:-true}" = "true" ]; then
    python manage.py seed_data   # no-op when data already exists
fi

exec "$@"
