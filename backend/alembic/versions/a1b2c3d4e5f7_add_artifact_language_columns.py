"""add artifact language columns

Revision ID: a1b2c3d4e5f7
Revises: f0e1d2c3b4a5
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f7"
down_revision = "f0e1d2c3b4a5"
branch_labels = None
depends_on = None


artifact_language_enum = sa.Enum("python", "javascript", name="artifactlanguage")


def upgrade() -> None:
    artifact_language_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "artifacts",
        sa.Column("language", artifact_language_enum, nullable=False, server_default="python"),
    )
    op.add_column(
        "artifact_revisions",
        sa.Column("language", artifact_language_enum, nullable=False, server_default="python"),
    )
    op.alter_column("artifacts", "language", server_default=None)
    op.alter_column("artifact_revisions", "language", server_default=None)


def downgrade() -> None:
    op.drop_column("artifact_revisions", "language")
    op.drop_column("artifacts", "language")
    artifact_language_enum.drop(op.get_bind(), checkfirst=True)
