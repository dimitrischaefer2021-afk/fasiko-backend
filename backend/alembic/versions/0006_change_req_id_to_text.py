"""
Ändert die Spalte ``req_id`` der Tabelle ``bsi_requirements`` in den Datentyp ``TEXT``.

Revision ID: 0006_change_req_id_to_text
Revises: 0005_expand_bsi_req_id_length
Create Date: 2026-01-17 13:55:00.000000

Begründung:
Die Kennung einer Anforderung (`req_id`) enthält den vollständigen
BSI‑Code sowie den Titel inkl. Klassifizierung. Einige BSI‑Dokumente
enthalten Anforderungen ohne explizite Klassifizierung oder mit sehr
langen Titeln. Dadurch kann die Kennung länger als 512 Zeichen
werden. Der Datentyp ``VARCHAR(512)`` reicht dann nicht aus und führt
zu einem ``StringDataRightTruncation``‑Fehler beim Einfügen. Durch
Umwandlung zu ``TEXT`` wird die Länge nicht mehr begrenzt.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0006_change_req_id_to_text'
down_revision = '0005_expand_bsi_req_id_length'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Ändert den Datentyp der Spalte ``req_id`` auf ``TEXT``."""
    op.alter_column(
        'bsi_requirements',
        'req_id',
        type_=sa.Text(),
        existing_type=sa.String(length=512),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Stellt den vorherigen Datentyp (VARCHAR(512)) wieder her."""
    op.alter_column(
        'bsi_requirements',
        'req_id',
        type_=sa.String(length=512),
        existing_type=sa.Text(),
        existing_nullable=False,
    )