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
