"""
Fügt zusätzliche Felder zur Tabelle ``bsi_requirements`` hinzu:

* ``title`` – der reine Titel der Anforderung (ohne Klassifizierung)
* ``classification`` – Kennzeichnung der Klassifizierung (B, S, H)
* ``is_obsolete`` – Flag für entfallene Anforderungen

Revision ID: 0007_add_req_extras
Revises: 0006_change_req_id_to_text
Create Date: 2026-01-17 14:00:00.000000

Diese Migration ergänzt die Tabelle ``bsi_requirements`` um zusätzliche Spalten
zur feingranularen Darstellung der Anforderung. Die Spalte ``req_id``
bleibt erhalten und enthält weiterhin den vollständigen BSI‑Code mit Titel und
Klassifizierung. ``title`` enthält den Titel ohne Code und ohne
Klassifizierung, ``classification`` speichert die Klassifizierung (B|S|H),
und ``is_obsolete`` ist ein Integer‑Flag (0/1) für entfallene Anforderungen.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
# Revision identifiers are limited to 32 characters because the
# ``version_num`` column in the ``alembic_version`` table ist
# ``VARCHAR(32)``. Verwende daher einen kurzen Namen.
revision = '0007_add_req_extras'
down_revision = '0006_change_req_id_to_text'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Neue Spalten hinzufügen
    op.add_column('bsi_requirements', sa.Column('title', sa.String(length=1000), nullable=False, server_default=''))
    op.add_column('bsi_requirements', sa.Column('classification', sa.String(length=1), nullable=True))
    op.add_column('bsi_requirements', sa.Column('is_obsolete', sa.Integer(), nullable=False, server_default='0'))

    # Entferne die server_defaults nach dem Anlegen, um zukünftige Datensätze korrekt zu speichern
    with op.batch_alter_table('bsi_requirements') as batch_op:
        batch_op.alter_column('title', server_default=None)
        batch_op.alter_column('is_obsolete', server_default=None)


def downgrade() -> None:
    # Spalten wieder entfernen
    op.drop_column('bsi_requirements', 'is_obsolete')
    op.drop_column('bsi_requirements', 'classification')
    op.drop_column('bsi_requirements', 'title')