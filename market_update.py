#!/usr/bin/env python3
"""SuperClaw market desk — keyless data + Kronos forecasts, compact mobile dashboard.

ASSETS OVERVIEW lines carry a Kronos-derived probability ("X% odds going up to the
next round level in next Nh"), served by the Kronos sidecar at $KRONOS_URL. All other
data is keyless: Hyperliquid (spot), CoinMarketCap trial-pro-api (regime), DefiLlama
(stables), RSS (headlines). The agent tags headlines, writes the verdict from the
hidden context block, and renders the perps-only menu.

Usage:
    python3 market_update.py                 # the dashboard
    python3 market_update.py analytics BTC   # one asset's Kronos read (for per-asset analytics)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HL = "https://api.hyperliquid.xyz/info"
CMC = "https://pro-api.coinmarketcap.com/trial-pro-api"
LLAMA = "https://stablecoins.llama.fi/stablecoins?includePrices=true"
KRONOS_URL = os.environ.get("KRONOS_URL", "https://superclaw-kronos-sidecar.onrender.com").rstrip("/")

# Display order = analytics menu order: 1)BTC 2)ETH 3)BNB 4)HYPE 5)SOL 6)GOLD
ASSET_ORDER = ["BTC", "ETH", "BNB", "HYPE", "SOL", "GOLD"]
DEX_ASSETS = {"GOLD": ("xyz", "xyz:GOLD")}
NO_PERPS = {"SOL"}


def _post(body: dict) -> list:
    req = urllib.request.Request(HL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _get(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "superclaw"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _cmc(path: str) -> dict:
    return json.loads(_get(CMC + path).decode())


def _ctxs(dex: str | None = None):
    body = {"type": "metaAndAssetCtxs"}
    if dex:
        body["dex"] = dex
    meta, ctxs = _post(body)
    return meta.get("universe", []), ctxs


def _price(p: float) -> str:
    if p >= 100:
        return f"${p:,.0f}"
    if p >= 1:
        return f"${p:,.2f}"
    return f"${p:.4f}"


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None


# ---- Kronos forecasts ---------------------------------------------------
def _kronos() -> dict:
    """Fetch cached per-asset forecasts from the sidecar. {} if unavailable.
    Retries once in case the service is briefly slow or just-redeployed."""
    if not KRONOS_URL:
        return {}
    for _ in range(2):
        try:
            data = json.loads(_get(KRONOS_URL + "/forecast", timeout=12).decode())
            assets = {a["asset"]: a for a in data.get("assets", []) if a.get("asset")}
            if assets:
                return assets
        except Exception:
            pass
        time.sleep(1.5)
    return {}


def _spot_map() -> dict:
    """Live spot per asset from Hyperliquid (main book + xyz dex for GOLD)."""
    out = {}
    try:
        uni, ctxs = _ctxs()
        cmap = {u.get("name"): c for u, c in zip(uni, ctxs)}
        for a in ASSET_ORDER:
            if a in cmap:
                out[a] = float(cmap[a]["markPx"])
    except Exception:
        pass
    for label, (dex, coin) in DEX_ASSETS.items():
        d = _safe(_ctxs, dex)
        if d:
            dm = {u.get("name"): c for u, c in zip(d[0], d[1])}
            if coin in dm:
                out[label] = float(dm[coin]["markPx"])
    return out


_SPARK = "▁▂▃▄▅▆▇█"


def _sparkline(path) -> str:
    if not path or len(path) < 2:
        return ""
    lo, hi = min(path), max(path)
    if hi == lo:
        return _SPARK[3] * len(path)
    return "".join(_SPARK[min(7, int((v - lo) / (hi - lo) * 7.999))] for v in path)


def _lean(k: dict | None):
    """Directional conviction from prob_up: dot + label."""
    up = (k or {}).get("prob_up_pct")
    if up is None:
        return "⚪", "Neutral"
    if up >= 60:
        return "🟢", "Bullish"
    if up <= 40:
        return "🔴", "Bearish"
    return "🟡", "Neutral"


def _asset_line(label: str, spot: float | None, k: dict | None) -> str:
    soon = "  (perps soon)" if label in NO_PERPS else ""
    if spot is None and k and k.get("spot"):
        spot = float(k["spot"])
    if spot is None:
        return f"**{label}:** n/a{soon}"
    if k and k.get("prob_long") is not None and k.get("target"):
        dot, _ = _lean(k)
        arrow = "↑" if k.get("direction") == "up" else "↓"
        hl, hs = k.get("horizon_long", 24), k.get("horizon_short", 4)
        return (f"**{label}:** {_price(spot)} · {dot} {int(k['prob_long'])}% {arrow} "
                f"{_price(float(k['target']))} in {hl}h ({int(k['prob_short'])}% in {hs}h){soon}")
    return f"**{label}:** {_price(spot)} · ⚪ forecast n/a{soon}"


def _top_setup(k: dict) -> str | None:
    cand = [(lab, d) for lab, d in k.items() if d and d.get("prob_long") is not None]
    if not cand:
        return None
    # strongest directional conviction, tie-broken by the odds of that move
    cand.sort(key=lambda x: (abs(x[1].get("prob_up_pct", 50) - 50), x[1]["prob_long"]), reverse=True)
    lab, d = cand[0]
    dot, lean = _lean(d)
    arrow = "↑" if d.get("direction") == "up" else "↓"
    return (f"🎯 **Top setup:** {lab} — {dot} {lean}, {int(d['prob_long'])}% to break "
            f"{_price(float(d['target']))} {arrow} over {d.get('horizon_long', 24)}h")


# ---- regime (grounds the verdict, not shown raw) ------------------------
def _fng():
    d = _cmc("/v3/fear-and-greed/latest").get("data", {})
    return (int(d["value"]), d.get("value_classification", "")) if d.get("value") is not None else None


def _altseason():
    d = _cmc("/v1/altcoin-season-index/latest").get("data", {})
    v = d.get("altcoin_index") or d.get("value")
    if v is None:
        return None
    v = float(v)
    regime = "Altcoin Season" if v >= 75 else ("Bitcoin Season" if v <= 25 else "Neutral")
    return (v, regime)


def _cmc_metrics() -> dict:
    d = _cmc("/v1/global-metrics/quotes/latest").get("data", {})
    q = (d.get("quote", {}) or {}).get("USD", {}) or {}
    return {"mcap_chg": q.get("total_market_cap_yesterday_percentage_change"),
            "btc_dom": d.get("btc_dominance")}


USD_MAJORS = {"USDT", "USDC", "DAI", "USDE", "FDUSD", "PYUSD", "TUSD",
              "USDD", "FRAX", "GUSD", "USDP", "USDS", "LUSD"}


def _stables():
    data = json.loads(_get(LLAMA).decode())
    total = 0.0; depegs = []
    for a in data.get("peggedAssets", []):
        if a.get("pegType") != "peggedUSD":
            continue
        circ = float(((a.get("circulating") or {}).get("peggedUSD")) or 0)
        total += circ
        sym = (a.get("symbol") or "").upper()
        price = a.get("price")
        if sym in USD_MAJORS and price and abs(float(price) - 1.0) >= 0.01 and circ > 1e8:
            depegs.append(f"{sym} ${float(price):.3f}")
    return total, depegs


NEWS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
]


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _news(limit: int = 5):
    for url in NEWS_FEEDS:
        try:
            root = ET.fromstring(_get(url))
        except Exception:
            continue
        titles = []
        for el in root.iter():
            if _local(el.tag) in ("item", "entry"):
                for ch in el:
                    if _local(ch.tag) == "title" and (ch.text or "").strip():
                        titles.append(ch.text.strip())
                        break
        titles = [t for t in titles if t][:limit]
        if titles:
            return titles
    return []


def _regime_context() -> str:
    bits = []
    fng = _safe(_fng)
    if fng:
        bits.append(f"Fear&Greed {fng[0]}/100 ({fng[1]})")
    alt = _safe(_altseason)
    if alt:
        bits.append(f"Altseason {int(alt[0])}/100 ({alt[1]})")
    m = _safe(_cmc_metrics)
    if m:
        if m.get("mcap_chg") is not None:
            bits.append(f"Mkt cap 24h {float(m['mcap_chg']):+.1f}%")
        if m.get("btc_dom") is not None:
            bits.append(f"BTC.D {float(m['btc_dom']):.1f}%")
    st = _safe(_stables)
    if st:
        total, depegs = st
        bits.append(f"Stables ${total/1e9:.0f}B " + ("⚠️ " + ", ".join(depegs) if depegs else "peg ok"))
    return " · ".join(bits) if bits else "regime data unavailable"


# ---- dashboard ----------------------------------------------------------
def cmd_dashboard() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    spots = _spot_map()
    k = _kronos()
    if not spots and not k:
        print("ERROR: market data unavailable (Hyperliquid + Kronos both unreachable).")
        return

    L = ["## 📊 SUPERCLAW MARKET DESK", f"`{ts}`", "",
         "**📊 Assets overview** — 🟢 bullish ↑ · 🔴 bearish ↓ · % = odds of that move"]
    for a in ASSET_ORDER:
        L.append("- " + _asset_line(a, spots.get(a), k.get(a)))
    if k:
        ts_line = _top_setup(k)
        if ts_line:
            L += ["", ts_line]
    else:
        L += ["", "_⚠️ Kronos forecast offline — showing prices only._"]
    dashboard = "\n".join(L)

    headlines = _safe(_news) or []
    regime = _regime_context()
    hl_block = "\n".join(f"- {h}" for h in headlines) if headlines else "- (no headlines fetched)"

    instructions = (
        "\n\n[AGENT INSTRUCTIONS — do not print this line]\n"
        "Everything ABOVE this line is the dashboard. Print it AS-IS as a Markdown list — keep each asset "
        "on its OWN line (do not merge them into a paragraph, do not wrap in a code block, do not "
        "reword/reorder). The asset lines and their odds are final — never invent or change a number.\n\n"
        "Then build the rest yourself:\n\n"
        "RAW HEADLINES (tag each by likely market impact — 🟢 bullish / 🔴 bearish / ⚪ neutral):\n"
        f"{hl_block}\n\n"
        f"MARKET CONTEXT (use to ground the verdict — do NOT print this line raw): {regime}\n\n"
        "Render EXACTLY this structure below the dashboard:\n\n"
        "### 📰 Headlines  ·  🟢 bullish · 🔴 bearish · ⚪ neutral\n"
        "- 🟢/🔴/⚪ <headline>   (one per headline above — ALWAYS keep that color key in the header so "
        "users know what the dots mean)\n\n"
        "### ⚖️ Verdict\n"
        "**<Risk-on / Risk-off / Mixed>.** <one-paragraph read of the overall market, grounded in the "
        "odds above + the market context. Plain text, descriptive, no buy/sell calls.>\n"
        "**Conviction:** 🟢 High / 🟡 Medium / 🔴 Low (pick one)\n\n"
        "### 👉 What now?\n"
        "📈 Deeper read on an asset: **1) BTC  2) ETH  3) BNB  4) HYPE  5) SOL  6) GOLD**\n"
        "📊 **7) Copy-trade perps**\n\n"
        "If the user replies 1–6, that number IS the asset — immediately run "
        "`python3 market_update.py analytics <ASSET>` and follow its instructions. Do NOT re-ask which "
        "asset. If they reply 7, start the perps flow. Descriptive only, never advice; never fabricate "
        "data; if a number isn't above, say it's unavailable."
    )
    print(dashboard + instructions)


# ---- per-asset analytics ------------------------------------------------
def _range_24h(label: str):
    dex = DEX_ASSETS.get(label, (None, label))[0]
    coin = DEX_ASSETS.get(label, (None, label))[1]
    end = int(time.time() * 1000); start = end - 26 * 3600_000
    body = {"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h",
                                              "startTime": start, "endTime": end}}
    if dex:
        body["req"]["dex"] = dex
    rows = _post(body)
    highs = [float(c["h"]) for c in rows]; lows = [float(c["l"]) for c in rows]
    return (max(highs), min(lows)) if highs else None


def cmd_analytics(label: str) -> None:
    label = (label or "").upper()
    if label not in ASSET_ORDER:
        print(f"Unknown asset '{label}'. Choose: {', '.join(ASSET_ORDER)}.")
        return
    spots = _spot_map()
    spot = spots.get(label)
    k = _kronos().get(label)
    rng = _safe(_range_24h, label)

    L = [f"## 📈 {label} — SuperClaw read  _(my estimates — not advice)_"]
    if spot is not None:
        L.append(f"Spot: {_price(spot)}")
    if k and k.get("exp_close"):
        hl, hs = k.get("horizon_long", 24), k.get("horizon_short", 4)
        dot, lean = _lean(k)
        L.append(f"Kronos lean: {dot} **{lean}** ({int(k.get('prob_up_pct', 0))}% close-up over {hl}h)")
        arrow = "↑" if k.get("direction") == "up" else "↓"
        L.append(f"Odds to break {_price(float(k['target']))} {arrow}: {int(k['prob_short'])}% in {hs}h · "
                 f"{int(k['prob_long'])}% in {hl}h")
        L.append(f"Kronos {hl}h range: ~{_price(float(k['exp_low']))}–{_price(float(k['exp_high']))} "
                 f"· exp close {_price(float(k['exp_close']))}")
        spark = _sparkline(k.get("path"))
        if spark:
            L.append(f"Forecast path ({hl}h): {spark}")
        if k.get("suggested_stop") and k.get("suggested_tp"):
            L.append(f"🎯 Kronos levels → stop ~{_price(float(k['suggested_stop']))} · "
                     f"target ~{_price(float(k['suggested_tp']))}")
    else:
        L.append("Kronos forecast: n/a (sidecar offline or asset unsupported)")
    if rng:
        L.append(f"Recent 24h range: {_price(rng[1])}–{_price(rng[0])}")

    perps = "coming soon" if label in NO_PERPS else "available"
    sltp = ""
    if k and k.get("suggested_stop") and k.get("suggested_tp"):
        sltp = (f" If they say yes, carry the Kronos levels into the handoff: "
                f"stop ~{_price(float(k['suggested_stop']))}, target ~{_price(float(k['suggested_tp']))}.")
    L.append(
        "\n[AGENT INSTRUCTIONS — do not print this line]\n"
        "Print everything above this line as-is, then write EXACTLY:\n\n"
        f"### 📈 {label} Analytics  _(my estimates — not advice)_\n"
        "- **Support:** ~$X — <why; tie to the recent 24h low and the Kronos forecast low/stop>\n"
        "- **Resistance:** ~$Y — <why; tie to the next round target and the Kronos forecast high>\n"
        "- **Trend:** <ranging / trending up / trending down, with lean> — <one line; use the Kronos "
        "lean + the dual-horizon odds above>\n"
        "- **Cycle:** <where this asset sits> — <one line>\n\n"
        f"Then offer (perps for {label} are {perps}):\n"
        f"\"Want to copy-trade {label} perps? **1) Yes  2) Back to market**\"{sltp}\n"
        "Use ONLY the numbers above; flag them as estimates; never fabricate. If a value is n/a, say so."
    )
    print("\n".join(L))


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] in ("analytics", "a"):
        cmd_analytics(argv[1] if len(argv) > 1 else "")
    else:
        cmd_dashboard()


if __name__ == "__main__":
    main()
