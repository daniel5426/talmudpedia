"""publish/runtime public id hard cut

Revision ID: 1a2b3c4d5e6f
Revises: f0e1d2c3b4a5
Create Date: 2026-04-20 00:00:00.000000
"""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa

revision = '1a2b3c4d5e6f'
down_revision = 'f0e1d2c3b4a5'
branch_labels = None
depends_on = None


def _build_public_id() -> str:
    return f"app_{uuid.uuid4().hex[:24]}"


def upgrade() -> None:
    op.add_column('published_apps', sa.Column('public_id', sa.String(), nullable=True))
    bind = op.get_bind()
    rows = list(bind.execute(sa.text('SELECT id FROM published_apps')).fetchall())
    for (app_id,) in rows:
        bind.execute(
            sa.text('UPDATE published_apps SET public_id = :public_id WHERE id = :id'),
            {'public_id': _build_public_id(), 'id': app_id},
        )
    op.alter_column('published_apps', 'public_id', nullable=False)
    op.create_unique_constraint('uq_published_apps_public_id', 'published_apps', ['public_id'])
    op.execute(sa.text('DROP INDEX IF EXISTS ix_published_apps_slug'))
    op.execute(sa.text('ALTER TABLE published_apps DROP CONSTRAINT IF EXISTS published_apps_slug_key'))
    op.drop_column('published_apps', 'slug')


def downgrade() -> None:
    op.add_column('published_apps', sa.Column('slug', sa.String(), nullable=True))
    bind = op.get_bind()
    rows = list(bind.execute(sa.text('SELECT id, public_id FROM published_apps')).fetchall())
    for app_id, public_id in rows:
        bind.execute(sa.text('UPDATE published_apps SET slug = :slug WHERE id = :id'), {'slug': public_id, 'id': app_id})
    op.alter_column('published_apps', 'slug', nullable=False)
    op.create_unique_constraint('published_apps_slug_key', 'published_apps', ['slug'])
    op.create_index(op.f('ix_published_apps_slug'), 'published_apps', ['slug'], unique=False)
    op.drop_constraint('uq_published_apps_public_id', 'published_apps', type_='unique')
    op.drop_column('published_apps', 'public_id')
