#!/usr/bin/env python3
"""SuperClaw market desk — keyless data, rendered as a compact mobile dashboard.

The script prints a ready-made dashboard (emoji status, gauge bars, compact
cards). The agent shows that verbatim, then appends Analytics + Verdict.

Sources (all keyless): Hyperliquid (price/funding/OI + movers),
CoinMarketCap trial-pro-api (mcap/vol/dominance/Fear&Greed/Altcoin Season),
DefiLlama (stablecoins), CoinDesk RSS (headlines).
On-chain whale/exchange-flow is intentionally omitted (no keyless source).
"""

from __future__ import annotations

import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HL = "https://api.hyperliquid.xyz/info"
CMC = "https://pro-api.coinmarketcap.com/trial-pro-api"
LLAMA = "https://stablecoins.llama.fi/stablecoins?includePrices=true"

MAIN_ASSETS = ["BTC", "ETH", "SOL", "BNB", "HYPE"]
DEX_ASSETS = {"GOLD": ("xyz", "xyz:GOLD")}
NO_PERPS = {"SOL"}
MOVER_MIN_VOL = 10_000_000


def _post(body: dict) -> list:
    req = urllib.request.Request(HL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _get(url: str):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "superclaw"})
    with urllib.request.urlopen(req, timeout=15) as r:
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


def _chg(c: dict) -> float:
    m = float(c["markPx"]); pv = float(c["prevDayPx"])
    return (m - pv) / pv * 100 if pv else 0.0


def _bar(v: float, width: int = 10) -> str:
    f = max(0, min(width, round(v / 100 * width)))
    return "▓" * f + "░" * (width - f)


def _oi(usd: float) -> str:
    return f"${usd/1e9:.1f}B" if usd >= 1e9 else f"${usd/1e6:.0f}M"


def _card(label: str, c: dict) -> str:
    m = float(c["markPx"]); ch = _chg(c)
    dot = "🟢" if ch >= 0 else "🔴"
    if label in NO_PERPS:
        extra = " · perps soon"
    else:
        f_apr = float(c.get("funding", 0)) * 24 * 365 * 100
        extra = f" · fund {f_apr:+.1f}%/yr · OI {_oi(float(c.get('openInterest',0))*m)}"
    return f"{dot} {label:<4} {_price(m):<9} {ch:+.1f}%{extra}"


def _movers(uni: list, ctxs: list):
    rows = []
    for u, c in zip(uni, ctxs):
        try:
            if float(c.get("dayNtlVlm", 0)) < MOVER_MIN_VOL:
                continue
            rows.append((u.get("name"), _chg(c)))
        except Exception:
            continue
    rows.sort(key=lambda x: x[1], reverse=True)
    up = [f"{n} {p:+.0f}%" for n, p in rows[:3] if p > 0]
    dn = [f"{n} {p:+.0f}%" for n, p in rows[-3:][::-1] if p < 0]
    return up, dn


def _cmc_metrics() -> dict:
    d = _cmc("/v1/global-metrics/quotes/latest").get("data", {})
    q = (d.get("quote", {}) or {}).get("USD", {}) or {}
    return {
        "mcap": d.get("total_market_cap") or q.get("total_market_cap"),
        "mcap_chg": q.get("total_market_cap_yesterday_percentage_change"),
        "vol": d.get("total_volume_24h") or q.get("total_volume_24h"),
        "btc_dom": d.get("btc_dominance"), "eth_dom": d.get("eth_dominance"),
    }


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


USD_MAJORS = {"USDT", "USDC", "DAI", "USDE", "FDUSD", "PYUSD", "TUSD",
              "USDD", "FRAX", "GUSD", "USDP", "USDS", "LUSD"}


def _stables():
    """USD-pegged stablecoin supply + de-peg flags for MAJOR $1 stables only.
    Excludes yield-bearing / treasury tokens (USYC, USDY, etc.) that float above $1
    by design and would otherwise show as false de-pegs."""
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
    return tag.split("}")[-1]  # strip XML namespace


def _news(limit: int = 4):
    for url in NEWS_FEEDS:
        try:
            root = ET.fromstring(_get(url))
        except Exception:
            continue
        titles = []
        for el in root.iter():
            if _local(el.tag) in ("item", "entry"):  # RSS item or Atom entry
                for ch in el:
                    if _local(ch.tag) == "title" and (ch.text or "").strip():
                        titles.append(ch.text.strip())
                        break
        titles = [t for t in titles if t][:limit]
        if titles:
            return titles
    return []


def _tone(fng_val: int):
    if fng_val < 25:
        return "🔴", "Risk-off"
    if fng_val < 50:
        return "🟠", "Cautious"
    if fng_val < 65:
        return "🟡", "Mixed"
    return "🟢", "Risk-on"


def _fng_face(v: int) -> str:
    return "😱" if v < 25 else "😟" if v < 45 else "😐" if v < 55 else "🙂" if v < 75 else "🤑"


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None


def main() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        uni, ctxs = _ctxs()
        cmap = {u.get("name"): c for u, c in zip(uni, ctxs)}
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: Hyperliquid fetch failed: {e}")
        return
    btc = float(cmap["BTC"]["markPx"]) if "BTC" in cmap else None
    eth = float(cmap["ETH"]["markPx"]) if "ETH" in cmap else None

    fng = _safe(_fng)
    L = [f"📊 SUPERCLAW MARKET DESK · {ts}"]
    if fng:
        te, tl = _tone(fng[0])
        L.append(f"{te} {tl} · {_fng_face(fng[0])} {fng[1]} ({fng[0]}/100)")
    L.append("")

    L.append("ASSETS")
    for a in MAIN_ASSETS:
        L.append(_card(a, cmap[a]) if a in cmap else f"⚪ {a} (n/a)")
    for label, (dex, coin) in DEX_ASSETS.items():
        d = _safe(_ctxs, dex)
        if d:
            dm = {u.get("name"): c for u, c in zip(d[0], d[1])}
            L.append(_card(label, dm[coin]) if coin in dm else f"⚪ {label} (n/a)")

    sent = []
    if fng:
        sent.append(f"Fear & Greed   {_bar(fng[0])}  {fng[0]}/100  {fng[1]}")
    alt = _safe(_altseason)
    if alt:
        sent.append(f"Altcoin Season {_bar(alt[0])}  {int(alt[0])}/100  {alt[1]}")
    if sent:
        L += ["", "🌡️ SENTIMENT"] + sent

    m = _safe(_cmc_metrics)
    if m and m.get("mcap"):
        parts = [f"Mkt cap ${float(m['mcap'])/1e12:.2f}T"]
        if m.get("mcap_chg") is not None:
            parts[0] += f" ({float(m['mcap_chg']):+.1f}%)"
        if m.get("vol"):
            parts.append(f"Vol ${float(m['vol'])/1e9:.0f}B")
        if m.get("btc_dom") is not None:
            parts.append(f"BTC.D {float(m['btc_dom']):.1f}%")
        if m.get("eth_dom") is not None:
            parts.append(f"ETH.D {float(m['eth_dom']):.1f}%")
        if btc and eth:
            parts.append(f"ETH/BTC {eth/btc:.4f}")
        L += ["", "🌐 MARKET", " · ".join(parts)]

    mv = _safe(_movers, uni, ctxs)
    if mv and (mv[0] or mv[1]):
        L += ["", "🔥 MOVERS"]
        if mv[0]:
            L.append("↑ " + " · ".join(mv[0]))
        if mv[1]:
            L.append("↓ " + " · ".join(mv[1]))

    st = _safe(_stables)
    if st:
        total, depegs = st
        peg = "⚠️ " + ", ".join(depegs) if depegs else "✅ all ~$1.00"
        L += ["", "🪙 STABLES", f"Supply ${total/1e9:.0f}B · peg {peg}"]

    nw = _safe(_news)
    if nw:
        L += ["", "📰 HEADLINES"] + [f"• {t}" for t in nw]

    L += [
        "",
        "[AGENT INSTRUCTIONS — do not print this line]",
        "Show EVERYTHING above this line to the user exactly as printed — it is the dashboard. "
        "Then append two short sections of your own, using ONLY the data above:\n"
        "📈 ANALYTICS — BTC support/resistance (mark these clearly as YOUR estimates), trend read "
        "(accumulation / distribution / ranging / trending), and where we are in the cycle.\n"
        "⚖️ VERDICT — one paragraph: risk-on or risk-off, what to watch next, conviction (low/med/high).\n"
        "Flag estimates and anything missing; on-chain whale/flow data is NOT in this build — say so if asked, never fabricate. "
        "End with: 'What now?  1) Trade memes   2) Trade perps'. Sharp, no filler.",
    ]
    print("\n".join(L))


if __name__ == "__main__":
    main()
