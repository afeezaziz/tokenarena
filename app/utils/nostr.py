from __future__ import annotations

from typing import Optional

try:
    from bech32 import bech32_encode, bech32_decode, convertbits  # type: ignore
except Exception:  # pragma: no cover
    bech32_encode = bech32_decode = convertbits = None  # type: ignore


def hex_to_npub(hex_pubkey: str) -> Optional[str]:
    """Encode 32-byte hex pubkey to NIP-19 npub bech32 string.
    Returns None if bech32 library is unavailable or input is invalid.
    """
    if bech32_encode is None or convertbits is None:
        return None
    try:
        raw = bytes.fromhex(hex_pubkey)
        data5 = convertbits(raw, 8, 5, True)
        if data5 is None:
            return None
        return bech32_encode("npub", data5)
    except Exception:
        return None


def npub_to_hex(npub: str) -> Optional[str]:
    """Decode NIP-19 npub bech32 to 32-byte hex pubkey.
    Returns None if invalid or bech32 lib unavailable.
    """
    if bech32_decode is None or convertbits is None:
        return None
    try:
        hrp, data = bech32_decode(npub)
        if hrp != "npub" or data is None:
            return None
        raw = convertbits(data, 5, 8, False)
        if raw is None:
            return None
        return bytes(raw).hex()
    except Exception:
        return None
