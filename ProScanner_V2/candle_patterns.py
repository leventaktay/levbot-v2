"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              CANDLESTICK PATTERNS — Mum Formasyonu Tespiti                 ║
║                      18 Profesyonel Formasyon                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

📚 EĞİTİM NOTU — MUM FORMASYONLARI:
════════════════════════════════════
Mum formasyonları Japonya'da 1700'lerde pirinç tüccarları tarafından geliştirildi.
Her mum 4 bilgi taşır: Open, High, Low, Close (OHLC)

Mum anatomisi:
  ┃  ← Üst fitil (upper wick/shadow) → Reddedilen yüksek fiyatlar
  ┃
  █  ← Gövde (body) → Open-Close arası
  █
  ┃  ← Alt fitil (lower wick) → Reddedilen düşük fiyatlar

Formasyonlar 3 kategoride:
  1. TEK MUM (Single candle) → Hammer, Doji, Marubozu...
  2. İKİ MUM (Double candle) → Engulfing, Harami, Tweezer...
  3. ÜÇ MUM (Triple candle)  → Morning Star, Three Soldiers...

⚠️ KRİTİK KURAL: Formasyon TEK BAŞINA sinyal DEĞİLDİR.
   Destek/direnç seviyesinde oluşması ŞARTTIR.
   Boşlukta oluşan formasyon = gürültü (noise).
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple


def body(o, c):
    """Gövde büyüklüğü (mutlak)."""
    return abs(c - o)

def upper_wick(o, c, h):
    """Üst fitil uzunluğu."""
    return h - max(o, c)

def lower_wick(o, c, l):
    """Alt fitil uzunluğu."""
    return min(o, c) - l

def is_bullish(o, c):
    """Yeşil mum mu?"""
    return c > o

def is_bearish(o, c):
    """Kırmızı mum mu?"""
    return c < o

def avg_body(df, lookback=10):
    """Son N mumun ortalama gövde büyüklüğü — karşılaştırma için."""
    return (df["close"] - df["open"]).abs().rolling(lookback).mean()


# ═══════════════════════════════════════════════════════════════════════════
# TEK MUM FORMASYONLARI
# ═══════════════════════════════════════════════════════════════════════════

def detect_hammer(df: pd.DataFrame) -> pd.Series:
    """
    📚 HAMMER (Çekiç) — Bullish dönüş sinyali
    ─────────────────────────────────────────
    Görünüm: Küçük gövde ÜSTTE, uzun alt fitil (gövdenin 2-3 katı)
    Anlam: Satıcılar fiyatı aşağı itti AMA alıcılar geri aldı.
           → Satış baskısı tükeniyor, dönüş gelebilir.
    Koşul: Düşüş trendinin DİBİNDE oluşmalı (tepede olursa Hanging Man olur)

      ┃
      █  ← küçük gövde
      ┃
      ┃  ← UZUN alt fitil (en az 2× gövde)
    """
    o, c, h, l = df["open"], df["close"], df["high"], df["low"]
    bd = body(o, c)
    lw = lower_wick(o, c, l)
    uw = upper_wick(o, c, h)
    ab = avg_body(df)

    return (
        (lw >= 2 * bd) &          # Alt fitil gövdenin 2 katı+
        (uw <= bd * 0.3) &        # Üst fitil çok kısa
        (bd > ab * 0.3) &         # Gövde çok küçük değil (doji değil)
        (bd <= ab * 1.5)          # Gövde çok büyük değil
    )


def detect_inverted_hammer(df: pd.DataFrame) -> pd.Series:
    """
    📚 INVERTED HAMMER (Ters Çekiç) — Bullish dönüş sinyali
    ────────────────────────────────────────────────────────
      ┃  ← UZUN üst fitil
      ┃
      █  ← küçük gövde ALTTA
    Anlam: Alıcılar yukarı denedi, satıcılar geri itti. AMA
           düşüş trendinde bunu görmek = alıcılar güç topluyor.
    """
    o, c, h, l = df["open"], df["close"], df["high"], df["low"]
    bd = body(o, c)
    lw = lower_wick(o, c, l)
    uw = upper_wick(o, c, h)

    return (
        (uw >= 2 * bd) &
        (lw <= bd * 0.3) &
        (bd > 0)
    )


def detect_hanging_man(df: pd.DataFrame) -> pd.Series:
    """
    📚 HANGING MAN (Asılan Adam) — Bearish dönüş sinyali
    ─────────────────────────────────────────────────────
    Hammer ile AYNI görünüm, ama yükseliş trendinin TEPESİNDE oluşur.
    Anlam: Satıcılar ilk kez güçlü şekilde geri itti → uyarı sinyali.
    """
    return detect_hammer(df)  # Aynı şekil, bağlam farklı (trend yönüne göre yorumlanır)


def detect_shooting_star(df: pd.DataFrame) -> pd.Series:
    """
    📚 SHOOTING STAR (Kayan Yıldız) — Bearish dönüş sinyali
    ───────────────────────────────────────────────────────
    Inverted Hammer ile aynı görünüm, yükseliş tepesinde.
      ┃  ← UZUN üst fitil (reddedildi!)
      █  ← küçük gövde altta
    Anlam: Alıcılar yukarı denedi ama REDDEDİLDİ → zirve sinyali.
    """
    return detect_inverted_hammer(df)


def detect_doji(df: pd.DataFrame) -> pd.Series:
    """
    📚 DOJI — Kararsızlık sinyali
    ─────────────────────────────
    Gövde neredeyse YOK (open ≈ close). Fitiller eşit veya değişken.

    Doji türleri:
      ┃     ← Standard Doji (fitiller eşit)
      ━
      ┃

      ┃     ← Dragonfly Doji (sadece alt fitil → bullish)
      ━

      ━     ← Gravestone Doji (sadece üst fitil → bearish)
      ┃

    Tek başına sinyal DEĞİL — bir sonraki mumun yönü belirler.
    """
    o, c, h, l = df["open"], df["close"], df["high"], df["low"]
    bd = body(o, c)
    ab = avg_body(df)
    total_range = h - l

    return (
        (bd <= ab * 0.1) &          # Gövde neredeyse yok
        (total_range > ab * 0.5)     # Ama fitiller var (tam düz çizgi değil)
    )


def detect_marubozu(df: pd.DataFrame) -> pd.Series:
    """
    📚 MARUBOZU — Güçlü momentum sinyali
    ─────────────────────────────────────
    Fitil YOK veya çok kısa, gövde BÜYÜK.
    Bullish Marubozu: Büyük yeşil mum, fitilsiz → alıcılar tam kontrol
    Bearish Marubozu: Büyük kırmızı mum, fitilsiz → satıcılar tam kontrol

      ████  ← Gövde = neredeyse tüm mum (fitil yok)

    En güçlü tek mum sinyallerinden biri.
    """
    o, c, h, l = df["open"], df["close"], df["high"], df["low"]
    bd = body(o, c)
    uw = upper_wick(o, c, h)
    lw = lower_wick(o, c, l)
    ab = avg_body(df)

    return (
        (bd > ab * 1.5) &           # Gövde ortalamanın 1.5 katı+
        (uw <= bd * 0.05) &         # Üst fitil neredeyse yok
        (lw <= bd * 0.05)           # Alt fitil neredeyse yok
    )


# ═══════════════════════════════════════════════════════════════════════════
# İKİ MUM FORMASYONLARI
# ═══════════════════════════════════════════════════════════════════════════

def detect_bullish_engulfing(df: pd.DataFrame) -> pd.Series:
    """
    📚 BULLISH ENGULFING (Boğa Yutma) — Güçlü bullish dönüş
    ──────────────────────────────────────────────────────────
    İki mum: Küçük kırmızı + Büyük yeşil (öncekini tamamen yutar)

      █     ← 1. mum: küçük kırmızı
     ███    ← 2. mum: BÜYÜK yeşil (1. mumun gövdesini tamamen kaplar)

    Anlam: Satıcılar kontrolü tamamen KAYBETTİ, alıcılar devraldı.
    Ne kadar büyük yutarsa o kadar güçlü sinyal.

    ⚠️ Düşüş trendinin DİBİNDE olması ŞART. Yatay piyasada güvenilmez.
    """
    o, c = df["open"], df["close"]
    o1, c1 = o.shift(1), c.shift(1)

    return (
        is_bearish(o1, c1) &         # Önceki mum kırmızı
        is_bullish(o, c) &           # Şimdiki mum yeşil
        (o <= c1) &                  # Şimdiki open ≤ önceki close
        (c >= o1) &                  # Şimdiki close ≥ önceki open
        (body(o, c) > body(o1, c1))  # Şimdiki gövde daha büyük
    )


def detect_bearish_engulfing(df: pd.DataFrame) -> pd.Series:
    """
    📚 BEARISH ENGULFING (Ayı Yutma) — Güçlü bearish dönüş
    Bullish engulfing'in tam tersi.
    """
    o, c = df["open"], df["close"]
    o1, c1 = o.shift(1), c.shift(1)

    return (
        is_bullish(o1, c1) &
        is_bearish(o, c) &
        (o >= c1) &
        (c <= o1) &
        (body(o, c) > body(o1, c1))
    )


def detect_bullish_harami(df: pd.DataFrame) -> pd.Series:
    """
    📚 BULLISH HARAMI — Potansiyel bullish dönüş
    ─────────────────────────────────────────────
    "Harami" Japonca "hamile" demek.
    Büyük kırmızı mumun İÇİNDE küçük yeşil mum.

     ███   ← 1. mum: BÜYÜK kırmızı
      █    ← 2. mum: küçük yeşil (1. mumun gövdesi içinde)

    Engulfing kadar güçlü DEĞİL ama dikkat çeker.
    """
    o, c = df["open"], df["close"]
    o1, c1 = o.shift(1), c.shift(1)

    return (
        is_bearish(o1, c1) &
        is_bullish(o, c) &
        (o >= c1) & (c <= o1) &
        (body(o, c) < body(o1, c1) * 0.6)
    )


def detect_bearish_harami(df: pd.DataFrame) -> pd.Series:
    """📚 BEARISH HARAMI — Potansiyel bearish dönüş. Bullish harami'nin tersi."""
    o, c = df["open"], df["close"]
    o1, c1 = o.shift(1), c.shift(1)

    return (
        is_bullish(o1, c1) &
        is_bearish(o, c) &
        (o <= c1) & (c >= o1) &
        (body(o, c) < body(o1, c1) * 0.6)
    )


def detect_tweezer_bottom(df: pd.DataFrame) -> pd.Series:
    """
    📚 TWEEZER BOTTOM (Cımbız Dibi) — Bullish dönüş
    ────────────────────────────────────────────────
    İki mumun DİP noktaları neredeyse aynı seviyede.
    Anlam: O seviyede güçlü DESTEK var, iki kez test edildi tuttu.
    """
    l = df["low"]
    o, c = df["open"], df["close"]
    o1, c1 = o.shift(1), c.shift(1)
    ab = avg_body(df)

    return (
        is_bearish(o1, c1) &
        is_bullish(o, c) &
        ((l - l.shift(1)).abs() <= ab * 0.05)  # Dipler neredeyse eşit
    )


def detect_tweezer_top(df: pd.DataFrame) -> pd.Series:
    """📚 TWEEZER TOP (Cımbız Tepe) — Bearish dönüş. Tweezer bottom'ın tersi."""
    h = df["high"]
    o, c = df["open"], df["close"]
    o1, c1 = o.shift(1), c.shift(1)
    ab = avg_body(df)

    return (
        is_bullish(o1, c1) &
        is_bearish(o, c) &
        ((h - h.shift(1)).abs() <= ab * 0.05)
    )


# ═══════════════════════════════════════════════════════════════════════════
# ÜÇ MUM FORMASYONLARI
# ═══════════════════════════════════════════════════════════════════════════

def detect_morning_star(df: pd.DataFrame) -> pd.Series:
    """
    📚 MORNING STAR (Sabah Yıldızı) — Güçlü bullish dönüş
    ──────────────────────────────────────────────────────
    3 mum: Büyük kırmızı → Küçük gövde (yıldız) → Büyük yeşil

      █         ← 1. Büyük kırmızı (düşüş devam ediyor)
       ●        ← 2. Küçük gövde/doji (kararsızlık — DÖNÜM NOKTASI)
        ███     ← 3. Büyük yeşil (alıcılar devraldı)

    En güvenilir 3 mum formasyonlarından biri.
    2. mumun doji olması sinyali GÜÇLENDİRİR.
    """
    o, c = df["open"], df["close"]
    o1, c1 = o.shift(1), c.shift(1)
    o2, c2 = o.shift(2), c.shift(2)
    ab = avg_body(df)

    return (
        is_bearish(o2, c2) &              # 1. mum kırmızı
        (body(o2, c2) > ab * 0.8) &       # 1. mum büyük
        (body(o1, c1) < ab * 0.4) &       # 2. mum küçük (yıldız)
        is_bullish(o, c) &                 # 3. mum yeşil
        (body(o, c) > ab * 0.8) &         # 3. mum büyük
        (c > (o2 + c2) / 2)               # 3. mum, 1. mumun ortasını geçti
    )


def detect_evening_star(df: pd.DataFrame) -> pd.Series:
    """
    📚 EVENING STAR (Akşam Yıldızı) — Güçlü bearish dönüş
    Morning Star'ın tam tersi. Yükseliş tepesinde oluşur.
    """
    o, c = df["open"], df["close"]
    o1, c1 = o.shift(1), c.shift(1)
    o2, c2 = o.shift(2), c.shift(2)
    ab = avg_body(df)

    return (
        is_bullish(o2, c2) &
        (body(o2, c2) > ab * 0.8) &
        (body(o1, c1) < ab * 0.4) &
        is_bearish(o, c) &
        (body(o, c) > ab * 0.8) &
        (c < (o2 + c2) / 2)
    )


def detect_three_white_soldiers(df: pd.DataFrame) -> pd.Series:
    """
    📚 THREE WHITE SOLDIERS (Üç Beyaz Asker) — Güçlü bullish devam
    ──────────────────────────────────────────────────────────────
    3 ardışık büyük yeşil mum, her biri öncekinden daha yüksek kapanır.
    Fitiller kısa (alıcılar tam kontrol).

       ███
      ███
     ███

    Düşüş trendinin sonunda = güçlü dönüş
    Yükseliş içinde = devam sinyali
    """
    o, c, h = df["open"], df["close"], df["high"]
    o1, c1 = o.shift(1), c.shift(1)
    o2, c2 = o.shift(2), c.shift(2)
    ab = avg_body(df)

    return (
        is_bullish(o2, c2) & is_bullish(o1, c1) & is_bullish(o, c) &
        (c > c1) & (c1 > c2) &                  # Her kapanış öncekinden yüksek
        (body(o, c) > ab * 0.6) &                # Gövdeler yeterince büyük
        (body(o1, c1) > ab * 0.6) &
        (body(o2, c2) > ab * 0.6) &
        (upper_wick(o, c, h) < body(o, c) * 0.3) # Üst fitil kısa
    )


def detect_three_black_crows(df: pd.DataFrame) -> pd.Series:
    """
    📚 THREE BLACK CROWS (Üç Kara Karga) — Güçlü bearish devam
    Three White Soldiers'ın tam tersi.
    """
    o, c, l = df["open"], df["close"], df["low"]
    o1, c1 = o.shift(1), c.shift(1)
    o2, c2 = o.shift(2), c.shift(2)
    ab = avg_body(df)

    return (
        is_bearish(o2, c2) & is_bearish(o1, c1) & is_bearish(o, c) &
        (c < c1) & (c1 < c2) &
        (body(o, c) > ab * 0.6) &
        (body(o1, c1) > ab * 0.6) &
        (body(o2, c2) > ab * 0.6) &
        (lower_wick(o, c, l) < body(o, c) * 0.3)
    )


# ═══════════════════════════════════════════════════════════════════════════
# ANA FONKSİYON — TÜM FORMASYONLARI TARA
# ═══════════════════════════════════════════════════════════════════════════

ALL_PATTERNS = {
    # (fonksiyon, yön, güç)  güç: 1=zayıf, 2=orta, 3=güçlü
    "Hammer":              (detect_hammer,              "BULLISH", 2),
    "Inverted Hammer":     (detect_inverted_hammer,     "BULLISH", 1),
    "Shooting Star":       (detect_shooting_star,       "BEARISH", 2),
    "Doji":                (detect_doji,                "NEUTRAL", 1),
    "Marubozu":            (detect_marubozu,            "TREND",   3),
    "Bullish Engulfing":   (detect_bullish_engulfing,   "BULLISH", 3),
    "Bearish Engulfing":   (detect_bearish_engulfing,   "BEARISH", 3),
    "Bullish Harami":      (detect_bullish_harami,      "BULLISH", 1),
    "Bearish Harami":      (detect_bearish_harami,      "BEARISH", 1),
    "Tweezer Bottom":      (detect_tweezer_bottom,      "BULLISH", 2),
    "Tweezer Top":         (detect_tweezer_top,         "BEARISH", 2),
    "Morning Star":        (detect_morning_star,        "BULLISH", 3),
    "Evening Star":        (detect_evening_star,        "BEARISH", 3),
    "Three White Soldiers": (detect_three_white_soldiers, "BULLISH", 3),
    "Three Black Crows":   (detect_three_black_crows,   "BEARISH", 3),
}


def scan_candle_patterns(df: pd.DataFrame, lookback: int = 3) -> Dict:
    """
    Son N mum içinde oluşan tüm formasyonları tespit eder.

    Returns:
        {
            "patterns": [{"name": str, "direction": str, "strength": int, "bar_index": int}],
            "bullish_count": int,
            "bearish_count": int,
            "score": float  (0-100)
        }
    """
    found = []

    for name, (func, direction, strength) in ALL_PATTERNS.items():
        try:
            result = func(df)
            # Son 'lookback' mum içinde oluştu mu?
            recent = result.iloc[-lookback:]
            for i, val in enumerate(recent):
                if val:
                    found.append({
                        "name": name,
                        "direction": direction,
                        "strength": strength,
                        "bars_ago": lookback - 1 - i,
                    })
        except Exception:
            continue

    bullish = [p for p in found if p["direction"] == "BULLISH"]
    bearish = [p for p in found if p["direction"] == "BEARISH"]

    # Skor hesapla
    bull_score = sum(p["strength"] for p in bullish)
    bear_score = sum(p["strength"] for p in bearish)
    total = bull_score + bear_score

    if total == 0:
        score = 50  # Nötr
    else:
        score = 50 + (bull_score - bear_score) / max(total, 1) * 40

    # Marubozu yön tespiti
    for p in found:
        if p["name"] == "Marubozu":
            last_o = df["open"].iloc[-1]
            last_c = df["close"].iloc[-1]
            p["direction"] = "BULLISH" if last_c > last_o else "BEARISH"

    return {
        "patterns": found,
        "bullish_count": len(bullish),
        "bearish_count": len(bearish),
        "score": round(max(0, min(100, score)), 1),
    }
