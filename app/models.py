from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, scoped_session, sessionmaker

Base = declarative_base()

# Engine/Session globals initialized by init_engine
_engine = None
_SessionLocal = None


def init_engine(db_url: str) -> None:
    """Initialize the SQLAlchemy engine and session factory."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(db_url, future=True)
        _SessionLocal = scoped_session(sessionmaker(bind=_engine, autoflush=False, autocommit=False))


def init_db() -> None:
    if _engine is None:
        raise RuntimeError("Engine not initialized. Call init_engine() first.")
    Base.metadata.create_all(_engine)


def get_session():
    if _SessionLocal is None:
        raise RuntimeError("Session factory not initialized. Call init_engine() first.")
    return _SessionLocal()

def remove_session() -> None:
    if _SessionLocal is not None:
        _SessionLocal.remove()

class Token(Base):
    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)

    price_usd = Column(Numeric(18, 8), default=Decimal("0"))
    market_cap_usd = Column(Numeric(20, 2), default=Decimal("0"))
    volume_24h_usd = Column(Numeric(20, 2), default=Decimal("0"))
    holders_count = Column(Integer, default=0)
    change_24h = Column(Float, default=0.0)  # percent change

    last_updated = Column(DateTime, default=datetime.utcnow)

    snapshots = relationship("TokenSnapshot", back_populates="token", cascade="all, delete-orphan")
    holdings = relationship("UserHolding", back_populates="token", cascade="all, delete-orphan")


class TokenSnapshot(Base):
    __tablename__ = "token_snapshots"

    id = Column(Integer, primary_key=True)
    token_id = Column(Integer, ForeignKey("tokens.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    price_usd = Column(Numeric(18, 8), default=Decimal("0"))
    market_cap_usd = Column(Numeric(20, 2), default=Decimal("0"))
    volume_24h_usd = Column(Numeric(20, 2), default=Decimal("0"))
    holders_count = Column(Integer, default=0)

    token = relationship("Token", back_populates="snapshots")


class GlobalMetrics(Base):
    __tablename__ = "global_metrics"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    total_tokens = Column(Integer, default=0)
    total_holders = Column(BigInteger, default=0)
    total_market_cap_usd = Column(Numeric(20, 2), default=Decimal("0"))
    total_volume_24h_usd = Column(Numeric(20, 2), default=Decimal("0"))


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    npub = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(128))
    avatar_url = Column(String(512))
    bio = Column(String(512))
    joined_at = Column(DateTime, default=datetime.utcnow)

    holdings = relationship("UserHolding", back_populates="user", cascade="all, delete-orphan")
    entries = relationship("CompetitionEntry", back_populates="user", cascade="all, delete-orphan")


class UserHolding(Base):
    __tablename__ = "user_holdings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_id = Column(Integer, ForeignKey("tokens.id"), nullable=False, index=True)
    quantity = Column(Numeric(36, 18), default=Decimal("0"))
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="holdings")
    token = relationship("Token", back_populates="holdings")


class Competition(Base):
    __tablename__ = "competitions"

    id = Column(Integer, primary_key=True)
    slug = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(256), nullable=False)
    description = Column(String(1024))
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    entries = relationship("CompetitionEntry", back_populates="competition", cascade="all, delete-orphan")


class CompetitionEntry(Base):
    __tablename__ = "competition_entries"

    id = Column(Integer, primary_key=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    score = Column(Numeric(20, 8), default=Decimal("0"))
    rank = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    competition = relationship("Competition", back_populates="entries")
    user = relationship("User", back_populates="entries")


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"

    id = Column(Integer, primary_key=True)
    pubkey = Column(String(64), index=True, nullable=False)
    nonce = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)


# ---------------------- AMM / Balances ----------------------
class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    precision = Column(Integer, default=0)
    rln_asset_id = Column(String(128))  # RGB asset identifier; null/empty for BTC
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by_user_id = Column(Integer, ForeignKey("users.id"))


class UserBalance(Base):
    __tablename__ = "user_balances"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    balance = Column(Numeric(36, 18), default=Decimal("0"))
    available = Column(Numeric(36, 18), default=Decimal("0"))
    updated_at = Column(DateTime, default=datetime.utcnow)


class Pool(Base):
    __tablename__ = "pools"

    id = Column(Integer, primary_key=True)
    asset_rgb_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    asset_btc_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    fee_bps = Column(Integer, default=100)           # 1.00% total
    lp_fee_bps = Column(Integer, default=50)         # 0.50% LP
    platform_fee_bps = Column(Integer, default=50)   # 0.50% platform
    is_vamm = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PoolLiquidity(Base):
    __tablename__ = "pool_liquidity"

    id = Column(Integer, primary_key=True)
    pool_id = Column(Integer, ForeignKey("pools.id"), nullable=False, index=True)
    reserve_rgb = Column(Numeric(36, 18), default=Decimal("0"))
    reserve_btc = Column(Numeric(36, 18), default=Decimal("0"))
    reserve_rgb_virtual = Column(Numeric(36, 18), default=Decimal("0"))
    reserve_btc_virtual = Column(Numeric(36, 18), default=Decimal("0"))
    updated_at = Column(DateTime, default=datetime.utcnow)


class Swap(Base):
    __tablename__ = "swaps"

    id = Column(Integer, primary_key=True)
    pool_id = Column(Integer, ForeignKey("pools.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    asset_in_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    asset_out_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    amount_in = Column(Numeric(36, 18), default=Decimal("0"))
    min_out = Column(Numeric(36, 18), default=Decimal("0"))
    amount_out = Column(Numeric(36, 18), default=Decimal("0"))
    fee_total_bps = Column(Integer, default=100)
    fee_lp_bps = Column(Integer, default=50)
    fee_platform_bps = Column(Integer, default=50)
    fee_amount_total = Column(Numeric(36, 18), default=Decimal("0"))
    fee_amount_lp = Column(Numeric(36, 18), default=Decimal("0"))
    fee_amount_platform = Column(Numeric(36, 18), default=Decimal("0"))
    status = Column(String(32), default="pending_approval")
    nonce = Column(String(64))
    deadline_ts = Column(BigInteger)
    created_at = Column(DateTime, default=datetime.utcnow)
    executed_at = Column(DateTime)


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True)
    swap_id = Column(Integer, ForeignKey("swaps.id"), nullable=False, index=True)
    nostr_pubkey = Column(String(64), nullable=False)
    event_id = Column(String(64), nullable=False)
    sig = Column(String(128), nullable=False)
    approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    delta = Column(Numeric(36, 18), nullable=False)
    ref_type = Column(String(32), nullable=False)  # swap, deposit, withdraw, fee, liquidity
    ref_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Deposit(Base):
    __tablename__ = "deposits"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    amount = Column(Numeric(36, 18), nullable=False)
    external_ref = Column(String(256))  # invoice or txid
    status = Column(String(32), default="pending")  # pending, settled, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    settled_at = Column(DateTime)


class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    amount = Column(Numeric(36, 18), nullable=False)
    external_ref = Column(String(256))  # invoice or txid
    status = Column(String(32), default="pending")  # pending, sent, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    settled_at = Column(DateTime)
