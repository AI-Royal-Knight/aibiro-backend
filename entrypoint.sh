#!/usr/bin/env sh
set -e

# Wait for PostgreSQL database if DATABASE_URL is configured for postgres
if [ -n "$DATABASE_URL" ] && echo "$DATABASE_URL" | grep -qE "postgres(ql)?://"; then
    echo "Waiting for PostgreSQL database to be ready..."
    python - <<'EOF'
import os
import sys
import time
from urllib.parse import urlparse
import psycopg

db_url = os.environ.get("DATABASE_URL", "")
parsed = urlparse(db_url)

host = parsed.hostname or "db"
port = parsed.port or 5432
user = parsed.username or "postgres"
password = parsed.password or ""
dbname = parsed.path.lstrip("/") or "postgres"

max_retries = 30
while max_retries > 0:
    try:
        conn = psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
            connect_timeout=3,
        )
        conn.close()
        print(f"Database at {host}:{port} is reachable.")
        sys.exit(0)
    except Exception as e:
        max_retries -= 1
        time.sleep(1)

print("Timed out waiting for database.")
sys.exit(1)
EOF
fi

# Apply migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

exec "$@"
