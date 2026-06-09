#!/usr/bin/env python3
"""SuperClaw market pulse — structured signals for the 6 tracked assets.

Pulls live price, 24h change, funding, and open interest from Hyperliquid
(no API key) and prints a compact per-asset block. The SuperClaw agent then
writes a short, DESCRIPTIVE trader TLDR from these real numbers — it must not
invent prices or give buy/sell calls.

Assets: BTC, ETH, SOL, BNB, HYPE (main perp book) + GOLD (xyz:GOLD builder dex).
SOL shows in the pulse but has no perps skill yet ("perps coming soon").

Usage:  python3 market_update.py
"""

from __future__ import annotations

import json
import sys
import urllib.request

HL = "https://api.hyperliquid.xyz/info"
MAIN_ASSETS = ["BTC", "ETH", "SOL", "BNB", "HYPE"]
DEX_ASSETS = {"GOLD": ("xyz", "xyz:GOLD")}  # display -> (dex, coin)
NO_PERPS = {"SOL"}  # in pulse, not in the perps menu


def _post(body: dict) -> list:
    req = urllib.request.Request(
        HL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _ctx_map(dex: str | None = None) -> dict:
    body = {"type": "metaAndAssetCtxs"}
    if dex:
        body["dex"] = dex
    meta, ctxs = _post(body)
    out = {}
    for u, c in zip(meta.get("universe", []), ctxs):
        out[u.get("name")] = c
    return out


def _fmt_price(p: float) -> str:
    if p >= 100:
        return f"{p:,.0f}"
    if p >= 1:
        return f"{p:,.2f}"
    return f"{p:.4f}"


def _row(label: str, ctx: dict) -> str:
    try:
        mark = float(ctx.get("markPx"))
        prev = float(ctx.get("prevDayPx"))
        chg = (mark - prev) / prev * 100 if prev else 0.0
        funding_hr = float(ctx.get("funding", 0))
        funding_apr = funding_hr * 24 * 365 * 100
        oi_coins = float(ctx.get("openInterest", 0))
        oi_usd = oi_coins * mark
        arrow = "▲" if chg >= 0 else "▼"
        tag = "  (perps coming soon)" if label in NO_PERPS else ""
        return (
            f"{label:<5} ${_fmt_price(mark)}  {arrow}{chg:+.2f}% 24h  "
            f"| funding {funding_apr:+.1f}%/yr  | OI ${oi_usd/1e6:,.1f}M{tag}"
        )
    except Exception as e:  # noqa: BLE001
        return f"{label:<5} (data unavailable: {e})"



CMC = "https://pro-api.coinmarketcap.com/trial-pro-api"  # keyless public base (rate-limited)


def _cmc_get(path: str) -> dict:
    req = urllib.request.Request(
        CMC + path, headers={"Accept": "application/json", "User-Agent": "superclaw"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def market_wide() -> list:
    """Keyless CoinMarketCap market-wide regime signals. Each metric is best-effort;
    any that fails is silently skipped so the pulse still prints."""
    out = []
    # Fear & Greed
    try:
        d = _cmc_get("/v3/fear-and-greed/latest").get("data", {})
        val = d.get("value")
        cls = d.get("value_classification", "")
        if val is not None:
            out.append(f"  Fear & Greed     : {val}/100  {cls}")
    except Exception:
        pass
    # Altcoin Season Index
    try:
        d = _cmc_get("/v3/altcoin-season/latest").get("data", {})
        sidx = d.get("altcoin_index") or d.get("value")
        if sidx is not None:
            regime = "Altcoin Season" if float(sidx) >= 75 else ("Bitcoin Season" if float(sidx) <= 25 else "Neutral")
            out.append(f"  Altcoin Season   : {sidx}/100  {regime}")
    except Exception:
        pass
    # Global metrics: total mcap, dominance
    try:
        d = _cmc_get("/v1/global-metrics/quotes/latest").get("data", {})
        btc_dom = d.get("btc_dominance")
        eth_dom = d.get("eth_dominance")
        mcap = d.get("total_market_cap")
        if mcap is None:
            mcap = (d.get("quote", {}).get("USD", {}) or {}).get("total_market_cap")
        if mcap:
            out.append(f"  Total mkt cap    : ${float(mcap)/1e12:,.2f}T")
        if btc_dom is not None and eth_dom is not None:
            out.append(f"  Dominance        : BTC {float(btc_dom):.1f}%  ETH {float(eth_dom):.1f}%")
    except Exception:
        pass
    return out


def main() -> None:
    try:
        main_ctx = _ctx_map()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: could not fetch Hyperliquid market data: {e}", file=sys.stderr)
        sys.exit(1)

    lines = ["SUPERCLAW MARKET PULSE (live, Hyperliquid)", ""]
    for a in MAIN_ASSETS:
        ctx = main_ctx.get(a)
        lines.append(_row(a, ctx) if ctx else f"{a:<5} (not found)")

    for label, (dex, coin) in DEX_ASSETS.items():
        try:
            dctx = _ctx_map(dex).get(coin)
            lines.append(_row(label, dctx) if dctx else f"{label:<5} (not found)")
        except Exception as e:  # noqa: BLE001
            lines.append(f"{label:<5} (data unavailable: {e})")

    mw = market_wide()
    if mw:
        lines += ["", "— Market-wide (CoinMarketCap) —"] + mw

    lines += [
        "",
        "[AGENT INSTRUCTIONS — do not print this line to the user]",
        "Write a 3-5 sentence trader-style TLDR using ONLY the numbers above: "
        "lead with the overall risk tone (use Fear & Greed + Altcoin Season + dominance "
        "for the regime read), call out the biggest movers and any notable funding/OI "
        "(crowded longs/shorts), and keep it DESCRIPTIVE — no buy/sell calls, no price "
        "predictions. Then ask the user: trade memes or perps?",
    ]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
