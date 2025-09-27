"""
AMM and Balances schema

Revision ID: 0003_amm_schema
Revises: 0002_add_volume_fields
Create Date: 2025-09-27 15:28:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_amm_schema'
down_revision = '0002_add_volume_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # assets
    op.create_table(
        'assets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('precision', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('rln_asset_id', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('symbol', name='uq_assets_symbol'),
    )
    op.create_index('ix_assets_symbol', 'assets', ['symbol'])

    # user_balances
    op.create_table(
        'user_balances',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('balance', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('available', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_user_balances_user_id', 'user_balances', ['user_id'])
    op.create_index('ix_user_balances_asset_id', 'user_balances', ['asset_id'])

    # pools
    op.create_table(
        'pools',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('asset_rgb_id', sa.Integer(), sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('asset_btc_id', sa.Integer(), sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('fee_bps', sa.Integer(), nullable=True, server_default='100'),
        sa.Column('lp_fee_bps', sa.Integer(), nullable=True, server_default='50'),
        sa.Column('platform_fee_bps', sa.Integer(), nullable=True, server_default='50'),
        sa.Column('is_vamm', sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_pools_asset_rgb_id', 'pools', ['asset_rgb_id'])
    op.create_index('ix_pools_asset_btc_id', 'pools', ['asset_btc_id'])

    # pool_liquidity
    op.create_table(
        'pool_liquidity',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pool_id', sa.Integer(), sa.ForeignKey('pools.id'), nullable=False),
        sa.Column('reserve_rgb', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('reserve_btc', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('reserve_rgb_virtual', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('reserve_btc_virtual', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_pool_liquidity_pool_id', 'pool_liquidity', ['pool_id'])

    # swaps
    op.create_table(
        'swaps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pool_id', sa.Integer(), sa.ForeignKey('pools.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('asset_in_id', sa.Integer(), sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('asset_out_id', sa.Integer(), sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('amount_in', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('min_out', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('amount_out', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('fee_total_bps', sa.Integer(), nullable=True, server_default='100'),
        sa.Column('fee_lp_bps', sa.Integer(), nullable=True, server_default='50'),
        sa.Column('fee_platform_bps', sa.Integer(), nullable=True, server_default='50'),
        sa.Column('fee_amount_total', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('fee_amount_lp', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('fee_amount_platform', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('status', sa.String(length=32), nullable=True, server_default='pending_approval'),
        sa.Column('nonce', sa.String(length=64), nullable=True),
        sa.Column('deadline_ts', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('executed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_swaps_pool_id', 'swaps', ['pool_id'])
    op.create_index('ix_swaps_user_id', 'swaps', ['user_id'])

    # approvals
    op.create_table(
        'approvals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('swap_id', sa.Integer(), sa.ForeignKey('swaps.id'), nullable=False),
        sa.Column('nostr_pubkey', sa.String(length=64), nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('sig', sa.String(length=128), nullable=False),
        sa.Column('approved', sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_approvals_swap_id', 'approvals', ['swap_id'])

    # ledger_entries
    op.create_table(
        'ledger_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('delta', sa.Numeric(36, 18), nullable=False),
        sa.Column('ref_type', sa.String(length=32), nullable=False),
        sa.Column('ref_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_ledger_entries_user_id', 'ledger_entries', ['user_id'])
    op.create_index('ix_ledger_entries_asset_id', 'ledger_entries', ['asset_id'])


def downgrade() -> None:
    op.drop_index('ix_ledger_entries_asset_id', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_user_id', table_name='ledger_entries')
    op.drop_table('ledger_entries')

    op.drop_index('ix_approvals_swap_id', table_name='approvals')
    op.drop_table('approvals')

    op.drop_index('ix_swaps_user_id', table_name='swaps')
    op.drop_index('ix_swaps_pool_id', table_name='swaps')
    op.drop_table('swaps')

    op.drop_index('ix_pool_liquidity_pool_id', table_name='pool_liquidity')
    op.drop_table('pool_liquidity')

    op.drop_index('ix_pools_asset_btc_id', table_name='pools')
    op.drop_index('ix_pools_asset_rgb_id', table_name='pools')
    op.drop_table('pools')

    op.drop_index('ix_user_balances_asset_id', table_name='user_balances')
    op.drop_index('ix_user_balances_user_id', table_name='user_balances')
    op.drop_table('user_balances')

    op.drop_index('ix_assets_symbol', table_name='assets')
    op.drop_table('assets')
