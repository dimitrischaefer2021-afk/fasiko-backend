"""
Erweitert die Länge der Spalte ``req_id`` in der Tabelle ``bsi_requirements``.

Revision ID: 0005_expand_bsi_req_id_length
Revises: 0004_alter_req_id_length
Create Date: 2026-01-17 01:55:00.000000

Diese Migration erhöht die maximale Länge der Spalte ``req_id`` weiter von
256 auf 512 Zeichen. Grund: Bei manchen BSI‑Dokumenten enthält die
Anforderungskennung den vollständigen Modulcode inkl. Titel sowie
Klassifizierung (B, S, H), was in seltenen Fällen mehr als 256 Zeichen
erreichen kann. Durch diese Anpassung werden zukünftige Uploads nicht
mehr aufgrund überschrittener Spaltenlängen fehlschlagen.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0005_expand_bsi_req_id_length'
down_revision = '0004_alter_req_id_length'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Erweitert die Länge der Spalte ``req_id`` auf 512 Zeichen."""
    op.alter_column(
        'bsi_requirements',
        'req_id',
        type_=sa.String(length=512),
        existing_type=sa.String(length=256),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Setzt die Länge der Spalte ``req_id`` wieder auf 256 Zeichen zurück."""
    op.alter_column(
        'bsi_requirements',
        'req_id',
        type_=sa.String(length=256),
        existing_type=sa.String(length=512),
        existing_nullable=False,
    )