import os
import json
import time
import uuid
import logging
from datetime import datetime, timedelta

try:
    from websocket import create_connection  # type: ignore
except Exception:  # pragma: no cover
    create_connection = None  # type: ignore


logger = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))


# Placeholder for queued tasks
# Example task signature for RQ: enqueue('app.tasks.ping', args=("hello",))

def ping(message: str = "pong") -> str:
    return f"[{datetime.utcnow().isoformat()}Z] {message}"


def nostr_poll(
    relay_url: str | None = None,
    filters: dict | None = None,
    duration_seconds: int | None = None,
    max_events: int | None = None,
) -> dict:
    """
    Connect to a Nostr relay, subscribe to events per NIP-01, collect a small batch,
    log them and return a summary. Intended to be run periodically as a scheduled RQ job.

    Env fallbacks:
      - NOSTR_RELAY_URL (default: wss://relay.damus.io)
      - NOSTR_FILTERS (JSON string)
      - NOSTR_POLL_SECONDS (default: 8)
      - NOSTR_MAX_EVENTS (default: 25)
    """
    relay = relay_url or os.environ.get("NOSTR_RELAY_URL", "wss://relay.damus.io")
    try:
        filters_obj = filters if filters is not None else json.loads(os.environ.get("NOSTR_FILTERS", "{}") or "{}")
    except Exception:
        filters_obj = {}
    if not isinstance(filters_obj, dict) or not filters_obj:
        # Default: text notes (kind=1), recent 20
        filters_obj = {"kinds": [1], "limit": 20}

    dur = int(duration_seconds or int(os.environ.get("NOSTR_POLL_SECONDS", "8") or 8))
    cap = int(max_events or int(os.environ.get("NOSTR_MAX_EVENTS", "25") or 25))

    if create_connection is None:
        logger.warning("nostr_poll: websocket-client not installed; skipping")
        return {"ok": False, "error": "websocket_missing"}

    subid = f"tb-{uuid.uuid4().hex[:8]}"
    start = datetime.utcnow()
    deadline = start + timedelta(seconds=dur)
    count = 0
    events = []

    try:
        ws = create_connection(relay, timeout=dur + 2)
        # Send subscription request per NIP-01: ["REQ", <subid>, {filters}]
        req = ["REQ", subid, filters_obj]
        ws.send(json.dumps(req, ensure_ascii=False))
        logger.info("nostr_poll: subscribed %s to %s with filters=%s", subid, relay, json.dumps(filters_obj))
        # Read until deadline or cap reached
        while datetime.utcnow() < deadline and count < cap:
            try:
                msg = ws.recv()
            except Exception:
                break
            if not msg:
                break
            try:
                data = json.loads(msg)
            except Exception:
                logger.debug("nostr_poll: non-json message: %s", msg)
                continue
            # Messages can be: ["EVENT", subid, event], ["EOSE", subid], ["NOTICE", <msg>]
            if isinstance(data, list) and data:
                kind = data[0]
                if kind == "EVENT" and len(data) >= 3:
                    ev = data[2]
                    count += 1
                    events.append(ev)
                    logger.info("nostr_poll: EVENT %s %s %s", ev.get("kind"), ev.get("pubkey"), (ev.get("content", "")[:80] + ("…" if len(ev.get("content", "")) > 80 else "")))
                elif kind == "EOSE":
                    logger.info("nostr_poll: EOSE for %s", subid)
                    break
                elif kind == "NOTICE":
                    logger.warning("nostr_poll: NOTICE %s", data[1:] if len(data) > 1 else "")
            # slight pacing to avoid hot loop
            time.sleep(0.01)
        # Close subscription
        try:
            ws.send(json.dumps(["CLOSE", subid]))
        except Exception:
            pass
        ws.close()
        elapsed = (datetime.utcnow() - start).total_seconds()
        return {"ok": True, "relay": relay, "count": count, "elapsed": elapsed}
    except Exception as e:
        logger.exception("nostr_poll: failure: %s", e)
        return {"ok": False, "error": str(e)}


# ---------------------- Funds reconciliation (stubs) ----------------------
def reconcile_funds() -> dict:
    """
    Analyze pending deposits/withdrawals and return a summary.
    This is a stub: integrate with RLN to verify invoices/tx states and
    call into admin settle/mark_sent endpoints or DB functions accordingly.
    """
    try:
        # Lazy import to avoid heavy dependencies when not needed
        from .models import get_session, Deposit, Withdrawal
    except Exception as e:
        logger.exception("reconcile_funds: import failed: %s", e)
        return {"ok": False, "error": str(e)}

    s = get_session()
    pending_deps = s.query(Deposit).filter(Deposit.status == "pending").count()
    pending_withs = s.query(Withdrawal).filter(Withdrawal.status == "pending").count()
    logger.info("reconcile_funds: pending deposits=%s, withdrawals=%s", pending_deps, pending_withs)
    return {"ok": True, "pending_deposits": int(pending_deps), "pending_withdrawals": int(pending_withs)}
