"""
Alembic‑Konfigurationsskript für das FaSiKo‑Backend.

Dieses Skript lädt die SQLAlchemy‑Metadaten aus dem Projekt, setzt die
Datenbank‑URL dynamisch anhand der Umgebungsvariable ``DATABASE_URL`` und
führt die Migrationen wahlweise offline (SQL‑Skripte) oder online (direkt
gegen die Datenbank) aus. Durch das Hinzufügen des Projekt‑Roots zum
``sys.path`` können Module wie ``app.db`` und ``app.models`` importiert
werden.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Dieses Modul wird innerhalb des Paketverzeichnisses ``backend`` ausgeführt.
# Füge das übergeordnete Verzeichnis von ``alembic/env.py`` zum ``sys.path``
# hinzu, damit ``app.db`` importiert werden kann.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Importiere die Basisklasse und die Modelle, sodass Alembic deren
# Metadaten kennt. Der Import von ``models`` ist notwendig, damit die
# Tabellen beim ``autogenerate`` erkannt werden. Wird explizit ignoriert.
from app.db import Base  # type: ignore  # noqa: E402
from app import models  # noqa: F401,E402

# Diese Konfigurationsdatei wird von Alembic verwendet; sie kann
# Programmeinträge verwenden. Wir verwenden sie zum Laden der
# Datenbank‑URL, die dynamisch über ``DATABASE_URL`` gesetzt wird.
config = context.config

# Lese die Datenbank‑URL aus der Umgebung und setze sie zur Laufzeit.
database_url = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
config.set_main_option("sqlalchemy.url", database_url)

# Wenn ``config.fileConfig`` definiert ist, dann wird das Logging anhand
# der Konfigurationsdatei (alembic.ini) eingerichtet.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Ziel‑Metadaten für automatische Migrationen.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Führt Migrationen im 'offline'-Modus aus.

    Bei Offline‑Migrationen wird die Ziel‑Datenbank nicht direkt
    verbunden. Stattdessen erzeugt Alembic reine SQL‑Skripte mit den
    erforderlichen Befehlen. Dies ist nützlich, wenn man Migrationen
    kontrolliert ausführen oder zur späteren Ausführung speichern möchte.
    """

    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Führt Migrationen im 'online'-Modus aus.

    Im Online‑Modus wird eine echte Verbindung zur Datenbank hergestellt
    und die Migrationen werden direkt ausgeführt. Dies ist der normale
    Modus beim Starten des Containers oder beim Testen.
    """

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()