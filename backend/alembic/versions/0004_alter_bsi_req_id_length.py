"""Alter req_id length on bsi_requirements to 256 characters.

Revision ID: 0004_alter_req_id_length
Revises: 0003_bsi_catalog_tables
Create Date: 2026-01-17 00:00:00.000000

Diese Migration erhöht die Länge der Spalte ``req_id`` in der Tabelle
``bsi_requirements`` von 50 auf 256 Zeichen. Dadurch können vollständige
BSI‑Codes inklusive Titel und Klassifizierung gespeichert werden.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004_alter_req_id_length'
down_revision = '0003_bsi_catalog_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alteriere die Länge der Spalte req_id. existing_type gibt den alten
    # Datentyp an, damit Alembic den richtigen Cast wählen kann.
    op.alter_column(
        'bsi_requirements',
        'req_id',
        type_=sa.String(length=256),
        existing_type=sa.String(length=50),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Setze die Länge wieder zurück auf 50 Zeichen. Dabei kann es zu
    # abgeschnittenen Daten kommen, wenn längere Bezeichner gespeichert sind.
    op.alter_column(
        'bsi_requirements',
        'req_id',
        type_=sa.String(length=50),
        existing_type=sa.String(length=256),
        existing_nullable=False,
    )