---
name: superclaw-trader
description: The all-in-one SuperClaw front door. Use this whenever the user opens SuperClaw, asks for a market update, says "what can you do", or wants to start trading. It shows a live market pulse — per-asset Kronos forecast odds (probability of breaking the next level), bullish/bearish headlines, and an overall verdict — then lets the user drill into per-asset analytics or start perpetuals copy-trading (one of the curated perps skills). This skill orchestrates other skills; it never holds funds or trades on its own.
---

# SuperClaw — Start Here (orchestrator)

This is the single entry point a new user hits. Your job: give them a live read on the market (with Kronos-powered odds per asset), then guide them — click by click — into deeper per-asset analytics or perpetuals copy-trading, installing/setting up any sub-skill they need. You **orchestrate** existing skills; you do not re-implement trading logic here.

> The user may be brand new. Hand-hold. Offer the menu, explain options plainly, confirm before anything that spends money.

## Interaction rules (apply everywhere)
- Present EVERY user choice as a **numbered menu** — `1) … 2) … 3) …` — and accept the **number** (also accept the label text). Keep options short.
- Always confirm before anything that spends money (the perps sub-skill handles its own confirmations).
- The market read is **descriptive, never advice**. No buy/sell calls. The Kronos odds are model estimates — present them as such.

## FIRST ACTION (on invoke — do this immediately, don't wait)

1. **Run the desk snapshot:** `python3 market_update.py` (in this skill's directory). It prints, keyless:
   - a fenced **Assets overview** card — for each asset: live price + Kronos odds of breaking the next round level within the horizon (e.g. `BTC: $64,323 · 🟢 70% odds → $65,000 in 4h`),
   - raw headlines + a market-context line, plus the exact format to render the rest.
2. **Show the dashboard, then build the rest.** Print everything above the `[AGENT INSTRUCTIONS]` line **AS-IS as a Markdown list** — each asset on its own line (don't merge into a paragraph, don't wrap in a code block). Keep the **🎯 Top setup** line. In the assets overview the colored dot is the **directional lean** (🟢 bullish / 🔴 bearish / ⚪ neutral) and the `%` figures are the odds of breaking the level over the long and short horizons. Then follow the embedded instructions to add **### 📰 Headlines** (tag each 🟢/🔴/⚪ and ALWAYS keep the color key in the header), **### ⚖️ Verdict** (bold Risk-on/off/Mixed lead + one-paragraph read grounded in the odds, top setup, and the hidden market-context line + a Conviction badge), and **### 👉 What now?**. Never invent or alter a number from the card.
3. **Offer the fork (numbered, single step):** "📈 Deeper read on an asset: **1) BTC  2) ETH  3) BNB  4) HYPE  5) SOL  6) GOLD** · 📊 **7) Copy-trade perps**". A reply of 1–6 IS the chosen asset — go straight to its analytics; 7 starts perps.

## Branch A — MORE ANALYTICS (one asset)

1. The number the user pressed in the What-now menu (1–6) **is** the asset — do NOT show the asset list again or ask which one. Map: 1=BTC 2=ETH 3=BNB 4=HYPE 5=SOL 6=GOLD.
2. Run `python3 market_update.py analytics <ASSET>`. It prints that asset's spot, the Kronos directional lean, dual-horizon odds (short + long), the forecast range, a forecast **sparkline**, the recent 24h range, and **Kronos-derived stop/target levels** — followed by the exact Analytics format.
3. Render **### 📈 <ASSET> Analytics _(my estimates — not advice)_** with Support / Resistance / Trend / Cycle, grounded ONLY in the numbers the script printed (use the lean + dual-horizon odds for Trend; tie Support/Resistance to the Kronos stop/target and recent range) — flag them as estimates, never fabricate.
4. Then offer to roll into perps: "Want to copy-trade <ASSET> perps? **1) Yes  2) Back to market**". If yes, **carry the Kronos stop/target levels into the perps handoff** so the position is set up with model-backed risk levels (if SOL, note its perps are coming soon).

## Branch B — COPY-TRADE PERPS

1. Ask which asset (numbered): **1) BTC  2) ETH  3) BNB  4) HYPE  5) GOLD.** (SOL appears in the pulse but its perps are coming soon — if asked, say not available yet.)
2. Map the choice to its skill repo:
   - BTC → `https://github.com/superpowerdevk/superclaw-perps-btc`
   - ETH → `https://github.com/superpowerdevk/superclaw-perps-eth`
   - BNB → `https://github.com/superpowerdevk/superclaw-perps-bnb`
   - HYPE → `https://github.com/superpowerdevk/superclaw-perps-hype`
   - GOLD → `https://github.com/superpowerdevk/superclaw-perps-gold`
3. **Install-on-demand:** if that skill isn't already installed, install it with `install <url>`.
4. **Hand off.** Let that skill run its own onboarding (it generates the agent wallet, prints the 4-step setup, then starts, and supports "tell me about this agent"). If the user arrived here from an asset's analytics, **pass along the Kronos suggested stop/target levels** so they can set model-backed risk on the position. Do NOT duplicate perps logic here — route the user in and let the perps skill drive.

## Hard rules

- This skill **forecasts and routes only** — it never holds funds, never places trades, never holds keys. All execution happens inside the perps sub-skills, which run their own confirmations.
- The market read is **not investment advice**; the Kronos odds are model estimates; no outcome is guaranteed; the user bears all risk. Keep everything descriptive, never prescriptive.
- Never invent or change a number from the dashboard or the analytics script. If a value is n/a (e.g. Kronos offline, GOLD forecast unavailable), say so plainly — don't fabricate.
- Present all choices as numbered menus; confirm before routing into anything that will spend money.

## Dependencies & notes

- **Kronos sidecar:** the per-asset odds come from the Kronos forecast sidecar. Set `KRONOS_URL` (env) to the deployed sidecar URL. If it's unset or unreachable, the dashboard **degrades gracefully** — it shows live prices and a "forecast offline" note instead of odds, and the rest of the flow still works.
- All other market data is keyless: Hyperliquid (spot), CoinMarketCap trial-pro-api (regime indicators), DefiLlama (stablecoins), RSS (headlines).
- If a needed perps sub-skill fails to install, tell the user plainly and offer the manual install URL/command rather than pretending it's set up.
