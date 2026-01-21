FROM python:3.11-slim

WORKDIR /app

# Vermeide das Erzeugen von .pyc Dateien und deaktiviere stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Damit ``from app.main import app`` funktioniert
ENV PYTHONPATH=/app

# Installiere Python‑Abhängigkeiten
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Kopiere den Anwendungscode und die Migrationen
COPY app /app/app
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic

# Kopiere das Startskript und mache es ausführbar
COPY entrypoint.sh /app/entrypoint.sh
# CRLF -> LF + ausführbar
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8000

# Standardbefehl: führe Migrationen aus und starte den Server
CMD ["/app/entrypoint.sh"]