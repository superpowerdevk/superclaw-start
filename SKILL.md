---
name: superclaw-trader
description: The all-in-one SuperClaw front door. Use this whenever the user opens SuperClaw, asks for a market update, says "what can you do", or wants to start trading. It shows a live market pulse with a trader-style TLDR, then hand-holds the user into either memecoin trading (Trenches Scout discovery + OKX DEX swap with stop-loss/take-profit) or perpetuals copy-trading (one of the curated perps skills), installing and setting up whatever sub-skill is needed along the way. This skill orchestrates other skills — it never holds funds or trades on its own.
---

# SuperClaw — Start Here (orchestrator)

This is the single entry point a new user hits. Your job: give them a live read on the market, then guide them — click by click — into memes or perps, installing/setting up any sub-skill they need, and walking them all the way through execution. You **orchestrate** existing skills; you do not re-implement trading logic here.

> The user may be brand new. Hand-hold. Offer the menu, explain options plainly, confirm before anything that spends money.

## Interaction rules (apply everywhere)
- Present EVERY user choice as a **numbered menu** — `1) … 2) … 3) …` — and accept the **number** as their answer (also accept the label text). Keep options short.
- Always confirm before anything that spends money (show the quote/amount first).

## FIRST ACTION (on invoke — do this immediately, don't wait)

1. **Run the desk snapshot.** Run `python3 market_update.py` (in this skill's directory). With no API keys it prints a full data set — tracked assets (price/24h/funding/OI), key metrics (mcap/volume/dominance/ETH-BTC ratio), top movers, sentiment (Fear & Greed, Altcoin Season), stablecoin supply + de-peg, and recent headlines — plus embedded instructions for the briefing format.
2. **Show the dashboard, then add your read.** The script prints the dashboard wrapped in a **code block** (between ``` fences). Output that fenced code block to the user **EXACTLY as printed — keep the ``` fences** so the line breaks and alignment are preserved. Do NOT convert it to markdown, bold the headers, or merge the lines into paragraphs. Then, **below the code block as normal text**, append two short sections from that data: **📈 Analytics** (BTC support/resistance — flag clearly as YOUR estimates; trend read; cycle read) and **⚖️ Verdict** (risk-on/off, what to watch, conviction low/med/high). The timestamp + sources are already in the dashboard. Descriptive, not advice — no buy/sell calls.
3. **Offer the fork (numbered):** "What do you want to do? **1) Trade memes  2) Trade perps**"

## Branch A — PERPS

1. Ask which asset (numbered): **1) BTC  2) ETH  3) BNB  4) HYPE  5) GOLD.** (SOL appears in the pulse but its perps are coming soon — if asked, say not available yet.)
2. Map the choice to its skill repo:
   - BTC → `https://github.com/superpowerdevk/superclaw-perps-btc`
   - ETH → `https://github.com/superpowerdevk/superclaw-perps-eth`
   - BNB → `https://github.com/superpowerdevk/superclaw-perps-bnb`
   - HYPE → `https://github.com/superpowerdevk/superclaw-perps-hype`
   - GOLD → `https://github.com/superpowerdevk/superclaw-perps-gold`
3. **Install-on-demand:** if that skill isn't already installed, install it with `install <url>`.
4. **Hand off.** Let that skill run its own onboarding (it will generate the agent wallet and print the 4-step setup, then start, and supports "tell me about this agent"). Do NOT duplicate perps logic here — just route the user in and let the perps skill drive.

## Branch B — MEMES

**Prerequisite gate — check before anything else:** the user needs the **OKX agentic wallet + DEX swap** installed and the wallet set up.
- If the OKX skills aren't installed: `npx skills add okx/onchainos-skills`, then walk the user through wallet setup (login / email OTP) using the `okx-agentic-wallet` skill. Only continue once the wallet is ready.

Then:
1. **Discover.** Run **Trenches Scout** (install `https://github.com/superpowerdevk/superclaw-trenches-scout` first if it isn't present). Take its signal-ranked candidates with each token's symbol, **contract address**, and chain. Never invent a token address — it must come from Scout.
2. **Present the picks as a NUMBERED list, top-signal pick first.** Example format:
   ```
   Top SuperClaw picks (signal-ranked):
   1) $WIF — 4 smart wallets, 1 KOL   ← top pick
   2) $vibecat — strongest smart-money cluster
   3) $TOKEN — <one-line reason>
   ```
   Then the blunt one-line meme-risk warning (can rug, go to zero, or become unsellable; SL/TP is best-effort).
3. **Lead with the action — offer to buy the #1 pick first (numbered):**
   "Want me to buy the **#1 pick ($WIF)**?
   **1) Yes — buy $WIF
   2) Pick a different one (reply with its number above)
   3) Not now**"
   This is the SuperClaw **trader** — it executes. Do NOT stop at "decide for yourself / execute manually on GMGN"; once the user picks a token, continue straight into the buy flow below. If they choose option 2, ask which number; if 3, stop politely.
4. **Ask the buy amount:** "How much **USDT** do you want to put in?"
5. **Ask stop loss (numbered):** "Stop loss at — **1) 5%  2) 10%  3) 15%  4) higher (tell me)**"
6. **Ask take profit (numbered):** "Take profit at — **1) 5%  2) 10%  3) 15%  4) higher (tell me)**"
7. **Ask the check interval (numbered):** "How often should I check the price for your SL/TP? **1) 2 min (recommended for memes)  2) 5 min  3) 10 min  4) 15 min  5) 30 min  6) 1 hour  7) 4 hours  8) 12 hours  9) daily.** Memes move fast — pick 1 unless you have a reason not to."
8. **Buy** via `okx-dex-swap`: resolve the token address → `swap quote` → show the quote (token, USDT in, expected out, price impact, fees) and **get explicit confirmation** → `swap execute`. Respect the swap skill's safety gates: **honeypot → STOP** and tell the user; **price impact > 5% or high tax → warn and require explicit confirmation.**
9. **Arm SL/TP.** Record the entry price. Set the recurring price check at the chosen interval. On each check, fetch the current price (`okx-dex-swap swap quote`, or GMGN). If price ≤ entry × (1 − SL%) → **sell all** via `swap execute` (stop-loss hit). If price ≥ entry × (1 + TP%) → **sell all** (take-profit hit). After a fill, stop the schedule. Keep the schedule running until SL or TP triggers.
10. **Summarize:** token, USDT spent, entry price, SL and TP levels, and the check interval — and remind them they can say "sell now" or "cancel" anytime.

## Hard rules

- Money is spent in **USDT/USDC** — always confirm the exact amount before any `swap execute`.
- **Always confirm before executing** any swap (show the quote first).
- Respect `okx-dex-swap` safety gates: honeypot = stop; high price impact / tax = warn + explicit confirm.
- At the meme buy step, state plainly: **memecoins can go to zero, rug, or become unsellable; SL/TP is best-effort** — a periodic price check can miss a fast dump and may not fill if liquidity dries up.
- This is **not investment advice**; no profit is guaranteed; the user bears all risk. Keep the market TLDR descriptive, never prescriptive.
- Never fabricate a token contract address. If you can't verify it from Scout/OKX, stop.
- This skill never holds funds or trades itself — it drives the sub-skills and confirms with the user at each money step.

## Notes

- All market data is keyless: Hyperliquid (prices/derivs, unlimited) + CoinMarketCap (regime indicators, rate-limited free tier — one pulse per request is fine).
- If a needed sub-skill fails to install, tell the user plainly and offer the manual install URL/command rather than pretending it's set up.
