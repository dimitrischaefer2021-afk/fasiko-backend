"""
Add extraction fields to sources

Revision ID: 0002_add_extraction_fields_to_sources
Revises: 0001_initial
Create Date: 2026-01-15

Diese Migration ergänzt die Tabelle ``sources`` um drei neue Spalten zur
Speicherung der Ergebnisse der Textextraktion. Sie werden im Rahmen
von Block 17 benötigt.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
# Hinweis: Die Spalten fügen wir in Block 17 hinzu. Der
# Revisionsname darf maximal 32 Zeichen lang sein, damit er in die
# alembic_version‑Tabelle (VARCHAR(32)) passt. Wähle daher eine
# kürzere ID als der Dateiname.
revision: str = "0002_extraction_fields"
down_revision: str = "0001_initial"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Fügt neue Spalten extraction_status, extraction_reason und extracted_text_len hinzu.

    Die Spalten werden nur angelegt, wenn sie noch nicht existieren. Dadurch ist die
    Migration idempotent und verursacht bei erneuter Ausführung keine
    DuplicateColumn‑Fehler. Wir verwenden ALTER TABLE ... ADD COLUMN IF NOT EXISTS
    und setzen Default‑Werte für bestehende Datensätze.
    """
    # Direktes Ausführen von SQL mit IF NOT EXISTS, um DuplicateColumn‑Fehler zu vermeiden
    op.execute(
        "ALTER TABLE sources ADD COLUMN IF NOT EXISTS extraction_status VARCHAR(50) NOT NULL DEFAULT 'unknown'"
    )
    op.execute(
        "ALTER TABLE sources ADD COLUMN IF NOT EXISTS extraction_reason VARCHAR(500)"
    )
    op.execute(
        "ALTER TABLE sources ADD COLUMN IF NOT EXISTS extracted_text_len INTEGER NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    """Entfernt die in upgrade hinzugefügten Spalten wieder."""
    op.drop_column("sources", "extraction_status")
    op.drop_column("sources", "extraction_reason")
    op.drop_column("sources", "extracted_text_len")