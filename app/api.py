from __future__ import annotations

from decimal import Decimal

from datetime import datetime, timedelta
import hashlib
import json
import secrets
from flask import Blueprint, jsonify, request, session, current_app
import os
from sqlalchemy import func, desc, or_, and_
import math
from statistics import mean, pstdev

try:
    from coincurve.schnorr import verify as schnorr_verify  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    schnorr_verify = None

from .models import (
    GlobalMetrics,
    Token, TokenSnapshot,
    User, UserHolding,
    Competition, CompetitionEntry,
    AuthChallenge,
    Asset, UserBalance, Pool, PoolLiquidity, Swap, Approval, LedgerEntry, Deposit, Withdrawal,
    get_session,
)
from .utils.nostr import hex_to_npub, npub_to_hex
from .limiter import limiter
from .integrations.rln import RLNClient

try:
    import boto3  # type: ignore
except Exception:  # pragma: no cover - optional
    boto3 = None

api_bp = Blueprint("api", __name__)

# ---------------------- Nostr Auth ----------------------
def _nostr_event_id(ev: dict) -> str:
    """Compute Nostr event id per NIP-01.
    id = sha256(json.dumps([0, pubkey, created_at, kind, tags, content]))
    """
    data = [
        0,
        ev.get("pubkey", ""),
        int(ev.get("created_at", 0)),
        int(ev.get("kind", 0)),
        ev.get("tags", []),
        ev.get("content", ""),
    ]
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@api_bp.post("/auth/nostr/challenge")
@limiter.limit("10 per minute; 2 per second")
def nostr_challenge():
    """Issue a short-lived challenge (nonce) for a given pubkey.
    Body: { pubkey: <hex 64> }
    Returns: { nonce, expires_at }
    """
    session_db = get_session()
    body = request.get_json(silent=True) or {}
    pubkey = (body.get("pubkey") or "").strip()
    if not (isinstance(pubkey, str) and len(pubkey) == 64 and all(c in "0123456789abcdefABCDEF" for c in pubkey)):
        return jsonify({"error": "invalid pubkey"}), 400

    nonce = secrets.token_hex(16)  # 32 hex chars
    now = datetime.utcnow()
    expires = now + timedelta(minutes=5)
    chal = AuthChallenge(pubkey=pubkey.lower(), nonce=nonce, created_at=now, expires_at=expires, used=False)
    session_db.add(chal)
    session_db.commit()
    return jsonify({"nonce": nonce, "expires_at": expires.isoformat() + "Z"})


@api_bp.post("/auth/nostr/verify")
@limiter.limit("20 per minute; 5 per second")
def nostr_verify():
    """Verify a signed Nostr event for the issued challenge and create/login user.
    Body: { event: {id,pubkey,created_at,kind,tags,content,sig} }
    """
    if schnorr_verify is None:
        return jsonify({"error": "server missing coincurve; install coincurve to enable nostr login"}), 500
    session_db = get_session()
    body = request.get_json(silent=True) or {}
    ev = body.get("event") or {}
    try:
        pubkey = str(ev.get("pubkey"))
        content = str(ev.get("content"))
        sig = str(ev.get("sig"))
        ev_id = str(ev.get("id"))
        # Basic checks
        if not (len(pubkey) == 64 and len(sig) == 128 and len(ev_id) == 64):
            return jsonify({"error": "invalid event fields"}), 400
        # Check challenge existence/validity
        chal = (
            session_db.query(AuthChallenge)
            .filter(AuthChallenge.pubkey == pubkey.lower(), AuthChallenge.nonce == content)
            .one_or_none()
        )
        if not chal:
            return jsonify({"error": "challenge not found"}), 400
        if chal.used:
            return jsonify({"error": "challenge already used"}), 400
        if chal.expires_at < datetime.utcnow():
            return jsonify({"error": "challenge expired"}), 400

        # Verify event id and signature (BIP-340)
        calc_id = _nostr_event_id(ev)
        if calc_id != ev_id:
            return jsonify({"error": "invalid event id"}), 400
        ok = schnorr_verify(bytes.fromhex(sig), bytes.fromhex(ev_id), bytes.fromhex(pubkey))
        if not ok:
            return jsonify({"error": "invalid signature"}), 400

        # Mark challenge used
        chal.used = True
        session_db.add(chal)

        # Upsert user by pubkey (stored in users.npub for now)
        user = session_db.query(User).filter(User.npub == pubkey).one_or_none()
        if not user:
            user = User(npub=pubkey, display_name=None)
            session_db.add(user)
            session_db.flush()

        session_db.commit()

        # Set session cookie
        session.permanent = True
        session["user_id"] = user.id
        session["nostr_pubkey"] = pubkey

        return jsonify({"ok": True, "user": {"npub": user.npub, "display_name": user.display_name}})
    except Exception as e:  # pragma: no cover
        return jsonify({"error": f"verify_failed: {e}"}), 400


@api_bp.get("/auth/me")
def auth_me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"user": None})
    session_db = get_session()
    user = session_db.query(User).filter(User.id == uid).one_or_none()
    if not user:
        return jsonify({"user": None})
    return jsonify({
        "user": {
            "npub": user.npub,
            "npub_bech32": (hex_to_npub(user.npub) if user.npub else None),
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
        }
    })


@api_bp.post("/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@api_bp.get("/overview")
def overview():
    session = get_session()

    total_tokens = session.query(func.count(Token.id)).scalar() or 0
    total_holders = session.query(func.coalesce(func.sum(Token.holders_count), 0)).scalar() or 0
    total_market_cap = session.query(func.coalesce(func.sum(Token.market_cap_usd), 0)).scalar() or Decimal("0")

    # Latest global metrics row for 24h volume
    gm = (
        session.query(GlobalMetrics)
        .order_by(desc(GlobalMetrics.timestamp))
        .limit(1)
        .one_or_none()
    )
    volume_24h = gm.total_volume_24h_usd if gm else Decimal("0")

    # Dominance: share of the largest token by market cap
    top = (
        session.query(Token.market_cap_usd)
        .order_by(desc(Token.market_cap_usd))
        .limit(1)
        .one_or_none()
    )
    dominance = float(top[0] / total_market_cap * 100) if top and total_market_cap and total_market_cap > 0 else 0.0

    return jsonify(
        {
            "total_tokens": int(total_tokens),
            "total_holders": int(total_holders),
            "total_market_cap_usd": float(total_market_cap),
            "volume_24h_usd": float(volume_24h),
            "dominance_pct": dominance,
        }
    )


@api_bp.get("/tokens")
def tokens():
    session = get_session()

    # Query params
    page = max(1, int(request.args.get("page", 1)))
    page_size = int(request.args.get("page_size", 10))
    page_size = min(max(page_size, 1), 100)
    sort_key = (request.args.get("sort", "market_cap_usd") or "market_cap_usd").lower()
    sort_dir = (request.args.get("dir", "desc") or "desc").lower()
    include_sparkline = request.args.get("sparkline") in {"1", "true", "yes"}
    days = int(request.args.get("days", 7))
    min_mcap = float(request.args.get("min_mcap", 0) or 0)
    min_volume = float(request.args.get("min_volume", 0) or 0)
    metric = (request.args.get("metric", "") or "").lower()
    q_param = (request.args.get("q", "") or "").strip()

    # Sorting
    sort_map = {
        "symbol": Token.symbol,
        "price_usd": Token.price_usd,
        "market_cap_usd": Token.market_cap_usd,
        "holders_count": Token.holders_count,
        "change_24h": Token.change_24h,
        "last_updated": Token.last_updated,
    }
    sort_col = sort_map.get(sort_key, Token.market_cap_usd)
    order_col = sort_col.asc() if sort_dir == "asc" else sort_col.desc()

    # Base filter for search and thresholds
    base = session.query(Token)
    if q_param:
        like = f"%{q_param.lower()}%"
        base = base.filter(or_(func.lower(Token.symbol).like(like), func.lower(Token.name).like(like)))
    if min_mcap > 0:
        base = base.filter((Token.market_cap_usd != None) & (Token.market_cap_usd >= min_mcap))  # noqa: E711
    if min_volume > 0:
        base = base.filter((Token.volume_24h_usd != None) & (Token.volume_24h_usd >= min_volume))  # noqa: E711

    total = base.with_entities(func.count(Token.id)).scalar() or 0

    # If a normalized metric is requested, compute for all filtered tokens and sort/paginate in Python
    allowed_metrics = {"change_24h","r7","r30","r7_sharpe","holders_growth_pct_24h","share_delta_7d","turnover_pct","composite"}
    if metric in allowed_metrics:
        all_tokens = base.order_by(Token.id.asc()).all()
        total = len(all_tokens)
        # Prepare snapshot maps for all filtered tokens
        token_ids_all = [t.id for t in all_tokens]
        now = datetime.utcnow()
        cut1 = now - timedelta(days=1)
        cut7 = now - timedelta(days=7)
        cut30 = now - timedelta(days=30)
        snaps_1d = session.query(TokenSnapshot).filter(TokenSnapshot.token_id.in_(token_ids_all), TokenSnapshot.timestamp >= cut1).order_by(TokenSnapshot.token_id.asc(), TokenSnapshot.timestamp.asc()).all()
        snaps_7d = session.query(TokenSnapshot).filter(TokenSnapshot.token_id.in_(token_ids_all), TokenSnapshot.timestamp >= cut7).order_by(TokenSnapshot.token_id.asc(), TokenSnapshot.timestamp.asc()).all()
        snaps_30d = session.query(TokenSnapshot).filter(TokenSnapshot.token_id.in_(token_ids_all), TokenSnapshot.timestamp >= cut30).order_by(TokenSnapshot.token_id.asc(), TokenSnapshot.timestamp.asc()).all()
        by1, by7, by30 = {}, {}, {}
        for s in snaps_1d:
            by1.setdefault(s.token_id, []).append(s)
        for s in snaps_7d:
            by7.setdefault(s.token_id, []).append(s)
        for s in snaps_30d:
            by30.setdefault(s.token_id, []).append(s)
        # Market cap shares
        total_mcap_now = float(session.query(func.coalesce(func.sum(Token.market_cap_usd), 0)).scalar() or 0) or 1.0
        early_mcap_7_by_tid = {tid: float(lst[0].market_cap_usd or 0) for tid, lst in by7.items() if lst}
        total_early_mcap_7 = sum(early_mcap_7_by_tid.values()) or 1.0

        def pct_return_from_snaps(lst):
            if not lst or len(lst) < 2:
                return None
            p0 = float(lst[0].price_usd or 0)
            p1 = float(lst[-1].price_usd or 0)
            if p0 <= 0:
                return None
            return (p1 / p0 - 1.0) * 100.0

        items_all = []
        for t in all_tokens:
            r24 = float(t.change_24h or 0.0)
            r7 = pct_return_from_snaps(by7.get(t.id, []))
            r30 = pct_return_from_snaps(by30.get(t.id, []))
            sharpe = None
            prices7 = [float(s.price_usd or 0) for s in by7.get(t.id, []) if float(s.price_usd or 0) > 0]
            if len(prices7) >= 3 and r7 is not None:
                lrs = []
                for i in range(1, len(prices7)):
                    if prices7[i-1] > 0 and prices7[i] > 0:
                        lrs.append(math.log(prices7[i] / prices7[i-1]))
                sigma = pstdev(lrs) if len(lrs) > 1 else 0.0
                if sigma and sigma > 1e-9:
                    sharpe = (r7 / 100.0) / sigma

            hg = None
            lst1 = by1.get(t.id, [])
            if len(lst1) >= 2:
                h0 = int(lst1[0].holders_count or 0)
                h1 = int(lst1[-1].holders_count or 0)
                if h0 > 0:
                    hg = (h1 - h0) / h0 * 100.0
                elif h1 > 0:
                    hg = 100.0
                else:
                    hg = 0.0

            share_now = (float(t.market_cap_usd or 0) / total_mcap_now) * 100.0 if total_mcap_now else None
            early_mcap_t = early_mcap_7_by_tid.get(t.id)
            early_share = (early_mcap_t / total_early_mcap_7 * 100.0) if (early_mcap_t is not None and total_early_mcap_7) else None
            share_delta_7d = (share_now - early_share) if (share_now is not None and early_share is not None) else None

            vol = float(t.volume_24h_usd or 0)
            mcap = float(t.market_cap_usd or 0)
            turnover = (vol / mcap * 100.0) if mcap > 0 and vol >= 0 else None

            it = {
                "id": t.id,
                "symbol": t.symbol,
                "name": t.name,
                "price_usd": float(t.price_usd or 0),
                "market_cap_usd": float(t.market_cap_usd or 0),
                "volume_24h_usd": float(t.volume_24h_usd or 0),
                "holders_count": int(t.holders_count or 0),
                "change_24h": r24,
                "last_updated": (t.last_updated.isoformat() if t.last_updated else None),
                "r24": r24,
                "r7": (None if r7 is None else float(r7)),
                "r30": (None if r30 is None else float(r30)),
                "r7_sharpe": (None if sharpe is None else float(sharpe)),
                "holders_growth_pct_24h": (None if hg is None else float(hg)),
                "share_t": (None if share_now is None else float(share_now)),
                "share_delta_7d": (None if share_delta_7d is None else float(share_delta_7d)),
                "turnover_pct": (None if turnover is None else float(turnover)),
            }
            items_all.append(it)

        # Composite on full filtered set with winsorization
        if items_all:
            def percentiles(xs_sorted, p):
                if not xs_sorted:
                    return None
                k = (len(xs_sorted) - 1) * p
                f = math.floor(k)
                c = math.ceil(k)
                if f == c:
                    return xs_sorted[int(k)]
                return xs_sorted[f] * (c - k) + xs_sorted[c] * (k - f)

            def winsorize(values, p=0.01):
                vals = [v for v in values if v is not None and not math.isnan(v)]
                if len(vals) < 3:
                    return values
                svals = sorted(vals)
                lo = percentiles(svals, p)
                hi = percentiles(svals, 1 - p)
                out = []
                for v in values:
                    if v is None or math.isnan(v):
                        out.append(v)
                    else:
                        out.append(min(max(v, lo), hi))
                return out

            def zlist(values):
                xs = [v for v in values if v is not None and not math.isnan(v)]
                if len(xs) < 2:
                    return [0.0 for _ in values]
                m = mean(xs)
                s = pstdev(xs) or 1.0
                return [0.0 if (v is None or math.isnan(v)) else (v - m) / s for v in values]

            r7L = winsorize([it.get("r7") for it in items_all])
            hgL = winsorize([it.get("holders_growth_pct_24h") for it in items_all])
            sdL = winsorize([it.get("share_delta_7d") for it in items_all])
            shL = winsorize([it.get("r7_sharpe") for it in items_all])
            toL = winsorize([it.get("turnover_pct") for it in items_all])
            zr7 = zlist(r7L); zhg = zlist(hgL); zsd = zlist(sdL); zsh = zlist(shL); zto = zlist(toL)
            for i, it in enumerate(items_all):
                comp = zr7[i] + 0.5*zhg[i] + zsd[i] + 0.5*zsh[i] + 0.5*zto[i]
                it["composite"] = float(comp)

        # Sort by metric and paginate
        def keyfun(it):
            v = it.get(metric)
            try:
                return float(v) if v is not None else float('-inf')
            except Exception:
                return float('-inf')
        reverse = (sort_dir != 'asc')
        items_all.sort(key=keyfun, reverse=reverse)
        start = (page - 1) * page_size
        end = start + page_size
        items = items_all[start:end]

        # Add sparkline for the page
        if include_sparkline and items:
            page_ids = [it['id'] for it in items]
            cutoff = datetime.utcnow() - timedelta(days=days) if days > 0 else None
            snaps_q = session.query(TokenSnapshot).filter(TokenSnapshot.token_id.in_(page_ids))
            if cutoff is not None:
                snaps_q = snaps_q.filter(TokenSnapshot.timestamp >= cutoff)
            snaps_q = snaps_q.order_by(TokenSnapshot.token_id.asc(), TokenSnapshot.timestamp.asc())
            spark_by_token = {}
            for s in snaps_q.all():
                spark_by_token.setdefault(s.token_id, []).append(float(s.price_usd or 0))
            for it in items:
                it['sparkline'] = spark_by_token.get(it['id'], [])

        return jsonify({
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": int(total),
        })

    # Default path: DB-side sort on base columns
    rows = (base.order_by(order_col)
                 .offset((page - 1) * page_size)
                 .limit(page_size)
                 .all())

    # Prepare sparkline data if requested
    spark_by_token = {}
    if rows:
        token_ids = [t.id for t in rows]
        if include_sparkline:
            cutoff = None
            if days > 0:
                cutoff = datetime.utcnow() - timedelta(days=days)
            snaps_q = session.query(TokenSnapshot).filter(TokenSnapshot.token_id.in_(token_ids))
            if cutoff is not None:
                snaps_q = snaps_q.filter(TokenSnapshot.timestamp >= cutoff)
            snaps_q = snaps_q.order_by(TokenSnapshot.token_id.asc(), TokenSnapshot.timestamp.asc())
            for s in snaps_q.all():
                spark_by_token.setdefault(s.token_id, []).append(float(s.price_usd or 0))

        # Normalized metrics (per returned page)
        now = datetime.utcnow()
        cut1 = now - timedelta(days=1)
        cut7 = now - timedelta(days=7)
        cut30 = now - timedelta(days=30)

        snaps_1d = session.query(TokenSnapshot).filter(
            TokenSnapshot.token_id.in_(token_ids), TokenSnapshot.timestamp >= cut1
        ).order_by(TokenSnapshot.token_id.asc(), TokenSnapshot.timestamp.asc()).all()
        snaps_7d = session.query(TokenSnapshot).filter(
            TokenSnapshot.token_id.in_(token_ids), TokenSnapshot.timestamp >= cut7
        ).order_by(TokenSnapshot.token_id.asc(), TokenSnapshot.timestamp.asc()).all()
        snaps_30d = session.query(TokenSnapshot).filter(
            TokenSnapshot.token_id.in_(token_ids), TokenSnapshot.timestamp >= cut30
        ).order_by(TokenSnapshot.token_id.asc(), TokenSnapshot.timestamp.asc()).all()

        by1, by7, by30 = {}, {}, {}
        for s in snaps_1d:
            by1.setdefault(s.token_id, []).append(s)
        for s in snaps_7d:
            by7.setdefault(s.token_id, []).append(s)
        for s in snaps_30d:
            by30.setdefault(s.token_id, []).append(s)

        # Total market cap now across all tokens (for market share)
        total_mcap_now = float(session.query(func.coalesce(func.sum(Token.market_cap_usd), 0)).scalar() or 0) or 1.0

        # Early 7d total market cap (approx over returned ids only to avoid heavy global scan)
        early_mcap_7_by_tid = {}
        for tid, lst in by7.items():
            if lst:
                early_mcap_7_by_tid[tid] = float(lst[0].market_cap_usd or 0)
        total_early_mcap_7 = sum(early_mcap_7_by_tid.values()) or 1.0

    items = []
    for t in rows:
        # Compute returns helpers
        def pct_return_from_snaps(lst):
            if not lst or len(lst) < 2:
                return None
            p0 = float(lst[0].price_usd or 0)
            p1 = float(lst[-1].price_usd or 0)
            if p0 <= 0:
                return None
            return (p1 / p0 - 1.0) * 100.0

        r24 = float(t.change_24h or 0.0)
        r7 = pct_return_from_snaps(by7.get(t.id, []))
        r30 = pct_return_from_snaps(by30.get(t.id, []))

        # r7 Sharpe-like (return divided by stdev of log returns in window)
        sharpe = None
        lst7 = by7.get(t.id, [])
        prices7 = [float(s.price_usd or 0) for s in lst7 if float(s.price_usd or 0) > 0]
        if len(prices7) >= 3 and r7 is not None:
            lrs = []
            for i in range(1, len(prices7)):
                if prices7[i-1] > 0 and prices7[i] > 0:
                    lrs.append(math.log(prices7[i] / prices7[i-1]))
            sigma = pstdev(lrs) if len(lrs) > 1 else 0.0
            if sigma and sigma > 1e-9:
                sharpe = (r7 / 100.0) / sigma

        # Holders growth 24h
        hg = None
        lst1 = by1.get(t.id, [])
        if len(lst1) >= 2:
            h0 = int(lst1[0].holders_count or 0)
            h1 = int(lst1[-1].holders_count or 0)
            if h0 > 0:
                hg = (h1 - h0) / h0 * 100.0
            elif h1 > 0:
                hg = 100.0
            else:
                hg = 0.0

        # Market share now and delta 7d (page-scoped early total for safety)
        share_now = (float(t.market_cap_usd or 0) / total_mcap_now) * 100.0 if total_mcap_now else None
        early_mcap_t = early_mcap_7_by_tid.get(t.id)
        early_share = (early_mcap_t / total_early_mcap_7 * 100.0) if (early_mcap_t is not None and total_early_mcap_7) else None
        share_delta_7d = (share_now - early_share) if (share_now is not None and early_share is not None) else None

        # Turnover (Volume/MarketCap)
        vol = float(t.volume_24h_usd or 0)
        mcap = float(t.market_cap_usd or 0)
        turnover = (vol / mcap * 100.0) if mcap > 0 and vol >= 0 else None

        item = {
            "id": t.id,
            "symbol": t.symbol,
            "name": t.name,
            "price_usd": float(t.price_usd or 0),
            "market_cap_usd": float(t.market_cap_usd or 0),
            "volume_24h_usd": float(t.volume_24h_usd or 0),
            "holders_count": int(t.holders_count or 0),
            "change_24h": float(t.change_24h or 0),
            "last_updated": (t.last_updated.isoformat() if t.last_updated else None),
            # Normalized metrics
            "r24": r24,
            "r7": (None if r7 is None else float(r7)),
            "r30": (None if r30 is None else float(r30)),
            "r7_sharpe": (None if sharpe is None else float(sharpe)),
            "holders_growth_pct_24h": (None if hg is None else float(hg)),
            "share_t": (None if share_now is None else float(share_now)),
            "share_delta_7d": (None if share_delta_7d is None else float(share_delta_7d)),
            "turnover_pct": (None if turnover is None else float(turnover)),
        }
        if include_sparkline:
            item["sparkline"] = spark_by_token.get(t.id, [])
        items.append(item)

    # Compute composite z-score over current page (best-effort; not global)
    if items:
        def percentiles(xs_sorted, p):
            if not xs_sorted:
                return None
            k = (len(xs_sorted) - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return xs_sorted[int(k)]
            return xs_sorted[f] * (c - k) + xs_sorted[c] * (k - f)

        def winsorize(values, p=0.01):
            vals = [v for v in values if v is not None and not math.isnan(v)]
            if len(vals) < 3:
                return values
            svals = sorted(vals)
            lo = percentiles(svals, p)
            hi = percentiles(svals, 1 - p)
            out = []
            for v in values:
                if v is None or math.isnan(v):
                    out.append(v)
                else:
                    out.append(min(max(v, lo), hi))
            return out

        def zscores(values):
            xs = [v for v in values if v is not None and not math.isnan(v)]
            if len(xs) < 2:
                return {i: 0.0 for i in range(len(values))}
            m = mean(xs)
            s = pstdev(xs) or 1.0
            out = {}
            for i, v in enumerate(values):
                out[i] = 0.0 if (v is None or math.isnan(v)) else (v - m) / s
            return out

        r7_list = [it.get("r7") for it in items]
        hg_list = [it.get("holders_growth_pct_24h") for it in items]
        sd_list = [it.get("share_delta_7d") for it in items]
        sh_list = [it.get("r7_sharpe") for it in items]
        to_list = [it.get("turnover_pct") for it in items]

        # Winsorize before z-scoring to tame outliers
        r7_list = winsorize(r7_list)
        hg_list = winsorize(hg_list)
        sd_list = winsorize(sd_list)
        sh_list = winsorize(sh_list)
        to_list = winsorize(to_list)

        zr7 = zscores(r7_list)
        zhg = zscores(hg_list)
        zsd = zscores(sd_list)
        zsh = zscores(sh_list)
        zto = zscores(to_list)
        for i, it in enumerate(items):
            composite = zr7.get(i, 0.0) + 0.5 * zhg.get(i, 0.0) + zsd.get(i, 0.0) + 0.5 * zsh.get(i, 0.0) + 0.5 * zto.get(i, 0.0)
            it["composite"] = float(composite)

    return jsonify({
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": int(total),
    })


# ---------------------- Profile (current user) ----------------------
@api_bp.get("/profile")
def get_profile():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "unauthorized"}), 401
    s = get_session()
    user = s.query(User).filter(User.id == uid).one_or_none()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({
        "npub": user.npub,
        "npub_bech32": (hex_to_npub(user.npub) if user.npub else None),
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "bio": user.bio,
        "joined_at": user.joined_at.isoformat() if user.joined_at else None,
    })


@api_bp.post("/profile")
@limiter.limit("30 per minute")
def update_profile():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "unauthorized"}), 401
    s = get_session()
    user = s.query(User).filter(User.id == uid).one_or_none()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    display_name = body.get("display_name")
    bio = body.get("bio")
    # Basic validation and normalization
    if display_name is not None:
        display_name = str(display_name).strip()
        if len(display_name) > 128:
            return jsonify({"error": "display_name too long"}), 400
        user.display_name = display_name or None
    if bio is not None:
        bio = str(bio).strip()
        if len(bio) > 512:
            return jsonify({"error": "bio too long"}), 400
        user.bio = bio or None
    s.add(user)
    s.commit()
    return jsonify({"ok": True})


@api_bp.post("/profile/avatar")
@limiter.limit("10 per minute; 2 per second")
def upload_avatar():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "unauthorized"}), 401
    s = get_session()
    user = s.query(User).filter(User.id == uid).one_or_none()
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    if 'avatar' not in request.files:
        return jsonify({"error": "no_file"}), 400
    f = request.files['avatar']
    if not f or f.filename == '':
        return jsonify({"error": "no_file"}), 400

    # Validate content type and size (<= 2MB)
    allowed = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/webp': '.webp',
    }
    ctype = (f.mimetype or '').lower()
    if ctype not in allowed:
        return jsonify({"error": "unsupported_type"}), 400
    data = f.read()
    max_bytes = int(current_app.config.get("AVATAR_MAX_BYTES", 2 * 1024 * 1024))
    if not data or len(data) > max_bytes:
        return jsonify({"error": "too_large"}), 400

    ext = allowed[ctype]
    fname = f"u{uid}-{int(datetime.utcnow().timestamp())}-{secrets.token_hex(4)}{ext}"
    out_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'avatars')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, fname)
    with open(out_path, 'wb') as wf:
        wf.write(data)

    # Update user avatar url
    user.avatar_url = f"/static/uploads/avatars/{fname}"
    s.add(user)
    s.commit()
    return jsonify({"ok": True, "avatar_url": user.avatar_url})


def _s3_cfg():
    cfg = current_app.config
    bucket = cfg.get("S3_AVATAR_BUCKET")
    region = cfg.get("S3_REGION")
    access = cfg.get("S3_ACCESS_KEY_ID")
    secret = cfg.get("S3_SECRET_ACCESS_KEY")
    endpoint = cfg.get("S3_ENDPOINT_URL")
    public_base = cfg.get("S3_PUBLIC_BASE_URL")
    return bucket, region, access, secret, endpoint, public_base


def _s3_client():
    bucket, region, access, secret, endpoint, _ = _s3_cfg()
    if not (boto3 and bucket and region and access and secret):
        return None
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        endpoint_url=endpoint,
    )


def _s3_public_url(key: str) -> str | None:
    bucket, region, _, _, endpoint, public_base = _s3_cfg()
    if not bucket:
        return None
    if public_base:
        base = public_base.rstrip("/")
        return f"{base}/{key}"
    if endpoint:
        base = endpoint.rstrip("/")
        return f"{base}/{bucket}/{key}"
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


@api_bp.post("/profile/avatar/presign")
@limiter.limit("10 per minute; 2 per second")
def presign_avatar():
    """Return a presigned POST for direct S3 upload. Fallback to 400 if S3 is not configured.
    Body: { content_type: str }
    Response: { url, fields, key, public_url }
    """
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "unauthorized"}), 401
    s3 = _s3_client()
    if not s3:
        return jsonify({"error": "s3_disabled"}), 400
    body = request.get_json(silent=True) or {}
    ctype = str(body.get("content_type") or "").lower()
    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    if ctype not in allowed:
        return jsonify({"error": "unsupported_type"}), 400
    ext = allowed[ctype]
    key = f"avatars/u{uid}/{int(datetime.utcnow().timestamp())}-{secrets.token_hex(4)}{ext}"
    bucket, _, _, _, _, _ = _s3_cfg()
    max_bytes = int(current_app.config.get("AVATAR_MAX_BYTES", 2 * 1024 * 1024))
    post = s3.generate_presigned_post(
        Bucket=bucket,
        Key=key,
        Fields={"Content-Type": ctype},
        Conditions=[
            {"Content-Type": ctype},
            ["content-length-range", 1, max_bytes],
        ],
        ExpiresIn=300,
    )
    public_url = _s3_public_url(key)
    return jsonify({
        "url": post["url"],
        "fields": post["fields"],
        "key": key,
        "public_url": public_url,
    })


@api_bp.post("/profile/avatar/complete")
@limiter.limit("30 per minute")
def complete_avatar():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "unauthorized"}), 401
    s = get_session()
    user = s.query(User).filter(User.id == uid).one_or_none()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    key = str(body.get("key") or "")
    if not key.startswith(f"avatars/u{uid}/"):
        return jsonify({"error": "invalid_key"}), 400
    url = _s3_public_url(key)
    if not url:
        return jsonify({"error": "s3_disabled"}), 400
    user.avatar_url = url
    s.add(user)
    s.commit()
    return jsonify({"ok": True, "avatar_url": user.avatar_url})


@api_bp.get("/top-movers")
def top_movers():
    session = get_session()
    limit = int(request.args.get("limit", 5))
    limit = min(max(limit, 1), 50)
    metric = (request.args.get("metric", "change_24h") or "change_24h").lower()
    min_mcap = float(request.args.get("min_mcap", 0) or 0)
    min_volume = float(request.args.get("min_volume", 0) or 0)

    # Fetch all tokens for metric computation
    q = session.query(Token)
    if min_mcap > 0:
        q = q.filter((Token.market_cap_usd != None) & (Token.market_cap_usd >= min_mcap))  # noqa: E711
    if min_volume > 0:
        q = q.filter((Token.volume_24h_usd != None) & (Token.volume_24h_usd >= min_volume))  # noqa: E711
    toks = q.all()
    if not toks:
        return jsonify([])

    token_ids = [t.id for t in toks]
    now = datetime.utcnow()
    cut1 = now - timedelta(days=1)
    cut7 = now - timedelta(days=7)
    cut30 = now - timedelta(days=30)

    # Preload snapshots
    snaps_1d = session.query(TokenSnapshot).filter(
        TokenSnapshot.token_id.in_(token_ids), TokenSnapshot.timestamp >= cut1
    ).order_by(TokenSnapshot.token_id.asc(), TokenSnapshot.timestamp.asc()).all()
    snaps_7d = session.query(TokenSnapshot).filter(
        TokenSnapshot.token_id.in_(token_ids), TokenSnapshot.timestamp >= cut7
    ).order_by(TokenSnapshot.token_id.asc(), TokenSnapshot.timestamp.asc()).all()
    snaps_30d = session.query(TokenSnapshot).filter(
        TokenSnapshot.token_id.in_(token_ids), TokenSnapshot.timestamp >= cut30
    ).order_by(TokenSnapshot.token_id.asc(), TokenSnapshot.timestamp.asc()).all()

    by1, by7, by30 = {}, {}, {}
    for s in snaps_1d:
        by1.setdefault(s.token_id, []).append(s)
    for s in snaps_7d:
        by7.setdefault(s.token_id, []).append(s)
    for s in snaps_30d:
        by30.setdefault(s.token_id, []).append(s)

    # Market share (global now and early 7d)
    total_mcap_now = float(session.query(func.coalesce(func.sum(Token.market_cap_usd), 0)).scalar() or 0) or 1.0
    early_mcap_7_by_tid = {}
    for tid, lst in by7.items():
        if lst:
            early_mcap_7_by_tid[tid] = float(lst[0].market_cap_usd or 0)
    total_early_mcap_7 = sum(early_mcap_7_by_tid.values()) or 1.0

    # Helpers
    def pct_return_from_snaps(lst):
        if not lst or len(lst) < 2:
            return None
        p0 = float(lst[0].price_usd or 0)
        p1 = float(lst[-1].price_usd or 0)
        if p0 <= 0:
            return None
        return (p1 / p0 - 1.0) * 100.0

    # Compute per-token metrics
    items = []
    for t in toks:
        r24 = float(t.change_24h or 0.0)
        r7 = pct_return_from_snaps(by7.get(t.id, []))
        r30 = pct_return_from_snaps(by30.get(t.id, []))

        # r7 sharpe-like
        sharpe = None
        prices7 = [float(s.price_usd or 0) for s in by7.get(t.id, []) if float(s.price_usd or 0) > 0]
        if len(prices7) >= 3 and r7 is not None:
            lrs = []
            for i in range(1, len(prices7)):
                if prices7[i-1] > 0 and prices7[i] > 0:
                    lrs.append(math.log(prices7[i]/prices7[i-1]))
            sigma = pstdev(lrs) if len(lrs) > 1 else 0.0
            if sigma and sigma > 1e-9:
                sharpe = (r7 / 100.0) / sigma

        # holders growth 24h
        hg = None
        lst1 = by1.get(t.id, [])
        if len(lst1) >= 2:
            h0 = int(lst1[0].holders_count or 0)
            h1 = int(lst1[-1].holders_count or 0)
            if h0 > 0:
                hg = (h1 - h0) / h0 * 100.0
            elif h1 > 0:
                hg = 100.0
            else:
                hg = 0.0

        share_now = (float(t.market_cap_usd or 0) / total_mcap_now) * 100.0 if total_mcap_now else None
        early_mcap_t = early_mcap_7_by_tid.get(t.id)
        early_share = (early_mcap_t / total_early_mcap_7 * 100.0) if (early_mcap_t is not None and total_early_mcap_7) else None
        share_delta_7d = (share_now - early_share) if (share_now is not None and early_share is not None) else None

        # turnover
        vol = float(t.volume_24h_usd or 0)
        mcap = float(t.market_cap_usd or 0)
        turnover = (vol / mcap * 100.0) if mcap > 0 and vol >= 0 else None

        items.append({
            "symbol": t.symbol,
            "name": t.name,
            "volume_24h_usd": float(t.volume_24h_usd or 0),
            "change_24h": r24,
            "r7": (None if r7 is None else float(r7)),
            "r30": (None if r30 is None else float(r30)),
            "r7_sharpe": (None if sharpe is None else float(sharpe)),
            "holders_growth_pct_24h": (None if hg is None else float(hg)),
            "share_delta_7d": (None if share_delta_7d is None else float(share_delta_7d)),
            "turnover_pct": (None if turnover is None else float(turnover)),
        })

    # Composite z-score across all tokens
    if items:
        def percentiles(xs_sorted, p):
            if not xs_sorted:
                return None
            k = (len(xs_sorted) - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return xs_sorted[int(k)]
            return xs_sorted[f] * (c - k) + xs_sorted[c] * (k - f)

        def winsorize(values, p=0.01):
            vals = [v for v in values if v is not None and not math.isnan(v)]
            if len(vals) < 3:
                return values
            svals = sorted(vals)
            lo = percentiles(svals, p)
            hi = percentiles(svals, 1 - p)
            out = []
            for v in values:
                if v is None or math.isnan(v):
                    out.append(v)
                else:
                    out.append(min(max(v, lo), hi))
            return out

        def zscores(values):
            xs = [v for v in values if v is not None and not math.isnan(v)]
            if len(xs) < 2:
                return [0.0 for _ in values]
            m = mean(xs)
            s = pstdev(xs) or 1.0
            return [0.0 if (v is None or math.isnan(v)) else (v - m) / s for v in values]

        r7_list = [it.get("r7") for it in items]
        hg_list = [it.get("holders_growth_pct_24h") for it in items]
        sd_list = [it.get("share_delta_7d") for it in items]
        sh_list = [it.get("r7_sharpe") for it in items]
        to_list = [it.get("turnover_pct") for it in items]

        r7_list = winsorize(r7_list)
        hg_list = winsorize(hg_list)
        sd_list = winsorize(sd_list)
        sh_list = winsorize(sh_list)
        to_list = winsorize(to_list)

        zr7 = zscores(r7_list)
        zhg = zscores(hg_list)
        zsd = zscores(sd_list)
        zsh = zscores(sh_list)
        zto = zscores(to_list)
        for i, it in enumerate(items):
            comp = zr7[i] + 0.5*zhg[i] + zsd[i] + 0.5*zsh[i] + 0.5*zto[i]
            it["composite"] = float(comp)

    # Pick metric values and sort
    metric_key = metric if metric in {"change_24h","r7","r30","r7_sharpe","holders_growth_pct_24h","share_delta_7d","turnover_pct","composite"} else "change_24h"
    filtered = [it for it in items if it.get(metric_key) is not None and not math.isnan(float(it.get(metric_key)))]
    filtered.sort(key=lambda x: abs(float(x.get(metric_key))), reverse=True if metric_key in {"change_24h","r7","r30","holders_growth_pct_24h","share_delta_7d","composite","r7_sharpe"} else True)
    top = filtered[:limit]

    # Respond with metric value included
    for it in top:
        it["metric"] = metric_key
        it["value"] = float(it.get(metric_key) or 0.0)
    return jsonify(top)


@api_bp.get("/chart/global")
def chart_global():
    session = get_session()
    q = session.query(GlobalMetrics)
    range_param = (request.args.get("range", "all") or "all").lower()
    days_map = {"7d": 7, "30d": 30, "90d": 90}
    if range_param in days_map:
        cutoff = datetime.utcnow() - timedelta(days=days_map[range_param])
        q = q.filter(GlobalMetrics.timestamp >= cutoff)
    metrics = q.order_by(GlobalMetrics.timestamp.asc()).all()

    labels = [m.timestamp.strftime("%Y-%m-%d") for m in metrics]
    tokens_series = [int(m.total_tokens or 0) for m in metrics]
    holders_series = [int(m.total_holders or 0) for m in metrics]

    return jsonify({
        "labels": labels,
        "tokens": tokens_series,
        "holders": holders_series,
    })


# ---------------------- User (npub) ----------------------
@api_bp.get("/user/<npub>")
def user_detail(npub: str):
    session = get_session()
    # Accept hex or npub bech32
    hex_pk = npub
    if npub.startswith("npub1"):
        decoded = npub_to_hex(npub)
        if decoded:
            hex_pk = decoded
    user = session.query(User).filter(User.npub == hex_pk).one_or_none()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Holdings with value
    q = (
        session.query(UserHolding, Token)
        .join(Token, Token.id == UserHolding.token_id)
        .filter(UserHolding.user_id == user.id)
        .all()
    )
    holdings = []
    total_value = Decimal("0")
    for uh, tok in q:
        price = Decimal(tok.price_usd or 0)
        qty = Decimal(uh.quantity or 0)
        val = (price * qty)
        total_value += val
        holdings.append({
            "symbol": tok.symbol,
            "name": tok.name,
            "quantity": float(qty),
            "price_usd": float(price),
            "value_usd": float(val),
        })
    # compute pct
    out_holdings = []
    for h in sorted(holdings, key=lambda x: x["value_usd"], reverse=True):
        pct = (h["value_usd"] / float(total_value)) * 100 if total_value and float(total_value) > 0 else 0
        h2 = dict(h)
        h2["pct"] = pct
        out_holdings.append(h2)

    return jsonify({
        "user": {
            "npub": user.npub,
            "npub_bech32": (hex_to_npub(user.npub) if user.npub else None),
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "bio": user.bio,
            "joined_at": user.joined_at.isoformat() if user.joined_at else None,
        },
        "portfolio": {
            "total_value_usd": float(total_value),
            "total_tokens": len(out_holdings),
            "holdings": out_holdings,
        }
    })


# ---------------------- Token ----------------------
@api_bp.get("/token/<symbol>")
def token_detail(symbol: str):
    session = get_session()
    sym = (symbol or "").upper()
    token = session.query(Token).filter(Token.symbol == sym).one_or_none()
    if not token:
        return jsonify({"error": "Token not found"}), 404

    # Top holders (by quantity)
    rows = (
        session.query(UserHolding, User)
        .join(User, User.id == UserHolding.user_id)
        .filter(UserHolding.token_id == token.id)
        .order_by(desc(UserHolding.quantity))
        .limit(10)
        .all()
    )
    top_holders = [{
        "npub": user.npub,
        "display_name": user.display_name,
        "quantity": float(uh.quantity or 0),
        "value_usd": float((Decimal(uh.quantity or 0) * Decimal(token.price_usd or 0))),
    } for uh, user in rows]

    return jsonify({
        "id": token.id,
        "symbol": token.symbol,
        "name": token.name,
        "price_usd": float(token.price_usd or 0),
        "market_cap_usd": float(token.market_cap_usd or 0),
        "holders_count": int(token.holders_count or 0),
        "change_24h": float(token.change_24h or 0),
        "last_updated": token.last_updated.isoformat() if token.last_updated else None,
        "top_holders": top_holders,
    })


@api_bp.get("/chart/token/<symbol>")
def chart_token(symbol: str):
    session = get_session()
    sym = (symbol or "").upper()
    token = session.query(Token).filter(Token.symbol == sym).one_or_none()
    if not token:
        return jsonify({"error": "Token not found"}), 404

    q = session.query(TokenSnapshot).filter(TokenSnapshot.token_id == token.id)
    range_param = (request.args.get("range", "all") or "all").lower()
    days_map = {"7d": 7, "30d": 30, "90d": 90}
    if range_param in days_map:
        cutoff = datetime.utcnow() - timedelta(days=days_map[range_param])
        q = q.filter(TokenSnapshot.timestamp >= cutoff)
    snaps = q.order_by(TokenSnapshot.timestamp.asc()).all()
    labels = [s.timestamp.strftime("%Y-%m-%d") for s in snaps]
    prices = [float(s.price_usd or 0) for s in snaps]
    holders = [int(s.holders_count or 0) for s in snaps]
    return jsonify({
        "labels": labels,
        "prices": prices,
        "holders": holders,
    })


@api_bp.get("/search")
@limiter.limit("60 per minute")
def search():
    session = get_session()
    q = (request.args.get("q", "") or "").strip()
    if not q:
        return jsonify({"tokens": [], "users": []})

    like = f"%{q.lower()}%"
    token_rows = (
        session.query(Token)
        .filter(or_(func.lower(Token.symbol).like(like), func.lower(Token.name).like(like)))
        .order_by(desc(Token.market_cap_usd))
        .limit(10)
        .all()
    )
    user_rows = (
        session.query(User)
        .filter(or_(func.lower(User.npub).like(like), func.lower(User.display_name).like(like)))
        .limit(10)
        .all()
    )

    tokens_out = [
        {"symbol": t.symbol, "name": t.name, "market_cap_usd": float(t.market_cap_usd or 0)}
        for t in token_rows
    ]
    users_out = [
        {
            "npub": u.npub,
            "npub_bech32": (hex_to_npub(u.npub) if u.npub else None),
            "display_name": u.display_name,
            "avatar_url": u.avatar_url,
        }
        for u in user_rows
    ]
    return jsonify({"tokens": tokens_out, "users": users_out})


# ---------------------- Competition ----------------------
@api_bp.get("/competitions")
def competitions_list():
    """Return a list of competitions with basic stats and status."""
    session = get_session()
    comps = session.query(Competition).order_by(Competition.start_at.desc()).all()
    now = datetime.utcnow()
    out = []
    for c in comps:
        # participants count
        part_count = (
            session.query(func.count(CompetitionEntry.id))
            .filter(CompetitionEntry.competition_id == c.id)
            .scalar()
            or 0
        )
        status = "upcoming"
        if c.start_at and c.end_at:
            if c.start_at <= now <= c.end_at:
                status = "active"
            elif now > c.end_at:
                status = "past"
        out.append({
            "slug": c.slug,
            "title": c.title,
            "description": c.description,
            "start_at": c.start_at.isoformat() if c.start_at else None,
            "end_at": c.end_at.isoformat() if c.end_at else None,
            "participants": int(part_count),
            "status": status,
        })
    return jsonify(out)


@api_bp.post("/admin/deposits/create")
def admin_deposit_create():
    ctx, err = _require_user_and_session()
    if err:
        return err
    uid, s = ctx
    if not _is_admin(s, uid):
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    try:
        user_id = int(body.get("user_id"))
        asset_id = int(body.get("asset_id"))
        amount = Decimal(str(body.get("amount")))
    except Exception:
        return jsonify({"error": "invalid_body"}), 400
    if amount <= 0:
        return jsonify({"error": "amount_must_be_positive"}), 400
    ext = body.get("external_ref")
    d = Deposit(user_id=user_id, asset_id=asset_id, amount=amount, external_ref=ext, status="pending", created_at=datetime.utcnow())
    s.add(d)
    s.commit()
    return jsonify({"ok": True, "deposit_id": d.id})


@api_bp.post("/admin/deposits/settle")
def admin_deposit_settle():
    ctx, err = _require_user_and_session()
    if err:
        return err
    uid, s = ctx
    if not _is_admin(s, uid):
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    try:
        dep_id = int(body.get("id"))
    except Exception:
        return jsonify({"error": "invalid_body"}), 400
    d = s.query(Deposit).filter(Deposit.id == dep_id).one_or_none()
    if not d:
        return jsonify({"error": "not_found"}), 404
    if d.status == "settled":
        return jsonify({"ok": True, "already": True})
    # credit user balance and ledger
    ub = s.query(UserBalance).filter(UserBalance.user_id == d.user_id, UserBalance.asset_id == d.asset_id).one_or_none()
    if not ub:
        ub = UserBalance(user_id=d.user_id, asset_id=d.asset_id, balance=Decimal("0"), available=Decimal("0"), updated_at=datetime.utcnow())
        s.add(ub)
        s.flush()
    ub.balance = (ub.balance or Decimal("0")) + (d.amount or Decimal("0"))
    ub.available = (ub.available or Decimal("0")) + (d.amount or Decimal("0"))
    ub.updated_at = datetime.utcnow()
    s.add(ub)
    le = LedgerEntry(user_id=d.user_id, asset_id=d.asset_id, delta=d.amount, ref_type="deposit", ref_id=d.id, created_at=datetime.utcnow())
    s.add(le)
    d.status = "settled"
    d.settled_at = datetime.utcnow()
    s.add(d)
    s.commit()
    return jsonify({"ok": True})


@api_bp.post("/admin/withdrawals/create")
def admin_withdrawal_create():
    ctx, err = _require_user_and_session()
    if err:
        return err
    uid, s = ctx
    if not _is_admin(s, uid):
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    try:
        user_id = int(body.get("user_id"))
        asset_id = int(body.get("asset_id"))
        amount = Decimal(str(body.get("amount")))
    except Exception:
        return jsonify({"error": "invalid_body"}), 400
    if amount <= 0:
        return jsonify({"error": "amount_must_be_positive"}), 400
    ext = body.get("external_ref")
    # ensure balance
    ub = s.query(UserBalance).filter(UserBalance.user_id == user_id, UserBalance.asset_id == asset_id).one_or_none()
    if not ub or (ub.available or Decimal("0")) < amount:
        return jsonify({"error": "insufficient_available"}), 400
    # debit immediately (simple flow)
    ub.available = (ub.available or Decimal("0")) - amount
    ub.balance = (ub.balance or Decimal("0")) - amount
    ub.updated_at = datetime.utcnow()
    s.add(ub)
    w = Withdrawal(user_id=user_id, asset_id=asset_id, amount=amount, external_ref=ext, status="pending", created_at=datetime.utcnow())
    s.add(w)
    s.flush()
    le = LedgerEntry(user_id=user_id, asset_id=asset_id, delta=(Decimal("0") - amount), ref_type="withdraw", ref_id=w.id, created_at=datetime.utcnow())
    s.add(le)
    s.commit()
    return jsonify({"ok": True, "withdrawal_id": w.id})


@api_bp.post("/admin/withdrawals/mark_sent")
def admin_withdrawal_mark_sent():
    ctx, err = _require_user_and_session()
    if err:
        return err
    uid, s = ctx
    if not _is_admin(s, uid):
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    try:
        wid = int(body.get("id"))
    except Exception:
        return jsonify({"error": "invalid_body"}), 400
    w = s.query(Withdrawal).filter(Withdrawal.id == wid).one_or_none()
    if not w:
        return jsonify({"error": "not_found"}), 404
    if w.status == "sent":
        return jsonify({"ok": True, "already": True})
    w.status = "sent"
    w.settled_at = datetime.utcnow()
    s.add(w)
    s.commit()
    return jsonify({"ok": True})


@api_bp.get("/competition/<slug>")
def competition_detail(slug: str):
    session = get_session()
    comp = session.query(Competition).filter(Competition.slug == slug).one_or_none()
    if not comp:
        return jsonify({"error": "Competition not found"}), 404

    entries = (
        session.query(CompetitionEntry, User)
        .join(User, User.id == CompetitionEntry.user_id)
        .filter(CompetitionEntry.competition_id == comp.id)
        .order_by(CompetitionEntry.rank.asc(), CompetitionEntry.score.desc())
        .all()
    )
    leaderboard = [{
        "rank": e.rank,
        "score": float(e.score or 0),
        "npub": u.npub,
        "display_name": u.display_name,
        "avatar_url": u.avatar_url,
    } for e, u in entries]

    return jsonify({
        "slug": comp.slug,
        "title": comp.title,
        "description": comp.description,
        "start_at": comp.start_at.isoformat() if comp.start_at else None,
        "end_at": comp.end_at.isoformat() if comp.end_at else None,
        "leaderboard": leaderboard,
    })


# ---------------------- Data Sources ----------------------
@api_bp.get("/datasources")
def datasources_list():
    """Return a list of data sources. Static for now (no DB model yet)."""
    # In the future, back this with a DataSource model
    sources = [
        {
            "slug": "lnfi",
            "name": "LNFI",
            "description": "Lightning Fi: token, prices, holders and volume (Nostr native).",
            "coverage": ["tokens", "prices", "holders", "snapshots"],
            "freshness": "~15m",
            "website": "https://lnfi.io/",
            "status": "operational",
            "last_sync_at": datetime.utcnow().isoformat() + "Z",
        },
        {
            "slug": "mempool-relays",
            "name": "Mempool Relays",
            "description": "Aggregated relay events for market activity.",
            "coverage": ["relays", "activity"],
            "freshness": "~5m",
            "website": "https://github.com/nostr-protocol/",
            "status": "operational",
            "last_sync_at": datetime.utcnow().isoformat() + "Z",
        },
    ]
    return jsonify(sources)


@api_bp.get("/datasource/<slug>")
def datasource_detail(slug: str):
    """Return details for a single data source. Static for now."""
    base = {
        "lnfi": {
            "slug": "lnfi",
            "name": "LNFI",
            "website": "https://lnfi.io/",
            "description": "Lightning Fi: token registry, prices, holders, market data.",
            "coverage": [
                {"key": "tokens", "desc": "Token registry and metadata"},
                {"key": "prices", "desc": "Spot and historical prices"},
                {"key": "holders", "desc": "Holders count and growth"},
                {"key": "snapshots", "desc": "Daily snapshots for charts"},
            ],
            "status": "operational",
            "last_sync_at": datetime.utcnow().isoformat() + "Z",
            "changelog": [
                {"version": "2025-09-01", "note": "Added holders growth 24h."},
                {"version": "2025-08-15", "note": "Initial integration."},
            ],
        },
        "mempool-relays": {
            "slug": "mempool-relays",
            "name": "Mempool Relays",
            "website": "https://github.com/nostr-protocol/",
            "description": "Relay activity and liquidity hints.",
            "coverage": [
                {"key": "relays", "desc": "Relay list and basic stats"},
                {"key": "activity", "desc": "Event rates and spikes"},
            ],
            "status": "operational",
            "last_sync_at": datetime.utcnow().isoformat() + "Z",
            "changelog": [
                {"version": "2025-09-05", "note": "Added activity spikes."},
            ],
        },
    }
    ds = base.get(slug)
    if not ds:
        return jsonify({"error": "not_found"}), 404
    return jsonify(ds)


# ---------------------- RLN (RGB Lightning Node) Proxies ----------------------
def _require_auth_session():
    uid = session.get("user_id")
    if not uid:
        return None, (jsonify({"error": "unauthorized"}), 401)
    s = get_session()
    user = s.query(User).filter(User.id == uid).one_or_none()
    if not user:
        return None, (jsonify({"error": "unauthorized"}), 401)
    return user, None


@api_bp.get("/rln/nodeinfo")
def rln_nodeinfo():
    user, err = _require_auth_session()
    if err:
        return err
    cli = RLNClient()
    try:
        return jsonify(cli.nodeinfo())
    except Exception as e:
        return jsonify({"error": f"rln_nodeinfo_failed: {e}"}), 502


@api_bp.post("/rln/btcbalance")
def rln_btcbalance():
    user, err = _require_auth_session()
    if err:
        return err
    cli = RLNClient()
    try:
        return jsonify(cli.btcbalance())
    except Exception as e:
        return jsonify({"error": f"rln_btcbalance_failed: {e}"}), 502


@api_bp.post("/rln/listassets")
def rln_listassets():
    user, err = _require_auth_session()
    if err:
        return err
    cli = RLNClient()
    try:
        return jsonify(cli.listassets())
    except Exception as e:
        return jsonify({"error": f"rln_listassets_failed: {e}"}), 502


@api_bp.post("/rln/assetbalance")
def rln_assetbalance():
    user, err = _require_auth_session()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    asset_id = str(body.get("asset_id") or "").strip()
    if not asset_id:
        return jsonify({"error": "asset_id_required"}), 400
    cli = RLNClient()
    try:
        return jsonify(cli.assetbalance(asset_id))
    except Exception as e:
        return jsonify({"error": f"rln_assetbalance_failed: {e}"}), 502


@api_bp.post("/rln/lninvoice")
def rln_lninvoice():
    user, err = _require_auth_session()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    amount_msat = int(body.get("amount_msat") or 0)
    memo = body.get("memo")
    if amount_msat <= 0:
        return jsonify({"error": "invalid_amount_msat"}), 400
    cli = RLNClient()
    try:
        return jsonify(cli.lninvoice(amount_msat=amount_msat, memo=memo))
    except Exception as e:
        return jsonify({"error": f"rln_lninvoice_failed: {e}"}), 502


@api_bp.post("/rln/payln")
def rln_payln():
    user, err = _require_auth_session()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    invoice = str(body.get("invoice") or "").strip()
    if not invoice:
        return jsonify({"error": "invoice_required"}), 400
    cli = RLNClient()
    try:
        return jsonify(cli.sendbtc(invoice))
    except Exception as e:
        return jsonify({"error": f"rln_payln_failed: {e}"}), 502


@api_bp.post("/rln/rgbinvoice")
def rln_rgbinvoice():
    user, err = _require_auth_session()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    asset_id = str(body.get("asset_id") or "").strip()
    amount = int(body.get("amount") or 0)
    endpoints = body.get("transport_endpoints")
    if not asset_id or amount <= 0:
        return jsonify({"error": "asset_id_and_amount_required"}), 400
    cli = RLNClient()
    try:
        return jsonify(cli.rgbinvoice(asset_id=asset_id, amount=amount, transport_endpoints=endpoints))
    except Exception as e:
        return jsonify({"error": f"rln_rgbinvoice_failed: {e}"}), 502


@api_bp.post("/rln/payrgb")
def rln_payrgb():
    user, err = _require_auth_session()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    invoice = str(body.get("invoice") or "").strip()
    if not invoice:
        return jsonify({"error": "invoice_required"}), 400
    cli = RLNClient()
    try:
        return jsonify(cli.sendasset(invoice))
    except Exception as e:
        return jsonify({"error": f"rln_payrgb_failed: {e}"}), 502

@api_bp.post("/rln/issue/nia")
def rln_issue_nia():
    user, err = _require_auth_session()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    ticker = str(body.get("ticker") or "").strip()
    name = str(body.get("name") or "").strip()
    amounts = body.get("amounts")
    precision = int(body.get("precision") or 0)
    if not ticker or not name or not isinstance(amounts, list) or not amounts:
        return jsonify({"error": "ticker_name_amounts_required"}), 400
    try:
        amounts_int = [int(x) for x in amounts]
    except Exception:
        return jsonify({"error": "amounts_must_be_ints"}), 400
    cli = RLNClient()
    try:
        return jsonify(cli.issueasset_nia(ticker=ticker, name=name, amounts=amounts_int, precision=precision))
    except Exception as e:
        return jsonify({"error": f"rln_issue_nia_failed: {e}"}), 502


# ---------------------- AMM Endpoints ----------------------
def _require_user_and_session():
    uid = session.get("user_id")
    if not uid:
        return None, (jsonify({"error": "unauthorized"}), 401)
    s = get_session()
    user = s.query(User).filter(User.id == uid).one_or_none()
    if not user:
        return None, (jsonify({"error": "unauthorized"}), 401)
    return (uid, s), None


def _amm_effective_reserves(s, pool_id: int):
    pl = s.query(PoolLiquidity).filter(PoolLiquidity.pool_id == pool_id).one_or_none()
    if not pl:
        return None
    R_rgb = float(pl.reserve_rgb or 0) + float(pl.reserve_rgb_virtual or 0)
    R_btc = float(pl.reserve_btc or 0) + float(pl.reserve_btc_virtual or 0)
    return R_rgb, R_btc


@api_bp.get("/amm/quote")
def amm_quote():
    try:
        pool_id = int(request.args.get("pool_id", 0))
        asset_in = (request.args.get("asset_in", "") or "").upper()
        amount_in = float(request.args.get("amount_in", 0) or 0)
    except Exception:
        return jsonify({"error": "invalid_params"}), 400
    if pool_id <= 0 or amount_in <= 0 or asset_in not in {"BTC", "RGB"}:
        return jsonify({"error": "invalid_params"}), 400
    s = get_session()
    pool = s.query(Pool).filter(Pool.id == pool_id, Pool.is_active == True).one_or_none()  # noqa: E712
    if not pool:
        return jsonify({"error": "pool_not_found"}), 404
    reserves = _amm_effective_reserves(s, pool.id)
    if not reserves:
        return jsonify({"error": "no_liquidity"}), 400
    R_rgb, R_btc = reserves
    fee_bps = int(pool.fee_bps or 100)
    total_fee = fee_bps / 10000.0
    if asset_in == "BTC":
        # BTC -> RGB (fee on BTC input)
        R_in, R_out = R_btc, R_rgb
        ain_eff = amount_in * (1.0 - total_fee)
        if R_in <= 0 or R_out <= 0:
            return jsonify({"error": "no_liquidity"}), 400
        amount_out = (ain_eff * R_out) / (R_in + ain_eff)
    else:
        # RGB -> BTC (fee on BTC output)
        R_in, R_out = R_rgb, R_btc
        if R_in <= 0 or R_out <= 0:
            return jsonify({"error": "no_liquidity"}), 400
        out_gross = (amount_in * R_out) / (R_in + amount_in)
        amount_out = out_gross * (1.0 - total_fee)
    return jsonify({"pool_id": pool.id, "asset_in": asset_in, "amount_in": amount_in, "amount_out": amount_out, "fee_bps": fee_bps})


@api_bp.post("/amm/swap/init")
def amm_swap_init():
    ctx, err = _require_user_and_session()
    if err:
        return err
    uid, s = ctx
    body = request.get_json(silent=True) or {}
    try:
        pool_id = int(body.get("pool_id") or 0)
        asset_in = str(body.get("asset_in") or "").upper()
        amount_in = float(body.get("amount_in") or 0)
        min_out = float(body.get("min_out") or 0)
        deadline_ts = int(body.get("deadline_ts") or 0)
    except Exception:
        return jsonify({"error": "invalid_body"}), 400
    if pool_id <= 0 or asset_in not in {"BTC", "RGB"} or amount_in <= 0 or min_out < 0 or deadline_ts <= 0:
        return jsonify({"error": "invalid_params"}), 400
    pool = s.query(Pool).filter(Pool.id == pool_id, Pool.is_active == True).one_or_none()  # noqa: E712
    if not pool:
        return jsonify({"error": "pool_not_found"}), 404
    # Resolve asset ids
    asset_btc_id = int(pool.asset_btc_id)
    asset_rgb_id = int(pool.asset_rgb_id)
    if asset_in == "BTC":
        asset_in_id, asset_out_id = asset_btc_id, asset_rgb_id
    else:
        asset_in_id, asset_out_id = asset_rgb_id, asset_btc_id
    # Create Swap (pending approval)
    import secrets, time as _time
    nonce = secrets.token_hex(16)
    sw = Swap(
        pool_id=pool_id,
        user_id=uid,
        asset_in_id=asset_in_id,
        asset_out_id=asset_out_id,
        amount_in=amount_in,
        min_out=min_out,
        fee_total_bps=pool.fee_bps or 100,
        fee_lp_bps=pool.lp_fee_bps or 50,
        fee_platform_bps=pool.platform_fee_bps or 50,
        status="pending_approval",
        nonce=nonce,
        deadline_ts=deadline_ts,
    )
    s.add(sw)
    s.commit()
    # Payload to sign over Nostr (store JSON in event.content)
    payload = {
        "type": "swap",
        "swap_id": sw.id,
        "pool_id": pool_id,
        "asset_in_id": asset_in_id,
        "asset_out_id": asset_out_id,
        "amount_in": amount_in,
        "min_out": min_out,
        "nonce": nonce,
        "deadline_ts": deadline_ts,
    }
    return jsonify({"ok": True, "swap_id": sw.id, "payload": payload})


@api_bp.post("/amm/swap/confirm")
def amm_swap_confirm():
    # Verify Nostr event signature and execute swap atomically
    ctx, err = _require_user_and_session()
    if err:
        return err
    uid, s = ctx
    body = request.get_json(silent=True) or {}
    ev = body.get("event") or {}
    swap_id = int(body.get("swap_id") or 0)
    if swap_id <= 0:
        return jsonify({"error": "invalid_swap_id"}), 400
    sw = s.query(Swap).filter(Swap.id == swap_id, Swap.user_id == uid).one_or_none()
    if not sw or sw.status != "pending_approval":
        return jsonify({"error": "invalid_state"}), 400
    # Signature verification
    if schnorr_verify is None:
        return jsonify({"error": "server_missing_schnorr"}), 500
    try:
        pubkey = str(ev.get("pubkey"))
        content = str(ev.get("content"))
        sig = str(ev.get("sig"))
        ev_id = str(ev.get("id"))
        if not (len(pubkey) == 64 and len(sig) == 128 and len(ev_id) == 64):
            return jsonify({"error": "invalid_event_fields"}), 400
        calc_id = _nostr_event_id(ev)
        if calc_id != ev_id:
            return jsonify({"error": "invalid_event_id"}), 400
        ok = schnorr_verify(bytes.fromhex(sig), bytes.fromhex(ev_id), bytes.fromhex(pubkey))
        if not ok:
            return jsonify({"error": "invalid_signature"}), 400
        # Content must match the swap
        data = json.loads(content)
        required = ["type","swap_id","pool_id","asset_in_id","asset_out_id","amount_in","min_out","nonce","deadline_ts"]
        if any(k not in data for k in required):
            return jsonify({"error": "invalid_payload"}), 400
        if data["type"] != "swap" or int(data["swap_id"]) != sw.id or data["nonce"] != sw.nonce or int(data["deadline_ts"]) != int(sw.deadline_ts):
            return jsonify({"error": "mismatch"}), 400
        # Deadline
        if int(sw.deadline_ts or 0) < int(datetime.utcnow().timestamp()):
            return jsonify({"error": "expired"}), 400
    except Exception as e:
        return jsonify({"error": f"verify_failed: {e}"}), 400
    # Compute output again and perform the swap
    pool = s.query(Pool).filter(Pool.id == sw.pool_id, Pool.is_active == True).one_or_none()  # noqa: E712
    if not pool:
        return jsonify({"error": "pool_not_found"}), 404
    pl = s.query(PoolLiquidity).filter(PoolLiquidity.pool_id == pool.id).one_or_none()
    if not pl:
        return jsonify({"error": "no_liquidity"}), 400
    R_rgb = float(pl.reserve_rgb or 0) + float(pl.reserve_rgb_virtual or 0)
    R_btc = float(pl.reserve_btc or 0) + float(pl.reserve_btc_virtual or 0)
    fee_bps = int(pool.fee_bps or 100)
    platform_bps = int(pool.platform_fee_bps or 50)
    lp_bps = int(pool.lp_fee_bps or 50)
    total_fee = fee_bps / 10000.0
    amount_in = float(sw.amount_in or 0)
    min_out = float(sw.min_out or 0)
    # Determine direction
    if sw.asset_in_id == pool.asset_btc_id:
        # BTC -> RGB: fee on BTC input
        R_in, R_out = R_btc, R_rgb
        if R_in <= 0 or R_out <= 0:
            return jsonify({"error": "no_liquidity"}), 400
        ain_eff = amount_in * (1.0 - total_fee)
        amount_out = (ain_eff * R_out) / (R_in + ain_eff)
        if amount_out < min_out:
            return jsonify({"error": "slippage"}), 400
        platform_fee = amount_in * (platform_bps / 10000.0)
        lp_fee = amount_in * (lp_bps / 10000.0)
        # Update balances and reserves
        def get_balance(user_id: int, asset_id: int):
            ub = s.query(UserBalance).filter(UserBalance.user_id == user_id, UserBalance.asset_id == asset_id).one_or_none()
            if not ub:
                ub = UserBalance(user_id=user_id, asset_id=asset_id, balance=0, available=0)
                s.add(ub)
                s.flush()
            return ub
        bal_in = get_balance(uid, sw.asset_in_id)
        bal_out = get_balance(uid, sw.asset_out_id)
        if float(bal_in.available or 0) < amount_in:
            return jsonify({"error": "insufficient_funds"}), 400
        from decimal import Decimal as D
        # User debits BTC, credits RGB
        bal_in.available = (bal_in.available or 0) - D(str(amount_in))
        bal_in.balance = (bal_in.balance or 0) - D(str(amount_in))
        bal_out.available = (bal_out.available or 0) + D(str(amount_out))
        bal_out.balance = (bal_out.balance or 0) + D(str(amount_out))
        # Platform BTC credit
        platform_user_id = int(os.environ.get("PLATFORM_USER_ID", "0") or 0)
        if platform_user_id > 0 and platform_fee > 0:
            pbal = get_balance(platform_user_id, sw.asset_in_id)
            pbal.available = (pbal.available or 0) + D(str(platform_fee))
            pbal.balance = (pbal.balance or 0) + D(str(platform_fee))
        # Reserves: add (amount_in - platform_fee) to BTC (LP fee remains in pool); subtract RGB amount_out
        pl.reserve_btc = D(str(float(pl.reserve_btc or 0) + (amount_in - platform_fee)))
        pl.reserve_rgb = D(str(max(0.0, float(pl.reserve_rgb or 0) - amount_out)))
    else:
        # RGB -> BTC: fee on BTC output
        R_in, R_out = R_rgb, R_btc
        if R_in <= 0 or R_out <= 0:
            return jsonify({"error": "no_liquidity"}), 400
        out_gross = (amount_in * R_out) / (R_in + amount_in)
        platform_fee = out_gross * (platform_bps / 10000.0)
        lp_fee = out_gross * (lp_bps / 10000.0)
        amount_out = out_gross - (platform_fee + lp_fee)
        if amount_out < min_out:
            return jsonify({"error": "slippage"}), 400
        # Update balances and reserves
        def get_balance(user_id: int, asset_id: int):
            ub = s.query(UserBalance).filter(UserBalance.user_id == user_id, UserBalance.asset_id == asset_id).one_or_none()
            if not ub:
                ub = UserBalance(user_id=user_id, asset_id=asset_id, balance=0, available=0)
                s.add(ub)
                s.flush()
            return ub
        bal_in = get_balance(uid, sw.asset_in_id)
        bal_out = get_balance(uid, sw.asset_out_id)
        if float(bal_in.available or 0) < amount_in:
            return jsonify({"error": "insufficient_funds"}), 400
        from decimal import Decimal as D
        # User debits RGB, credits BTC (net after fee)
        bal_in.available = (bal_in.available or 0) - D(str(amount_in))
        bal_in.balance = (bal_in.balance or 0) - D(str(amount_in))
        bal_out.available = (bal_out.available or 0) + D(str(amount_out))
        bal_out.balance = (bal_out.balance or 0) + D(str(amount_out))
        # Platform BTC credit (fee on output)
        platform_user_id = int(os.environ.get("PLATFORM_USER_ID", "0") or 0)
        if platform_user_id > 0 and platform_fee > 0:
            pbal = get_balance(platform_user_id, sw.asset_out_id)
            pbal.available = (pbal.available or 0) + D(str(platform_fee))
            pbal.balance = (pbal.balance or 0) + D(str(platform_fee))
        # Reserves: add RGB amount_in; subtract BTC (amount_out + platform_fee) so LP fee remains in pool
        pl.reserve_rgb = D(str(float(pl.reserve_rgb or 0) + amount_in))
        pl.reserve_btc = D(str(max(0.0, float(pl.reserve_btc or 0) - (amount_out + platform_fee))))
    def get_balance(user_id: int, asset_id: int):
        ub = s.query(UserBalance).filter(UserBalance.user_id == user_id, UserBalance.asset_id == asset_id).one_or_none()
        if not ub:
            ub = UserBalance(user_id=user_id, asset_id=asset_id, balance=0, available=0)
            s.add(ub)
            s.flush()
        return ub
    bal_in = get_balance(uid, sw.asset_in_id)
    bal_out = get_balance(uid, sw.asset_out_id)
    if float(bal_in.available or 0) < amount_in:
        return jsonify({"error": "insufficient_funds"}), 400
    # Platform fee credit
    platform_fee = amount_in * (platform_bps / 10000.0)
    platform_user_id = int(os.environ.get("PLATFORM_USER_ID", "0") or 0)
    # Update balances and reserves atomically
    from decimal import Decimal as D
    bal_in.available = (bal_in.available or 0) - D(str(amount_in))
    bal_in.balance = (bal_in.balance or 0) - D(str(amount_in))
    bal_out.available = (bal_out.available or 0) + D(str(amount_out))
    bal_out.balance = (bal_out.balance or 0) + D(str(amount_out))
    if platform_user_id > 0 and platform_fee > 0:
        pbal = get_balance(platform_user_id, sw.asset_in_id)
        pbal.available = (pbal.available or 0) + D(str(platform_fee))
        pbal.balance = (pbal.balance or 0) + D(str(platform_fee))
    # Update pool reserves: add gross input to R_in; subtract output from R_out.
    if sw.asset_in_id == pool.asset_btc_id:
        pl.reserve_btc = D(str(float(pl.reserve_btc or 0) + amount_in))
        pl.reserve_rgb = D(str(max(0.0, float(pl.reserve_rgb or 0) - amount_out)))
    else:
        pl.reserve_rgb = D(str(float(pl.reserve_rgb or 0) + amount_in))
        pl.reserve_btc = D(str(max(0.0, float(pl.reserve_btc or 0) - amount_out)))
    pl.updated_at = datetime.utcnow()
    # Mark swap and record approval
    sw.amount_out = amount_out
    sw.status = "executed"
    sw.executed_at = datetime.utcnow()
    appr = Approval(swap_id=sw.id, nostr_pubkey=ev.get("pubkey"), event_id=ev.get("id"), sig=ev.get("sig"), approved=True)
    s.add(appr)
    # Ledger entries
    s.add_all([
        LedgerEntry(user_id=uid, asset_id=sw.asset_in_id, delta=D(str(-amount_in)), ref_type="swap", ref_id=sw.id),
        LedgerEntry(user_id=uid, asset_id=sw.asset_out_id, delta=D(str(amount_out)), ref_type="swap", ref_id=sw.id),
    ])
    if platform_user_id > 0 and platform_fee > 0:
        # Platform fee asset depends on direction: BTC asset id is sw.asset_in_id for BTC->RGB, or sw.asset_out_id for RGB->BTC
        fee_asset_id = sw.asset_in_id if sw.asset_in_id == pool.asset_btc_id else sw.asset_out_id
        s.add(LedgerEntry(user_id=platform_user_id, asset_id=fee_asset_id, delta=D(str(platform_fee)), ref_type="fee", ref_id=sw.id))
    s.commit()
    return jsonify({"ok": True, "swap_id": sw.id, "amount_out": amount_out})


@api_bp.post("/launchpad/issue_nia_and_pool")
def launchpad_issue_and_pool():
    # Issue RGB asset via RLN and create a vAMM pool with virtual reserves
    ctx, err = _require_user_and_session()
    if err:
        return err
    uid, s = ctx
    body = request.get_json(silent=True) or {}
    ticker = str(body.get("ticker") or "").upper().strip()
    name = str(body.get("name") or "").strip()
    amounts = body.get("amounts") or [1]
    precision = int(body.get("precision") or 0)
    initial_price = float(body.get("initial_price") or 0)
    virtual_depth_btc = float(body.get("virtual_depth_btc") or 0)
    if not ticker or not name or initial_price <= 0 or virtual_depth_btc <= 0:
        return jsonify({"error": "invalid_params"}), 400
    # Issue via RLN
    cli = RLNClient()
    try:
        res = cli.issueasset_nia(ticker=ticker, name=name, amounts=[int(x) for x in amounts], precision=precision)
        asset_id = res.get("asset_id") or res.get("asset") or None
        if not asset_id:
            return jsonify({"error": "rln_issue_failed", "detail": res}), 502
    except Exception as e:
        return jsonify({"error": f"rln_issue_failed: {e}"}), 502
    # Ensure BTC asset exists
    btc = s.query(Asset).filter(Asset.symbol == "BTC").one_or_none()
    if not btc:
        btc = Asset(symbol="BTC", name="Bitcoin", precision=8, rln_asset_id=None)
        s.add(btc)
        s.flush()
    # Create RGB asset (track creator)
    rgb = s.query(Asset).filter(Asset.symbol == ticker).one_or_none()
    if not rgb:
        rgb = Asset(symbol=ticker, name=name, precision=precision, rln_asset_id=asset_id, created_by_user_id=uid)
        s.add(rgb)
        s.flush()
    # Create pool and virtual reserves
    pool = Pool(asset_rgb_id=rgb.id, asset_btc_id=btc.id, fee_bps=100, lp_fee_bps=50, platform_fee_bps=50, is_vamm=True, is_active=True)
    s.add(pool)
    s.flush()
    reserve_btc_virtual = virtual_depth_btc
    reserve_rgb_virtual = virtual_depth_btc / initial_price
    pl = PoolLiquidity(pool_id=pool.id, reserve_rgb=0, reserve_btc=0, reserve_rgb_virtual=reserve_rgb_virtual, reserve_btc_virtual=reserve_btc_virtual)
    s.add(pl)
    s.commit()
    return jsonify({"ok": True, "asset": {"id": rgb.id, "symbol": rgb.symbol, "rln_asset_id": rgb.rln_asset_id}, "pool_id": pool.id, "virtual": {"btc": reserve_btc_virtual, "rgb": reserve_rgb_virtual}})


# ---------------------- Admin Endpoints ----------------------
def _is_admin(s, user_id: int) -> bool:
    admin_uid = int(os.environ.get("ADMIN_USER_ID", "0") or 0)
    if admin_uid and user_id == admin_uid:
        return True
    admin_npub = os.environ.get("ADMIN_NPUB")
    if admin_npub:
        u = s.query(User).filter(User.id == user_id).one_or_none()
        return bool(u and (u.npub or '').lower() == admin_npub.lower())
    return False


@api_bp.get("/admin/users")
def admin_users():
    ctx, err = _require_user_and_session()
    if err:
        return err
    uid, s = ctx
    if not _is_admin(s, uid):
        return jsonify({"error": "forbidden"}), 403
    rows = s.query(User).order_by(User.id.asc()).all()
    out = [{"id": u.id, "npub": u.npub, "display_name": u.display_name, "avatar_url": u.avatar_url} for u in rows]
    return jsonify(out)


@api_bp.get("/admin/assets")
def admin_assets():
    ctx, err = _require_user_and_session()
    if err:
        return err
    uid, s = ctx
    if not _is_admin(s, uid):
        return jsonify({"error": "forbidden"}), 403
    rows = s.query(Asset).order_by(Asset.id.asc()).all()
    creator_ids = [a.created_by_user_id for a in rows if a.created_by_user_id]
    creators = {}
    if creator_ids:
        for u in s.query(User).filter(User.id.in_(creator_ids)).all():
            creators[u.id] = {"id": u.id, "display_name": u.display_name, "npub": u.npub}
    out = []
    for a in rows:
        creator = creators.get(a.created_by_user_id) if a.created_by_user_id else None
        out.append({
            "id": a.id,
            "symbol": a.symbol,
            "name": a.name,
            "precision": a.precision,
            "rln_asset_id": a.rln_asset_id,
            "created_by_user_id": a.created_by_user_id,
            "creator": creator,
        })
    return jsonify(out)


@api_bp.get("/admin/pools")
def admin_pools():
    ctx, err = _require_user_and_session()
    if err:
        return err
    uid, s = ctx
    if not _is_admin(s, uid):
        return jsonify({"error": "forbidden"}), 403
    pools = s.query(Pool).order_by(Pool.id.asc()).all()
    asset_ids = set()
    for p in pools:
        asset_ids.add(p.asset_rgb_id)
        asset_ids.add(p.asset_btc_id)
    assets_map = {}
    if asset_ids:
        for a in s.query(Asset).filter(Asset.id.in_(list(asset_ids))).all():
            assets_map[a.id] = a.symbol
    out = []
    for p in pools:
        pl = s.query(PoolLiquidity).filter(PoolLiquidity.pool_id == p.id).one_or_none()
        R_rgb = float((pl.reserve_rgb if pl else 0) or 0) + float((pl.reserve_rgb_virtual if pl else 0) or 0)
        R_btc = float((pl.reserve_btc if pl else 0) or 0) + float((pl.reserve_btc_virtual if pl else 0) or 0)
        out.append({
            "id": p.id,
            "asset_rgb_id": p.asset_rgb_id,
            "asset_btc_id": p.asset_btc_id,
            "asset_rgb_symbol": assets_map.get(p.asset_rgb_id),
            "asset_btc_symbol": assets_map.get(p.asset_btc_id),
            "fee_bps": p.fee_bps,
            "lp_fee_bps": p.lp_fee_bps,
            "platform_fee_bps": p.platform_fee_bps,
            "is_vamm": p.is_vamm,
            "is_active": p.is_active,
            "reserves": {"rgb": R_rgb, "btc": R_btc},
        })
    return jsonify(out)


@api_bp.get("/admin/deposits")
def admin_deposits():
    ctx, err = _require_user_and_session()
    if err:
        return err
    uid, s = ctx
    if not _is_admin(s, uid):
        return jsonify({"error": "forbidden"}), 403
    rows = s.query(Deposit).order_by(Deposit.id.desc()).limit(500).all()
    user_ids = {d.user_id for d in rows}
    asset_ids = {d.asset_id for d in rows}
    users = {}
    assets = {}
    if user_ids:
        for u in s.query(User).filter(User.id.in_(list(user_ids))).all():
            users[u.id] = {"display_name": u.display_name, "npub": u.npub}
    if asset_ids:
        for a in s.query(Asset).filter(Asset.id.in_(list(asset_ids))).all():
            assets[a.id] = a.symbol
    out = []
    for d in rows:
        out.append({
            "id": d.id,
            "user_id": d.user_id,
            "user_display_name": users.get(d.user_id, {}).get("display_name"),
            "user_npub": users.get(d.user_id, {}).get("npub"),
            "asset_id": d.asset_id,
            "asset_symbol": assets.get(d.asset_id),
            "amount": float(d.amount or 0),
            "status": d.status,
            "external_ref": d.external_ref,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })
    return jsonify(out)


@api_bp.get("/admin/withdrawals")
def admin_withdrawals():
    ctx, err = _require_user_and_session()
    if err:
        return err
    uid, s = ctx
    if not _is_admin(s, uid):
        return jsonify({"error": "forbidden"}), 403
    rows = s.query(Withdrawal).order_by(Withdrawal.id.desc()).limit(500).all()
    user_ids = {w.user_id for w in rows}
    asset_ids = {w.asset_id for w in rows}
    users = {}
    assets = {}
    if user_ids:
        for u in s.query(User).filter(User.id.in_(list(user_ids))).all():
            users[u.id] = {"display_name": u.display_name, "npub": u.npub}
    if asset_ids:
        for a in s.query(Asset).filter(Asset.id.in_(list(asset_ids))).all():
            assets[a.id] = a.symbol
    out = []
    for w in rows:
        out.append({
            "id": w.id,
            "user_id": w.user_id,
            "user_display_name": users.get(w.user_id, {}).get("display_name"),
            "user_npub": users.get(w.user_id, {}).get("npub"),
            "asset_id": w.asset_id,
            "asset_symbol": assets.get(w.asset_id),
            "amount": float(w.amount or 0),
            "status": w.status,
            "external_ref": w.external_ref,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        })
    return jsonify(out)
