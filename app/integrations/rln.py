from __future__ import annotations

import os
import json
from typing import Any, Dict, Optional

import requests


class RLNClient:
    """Minimal REST client for RGB Lightning Node (RLN).

    Config via env:
      - RLN_BASE_URL (e.g., http://localhost:3001)
      - RLN_BEARER (optional; sends Authorization: Bearer <token>)
      - RLN_BASIC_USER / RLN_BASIC_PASS (optional; HTTP Basic)
      - RLN_TIMEOUT_SECONDS (optional; default 20)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        bearer: Optional[str] = None,
        basic_user: Optional[str] = None,
        basic_pass: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("RLN_BASE_URL") or "http://localhost:3001").rstrip("/")
        self.bearer = bearer or os.environ.get("RLN_BEARER")
        self.basic_user = basic_user or os.environ.get("RLN_BASIC_USER")
        self.basic_pass = basic_pass or os.environ.get("RLN_BASIC_PASS")
        self.timeout = int(timeout or int(os.environ.get("RLN_TIMEOUT_SECONDS", "20") or 20))

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.bearer:
            h["Authorization"] = f"Bearer {self.bearer}"
        return h

    def _auth(self):
        if self.basic_user and self.basic_pass:
            return (self.basic_user, self.basic_pass)
        return None

    def get(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        r = requests.get(url, headers=self._headers(), auth=self._auth(), timeout=self.timeout)
        r.raise_for_status()
        return r.json() if r.content else None

    def post(self, path: str, payload: Dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload or {})
        r = requests.post(url, headers=self._headers(), auth=self._auth(), data=data, timeout=self.timeout)
        r.raise_for_status()
        return r.json() if r.content else None

    # Convenience wrappers for common endpoints
    def nodeinfo(self) -> Any:
        return self.get("/nodeinfo")

    def btcbalance(self) -> Any:
        return self.post("/btcbalance")

    def listassets(self) -> Any:
        return self.post("/listassets")

    def assetbalance(self, asset_id: str) -> Any:
        return self.post("/assetbalance", {"asset_id": asset_id})

    def lninvoice(self, amount_msat: int, memo: str | None = None) -> Any:
        payload = {"amount_msat": amount_msat}
        if memo: payload["description"] = memo
        return self.post("/lninvoice", payload)

    def rgbinvoice(self, asset_id: str, amount: int, transport_endpoints: list[str] | None = None) -> Any:
        payload = {"asset_id": asset_id, "amount": amount}
        if transport_endpoints: payload["transport_endpoints"] = transport_endpoints
        return self.post("/rgbinvoice", payload)

    def sendbtc(self, invoice: str) -> Any:
        return self.post("/sendpayment", {"invoice": invoice})

    def sendasset(self, invoice: str) -> Any:
        return self.post("/sendasset", {"invoice": invoice})

    def issueasset_nia(self, ticker: str, name: str, amounts: list[int], precision: int = 0) -> Any:
        payload = {
            "ticker": ticker,
            "name": name,
            "amounts": amounts,
            "precision": precision,
        }
        return self.post("/issueassetnia", payload)
