"""Optional read-only quotes from one fixed provider host; never send exchange secrets."""

import os
import time
from decimal import Decimal, InvalidOperation
import httpx
from fastapi import HTTPException


def quotes(asset_ids):
    key = os.getenv("COINGECKO_DEMO_API_KEY")
    if not key:
        raise HTTPException(
            503, "Set COINGECKO_DEMO_API_KEY to enable optional current quotes. CSV analytics works without it."
        )
    try:
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            r = client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": ",".join(asset_ids), "vs_currencies": "usd", "include_last_updated_at": "true"},
                headers={"x-cg-demo-api-key": key},
            )
            if r.status_code == 429:
                raise HTTPException(503, "Market provider rate limit reached; retry later.")
            r.raise_for_status()
            body = r.json()
        result = []
        now = int(time.time())
        for aid in asset_ids:
            item = body.get(aid, {})
            p = Decimal(str(item.get("usd", "NaN")))
            stamp = item.get("last_updated_at")
            if (
                not p.is_finite()
                or p <= 0
                or not isinstance(stamp, int)
                or isinstance(stamp, bool)
                or stamp <= 0
                or stamp > now + 60
            ):
                raise ValueError("Invalid quote")
            result.append(
                dict(
                    asset_id=aid,
                    currency="USD",
                    price=format(p, "f"),
                    last_updated_at=stamp,
                    age_seconds=max(0, now - stamp),
                    stale=now - stamp > 300,
                )
            )
        return dict(
            provider="CoinGecko Demo",
            quotes=result,
            note="Current quotes are not historical daily closes and are never silently inserted into an analysis.",
        )
    except (httpx.HTTPError, ValueError, TypeError, InvalidOperation):
        raise HTTPException(502, "Market provider returned unavailable or incomplete quotes.") from None
