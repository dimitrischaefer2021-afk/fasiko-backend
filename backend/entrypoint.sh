#!/bin/sh
set -eu

echo "[entrypoint] FÃ¼hre Alembic-Migrationen ausâ€¦"
alembic upgrade head

echo "[entrypoint] Starte Uvicornâ€¦"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
