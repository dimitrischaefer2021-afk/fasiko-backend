"""
Fügt Rohdatenfelder zur Tabelle ``bsi_requirements`` hinzu.

Diese Migration ergänzt die BSI‑Anforderungen um zwei zusätzliche Spalten:

* ``raw_title`` – Speichert den unveränderten Titel aus der PDF‑Extraktion.
  Diese Spalte ist optional (nullable), da bestehende Datensätze vor der
  Einführung des Normalizers noch keine Rohdaten besitzen.
* ``raw_description`` – Speichert die ursprüngliche, nicht normalisierte
  Beschreibung der Maßnahme. Auch diese Spalte ist optional.

Bei der Ausführung der Migration werden die neuen Spalten angelegt und
anschließend für alle bestehenden Anforderungen mit den aktuellen Werten
von ``title`` und ``description`` gefüllt. So bleiben die Rohdaten
erhalten, wenn später eine Normalisierung durchgeführt wird.

Revision ID: 0008_add_raw_fields
Revises: 0007_add_req_extras
Create Date: 2026-01-19 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers, used by Alembic.
revision = '0008_add_raw_fields'
down_revision = '0007_add_req_extras'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Migration nach oben (Upgrade).

    Fügt die Spalten ``raw_title`` und ``raw_description`` zur Tabelle
    ``bsi_requirements`` hinzu und befüllt sie mit den aktuellen
    Normalisierungswerten.
    """
    # Neue Spalten hinzufügen. Nullable=True erlaubt es, dass bestehende
    # Datensätze ohne Rohdaten bleiben, bis eine Normalisierung erfolgt.
    op.add_column('bsi_requirements', sa.Column('raw_title', sa.String(length=1000), nullable=True))
    op.add_column('bsi_requirements', sa.Column('raw_description', sa.Text(), nullable=True))
    # Kopiere vorhandene Daten in die neuen Spalten, damit Rohdaten
    # vor der ersten Normalisierung identisch mit den aktuellen Werten sind.
    op.execute(
        "UPDATE bsi_requirements SET raw_title = title, raw_description = description"
    )


def downgrade() -> None:
    """Migration zurück (Downgrade).

    Entfernt die Spalten ``raw_title`` und ``raw_description`` aus
    ``bsi_requirements``. Alle darin enthaltenen Daten gehen verloren.
    """
    op.drop_column('bsi_requirements', 'raw_description')
    op.drop_column('bsi_requirements', 'raw_title')