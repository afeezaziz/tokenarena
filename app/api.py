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

from .models import GlobalMetrics, Token, TokenSnapshot, User, UserHolding, Competition, CompetitionEntry, AuthChallenge, get_session
from .utils.nostr import hex_to_npub, npub_to_hex
from .limiter import limiter

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
