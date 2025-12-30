"""
Datenbankanbindung und Sessionverwaltung für das FaSiKo‑Backend.

Dieses Modul stellt die zentrale SQLAlchemy‑Engine, eine
Session‑Factory und die Basisklasse für alle ORM‑Modelle bereit.

Die Konfiguration der Datenbank erfolgt über die Umgebungsvariable
``DATABASE_URL``. Beim Einsatz von SQLite muss ``check_same_thread``
gesetzt werden, damit FastAPI mit dem asynchronen Thread‑Pool
zusammenarbeitet. Für PostgreSQL sind keine besonderen
``connect_args`` erforderlich.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .settings import DATABASE_URL

# Für SQLite muss ``check_same_thread`` deaktiviert werden.
connect_args: dict[str, object] = {}
if DATABASE_URL.startswith("sqlite:"):
    connect_args = {"check_same_thread": False}

# Engine erstellen. ``future=True`` aktiviert das neue SQLAlchemy 2.x API.
engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
)

# Session‑Factory. ``autoflush=False`` vermeidet unnötige Flushes,
# ``autocommit=False`` erzwingt explizite Commits.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):  # type: ignore[call-arg]
    """Gemeinsame Basisklasse für alle ORM‑Modelle."""

    pass


def get_db():
    """Abhängigkeit für FastAPI‑Endpoints.

    Erstellt eine neue Datenbank‑Session und gibt sie zur Nutzung frei.
    Nach der Nutzung wird die Session sauber geschlossen.
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialisiert die Datenbanktabellen.

    Diese Funktion importiert alle Modelle, damit SQLAlchemy die
    Tabellendefinitionen kennt, und ruft anschließend ``create_all``
    auf der ``Base.metadata`` auf. Beim Einsatz von Alembic wird diese
    Funktion nur in Entwicklungsumgebungen genutzt, um ein frisches
    SQLite‑Schema anzulegen. In Produktionsumgebungen sollte die
    Schemaerstellung ausschließlich über Migrationen erfolgen.
    """

    # Importiere Modelle, damit SQLAlchemy die Tabellen kennt.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)