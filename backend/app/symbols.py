from __future__ import annotations


KNOWN_QUOTES = ("DUSDT", "DUSDC", "USDT", "USDC", "USD", "EUR", "BTC")


def canonical_symbol(symbol: str) -> str:
    """Return the cross-venue base asset while preserving venue symbols separately."""

    value = "".join(character for character in str(symbol).upper() if character.isalnum())
    if value.startswith("D") and value[1:].startswith(("BTC", "ETH", "SOL", "HYPE")):
        value = value[1:]
    for quote in KNOWN_QUOTES:
        if value.endswith(quote) and len(value) > len(quote):
            value = value[: -len(quote)]
            break
    return "BTC" if value == "XBT" else value
