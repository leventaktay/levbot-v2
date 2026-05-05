#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ══════════════════════════════════════════════════════════════════════════════
#  KRIPTO TARAYICI v10.0 — Binance Futures & BingX
#  ● V9 analiz motoru (T3 + WaveTrend + VMC + BB + SMC)
#  ● V2 tarzı arayüz (filtre barı, ayarlar, geçmiş, skor tablosu)
#  ● Otomatik bağımlılık kurulumu
#  ● Telegram sinyal entegrasyonu
# ══════════════════════════════════════════════════════════════════════════════

# ─── OTOMATİK BAĞIMLILIK KURULUMU ────────────────────────────────────────────
# Öğretici: subprocess.check_call ile pip'i Python içinden çalıştırıyoruz.
# sys.executable → hangi Python çalışıyorsa onun pip'ini kullanır.
# Bu sayede başka bilgisayara taşıdığında "requests bulunamadı" hatası almaz.
import subprocess, sys

def auto_install():
    """Eksik kütüphaneleri otomatik kur"""
    required = ["requests"]  # Gerekli dış kütüphaneler
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            print(f"⏳ {pkg} kuruluyor...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", pkg, "--quiet"
            ])
            print(f"✅ {pkg} kuruldu!")

auto_install()

# ─── IMPORTLAR ────────────────────────────────────────────────────────────────
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import math
import json
import csv
import os
import queue
import webbrowser
from datetime import datetime
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─── DOSYA YOLLARI ────────────────────────────────────────────────────────────
# Öğretici: os.path.dirname(__file__) → scriptin bulunduğu klasörü verir.
# Bu sayede BASLAT.bat nerede olursa olsun ayar dosyasını bulur.
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings_v10.json")
LOG_FILE      = os.path.join(BASE_DIR, "scan_log.csv")

# ─── RENK PALETI (V2 tarzı koyu tema) ────────────────────────────────────────
BG       = "#0a0e1a"      # Ana arka plan
BG2      = "#111827"      # İkincil arka plan (filtre barı)
BG3      = "#1a2235"      # Üçüncül (input alanları)
BG4      = "#243049"      # Buton arka planı
ACCENT   = "#00e5ff"      # Ana vurgu rengi (cyan)
ACCENT2  = "#ff6b35"      # İkincil vurgu (turuncu)
GREEN    = "#00ff88"      # Yeşil (long/pozitif)
RED      = "#ff3366"      # Kırmızı (short/negatif)
YELLOW   = "#ffd700"      # Sarı (uyarı)
PURPLE   = "#a855f7"      # Mor (OI)
TEXT     = "#e2e8f0"      # Ana yazı rengi
TEXT_DIM = "#64748b"      # Soluk yazı
BORDER   = "#1e3a5f"      # Kenarlık

# ─── VARSAYILAN AYARLAR ──────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    # Tarama
    "scan_interval":     15,          # dakika
    "min_volume_usd":    5_000_000,   # $5M minimum hacim
    "min_score":         60,          # minimum skor
    "min_rr":            2.5,         # minimum R/R
    "show_mode":         "Tümü",      # Tümü | Sadece LONG | Sadece SHORT

    # Filtreler
    "vol_change_min":    40.0,        # % hacim değişimi
    "funding_max":       0.01,        # % fonlama üst sınırı
    "oi_change_min":     10.0,        # % OI değişimi
    "price_change_max":  15.0,        # % fiyat değişimi üst sınır

    # Borsalar
    "use_binance":       True,
    "use_bingx":         True,

    # BTC Filtre
    "btc_filter":        True,
    "btc_drop_pct":      3.0,

    # İndikatör parametreleri (V9)
    "t3_period":         6,
    "t3_v_factor":       0.7,
    "wt_channel_len":    9,
    "wt_avg_len":        12,
    "wt_ob_level":       53,
    "wt_os_level":       -53,
    "bb_period":         20,
    "bb_std_dev":        2.0,

    # Analiz
    "ob_lookback_4h":    100,
    "ob_lookback_1h":    60,
    "weekly_lookback":   20,

    # Telegram
    "telegram_token":    "",
    "telegram_chat_id":  "",
    "telegram_enabled":  False,

    # CoinGlass
    "coinglass_api_key": "",
    "use_coinglass":     False,
}

def load_settings():
    """JSON dosyasından ayarları yükle, eksikleri varsayılanla doldur"""
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            settings.update(saved)
        except Exception:
            pass
    return settings

def save_settings(settings):
    """Ayarları JSON dosyasına kaydet"""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

# ─── HTTP YARDIMCILARI ───────────────────────────────────────────────────────
# Öğretici: HTTPAdapter + Retry = otomatik tekrar deneme.
# API bazen 429 (rate limit) veya 502 (server error) döner.
# Retry ile 2 kez daha dener, 0.3 sn bekleyerek. Böylece geçici hatalar
# programı kırmaz.
def create_session():
    """Retry mekanizmalı HTTP session oluştur"""
    s = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

def safe_get(url, timeout=12, params=None):
    """Güvenli GET isteği — hata olursa boş dict döner"""
    try:
        s = create_session()
        r = s.get(url, timeout=timeout, params=params)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

def safe_float(val, default=0.0):
    """Güvenli float dönüşümü"""
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default

# ══════════════════════════════════════════════════════════════════════════════
#  BORSA API'LERİ
# ══════════════════════════════════════════════════════════════════════════════

# ─── BINANCE FUTURES ─────────────────────────────────────────────────────────
# Öğretici: Binance Futures API endpoint'leri:
# - /fapi/v1/ticker/24hr → 24 saatlik fiyat/hacim özeti
# - /fapi/v1/klines      → Mum verileri (OHLCV)
# - /fapi/v1/premiumIndex → Fonlama oranları
# - /fapi/v2/ticker/price → Anlık fiyat
# Türkiye'den sorunsuz çalışıyor.

BINANCE_BASE = "https://fapi.binance.com"

def get_binance_tickers():
    """Binance Futures 24h ticker verisi çek"""
    data = safe_get(f"{BINANCE_BASE}/fapi/v1/ticker/24hr")
    if isinstance(data, list):
        return data
    return []

def get_binance_funding():
    """Binance Futures fonlama oranları"""
    funding = {}
    data = safe_get(f"{BINANCE_BASE}/fapi/v1/premiumIndex")
    if isinstance(data, list):
        for item in data:
            sym = item.get("symbol", "").replace("USDT", "")
            rate = safe_float(item.get("lastFundingRate", 0)) * 100
            funding[sym] = rate
    return funding

def get_binance_candles(symbol, interval="4h", limit=200):
    """
    Binance Futures mum verisi çek
    Öğretici: Kline = Open, High, Low, Close, Volume bilgisi.
    Dönen veri: [[timestamp, open, high, low, close, volume, ...], ...]
    Biz bunları ayrı listelere ayırıyoruz çünkü indikatör fonksiyonları
    düz Python listeleri bekliyor (pandas kullanmıyoruz, hız için).
    """
    params = {"symbol": f"{symbol}USDT", "interval": interval, "limit": limit}
    data = safe_get(f"{BINANCE_BASE}/fapi/v1/klines", params=params)
    if not isinstance(data, list) or len(data) < 10:
        return None

    opens, highs, lows, closes, volumes = [], [], [], [], []
    for candle in data:
        try:
            opens.append(float(candle[1]))
            highs.append(float(candle[2]))
            lows.append(float(candle[3]))
            closes.append(float(candle[4]))
            volumes.append(float(candle[5]))
        except (IndexError, ValueError):
            continue

    if len(closes) < 10:
        return None
    return opens, highs, lows, closes, volumes

def get_binance_data(prev_oi, settings):
    """Binance Futures tüm verileri topla"""
    results = []
    oi_snap = {}

    tickers = get_binance_tickers()
    funding = get_binance_funding()

    for t in tickers:
        try:
            symbol_raw = t.get("symbol", "")
            if not symbol_raw.endswith("USDT"):
                continue
            # _1000, _2, vb. margin sembollerini atla
            if "_" in symbol_raw:
                continue

            symbol = symbol_raw.replace("USDT", "")
            last = safe_float(t.get("lastPrice"))
            if last == 0:
                continue

            vol_usd = safe_float(t.get("quoteVolume"))
            if vol_usd < settings["min_volume_usd"]:
                continue

            price_change = abs(safe_float(t.get("priceChangePercent")))
            high24 = safe_float(t.get("highPrice", last))
            low24 = safe_float(t.get("lowPrice", last))

            # Hacim değişimi (basit: şu anki hacim / ortalama)
            vol_change = 0.0

            # Fonlama
            fund_rate = funding.get(symbol, 0.0)

            # OI değişimi (önceki taramaya göre)
            # Öğretici: OI (Open Interest) = açık pozisyon sayısı.
            # OI artıyorsa → yeni para giriyor, OI düşüyorsa → pozisyonlar kapanıyor.
            curr_oi = safe_float(t.get("openInterest", 0))
            key = f"BN_{symbol}"
            prev = prev_oi.get(key, curr_oi)
            oi_change = abs((curr_oi - prev) / prev * 100) if prev > 0 else 0.0
            oi_snap[key] = curr_oi

            results.append({
                "exchange": "Binance",
                "symbol": symbol,
                "price": last,
                "high24": high24,
                "low24": low24,
                "price_change": price_change,
                "volume_usd": vol_usd,
                "vol_change": vol_change,
                "funding": fund_rate,
                "oi_change": oi_change,
            })
        except Exception:
            continue

    return results, oi_snap


# ─── BINGX ───────────────────────────────────────────────────────────────────
BINGX_BASE = "https://open-api.bingx.com"

def get_bingx_tickers():
    """BingX perpetual swap ticker verisi"""
    data = safe_get(f"{BINGX_BASE}/openApi/swap/v2/quote/ticker")
    tickers = data.get("data", [])
    if isinstance(tickers, dict):
        tickers = tickers.get("tickers", [])
    return tickers if isinstance(tickers, list) else []

def get_bingx_funding():
    """BingX fonlama oranları"""
    funding = {}
    data = safe_get(f"{BINGX_BASE}/openApi/swap/v2/quote/premiumIndex")
    items = data.get("data", [])
    if isinstance(items, dict):
        items = items.get("premiumIndex", [])
    if isinstance(items, list):
        for item in items:
            sym = item.get("symbol", "").replace("-USDT", "").replace("_USDT", "")
            rate = safe_float(item.get("lastFundingRate", 0)) * 100
            funding[sym] = rate
    return funding

def get_bingx_candles(symbol, interval="4h", limit=200):
    """BingX mum verisi çek"""
    # BingX interval formatı: 1h, 4h, 1d, 1w
    params = {
        "symbol": f"{symbol}-USDT",
        "interval": interval,
        "limit": str(limit)
    }
    data = safe_get(f"{BINGX_BASE}/openApi/swap/v2/quote/klines", params=params)
    candles = data.get("data", [])
    if not isinstance(candles, list) or len(candles) < 10:
        return None

    opens, highs, lows, closes, volumes = [], [], [], [], []
    for c in candles:
        try:
            opens.append(safe_float(c.get("open")))
            highs.append(safe_float(c.get("high")))
            lows.append(safe_float(c.get("low")))
            closes.append(safe_float(c.get("close")))
            volumes.append(safe_float(c.get("volume")))
        except Exception:
            continue

    if len(closes) < 10:
        return None
    return opens, highs, lows, closes, volumes

def get_bingx_data(prev_oi, settings):
    """BingX tüm verileri topla"""
    results = []
    oi_snap = {}

    tickers = get_bingx_tickers()
    funding = get_bingx_funding()

    for t in tickers:
        try:
            symbol_raw = t.get("symbol", "")
            symbol = symbol_raw.replace("-USDT", "").replace("_USDT", "")
            if not symbol:
                continue

            last = safe_float(t.get("lastPrice", t.get("last", 0)))
            if last == 0:
                continue

            vol_usd = safe_float(t.get("quoteVolume", t.get("volume", 0)))
            if vol_usd < settings["min_volume_usd"]:
                continue

            price_change = abs(safe_float(t.get("priceChangePercent", 0)))
            high24 = safe_float(t.get("highPrice", last))
            low24 = safe_float(t.get("lowPrice", last))

            fund_rate = funding.get(symbol, 0.0)

            curr_oi = safe_float(t.get("openInterest", 0))
            key = f"BX_{symbol}"
            prev = prev_oi.get(key, curr_oi)
            oi_change = abs((curr_oi - prev) / prev * 100) if prev > 0 else 0.0
            oi_snap[key] = curr_oi

            results.append({
                "exchange": "BingX",
                "symbol": symbol,
                "price": last,
                "high24": high24,
                "low24": low24,
                "price_change": price_change,
                "volume_usd": vol_usd,
                "vol_change": 0.0,
                "funding": fund_rate,
                "oi_change": oi_change,
            })
        except Exception:
            continue

    return results, oi_snap


# ═══════════════════════════════════════════════════════════════════════════════
#  İNDİKATÖR FONKSİYONLARI (V9 motoru — saf Python, pandas yok)
# ═══════════════════════════════════════════════════════════════════════════════

# Öğretici: Neden pandas kullanmıyoruz?
# 1. Daha hızlı: Küçük veri setlerinde düz liste işlemleri pandas'tan hızlı
# 2. Daha hafif: pandas import etmek ~150MB RAM, düz Python 0
# 3. Daha taşınabilir: pandas kurmaya gerek yok

def calc_ema(data, period):
    """
    EMA (Exponential Moving Average) hesapla
    Öğretici: EMA = ağırlıklı ortalama. Son fiyatlara daha çok ağırlık verir.
    Formül: EMA_bugün = fiyat × k + EMA_dün × (1 - k)
    k = 2 / (period + 1) → period küçükse k büyük → son fiyata daha çok tepki
    """
    if len(data) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(data[:period]) / period  # İlk değer: SMA
    for val in data[period:]:
        ema = val * k + ema * (1 - k)
    return round(ema, 8)

def calc_ema_series(data, period):
    """EMA serisini döndür (her mum için hesaplanmış)"""
    if len(data) < period:
        return []
    k = 2.0 / (period + 1)
    result = []
    ema = sum(data[:period]) / period
    result.append(ema)
    for val in data[period:]:
        ema = val * k + ema * (1 - k)
        result.append(ema)
    return result

def calc_rsi(closes, period=14):
    """
    RSI (Relative Strength Index) hesapla
    Öğretici: RSI = 100 - (100 / (1 + RS))
    RS = ortalama kazanç / ortalama kayıp
    RSI > 70 → aşırı alım, RSI < 30 → aşırı satım
    """
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calc_tilson_t3(closes, period=6, v_factor=0.7):
    """
    Tilson T3 Moving Average
    Öğretici: 6 katmanlı EMA → çok pürüzsüz trend çizgisi.
    v_factor = 0.7 → hız/pürüzsüzlük dengesi.
    Kullanım: 4H'de trend yönünü belirler.
    Fiyat T3 üstünde + T3 yükseliyorsa → LONG bias
    Fiyat T3 altında + T3 düşüyorsa → SHORT bias
    """
    if len(closes) < period * 6:
        return {"value": 0, "rising": False, "price_above": False}

    # 6 katmanlı EMA
    e1 = calc_ema_series(closes, period)
    if len(e1) < period:
        return {"value": 0, "rising": False, "price_above": False}
    e2 = calc_ema_series(e1, period)
    if len(e2) < period:
        return {"value": 0, "rising": False, "price_above": False}
    e3 = calc_ema_series(e2, period)
    if len(e3) < period:
        return {"value": 0, "rising": False, "price_above": False}
    e4 = calc_ema_series(e3, period)
    if len(e4) < period:
        return {"value": 0, "rising": False, "price_above": False}
    e5 = calc_ema_series(e4, period)
    if len(e5) < period:
        return {"value": 0, "rising": False, "price_above": False}
    e6 = calc_ema_series(e5, period)
    if not e6:
        return {"value": 0, "rising": False, "price_above": False}

    # T3 katsayıları
    v = v_factor
    c1 = -(v * v * v)
    c2 = 3 * v * v + 3 * v * v * v
    c3 = -6 * v * v - 3 * v - 3 * v * v * v
    c4 = 1 + 3 * v + v * v * v + 3 * v * v

    # Son değerleri al (diziler farklı uzunlukta)
    val = c1 * e6[-1] + c2 * e5[-1] + c3 * e4[-1] + c4 * e3[-1]
    prev_val = None
    if len(e6) >= 2 and len(e5) >= 2 and len(e4) >= 2 and len(e3) >= 2:
        prev_val = c1 * e6[-2] + c2 * e5[-2] + c3 * e4[-2] + c4 * e3[-2]

    rising = val > prev_val if prev_val is not None else False
    price_above = closes[-1] > val

    return {
        "value": round(val, 8),
        "rising": rising,
        "price_above": price_above
    }

def calc_wavetrend(highs, lows, closes, channel_len=9, avg_len=12,
                    ob_level=53, os_level=-53):
    """
    WaveTrend Oscillator (VMC Cipher B'nin çekirdeği)
    Öğretici: HLC3 (ortalama fiyat) üzerine EMA uygulayıp trend sinyali üretir.
    wt1 > wt2 ve wt1 < os_level → LONG sinyal (oversold'dan çıkış)
    wt1 < wt2 ve wt1 > ob_level → SHORT sinyal (overbought'tan düşüş)
    Yeşil daire = al, Kırmızı daire = sat (TradingView'daki gibi)
    """
    n = len(closes)
    if n < channel_len + avg_len + 5:
        return {"wt1": 0, "wt2": 0, "buy_signal": False, "sell_signal": False,
                "overbought": False, "oversold": False}

    # HLC3 = (High + Low + Close) / 3
    hlc3 = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]

    # ESA = EMA(HLC3, channel_len)
    esa = calc_ema_series(hlc3, channel_len)
    if not esa:
        return {"wt1": 0, "wt2": 0, "buy_signal": False, "sell_signal": False,
                "overbought": False, "oversold": False}

    # D = EMA(|HLC3 - ESA|, channel_len)
    offset = n - len(esa)
    abs_diff = [abs(hlc3[offset + i] - esa[i]) for i in range(len(esa))]
    d = calc_ema_series(abs_diff, channel_len)
    if not d:
        return {"wt1": 0, "wt2": 0, "buy_signal": False, "sell_signal": False,
                "overbought": False, "oversold": False}

    # CI = (HLC3 - ESA) / (0.015 * D)
    offset2 = len(esa) - len(d)
    ci = []
    esa_start = offset + offset2
    for i in range(len(d)):
        denom = 0.015 * d[i] if d[i] != 0 else 0.0001
        ci.append((hlc3[esa_start + i] - esa[offset2 + i]) / denom)

    # WT1 = EMA(CI, avg_len), WT2 = SMA(WT1, 4)
    wt1_series = calc_ema_series(ci, avg_len)
    if len(wt1_series) < 4:
        return {"wt1": 0, "wt2": 0, "buy_signal": False, "sell_signal": False,
                "overbought": False, "oversold": False}

    wt1 = round(wt1_series[-1], 2)
    wt2 = round(sum(wt1_series[-4:]) / 4, 2)
    prev_wt1 = round(wt1_series[-2], 2)
    prev_wt2 = round(sum(wt1_series[-5:-1]) / 4, 2) if len(wt1_series) >= 5 else wt2

    # Sinyal: wt1 wt2'yi yukarı keserse → al, aşağı keserse → sat
    buy_signal = (prev_wt1 <= prev_wt2 and wt1 > wt2 and wt1 < os_level + 20)
    sell_signal = (prev_wt1 >= prev_wt2 and wt1 < wt2 and wt1 > ob_level - 20)

    return {
        "wt1": wt1,
        "wt2": wt2,
        "buy_signal": buy_signal,
        "sell_signal": sell_signal,
        "overbought": wt1 > ob_level,
        "oversold": wt1 < os_level,
    }

def calc_vmc_rsimfi(highs, lows, closes, opens, period=14):
    """
    VMC Cipher B — RSI+MFI bileşeni
    Öğretici: Normal MFI (Money Flow Index) sadece hacim kullanır.
    Burada hacim yerine mum gövde büyüklüğü kullanılıyor.
    Pozitif → para giriyor, Negatif → para çıkıyor.
    """
    if len(closes) < period + 1:
        return 0.0

    # Mum gövdesi bazlı "money flow"
    mf_vals = []
    for i in range(len(closes)):
        body = closes[i] - opens[i]
        hl_range = highs[i] - lows[i]
        if hl_range == 0:
            hl_range = 0.0001
        mf_vals.append(body / hl_range * 100)

    # Son period değerin RSI'ını hesapla
    if len(mf_vals) < period + 1:
        return 0.0

    gains, losses = [], []
    for i in range(1, len(mf_vals)):
        diff = mf_vals[i] - mf_vals[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    if len(gains) < period:
        return 0.0

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 50.0
    rs = avg_gain / avg_loss
    rsi_mfi = 100 - (100 / (1 + rs))
    return round(rsi_mfi - 50, 2)  # 0 merkezli

def calc_bollinger_bands(closes, period=20, std_dev=2.0):
    """
    Bollinger Bands hesapla
    Öğretici: Orta bant = SMA, üst/alt bantlar = SMA ± (stddev × çarpan)
    Fiyat üst bandın üstüne çıkıp geri girerse → sweep (sahte kırılma)
    Bantlar sıkışırsa (squeeze) → büyük hareket yaklaşıyor
    """
    if len(closes) < period:
        return None

    window = closes[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std = variance ** 0.5

    upper = mean + std_dev * std
    lower = mean - std_dev * std

    # Squeeze tespiti: band genişliği ortalamanın %4'ünden az
    bandwidth = (upper - lower) / mean * 100 if mean > 0 else 0
    squeeze = bandwidth < 4.0

    # Sweep tespiti: fiyat band dışına çıkıp geri girdi mi?
    sweep_up = False
    sweep_down = False
    if len(closes) >= 3:
        # Önceki mum üst bandı aştı, şimdiki geri girdi
        prev_upper = mean + std_dev * std  # basitleştirilmiş
        if closes[-2] > upper and closes[-1] < upper:
            sweep_up = True
        if closes[-2] < lower and closes[-1] > lower:
            sweep_down = True

    return {
        "upper": round(upper, 8),
        "middle": round(mean, 8),
        "lower": round(lower, 8),
        "squeeze": squeeze,
        "bandwidth": round(bandwidth, 2),
        "sweep_up": sweep_up,
        "sweep_down": sweep_down,
    }

def calc_mfi(highs, lows, closes, volumes, period=14):
    """
    Money Flow Index (Hacim ağırlıklı RSI)
    Öğretici: MFI = RSI gibi ama hacmi de hesaba katar.
    MFI > 80 → aşırı alım, MFI < 20 → aşırı satım.
    """
    if len(closes) < period + 1:
        return None

    pos_flow = 0.0
    neg_flow = 0.0

    for i in range(-period, 0):
        tp_now = (highs[i] + lows[i] + closes[i]) / 3
        tp_prev = (highs[i - 1] + lows[i - 1] + closes[i - 1]) / 3
        raw_mf = tp_now * volumes[i]
        if tp_now > tp_prev:
            pos_flow += raw_mf
        else:
            neg_flow += raw_mf

    if neg_flow == 0:
        return 100.0
    mf_ratio = pos_flow / neg_flow
    return round(100 - (100 / (1 + mf_ratio)), 2)


# ══════════════════════════════════════════════════════════════════════════════
#  ANALİZ MOTORU
# ══════════════════════════════════════════════════════════════════════════════

def analyze_coin(symbol, exchange, settings):
    """
    Tek coin için çok-zaman dilimli analiz yap
    Öğretici: 3 katmanlı analiz sistemi:
    1. 4H → Trend yönü (T3 + VMC RSI+MFI) → "nereye gidiyoruz?"
    2. 1H → Giriş sinyali (WaveTrend) → "ne zaman girmeliyiz?"
    3. 1D → Büyük resim (RSI + BB) → "genel durum ne?"
    """
    result = {
        "direction": "NÖTR",
        "t3_trend": "—",
        "wt_signal": "—",
        "rsi": 0,
        "bb_squeeze": False,
        "mfi": 0,
        "analysis_score": 0,
    }

    # Mum verisini çek (borsaya göre)
    if exchange == "Binance":
        candles_4h = get_binance_candles(symbol, "4h", 200)
        candles_1h = get_binance_candles(symbol, "1h", 200)
    else:
        candles_4h = get_bingx_candles(symbol, "4h", 200)
        candles_1h = get_bingx_candles(symbol, "1h", 200)

    score = 0

    # ── 4H ANALİZ: T3 Trend Filtresi ──
    if candles_4h:
        opens_4h, highs_4h, lows_4h, closes_4h, vols_4h = candles_4h

        t3 = calc_tilson_t3(closes_4h, settings["t3_period"], settings["t3_v_factor"])
        if t3["price_above"] and t3["rising"]:
            result["t3_trend"] = "↑ LONG"
            result["direction"] = "LONG"
            score += 15
        elif not t3["price_above"] and not t3["rising"]:
            result["t3_trend"] = "↓ SHORT"
            result["direction"] = "SHORT"
            score += 15
        else:
            result["t3_trend"] = "↔ NÖTR"

        # VMC RSI+MFI
        rsimfi = calc_vmc_rsimfi(highs_4h, lows_4h, closes_4h, opens_4h)
        if result["direction"] == "LONG" and rsimfi > 0:
            score += 10  # Para akışı trendle uyumlu
        elif result["direction"] == "SHORT" and rsimfi < 0:
            score += 10

        # RSI
        rsi = calc_rsi(closes_4h)
        if rsi:
            result["rsi"] = rsi
            if rsi < 30:
                score += 5  # Oversold
            elif rsi > 70:
                score += 5  # Overbought

        # BB
        bb = calc_bollinger_bands(closes_4h, settings["bb_period"], settings["bb_std_dev"])
        if bb:
            result["bb_squeeze"] = bb["squeeze"]
            if bb["squeeze"]:
                score += 8  # Squeeze = patlama yakın
            if bb["sweep_down"] and result["direction"] == "LONG":
                score += 10  # BB sweep + long = güçlü sinyal
            elif bb["sweep_up"] and result["direction"] == "SHORT":
                score += 10

        # MFI
        mfi = calc_mfi(highs_4h, lows_4h, closes_4h, vols_4h)
        if mfi:
            result["mfi"] = mfi

    # ── 1H ANALİZ: WaveTrend Giriş Sinyali ──
    if candles_1h:
        opens_1h, highs_1h, lows_1h, closes_1h, vols_1h = candles_1h

        wt = calc_wavetrend(
            highs_1h, lows_1h, closes_1h,
            settings["wt_channel_len"], settings["wt_avg_len"],
            settings["wt_ob_level"], settings["wt_os_level"]
        )

        if wt["buy_signal"] and result["direction"] == "LONG":
            result["wt_signal"] = "🟢 AL"
            score += 22
        elif wt["sell_signal"] and result["direction"] == "SHORT":
            result["wt_signal"] = "🔴 SAT"
            score += 22
        elif wt["oversold"]:
            result["wt_signal"] = "⬇ Aşırı Satım"
            if result["direction"] != "SHORT":
                score += 8
        elif wt["overbought"]:
            result["wt_signal"] = "⬆ Aşırı Alım"
            if result["direction"] != "LONG":
                score += 8
        else:
            result["wt_signal"] = "↔ Nötr"

    result["analysis_score"] = score
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  FİLTRE & SKOR
# ══════════════════════════════════════════════════════════════════════════════

def apply_filters(coins, settings):
    """Temel filtreleri uygula"""
    filtered = []
    for c in coins:
        try:
            oi_ok = c["oi_change"] >= settings["oi_change_min"] if c["oi_change"] > 0 else True
            vol_ok = c["vol_change"] >= settings["vol_change_min"] if c["vol_change"] > 0 else True
            fund_ok = c["funding"] < settings["funding_max"]
            price_ok = c["price_change"] < settings["price_change_max"]

            if vol_ok and fund_ok and oi_ok and price_ok:
                filtered.append(c)
        except Exception:
            continue
    return filtered

def base_score(coin, settings):
    """Temel skor hesapla (0-100)"""
    s = 0.0
    if coin["vol_change"] > 0:
        s += min(coin["vol_change"] / 200, 1.0) * 20
    if coin["funding"] < 0:
        s += min(abs(coin["funding"]) / 0.1, 1.0) * 15
    if coin["oi_change"] > 0:
        s += min(coin["oi_change"] / 50, 1.0) * 20
    pm = coin["price_change"]
    cap = settings["price_change_max"]
    if pm < cap:
        s += ((cap - pm) / cap) * 15
    return round(s, 1)


# ══════════════════════════════════════════════════════════════════════════════
#  BTC DURUM FİLTRESİ
# ══════════════════════════════════════════════════════════════════════════════

_btc_cache = {"price": 0, "change": 0, "trend": "—", "ts": 0}

def get_btc_status(settings):
    """BTC anlık durum (5 dakikada bir güncelle)"""
    global _btc_cache
    now = time.time()
    if now - _btc_cache["ts"] < 300:
        return _btc_cache

    try:
        if settings["use_binance"]:
            data = safe_get(f"{BINANCE_BASE}/fapi/v1/ticker/24hr",
                            params={"symbol": "BTCUSDT"})
            if isinstance(data, dict) and data.get("lastPrice"):
                price = safe_float(data["lastPrice"])
                change = safe_float(data.get("priceChangePercent", 0))
                _btc_cache = {"price": price, "change": change,
                              "trend": "YUKARI" if change > 0 else "AŞAĞI",
                              "ts": now}
                return _btc_cache

        # Fallback: BingX
        data = safe_get(f"{BINGX_BASE}/openApi/swap/v2/quote/ticker")
        tickers = data.get("data", [])
        if isinstance(tickers, dict):
            tickers = tickers.get("tickers", [])
        for t in (tickers or []):
            sym = t.get("symbol", "")
            if "BTC" in sym and "USDT" in sym:
                price = safe_float(t.get("lastPrice", t.get("last", 0)))
                change = safe_float(t.get("priceChangePercent", 0))
                _btc_cache = {"price": price, "change": change,
                              "trend": "YUKARI" if change > 0 else "AŞAĞI",
                              "ts": now}
                return _btc_cache
    except Exception:
        pass

    return _btc_cache


# ══════════════════════════════════════════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════

def send_telegram(msg, settings):
    """Telegram'a sinyal mesajı gönder"""
    token = settings.get("telegram_token", "").strip()
    chat_id = settings.get("telegram_chat_id", "").strip()
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "HTML"
        }, timeout=10)
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  LOG KAYIT
# ══════════════════════════════════════════════════════════════════════════════

def log_results(results):
    """Sonuçları CSV dosyasına kaydet"""
    file_exists = os.path.exists(LOG_FILE)
    try:
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "zaman", "borsa", "sembol", "fiyat", "skor",
                    "yön", "t3_trend", "wt_sinyal", "rsi",
                    "fiyat_deg", "hacim_usd", "fonlama", "oi_deg"
                ])
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            for r in results:
                writer.writerow([
                    now, r.get("exchange", ""),
                    r.get("symbol", ""), r.get("price", ""),
                    r.get("total_score", ""), r.get("direction", ""),
                    r.get("t3_trend", ""), r.get("wt_signal", ""),
                    r.get("rsi", ""), r.get("price_change", ""),
                    r.get("volume_usd", ""), r.get("funding", ""),
                    r.get("oi_change", ""),
                ])
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  ANA TARAMA FONKSİYONU
# ══════════════════════════════════════════════════════════════════════════════

def full_scan(prev_oi, settings, progress_callback=None):
    """
    Tam tarama döngüsü
    1. Borsalardan veri çek (paralel)
    2. Filtreleri uygula
    3. Skorla
    4. En yüksek skorluları analiz et (detaylı)
    5. Telegram'a at
    """
    all_coins = []
    new_oi = {}
    counts = {"binance": 0, "bingx": 0}
    thread_results = {}

    def run_binance():
        if settings["use_binance"]:
            data, oi = get_binance_data(prev_oi, settings)
            thread_results["binance"] = (data, oi)

    def run_bingx():
        if settings["use_bingx"]:
            data, oi = get_bingx_data(prev_oi, settings)
            thread_results["bingx"] = (data, oi)

    if progress_callback:
        progress_callback("Borsalardan veri çekiliyor...")

    t1 = threading.Thread(target=run_binance)
    t2 = threading.Thread(target=run_bingx)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    bn_data, bn_oi = thread_results.get("binance", ([], {}))
    bx_data, bx_oi = thread_results.get("bingx", ([], {}))

    new_oi.update(bn_oi)
    new_oi.update(bx_oi)
    counts["binance"] = len(bn_data)
    counts["bingx"] = len(bx_data)
    all_coins = bn_data + bx_data

    if progress_callback:
        progress_callback(f"Filtreler uygulanıyor... ({len(all_coins)} coin)")

    # Filtrele
    filtered = apply_filters(all_coins, settings)

    # Skorla
    for coin in filtered:
        coin["base_score"] = base_score(coin, settings)

    # Skora göre sırala, en iyi 30'u detaylı analiz et
    filtered.sort(key=lambda x: x["base_score"], reverse=True)
    top_coins = filtered[:30]

    if progress_callback:
        progress_callback(f"Detaylı analiz yapılıyor... ({len(top_coins)} coin)")

    # Detaylı analiz (sıralı, API rate limit'e dikkat)
    analyzed = []
    for i, coin in enumerate(top_coins):
        try:
            analysis = analyze_coin(coin["symbol"], coin["exchange"], settings)
            coin.update(analysis)
            coin["total_score"] = round(coin["base_score"] + coin["analysis_score"], 1)

            # Yön filtresi
            mode = settings.get("show_mode", "Tümü")
            if mode == "Sadece LONG" and coin["direction"] != "LONG":
                continue
            if mode == "Sadece SHORT" and coin["direction"] != "SHORT":
                continue

            analyzed.append(coin)

            if progress_callback and (i + 1) % 5 == 0:
                progress_callback(f"Analiz: {i + 1}/{len(top_coins)}")
        except Exception:
            coin["total_score"] = coin.get("base_score", 0)
            analyzed.append(coin)

    # Skora göre sırala
    analyzed.sort(key=lambda x: x.get("total_score", 0), reverse=True)

    # Minimum skor filtresi
    min_score = settings.get("min_score", 60)
    final = [c for c in analyzed if c.get("total_score", 0) >= min_score]

    # Log
    if final:
        log_results(final)

    # Telegram
    if settings.get("telegram_enabled") and final:
        btc = get_btc_status(settings)
        msg = f"🔍 <b>Tarama Sonuçları</b>\n"
        msg += f"BTC: ${btc['price']:,.0f} ({btc['change']:+.1f}%)\n\n"
        for c in final[:5]:
            emoji = "🟢" if c.get("direction") == "LONG" else "🔴" if c.get("direction") == "SHORT" else "⚪"
            msg += f"{emoji} <b>{c['symbol']}</b> ({c['exchange']})\n"
            msg += f"   Fiyat: ${c['price']:.4f} | Skor: {c['total_score']}\n"
            msg += f"   T3: {c.get('t3_trend', '—')} | WT: {c.get('wt_signal', '—')}\n\n"
        send_telegram(msg, settings)

    return final, new_oi, counts


# ══════════════════════════════════════════════════════════════════════════════
#  TKINTER ARAYÜZÜ — V2 TARZI
# ══════════════════════════════════════════════════════════════════════════════

class ScannerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("◈ Kripto Tarayıcı v10.0 — Binance & BingX")
        self.geometry("1200x750")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(900, 500)

        # Durum değişkenleri
        self.settings = load_settings()
        self.prev_oi = {}
        self.results = []
        self.scanning = False
        self.countdown = self.settings["scan_interval"] * 60
        self.result_queue = queue.Queue()

        self._apply_style()
        self._build_ui()
        self._start_timer()
        self._process_queue()

    # ── Ttk Stil ──
    def _apply_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Treeview",
                     background=BG2, foreground=TEXT,
                     fieldbackground=BG2, rowheight=28,
                     font=("Consolas", 10))
        s.configure("Treeview.Heading",
                     background=BG3, foreground=ACCENT,
                     font=("Consolas", 9, "bold"),
                     relief="flat")
        s.map("Treeview",
               background=[("selected", BG4)],
               foreground=[("selected", ACCENT)])

    # ── Yardımcı: Buton oluştur ──
    def _btn(self, parent, text, bg_color, cmd, fg_color=BG):
        return tk.Button(
            parent, text=text,
            font=("Consolas", 9, "bold"),
            fg=fg_color, bg=bg_color,
            activebackground=bg_color,
            relief="flat", padx=10, pady=5,
            cursor="hand2", command=cmd
        )

    # ── Yardımcı: Filtre chip'i oluştur ──
    def _chip(self, parent, label, setting_key, op, unit, color):
        """
        Filtre barındaki chip widget'ı
        Öğretici: Chip = küçük etiket. Kullanıcıya hangi filtrelerin aktif
        olduğunu gösterir. V2 arayüzünde bunlar filtre barında sıralanır.
        """
        frame = tk.Frame(parent, bg=BG2)
        frame.pack(side="left", padx=6)
        tk.Label(frame, text=label, font=("Consolas", 8),
                 fg=TEXT_DIM, bg=BG2).pack(side="left")
        val = self.settings.get(setting_key, "?")
        if isinstance(val, float) and val >= 1_000_000:
            display = f"{op} ${val / 1_000_000:.0f}M"
        elif isinstance(val, float):
            display = f"{op} {val}{unit}"
        else:
            display = f"{op} {val}{unit}"
        lbl = tk.Label(frame, text=display, font=("Consolas", 9, "bold"),
                        fg=color, bg=BG2)
        lbl.pack(side="left", padx=(3, 0))
        return lbl

    # ══════════════════════════════════════════════════════════════════════════
    #  ANA ARAYÜZ İNŞASI
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        # ── HEADER ──
        header = tk.Frame(self, bg=BG, pady=10)
        header.pack(fill="x", padx=18)

        tk.Label(header, text="◈ KRIPTO TARAYICI",
                 font=("Consolas", 17, "bold"),
                 fg=ACCENT, bg=BG).pack(side="left")
        tk.Label(header, text=" v10.0",
                 font=("Consolas", 10),
                 fg=TEXT_DIM, bg=BG).pack(side="left", pady=4)

        # Sağ taraf: butonlar + durum
        right = tk.Frame(header, bg=BG)
        right.pack(side="right")

        self.status_lbl = tk.Label(right, text="● Hazır",
                                    font=("Consolas", 10), fg=GREEN, bg=BG)
        self.status_lbl.pack(side="right", padx=(10, 0))

        self.timer_lbl = tk.Label(right, text="⏱ --:--",
                                   font=("Consolas", 11), fg=TEXT_DIM, bg=BG)
        self.timer_lbl.pack(side="right", padx=(0, 12))

        self._btn(right, "▶  TARA", ACCENT,
                  self._manual_scan).pack(side="right", padx=3)
        self._btn(right, "⚙  AYARLAR", BG4,
                  self._open_settings, fg_color=TEXT).pack(side="right", padx=3)
        self._btn(right, "📋  GEÇMİŞ", BG4,
                  self._open_log, fg_color=TEXT).pack(side="right", padx=3)
        self._btn(right, "🔄  TEMİZLE", BG4,
                  self._clear_results, fg_color=TEXT).pack(side="right", padx=3)

        # ── FİLTRE BARI ──
        fbar = tk.Frame(self, bg=BG2, pady=7)
        fbar.pack(fill="x", padx=18, pady=(0, 8))

        self.filter_labels = {}
        self.filter_labels["vol"] = self._chip(
            fbar, "Hacim Değ.", "vol_change_min", ">", "%", ACCENT)
        self.filter_labels["fund"] = self._chip(
            fbar, "Fonlama", "funding_max", "<", "%", RED)
        self.filter_labels["oi"] = self._chip(
            fbar, "OI Değ.", "oi_change_min", ">", "%", PURPLE)
        self.filter_labels["price"] = self._chip(
            fbar, "Fiyat Değ.", "price_change_max", "<", "%", GREEN)
        self.filter_labels["minvol"] = self._chip(
            fbar, "Min Hacim", "min_volume_usd", ">", "$", YELLOW)

        tk.Frame(fbar, bg=BORDER, width=1).pack(side="left", fill="y", padx=10)

        self.match_lbl = tk.Label(fbar, text="— eşleşme",
                                   font=("Consolas", 10, "bold"),
                                   fg=TEXT_DIM, bg=BG2)
        self.match_lbl.pack(side="left", padx=8)

        self.scan_info_lbl = tk.Label(fbar, text="",
                                       font=("Consolas", 9),
                                       fg=TEXT_DIM, bg=BG2)
        self.scan_info_lbl.pack(side="right", padx=16)

        # ── BTC DURUM BARI ──
        btc_bar = tk.Frame(self, bg=BG3, pady=4)
        btc_bar.pack(fill="x", padx=18, pady=(0, 5))

        self.btc_lbl = tk.Label(btc_bar,
                                 text="₿ BTC: — | — | —",
                                 font=("Consolas", 10, "bold"),
                                 fg=YELLOW, bg=BG3)
        self.btc_lbl.pack(side="left", padx=10)

        self.progress_lbl = tk.Label(btc_bar, text="",
                                      font=("Consolas", 9),
                                      fg=TEXT_DIM, bg=BG3)
        self.progress_lbl.pack(side="right", padx=10)

        # ── ANA TABLO ──
        table_frame = tk.Frame(self, bg=BG)
        table_frame.pack(fill="both", expand=True, padx=18, pady=(0, 8))

        columns = (
            "Skor", "Borsa", "Sembol", "Fiyat", "Yön",
            "T3 Trend", "WT Sinyal", "RSI",
            "Fiyat Değ.", "Hacim ($)", "Fonlama", "OI Değ."
        )
        widths = (60, 70, 80, 100, 70, 90, 100, 50, 80, 100, 70, 70)

        self.tree = ttk.Treeview(table_frame, columns=columns,
                                  show="headings", height=20)

        for col, w in zip(columns, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="center", minwidth=50)

        # Scrollbar
        sb_y = ttk.Scrollbar(table_frame, orient="vertical",
                              command=self.tree.yview)
        sb_x = ttk.Scrollbar(table_frame, orient="horizontal",
                              command=self.tree.xview)
        self.tree.configure(yscrollcommand=sb_y.set,
                            xscrollcommand=sb_x.set)
        sb_y.pack(side="right", fill="y")
        sb_x.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        # Sağ tık menüsü
        self.ctx_menu = tk.Menu(self, tearoff=0, bg=BG3, fg=TEXT,
                                 font=("Consolas", 9))
        self.ctx_menu.add_command(label="📊 TradingView'da Aç",
                                   command=self._open_tv)
        self.ctx_menu.add_command(label="🔍 Detaylı Analiz",
                                   command=self._detailed_analysis)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="📋 Kopyala",
                                   command=self._copy_symbol)

        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Double-1>", lambda e: self._open_tv())

        # ── ALT BAR ──
        footer = tk.Frame(self, bg=BG2, pady=5)
        footer.pack(fill="x", padx=18, side="bottom")

        self.footer_lbl = tk.Label(
            footer,
            text="Kripto Tarayıcı v10.0 | T3 + WaveTrend + VMC + BB | Binance & BingX",
            font=("Consolas", 8),
            fg=TEXT_DIM, bg=BG2
        )
        self.footer_lbl.pack()

    # ══════════════════════════════════════════════════════════════════════════
    #  TARAMA İŞLEMLERİ
    # ══════════════════════════════════════════════════════════════════════════

    def _manual_scan(self):
        """Manuel tarama başlat"""
        if self.scanning:
            return
        self.scanning = True
        self.status_lbl.config(text="● Taranıyor...", fg=YELLOW)
        threading.Thread(target=self._run_scan, daemon=True).start()

    def _run_scan(self):
        """Arka planda tarama yap"""
        try:
            def progress(msg):
                self.result_queue.put(("progress", msg))

            results, new_oi, counts = full_scan(
                self.prev_oi, self.settings, progress_callback=progress
            )
            self.prev_oi.update(new_oi)
            self.result_queue.put(("results", results, counts))
        except Exception as e:
            self.result_queue.put(("error", str(e)))

    def _process_queue(self):
        """
        Queue'dan sonuçları al ve UI'ı güncelle
        Öğretici: Tkinter tek thread'li çalışır. Arka plan thread'i
        doğrudan UI'a dokunamaz (çöker). Bu yüzden queue kullanıyoruz:
        1. Arka plan thread sonuçları queue'ya koyar
        2. Ana thread (after ile) queue'yu kontrol eder
        3. Sonuç varsa UI'ı günceller
        """
        try:
            while True:
                item = self.result_queue.get_nowait()

                if item[0] == "progress":
                    self.progress_lbl.config(text=item[1])

                elif item[0] == "results":
                    results, counts = item[1], item[2]
                    self._display_results(results)
                    bn = counts.get("binance", 0)
                    bx = counts.get("bingx", 0)
                    self.scan_info_lbl.config(
                        text=f"Binance: {bn} | BingX: {bx} | Toplam: {bn + bx}"
                    )
                    self.match_lbl.config(
                        text=f"{len(results)} eşleşme",
                        fg=GREEN if results else TEXT_DIM
                    )
                    self.scanning = False
                    self.countdown = self.settings["scan_interval"] * 60
                    self.status_lbl.config(text="● Hazır", fg=GREEN)
                    self.progress_lbl.config(text="")

                    # BTC güncelle
                    btc = get_btc_status(self.settings)
                    color = GREEN if btc["change"] > 0 else RED
                    self.btc_lbl.config(
                        text=f"₿ BTC: ${btc['price']:,.0f} | "
                             f"{btc['change']:+.1f}% | {btc['trend']}",
                        fg=color
                    )

                elif item[0] == "error":
                    self.status_lbl.config(text=f"● HATA", fg=RED)
                    self.progress_lbl.config(text=str(item[1]))
                    self.scanning = False

        except queue.Empty:
            pass

        self.after(200, self._process_queue)

    def _display_results(self, results):
        """Sonuçları tabloya yaz"""
        # Tabloyu temizle
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.results = results

        for r in results:
            direction = r.get("direction", "NÖTR")
            tag = "long" if direction == "LONG" else "short" if direction == "SHORT" else "neutral"

            vol_str = f"${r['volume_usd']:,.0f}" if r.get('volume_usd') else "—"

            self.tree.insert("", "end", values=(
                r.get("total_score", r.get("base_score", 0)),
                r.get("exchange", ""),
                r.get("symbol", ""),
                f"${r['price']:.4f}" if r.get('price', 0) < 1 else f"${r['price']:,.2f}",
                direction,
                r.get("t3_trend", "—"),
                r.get("wt_signal", "—"),
                r.get("rsi", "—"),
                f"{r.get('price_change', 0):.1f}%",
                vol_str,
                f"{r.get('funding', 0):.4f}%",
                f"{r.get('oi_change', 0):.1f}%",
            ), tags=(tag,))

        # Renklendirme
        self.tree.tag_configure("long", foreground=GREEN)
        self.tree.tag_configure("short", foreground=RED)
        self.tree.tag_configure("neutral", foreground=TEXT)

    # ── Zamanlayıcı ──
    def _start_timer(self):
        """Geri sayım ve otomatik tarama"""
        if not self.scanning:
            self.countdown -= 1
            if self.countdown <= 0:
                self._manual_scan()
            else:
                mins = self.countdown // 60
                secs = self.countdown % 60
                self.timer_lbl.config(text=f"⏱ {mins:02d}:{secs:02d}")
        self.after(1000, self._start_timer)

    # ── Sağ Tık Menüsü ──
    def _show_context_menu(self, event):
        sel = self.tree.selection()
        if sel:
            self.ctx_menu.post(event.x_root, event.y_root)

    def _get_selected_symbol(self):
        sel = self.tree.selection()
        if sel:
            vals = self.tree.item(sel[0], "values")
            return vals[2] if vals else None  # Sembol sütunu
        return None

    def _open_tv(self):
        """TradingView'da aç"""
        sym = self._get_selected_symbol()
        if sym:
            url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{sym}USDT.P"
            webbrowser.open(url)

    def _copy_symbol(self):
        """Sembolü panoya kopyala"""
        sym = self._get_selected_symbol()
        if sym:
            self.clipboard_clear()
            self.clipboard_append(f"{sym}USDT")

    def _detailed_analysis(self):
        """Seçili coin için detaylı analiz penceresi"""
        sym = self._get_selected_symbol()
        if not sym:
            return

        # İlgili sonucu bul
        coin = None
        for r in self.results:
            if r.get("symbol") == sym:
                coin = r
                break

        if not coin:
            return

        win = tk.Toplevel(self)
        win.title(f"📊 {sym} Detaylı Analiz")
        win.configure(bg=BG)
        win.geometry("500x400")

        tk.Label(win, text=f"◈ {sym}/USDT",
                 font=("Consolas", 16, "bold"),
                 fg=ACCENT, bg=BG).pack(pady=10)

        info_frame = tk.Frame(win, bg=BG2, padx=15, pady=15)
        info_frame.pack(fill="x", padx=20, pady=5)

        rows = [
            ("Borsa", coin.get("exchange", "—")),
            ("Fiyat", f"${coin.get('price', 0):,.4f}"),
            ("Toplam Skor", f"{coin.get('total_score', 0)}"),
            ("Yön", coin.get("direction", "NÖTR")),
            ("T3 Trend (4H)", coin.get("t3_trend", "—")),
            ("WaveTrend (1H)", coin.get("wt_signal", "—")),
            ("RSI (4H)", f"{coin.get('rsi', 0)}"),
            ("MFI", f"{coin.get('mfi', 0)}"),
            ("BB Squeeze", "✅ EVET" if coin.get("bb_squeeze") else "❌ HAYIR"),
            ("Fiyat Değ.", f"{coin.get('price_change', 0):.1f}%"),
            ("Fonlama", f"{coin.get('funding', 0):.4f}%"),
            ("OI Değ.", f"{coin.get('oi_change', 0):.1f}%"),
        ]

        for label, value in rows:
            row = tk.Frame(info_frame, bg=BG2)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, font=("Consolas", 10),
                     fg=TEXT_DIM, bg=BG2, width=18, anchor="w").pack(side="left")
            color = GREEN if "LONG" in str(value) or "↑" in str(value) else \
                    RED if "SHORT" in str(value) or "↓" in str(value) else TEXT
            tk.Label(row, text=value, font=("Consolas", 10, "bold"),
                     fg=color, bg=BG2, anchor="w").pack(side="left")

    # ── Sonuçları Temizle ──
    def _clear_results(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results = []
        self.match_lbl.config(text="— eşleşme", fg=TEXT_DIM)

    # ══════════════════════════════════════════════════════════════════════════
    #  AYARLAR PENCERESİ
    # ══════════════════════════════════════════════════════════════════════════

    def _open_settings(self):
        """
        Ayarlar penceresi
        Öğretici: tk.Toplevel = ana pencereden bağımsız yeni pencere.
        Notebook (sekmeler) ile ayarları kategorilere ayırıyoruz.
        """
        win = tk.Toplevel(self)
        win.title("⚙ Ayarlar")
        win.configure(bg=BG)
        win.geometry("550x600")
        win.resizable(False, False)

        # Notebook (sekmeli yapı)
        style = ttk.Style()
        style.configure("Settings.TNotebook", background=BG)
        style.configure("Settings.TNotebook.Tab",
                         background=BG3, foreground=TEXT,
                         font=("Consolas", 9, "bold"), padding=[10, 5])
        style.map("Settings.TNotebook.Tab",
                   background=[("selected", BG4)],
                   foreground=[("selected", ACCENT)])

        nb = ttk.Notebook(win, style="Settings.TNotebook")
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        entries = {}  # setting_key → Entry widget

        def add_tab(title, fields):
            """Sekme oluştur"""
            tab = tk.Frame(nb, bg=BG)
            nb.add(tab, text=title)

            for i, (label, key, type_hint) in enumerate(fields):
                row = tk.Frame(tab, bg=BG)
                row.pack(fill="x", padx=15, pady=4)

                tk.Label(row, text=label, font=("Consolas", 10),
                         fg=TEXT, bg=BG, width=22, anchor="w").pack(side="left")

                if type_hint == "bool":
                    var = tk.BooleanVar(value=self.settings.get(key, False))
                    cb = tk.Checkbutton(row, variable=var, bg=BG,
                                         fg=ACCENT, selectcolor=BG3,
                                         activebackground=BG)
                    cb.pack(side="left")
                    entries[key] = var
                elif type_hint == "combo":
                    var = tk.StringVar(value=self.settings.get(key, "Tümü"))
                    combo = ttk.Combobox(row, textvariable=var, width=18,
                                          values=["Tümü", "Sadece LONG", "Sadece SHORT"],
                                          state="readonly")
                    combo.pack(side="left")
                    entries[key] = var
                else:
                    ent = tk.Entry(row, font=("Consolas", 10), bg=BG3,
                                    fg=TEXT, insertbackground=ACCENT,
                                    width=20, relief="flat")
                    ent.insert(0, str(self.settings.get(key, "")))
                    ent.pack(side="left")
                    entries[key] = ent

        # Sekmeler
        add_tab("📊 Tarama", [
            ("Tarama Aralığı (dk)", "scan_interval", "int"),
            ("Min Hacim ($)", "min_volume_usd", "int"),
            ("Min Skor", "min_score", "int"),
            ("Min R/R", "min_rr", "float"),
            ("Gösterim Modu", "show_mode", "combo"),
        ])

        add_tab("🔧 Filtreler", [
            ("Hacim Değ. Min (%)", "vol_change_min", "float"),
            ("Fonlama Max (%)", "funding_max", "float"),
            ("OI Değ. Min (%)", "oi_change_min", "float"),
            ("Fiyat Değ. Max (%)", "price_change_max", "float"),
        ])

        add_tab("📈 İndikatörler", [
            ("T3 Periyot", "t3_period", "int"),
            ("T3 V Faktör", "t3_v_factor", "float"),
            ("WT Kanal Uzunluğu", "wt_channel_len", "int"),
            ("WT Ortalama Uzunluğu", "wt_avg_len", "int"),
            ("WT Overbought", "wt_ob_level", "int"),
            ("WT Oversold", "wt_os_level", "int"),
            ("BB Periyot", "bb_period", "int"),
            ("BB Std Dev", "bb_std_dev", "float"),
        ])

        add_tab("🏦 Borsalar", [
            ("Binance Futures", "use_binance", "bool"),
            ("BingX", "use_bingx", "bool"),
            ("BTC Filtre", "btc_filter", "bool"),
            ("BTC Düşüş Eşiği (%)", "btc_drop_pct", "float"),
        ])

        add_tab("📱 Telegram", [
            ("Telegram Aktif", "telegram_enabled", "bool"),
            ("Bot Token", "telegram_token", "str"),
            ("Chat ID", "telegram_chat_id", "str"),
        ])

        add_tab("🔑 API", [
            ("CoinGlass Kullan", "use_coinglass", "bool"),
            ("CoinGlass API Key", "coinglass_api_key", "str"),
        ])

        # Kaydet butonu
        def save():
            for key, widget in entries.items():
                if isinstance(widget, tk.BooleanVar):
                    self.settings[key] = widget.get()
                elif isinstance(widget, tk.StringVar):
                    self.settings[key] = widget.get()
                elif isinstance(widget, tk.Entry):
                    val = widget.get().strip()
                    # Tip dönüşümü
                    old = self.settings.get(key)
                    try:
                        if isinstance(old, int):
                            self.settings[key] = int(val)
                        elif isinstance(old, float):
                            self.settings[key] = float(val)
                        else:
                            self.settings[key] = val
                    except (ValueError, TypeError):
                        self.settings[key] = val

            save_settings(self.settings)
            self.countdown = self.settings["scan_interval"] * 60
            win.destroy()
            messagebox.showinfo("Ayarlar", "✅ Ayarlar kaydedildi!")

        btn_frame = tk.Frame(win, bg=BG)
        btn_frame.pack(pady=10)
        self._btn(btn_frame, "💾  KAYDET", GREEN, save).pack(side="left", padx=5)
        self._btn(btn_frame, "❌  İPTAL", RED,
                  win.destroy, fg_color=TEXT).pack(side="left", padx=5)

    # ══════════════════════════════════════════════════════════════════════════
    #  GEÇMİŞ LOG PENCERESİ
    # ══════════════════════════════════════════════════════════════════════════

    def _open_log(self):
        """Tarama geçmişi penceresi"""
        if not os.path.exists(LOG_FILE):
            messagebox.showinfo("Geçmiş", "Henüz kayıt yok.")
            return

        win = tk.Toplevel(self)
        win.title("📋 Tarama Geçmişi")
        win.configure(bg=BG)
        win.geometry("1000x500")

        cols = ("Zaman", "Borsa", "Sembol", "Fiyat", "Skor",
                "Yön", "T3", "WT", "RSI", "Fiyat Değ.", "Fonlama", "OI Değ.")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=80, anchor="center", minwidth=50)

        sb = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        try:
            with open(LOG_FILE, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                for row in reversed(rows[-500:]):
                    tree.insert("", "end", values=(
                        row.get("zaman", ""),
                        row.get("borsa", ""),
                        row.get("sembol", ""),
                        row.get("fiyat", ""),
                        row.get("skor", ""),
                        row.get("yön", ""),
                        row.get("t3_trend", ""),
                        row.get("wt_sinyal", ""),
                        row.get("rsi", ""),
                        row.get("fiyat_deg", ""),
                        row.get("fonlama", ""),
                        row.get("oi_deg", ""),
                    ))
        except Exception as e:
            tk.Label(win, text=f"Log okunamadı: {e}",
                     fg=RED, bg=BG).pack()

        # Temizle butonu
        def clear_log():
            if messagebox.askyesno("Geçmiş", "Tüm geçmiş silinsin mi?"):
                try:
                    os.remove(LOG_FILE)
                    win.destroy()
                except Exception:
                    pass

        self._btn(win, "🗑  GEÇMİŞİ TEMİZLE", RED,
                  clear_log, fg_color=TEXT).pack(pady=5)


# ══════════════════════════════════════════════════════════════════════════════
#  BAŞLAT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = ScannerApp()
    app.mainloop()
