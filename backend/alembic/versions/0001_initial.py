"""
Initiale Datenbankschemamigration für das FaSiKo‑Backend.

Diese Migration erzeugt alle Tabellen, die in ``app.models`` definiert
sind, indem sie die SQLAlchemy‑Metadaten nutzt. Bei einem Downgrade
werden sämtliche Tabellen wieder entfernt. Die IDs werden als Strings
(UUIDs) gespeichert, Zeitstempel sind timezone‑aware ``datetime``
Felder.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# Revisionskennung und Abhängigkeiten
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Erzeuge alle Tabellen entsprechend der SQLAlchemy‑Metadaten."""
    # Importiere Base aus app.db. Der Import findet zur Laufzeit statt,
    # damit Alembic nicht bereits während der Modulinitialisierung versucht,
    # ``app.db`` zu laden.
    from app.db import Base  # type: ignore
    from app import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Entferne alle Tabellen dieses Backends.

    Achtung: Beim Downgrade werden sämtliche Tabellen und damit alle
    Daten gelöscht. In produktiven Umgebungen sollte ein Downgrade
    sorgfältig geplant werden.
    """

    from app.db import Base  # type: ignore
    from app import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)