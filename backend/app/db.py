"""
Datenbank-Initialisierung (PostgreSQL) für das FaSiKo-Backend.

WICHTIG:
- Alembic ist die einzige Quelle für Schema-Änderungen.
- Daher darf hier KEIN Base.metadata.create_all() automatisch ausgeführt werden.

ABER:
- Das SQLAlchemy "Base" Objekt muss vorhanden sein (models importiert Base).
- Einige Teile der App erwarten init_db() (z.B. app/main.py).
"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from .settings import DATABASE_URL

# SQLAlchemy Base (wird in app/models.py importiert)
Base = declarative_base()

# Engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# Session Factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """
    Initialisiert die DB-Verbindung.

    Absichtlich KEIN create_all().
    Schema wird ausschließlich über Alembic-Migrationen verwaltet.
    Diese Funktion prüft nur, ob die DB erreichbar ist.
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def get_db():
    """FastAPI Dependency: liefert DB Session und schließt sauber."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
