# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This workspace contains six independent cryptocurrency trading and scanning projects, all written in Python. UI and log messages throughout are in Turkish. All projects target crypto futures markets (Binance, OKX, BingX).

## Trading Philosophy
- "Tahmin para kaybettirir, onay para kazandırır"
- ICT/SMC methodology: liquidity sweep → displacement → entry
- Never enter before liquidity is swept
- Minimum R:R 1:2 for any trade

## Projects

### `levbot/` — Telegram Trading Bot + Scanner
The main production bot. Two components run concurrently:

- **`levbot_combined.py`** — Entry point. Starts `_scanner_loop()` as a daemon thread, then runs the `python-telegram-bot` async event loop. OKX trades use HMAC-SHA256 auth (`hmac` + `hashlib` + `base64`). All orders are market orders, cross-margin. Pending orders expire after 120 seconds via `asyncio.create_task`.
- **`scanner_bot.py`** — Standalone tkinter GUI scanner; also imported by `levbot_combined.py` as `sc.scan_all()`. Deduplicates signals within 4-hour windows via `_sent_signals` dict.

```bash
python levbot_combined.py   # Bot + scanner together
python scanner_bot.py       # GUI scanner standalone
```

Required env vars: `OKX_API_KEY`, `OKX_SECRET`, `OKX_PASSPHRASE`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`

Leverage caps enforced in code: BTC/ETH → 15x, alts → 10x, commodities → 5x.

On startup, `levbot_combined.py` deletes the Telegram webhook and waits 45 seconds before polling to avoid Conflict errors. On Conflict it retries after 90 seconds.

---

### `indikator tarayıcılar/` — PyQt5 Scanner (MVC)
Strict MVC separation:
- **`coin_scanner.py`** — PyQt5 View only; imports `scanner_engine.run_full_scan()`
- **`scanner_engine.py`** — Scan orchestration and API calls (OKX primary, BingX fallback)
- **`indicators.py`** — Tilson T3, WaveTrend, RSI, MACD, BB, MFI, ATR calculations
- **`patterns.py`** — SMC: order blocks, FVG, BOS/CHOCH, liquidity sweeps; candlestick patterns

```bash
BASLAT.bat          # Windows launcher
KUR_VE_BASLAT.bat   # Install deps + launch
python coin_scanner.py
```

Settings persist to `scanner_settings.json`; signals log to a CSV file.

---

### `order blok scanner/` — tkinter Scanner v10
All-in-one single-file scanner (`scanner_v10.py`). Targets Binance Futures + BingX. Includes auto-install for missing packages via `subprocess`/`pip`. Settings persist to `settings_v10.json`, signal log to `scan_log.csv`.

```bash
BASLAT.bat
python scanner_v10.py
```

---

### `ProScanner_V2/` — Educational Scanner (PyQt5)
Explicitly designed with a 4-layer architecture for learning:
1. Data layer — `pro_scanner.py` fetches OHLCV from Binance Futures
2. Indicator layer — RSI, MACD, BB, StochRSI, ADX, WaveTrend in `pro_scanner.py`
3. Scoring layer — weighted signal scoring (`ScannerConfig` dataclass)
4. Presentation layer — `scanner_gui.py` (PyQt5 + QThread for non-blocking scans)

Additional modules:
- **`sessions.py`** — Asia/London/NY session detection and overlap logic
- **`candle_patterns.py`** — Candlestick pattern recognition
- **`chart_patterns.py`** — Chart pattern detection
- **`links.py`** — Exchange URL builders

```bash
BASLAT_CMD.bat   # Console mode
BASLAT_GUI.bat   # GUI mode
python scanner_gui.py
```

---

### `MarketWatch/` — Desktop Market Widget (PyQt5 + WebView)
A narrow (440px wide) always-on-screen desktop widget that renders `market_watch.html` inside a `QWebEngineView`. The HTML file contains all market data logic (JS/CSS). `market_watch.py` is the entry point; `app.py` and `levbot.py` are supporting files.

Packaged to `.exe` via PyInstaller (`MarketWatch.spec`); `resource_path()` handles both dev and frozen paths.

```bash
python market_watch.py
dist/MarketWatch.exe   # Packaged build
```

---

### `levbot_inducement V.2/` — Pine Script Indicator
**SHIELD v2.0** — TradingView Pine Script indicator (`levbot_inducement_shield_v2_0_2.pine.txt`). Not a Python project — paste contents into TradingView's Pine Editor to use.

- Zones are based on swing pivot liquidity pools
- Multi-timeframe stack: 1D structural direction → 4H swing pivot zones → 15M entry trigger
- Confluence filters: OI divergence, BB squeeze, session awareness, smart cooldown
- Signal strength displayed as bolts (max 6)

---

## Shared Technical Indicators

All Python scanners implement variations of the same core indicators:

| Indicator | Description |
|-----------|-------------|
| **Tilson T3** | 6-layer nested EMA (period=6, v=0.7); returns value, direction, price-above-T3 |
| **WaveTrend (VMC Cipher B)** | Channel-based momentum oscillator; buy/sell signals fire when WT1 crosses WT2 in OB/OS zones |
| **SMC** | Order blocks (bullish/bearish), FVG, BOS/CHOCH, liquidity sweep detection |

## Common Dependencies

| Project | GUI | Key packages |
|---------|-----|-------------|
| levbot | tkinter | `python-telegram-bot==20.7`, `requests==2.31.0` |
| indikator tarayıcılar | PyQt5 | `PyQt5`, `requests` |
| order blok scanner | tkinter | `requests` (auto-installs) |
| ProScanner_V2 | PyQt5 | `PyQt5`, `numpy`, `pandas`, `requests` |
| MarketWatch | PyQt5 + WebEngine | `PyQt5`, `PyQtWebEngine` |

## Data Sources

- **OKX** (`api/v5/`) — candle data, order execution, account/positions
- **Binance Futures** (`fapi/binance.com`) — candle data, L/S ratio, OI; used as fallback in most scanners
- **BingX** — secondary scanner exchange
- **CoinGlass** — institutional metrics (levbot scanner)
- **Fear & Greed Index** — sentiment (levbot scanner)

## Coding Rules
- API keys must always be read from environment variables — never hardcoded
- All UI text, labels, and log messages in Turkish
- Error handling is mandatory on every API call and external request
- Signal deduplication required — never send the same signal twice within a 4-hour window

## Known Issues
- **Telegram Conflict error** — occurs when multiple bot instances run simultaneously; handled by deleting the webhook on startup and retrying after 90s
- **OKX Turkey access** — OKX API may be blocked in Turkey; use a VPN or proxy if requests fail
- **OneDrive sync locks** — project files live on OneDrive Desktop; sync can lock `.json`/`.csv` files mid-write and corrupt settings or signal logs
