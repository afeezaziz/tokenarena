from __future__ import annotations

import os
import random
from datetime import datetime, timedelta
from decimal import Decimal

from app.models import (
    GlobalMetrics,
    Token,
    TokenSnapshot,
    User,
    UserHolding,
    Competition,
    CompetitionEntry,
    get_session,
    init_db,
    init_engine,
)

DB_URL = os.getenv("DATABASE_URL", "sqlite:///token_battles.db")


def seed():
    init_engine(DB_URL)
    init_db()
    session = get_session()

    # Clear existing (children first)
    session.query(CompetitionEntry).delete()
    session.query(Competition).delete()
    session.query(UserHolding).delete()
    session.query(User).delete()
    session.query(TokenSnapshot).delete()
    session.query(GlobalMetrics).delete()
    session.query(Token).delete()
    session.commit()

    symbols = [
        ("BTC", "Bitcoin"), ("ETH", "Ethereum"), ("SOL", "Solana"), ("APT", "Aptos"), ("SUI", "Sui"),
        ("ARB", "Arbitrum"), ("OP", "Optimism"), ("LDO", "Lido"), ("UNI", "Uniswap"), ("LINK", "Chainlink"),
        ("BONK", "Bonk"), ("PEPE", "Pepe"), ("DOGE", "Dogecoin"), ("SHIB", "Shiba Inu"), ("TIA", "Celestia"),
        ("TIA2", "Celestia 2"), ("SEI", "Sei"), ("TIA3", "Celestia 3"), ("TIA4", "Celestia 4"), ("TIA5", "Celestia 5"),
    ]

    tokens = []
    for sym, name in symbols:
        price = Decimal(random.uniform(0.0001, 50000)).quantize(Decimal("0.00000001"))
        mcap = Decimal(random.uniform(1e6, 5e11)).quantize(Decimal("1"))
        holders = random.randint(1_000, 5_000_000)
        t = Token(symbol=sym, name=name, price_usd=price, market_cap_usd=mcap, holders_count=holders, change_24h=0.0)
        tokens.append(t)
        session.add(t)
    session.commit()

    # Generate 30 days of snapshots
    days = 30
    start = datetime.utcnow() - timedelta(days=days - 1)
    prev_prices = {t.id: t.price_usd for t in tokens}

    for i in range(days):
        ts = start + timedelta(days=i)

        total_tokens = 0
        total_holders = 0
        total_mcap = Decimal("0")
        total_vol = Decimal("0")

        for t in tokens:
            # light random walk
            price = (Decimal(prev_prices[t.id]) * Decimal(1 + random.uniform(-0.05, 0.05))).quantize(Decimal("0.00000001"))
            holders = max(0, int((t.holders_count or 0) * (1 + random.uniform(-0.01, 0.03))))
            mcap = (Decimal(t.market_cap_usd or 0) * Decimal(1 + random.uniform(-0.04, 0.04))).quantize(Decimal("1"))

            snap = TokenSnapshot(token_id=t.id, timestamp=ts, price_usd=price, market_cap_usd=mcap, holders_count=holders)
            session.add(snap)

            prev_prices[t.id] = price

            total_tokens += 1
            total_holders += holders
            total_mcap += mcap
            total_vol += (mcap * Decimal(random.uniform(0.001, 0.01))).quantize(Decimal("1"))

            # On last day, set the live token values and 24h change
            if i == days - 1:
                # Change vs previous day
                prev_snap = session.query(TokenSnapshot).filter_by(token_id=t.id).order_by(TokenSnapshot.timestamp.desc()).offset(1).limit(1).one_or_none()
                if prev_snap:
                    try:
                        pct = float((Decimal(price) - Decimal(prev_snap.price_usd)) / Decimal(prev_snap.price_usd) * 100)
                    except Exception:
                        pct = 0.0
                else:
                    pct = random.uniform(-10, 10)
                t.price_usd = price
                t.market_cap_usd = mcap
                t.holders_count = holders
                t.change_24h = pct
                t.last_updated = ts

        gm = GlobalMetrics(
            timestamp=ts,
            total_tokens=total_tokens,
            total_holders=total_holders,
            total_market_cap_usd=total_mcap,
            total_volume_24h_usd=total_vol,
        )
        session.add(gm)

    session.commit()

    # -------- Mock Users --------
    users_data = [
        ("npub1alice", "Alice", None, "Loves memecoins and DeFi."),
        ("npub1bob", "Bob", None, "On-chain sleuth."),
        ("npub1carol", "Carol", None, "Yield farmer."),
        ("npub1dave", "Dave", None, "Market maker."),
        ("npub1eve", "Eve", None, "Bot enjoyer."),
    ]
    users = []
    for npub, name, avatar, bio in users_data:
        u = User(npub=npub, display_name=name, avatar_url=avatar, bio=bio)
        users.append(u)
        session.add(u)
    session.commit()

    # -------- Mock Holdings --------
    for u in users:
        picks = random.sample(tokens, k=min(len(tokens), random.randint(5, 10)))
        for t in picks:
            qty = Decimal(random.uniform(0.01, 500)).quantize(Decimal("0.00000001"))
            session.add(UserHolding(user_id=u.id, token_id=t.id, quantity=qty))
    session.commit()

    # -------- Mock Competitions --------
    now = datetime.utcnow()
    comps = [
        Competition(
            slug="battle-of-gains",
            title="Battle of Gains",
            description="Highest portfolio % gains over the period.",
            start_at=now - timedelta(days=7),
            end_at=now + timedelta(days=7),
        ),
        Competition(
            slug="holders-cup",
            title="Hodlers' Cup",
            description="Largest holdings value wins.",
            start_at=now - timedelta(days=3),
            end_at=now + timedelta(days=10),
        ),
    ]
    for c in comps:
        session.add(c)
    session.commit()

    # Entries for competitions
    for comp in comps:
        scores = []
        for u in users:
            # score: sum of value of a sample of holdings times a random factor
            uhs = session.query(UserHolding).filter(UserHolding.user_id == u.id).all()
            total_val = Decimal("0")
            for uh in random.sample(uhs, k=min(len(uhs), random.randint(3, len(uhs) if uhs else 3))):
                token = next((t for t in tokens if t.id == uh.token_id), None)
                if token:
                    total_val += (Decimal(uh.quantity or 0) * Decimal(token.price_usd or 0))
            score = total_val * Decimal(1 + random.uniform(-0.1, 0.25))
            scores.append((u, score))

        # rank by score desc
        scores.sort(key=lambda x: x[1], reverse=True)
        for rank, (u, score) in enumerate(scores, start=1):
            session.add(CompetitionEntry(competition_id=comp.id, user_id=u.id, score=score, rank=rank))
    session.commit()

    print("Seeded database with tokens, snapshots, global metrics, users, holdings, competitions, and entries.")


if __name__ == "__main__":
    seed()
