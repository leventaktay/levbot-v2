# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**LevBot** is a cryptocurrency trading system with two integrated components:

1. **Telegram Trading Bot** (`levbot_combined.py`) — interactive futures trading interface on OKX exchange
2. **Crypto Scanner GUI** (`scanner_bot.py`) — tkinter-based scanner for swing trade signals on Binance/BingX

The UI and log messages are in Turkish.

## Trading Philosophy
- "Tahmin para kaybettirir, onay para kazandırır"
- ICT/SMC methodology: liquidity sweep → displacement → entry
- Never enter before liquidity is swept
- Minimum R:R 1:2 for any trade

## Running the Project

```bash
# Run the full system (Telegram bot + background scanner thread)
python levbot_combined.py

# Run the GUI scanner standalone
python scanner_bot.py
```

No build step. Python 3.x with these pip packages: `python-telegram-bot`, `requests`. `tkinter` is bundled with Python.

## Required Environment Variables

```
OKX_API_KEY
OKX_SECRET
OKX_PASSPHRASE
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
```

## Architecture

### `levbot_combined.py`
- Entry point that starts both the Telegram bot and the scanner background thread.
- Telegram handlers use `python-telegram-bot` async/await.
- OKX REST API calls are authenticated via HMAC-SHA256 (`hmac` + `hashlib` + `base64`).
- Trades are market orders only, cross margin, with leverage capped by asset class (15x BTC/ETH, 10x alts, 5x commodities).
- Trade flow: command → confirmation dialog (inline buttons, 2-min timeout) → order execution.
- Auto-reconnects on Telegram conflict errors (90s retry).

### `scanner_bot.py`
- Standalone tkinter GUI; also launched as a daemon thread from `levbot_combined.py`.
- Scans every 30 minutes (configurable); deduplicates signals within a 4-hour window.
- Persists settings to `settings_v7.json` and logs signals to `tarama_v7.csv`.
- Parallel API requests are rate-limited via a `threading.Semaphore(8)`.

### Technical Indicators
- **Tilson T3** — 6-layer nested EMA for low-lag trend following; returns value, direction, and price position.
- **WaveTrend (VMC Cipher B)** — channel-based momentum oscillator with configurable OB/OS levels.
- **SMC** — Order blocks, FVG, liquidity sweeps, BOS/CHOCH market structure.
- Supporting: RSI, MACD, Bollinger Bands, MFI, ATR.

### External Data Sources
- **OKX** — candle data and order execution.
- **Binance** — fallback candle data; L/S ratio and OI metrics.
- **BingX** — additional scanner exchange.
- **CoinGlass** — institutional metrics.
- **Fear & Greed Index** — sentiment data.

## Key Files

| File | Purpose |
|------|---------|
| `levbot_combined.py` | Main entry point; Telegram bot + scanner coordinator |
| `scanner_bot.py` | Scanner engine + tkinter GUI |
| `settings_v7.json` | Scanner runtime settings (auto-generated) |
| `tarama_v7.csv` | Signal log (auto-generated) |
