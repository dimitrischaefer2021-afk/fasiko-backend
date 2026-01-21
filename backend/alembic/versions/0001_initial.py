"""
Initiale Datenbankschemamigration für das FaSiKo-Backend.

WICHTIG:
Diese Migration darf NICHT Base.metadata.create_all() nutzen.

Warum?
- create_all()/drop_all() erstellt/entfernt Tabellen abhängig davon, welche
  Models importiert sind. Das kollidiert mit späteren Alembic-Migrationen
  (z. B. BSI-Katalogtabellen in 0003) und führt zu DuplicateTable.

Diese Migration erzeugt daher nur die initialen Tabellen, die für die
frühen Blöcke (Projects, Sources, Jobs) benötigt werden. Weitere Tabellen
werden in späteren Migrationen ergänzt.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- sources (Uploads) ---
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sources_project_id", "sources", ["project_id"])

    # --- jobs (Async) ---
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("result_file", sa.String(length=1024), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Reihenfolge wegen Foreign Keys
    op.drop_table("jobs")
    op.drop_index("ix_sources_project_id", table_name="sources")
    op.drop_table("sources")
    op.drop_table("projects")
