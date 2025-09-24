"""
Initial database schema

Revision ID: 0001_initial
Revises: 
Create Date: 2025-09-24 14:50:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tokens
    op.create_table(
        'tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('price_usd', sa.Numeric(18, 8), nullable=True, server_default='0'),
        sa.Column('market_cap_usd', sa.Numeric(20, 2), nullable=True, server_default='0'),
        sa.Column('holders_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('change_24h', sa.Float(), nullable=True, server_default='0'),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('symbol', name='uq_tokens_symbol'),
    )
    op.create_index('ix_tokens_symbol', 'tokens', ['symbol'])

    # token_snapshots
    op.create_table(
        'token_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('token_id', sa.Integer(), sa.ForeignKey('tokens.id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('price_usd', sa.Numeric(18, 8), nullable=True, server_default='0'),
        sa.Column('market_cap_usd', sa.Numeric(20, 2), nullable=True, server_default='0'),
        sa.Column('holders_count', sa.Integer(), nullable=True, server_default='0'),
    )
    op.create_index('ix_token_snapshots_token_id', 'token_snapshots', ['token_id'])
    op.create_index('ix_token_snapshots_timestamp', 'token_snapshots', ['timestamp'])

    # global_metrics
    op.create_table(
        'global_metrics',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('total_holders', sa.BigInteger(), nullable=True, server_default='0'),
        sa.Column('total_market_cap_usd', sa.Numeric(20, 2), nullable=True, server_default='0'),
        sa.Column('total_volume_24h_usd', sa.Numeric(20, 2), nullable=True, server_default='0'),
    )
    op.create_index('ix_global_metrics_timestamp', 'global_metrics', ['timestamp'])

    # users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('npub', sa.String(length=64), nullable=False),
        sa.Column('display_name', sa.String(length=128), nullable=True),
        sa.Column('avatar_url', sa.String(length=512), nullable=True),
        sa.Column('bio', sa.String(length=512), nullable=True),
        sa.Column('joined_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('npub', name='uq_users_npub'),
    )
    op.create_index('ix_users_npub', 'users', ['npub'])

    # user_holdings
    op.create_table(
        'user_holdings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('token_id', sa.Integer(), sa.ForeignKey('tokens.id'), nullable=False),
        sa.Column('quantity', sa.Numeric(36, 18), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_user_holdings_user_id', 'user_holdings', ['user_id'])
    op.create_index('ix_user_holdings_token_id', 'user_holdings', ['token_id'])

    # competitions
    op.create_table(
        'competitions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('slug', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('description', sa.String(length=1024), nullable=True),
        sa.Column('start_at', sa.DateTime(), nullable=False),
        sa.Column('end_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('slug', name='uq_competitions_slug'),
    )
    op.create_index('ix_competitions_slug', 'competitions', ['slug'])

    # competition_entries
    op.create_table(
        'competition_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('competition_id', sa.Integer(), sa.ForeignKey('competitions.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('score', sa.Numeric(20, 8), nullable=True, server_default='0'),
        sa.Column('rank', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_competition_entries_competition_id', 'competition_entries', ['competition_id'])
    op.create_index('ix_competition_entries_user_id', 'competition_entries', ['user_id'])

    # auth_challenges
    op.create_table(
        'auth_challenges',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pubkey', sa.String(length=64), nullable=False),
        sa.Column('nonce', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.UniqueConstraint('nonce', name='uq_auth_challenges_nonce'),
    )
    op.create_index('ix_auth_challenges_pubkey', 'auth_challenges', ['pubkey'])
    op.create_index('ix_auth_challenges_nonce', 'auth_challenges', ['nonce'])


def downgrade() -> None:
    op.drop_index('ix_auth_challenges_nonce', table_name='auth_challenges')
    op.drop_index('ix_auth_challenges_pubkey', table_name='auth_challenges')
    op.drop_table('auth_challenges')

    op.drop_index('ix_competition_entries_user_id', table_name='competition_entries')
    op.drop_index('ix_competition_entries_competition_id', table_name='competition_entries')
    op.drop_table('competition_entries')

    op.drop_index('ix_competitions_slug', table_name='competitions')
    op.drop_table('competitions')

    op.drop_index('ix_user_holdings_token_id', table_name='user_holdings')
    op.drop_index('ix_user_holdings_user_id', table_name='user_holdings')
    op.drop_table('user_holdings')

    op.drop_index('ix_users_npub', table_name='users')
    op.drop_table('users')

    op.drop_index('ix_global_metrics_timestamp', table_name='global_metrics')
    op.drop_table('global_metrics')

    op.drop_index('ix_token_snapshots_timestamp', table_name='token_snapshots')
    op.drop_index('ix_token_snapshots_token_id', table_name='token_snapshots')
    op.drop_table('token_snapshots')

    op.drop_index('ix_tokens_symbol', table_name='tokens')
    op.drop_table('tokens')
