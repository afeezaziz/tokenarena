"""
Add volume_24h_usd to tokens and token_snapshots

Revision ID: 0002_add_volume_fields
Revises: 0001_initial
Create Date: 2025-09-25 00:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_volume_fields'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tokens', sa.Column('volume_24h_usd', sa.Numeric(20, 2), nullable=True, server_default='0'))
    op.add_column('token_snapshots', sa.Column('volume_24h_usd', sa.Numeric(20, 2), nullable=True, server_default='0'))


def downgrade() -> None:
    op.drop_column('token_snapshots', 'volume_24h_usd')
    op.drop_column('tokens', 'volume_24h_usd')
