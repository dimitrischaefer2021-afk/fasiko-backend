#!/bin/sh
# Startskript für den Fasiko‑Backend‑Container.
#
# Es führt zunächst die Datenbankmigrationen mittels Alembic aus
# (Upgrade auf die neueste Version) und startet anschließend den
# FastAPI‑Server via Uvicorn. Fehlermeldungen während der Migration
# führen zum Abbruch.

set -e

echo "[entrypoint] Führe Alembic‑Migrationen aus…"
alembic upgrade head

echo "[entrypoint] Starte Uvicorn…"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000