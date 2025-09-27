"""
Admin funds tables and asset creator

Revision ID: 0004_admin_funds
Revises: 0003_amm_schema
Create Date: 2025-09-27 15:36:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004_admin_funds'
down_revision = '0003_amm_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add created_by_user_id to assets with FK (use batch for SQLite compatibility)
    with op.batch_alter_table('assets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_by_user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_assets_created_by_user', 'users', ['created_by_user_id'], ['id'])

    # deposits
    op.create_table(
        'deposits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('amount', sa.Numeric(36, 18), nullable=False),
        sa.Column('external_ref', sa.String(length=256), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('settled_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_deposits_user_id', 'deposits', ['user_id'])
    op.create_index('ix_deposits_asset_id', 'deposits', ['asset_id'])

    # withdrawals
    op.create_table(
        'withdrawals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('amount', sa.Numeric(36, 18), nullable=False),
        sa.Column('external_ref', sa.String(length=256), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('settled_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_withdrawals_user_id', 'withdrawals', ['user_id'])
    op.create_index('ix_withdrawals_asset_id', 'withdrawals', ['asset_id'])


def downgrade() -> None:
    op.drop_index('ix_withdrawals_asset_id', table_name='withdrawals')
    op.drop_index('ix_withdrawals_user_id', table_name='withdrawals')
    op.drop_table('withdrawals')

    op.drop_index('ix_deposits_asset_id', table_name='deposits')
    op.drop_index('ix_deposits_user_id', table_name='deposits')
    op.drop_table('deposits')

    # Drop FK and column using batch mode for SQLite compatibility
    with op.batch_alter_table('assets', schema=None) as batch_op:
        batch_op.drop_constraint('fk_assets_created_by_user', type_='foreignkey')
        batch_op.drop_column('created_by_user_id')
