"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              CHART PATTERNS — Grafik Formasyonu Tespiti                    ║
║          Double Top/Bottom, H&S, Triangle, Wedge, Flag, Channel           ║
╚══════════════════════════════════════════════════════════════════════════════╝

📚 EĞİTİM NOTU — CHART PATTERN TESPİTİ:
════════════════════════════════════════
Chart pattern'ler mum formasyonlarından FARKLIDIR:
  - Mum formasyonu: 1-3 mum → kısa vadeli sinyal
  - Chart pattern: 20-100+ mum → büyük yapısal sinyal

Tespit yöntemi:
  1. Pivot noktaları bul (yerel tepe ve dipler)
  2. Pivot'ları birbirine bağla (trend çizgileri)
  3. Oluşan şekli tanı (üçgen, kama, bayrak vb.)

⚠️ Chart pattern tespiti %100 kesin DEĞİLDİR.
   Algoritmik tespit yaklaşık sonuç verir.
   Her zaman GÖZLE ONAY yap — bu yüzden TradingView linki ekliyoruz.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional


def find_pivots(df: pd.DataFrame, left: int = 5, right: int = 5) -> Tuple[List, List]:
    """
    📚 PİVOT NOKTALARI BULMA:
    ─────────────────────────
    Pivot High: Solundaki ve sağındaki 'left/right' mumdan yüksek olan tepe
    Pivot Low:  Solundaki ve sağındaki 'left/right' mumdan düşük olan dip

    left=5, right=5 → Bir noktanın pivot sayılması için
    hem solunda hem sağında 5 mum daha düşük/yüksek olmalı.

    Bu "zigzag" mantığıdır — gürültüyü filtreler,
    sadece anlamlı tepe ve dipleri bulur.
    """
    highs = df["high"].values
    lows = df["low"].values
    pivot_highs = []  # (index, price)
    pivot_lows = []

    for i in range(left, len(df) - right):
        # Pivot High kontrolü
        is_ph = True
        for j in range(1, left + 1):
            if highs[i] <= highs[i - j]:
                is_ph = False
                break
        if is_ph:
            for j in range(1, right + 1):
                if highs[i] <= highs[i + j]:
                    is_ph = False
                    break
        if is_ph:
            pivot_highs.append((i, highs[i]))

        # Pivot Low kontrolü
        is_pl = True
        for j in range(1, left + 1):
            if lows[i] >= lows[i - j]:
                is_pl = False
                break
        if is_pl:
            for j in range(1, right + 1):
                if lows[i] >= lows[i + j]:
                    is_pl = False
                    break
        if is_pl:
            pivot_lows.append((i, lows[i]))

    return pivot_highs, pivot_lows


def detect_double_top(pivot_highs: List, pivot_lows: List,
                      close: np.ndarray, tolerance: float = 0.035) -> Optional[Dict]:
    """
    📚 DOUBLE TOP (Çift Tepe) — Bearish dönüş formasyonu
    ─────────────────────────────────────────────────────
    Görünüm:
         ╱╲     ╱╲
        ╱  ╲   ╱  ╲
       ╱    ╲ ╱    ╲
      ╱      ╳      ╲    ← Neckline (boyun çizgisi)

    İki tepe AYNI seviyede (tolerance içinde).
    Aralarında bir dip var (neckline).
    İkinci tepeden sonra neckline kırılırsa → SHORT sinyali.

    Hedef: Tepe ile neckline arası mesafe kadar aşağı.
    """
    if len(pivot_highs) < 2 or len(pivot_lows) < 1:
        return None

    # Son iki tepeyi al
    for i in range(len(pivot_highs) - 1, 0, -1):
        h2_idx, h2_price = pivot_highs[i]
        h1_idx, h1_price = pivot_highs[i - 1]

        if h2_idx <= h1_idx:
            continue

        # İki tepe aynı seviyede mi? (tolerance içinde)
        price_diff = abs(h2_price - h1_price) / max(h1_price, 1e-10)
        if price_diff > tolerance:
            continue

        # Aradaki dip (neckline) bul
        neckline = None
        for low_idx, low_price in pivot_lows:
            if h1_idx < low_idx < h2_idx:
                if neckline is None or low_price < neckline[1]:
                    neckline = (low_idx, low_price)

        if neckline is None:
            continue

        # Mevcut fiyat neckline'ın altına düşmüş mü?
        current_price = close[-1]
        avg_peak = (h1_price + h2_price) / 2
        height = avg_peak - neckline[1]
        target = neckline[1] - height

        return {
            "name": "Double Top",
            "direction": "BEARISH",
            "strength": 3,
            "neckline": round(neckline[1], 6),
            "peaks": [round(h1_price, 6), round(h2_price, 6)],
            "target": round(target, 6),
            "confirmed": current_price < neckline[1],
            "description": f"Çift tepe: {h1_price:.4f} / {h2_price:.4f}, Neckline: {neckline[1]:.4f}",
        }

    return None


def detect_double_bottom(pivot_highs: List, pivot_lows: List,
                         close: np.ndarray, tolerance: float = 0.035) -> Optional[Dict]:
    """
    📚 DOUBLE BOTTOM (Çift Dip) — Bullish dönüş formasyonu
    ──────────────────────────────────────────────────────
    Double Top'ın tam tersi. İki dip aynı seviyede.
       ╲      ╳      ╱    ← Neckline
        ╲    ╱ ╲    ╱
         ╲  ╱   ╲  ╱
          ╲╱     ╲╱
    """
    if len(pivot_lows) < 2 or len(pivot_highs) < 1:
        return None

    for i in range(len(pivot_lows) - 1, 0, -1):
        l2_idx, l2_price = pivot_lows[i]
        l1_idx, l1_price = pivot_lows[i - 1]

        if l2_idx <= l1_idx:
            continue

        price_diff = abs(l2_price - l1_price) / max(l1_price, 1e-10)
        if price_diff > tolerance:
            continue

        neckline = None
        for high_idx, high_price in pivot_highs:
            if l1_idx < high_idx < l2_idx:
                if neckline is None or high_price > neckline[1]:
                    neckline = (high_idx, high_price)

        if neckline is None:
            continue

        current_price = close[-1]
        avg_bottom = (l1_price + l2_price) / 2
        height = neckline[1] - avg_bottom
        target = neckline[1] + height

        return {
            "name": "Double Bottom",
            "direction": "BULLISH",
            "strength": 3,
            "neckline": round(neckline[1], 6),
            "bottoms": [round(l1_price, 6), round(l2_price, 6)],
            "target": round(target, 6),
            "confirmed": current_price > neckline[1],
            "description": f"Çift dip: {l1_price:.4f} / {l2_price:.4f}, Neckline: {neckline[1]:.4f}",
        }

    return None


def detect_head_and_shoulders(pivot_highs: List, pivot_lows: List,
                               close: np.ndarray, tolerance: float = 0.02) -> Optional[Dict]:
    """
    📚 HEAD & SHOULDERS (Baş-Omuz) — En güvenilir bearish dönüş
    ──────────────────────────────────────────────────────────────
              ╱╲
             ╱  ╲          ← HEAD (baş — en yüksek)
        ╱╲  ╱    ╲  ╱╲
       ╱  ╲╱      ╲╱  ╲   ← LEFT + RIGHT SHOULDER (omuzlar — eşit)
      ╱                 ╲
     ────────────────────── ← NECKLINE

    3 tepe: Sol omuz < Baş > Sağ omuz
    Sol omuz ≈ Sağ omuz (tolerance içinde)
    Neckline kırılması = onay

    En güvenilir formasyonlardan biri — başarı oranı %80+ (onaylanmış).
    """
    if len(pivot_highs) < 3:
        return None

    for i in range(len(pivot_highs) - 2, 1, -1):
        rs_idx, rs_price = pivot_highs[i]      # Sağ omuz (en son)
        h_idx, h_price = pivot_highs[i - 1]    # Baş
        ls_idx, ls_price = pivot_highs[i - 2]  # Sol omuz

        if not (ls_idx < h_idx < rs_idx):
            continue

        # Baş en yüksek olmalı
        if not (h_price > ls_price and h_price > rs_price):
            continue

        # Omuzlar yaklaşık eşit
        shoulder_diff = abs(ls_price - rs_price) / max(ls_price, 1e-10)
        if shoulder_diff > tolerance * 2:
            continue

        # Neckline: omuzlar arasındaki dipler
        nl_prices = []
        for low_idx, low_price in pivot_lows:
            if ls_idx < low_idx < rs_idx:
                nl_prices.append(low_price)

        if len(nl_prices) < 1:
            continue

        neckline = np.mean(nl_prices)
        current_price = close[-1]
        height = h_price - neckline
        target = neckline - height

        return {
            "name": "Head & Shoulders",
            "direction": "BEARISH",
            "strength": 3,
            "neckline": round(neckline, 6),
            "head": round(h_price, 6),
            "shoulders": [round(ls_price, 6), round(rs_price, 6)],
            "target": round(target, 6),
            "confirmed": current_price < neckline,
            "description": f"Baş-Omuz: Sol:{ls_price:.4f} Baş:{h_price:.4f} Sağ:{rs_price:.4f}",
        }

    return None


def detect_inv_head_and_shoulders(pivot_highs: List, pivot_lows: List,
                                   close: np.ndarray, tolerance: float = 0.02) -> Optional[Dict]:
    """📚 INVERSE HEAD & SHOULDERS — Bullish dönüş. H&S'nin tersi."""
    if len(pivot_lows) < 3:
        return None

    for i in range(len(pivot_lows) - 2, 1, -1):
        rs_idx, rs_price = pivot_lows[i]
        h_idx, h_price = pivot_lows[i - 1]
        ls_idx, ls_price = pivot_lows[i - 2]

        if not (ls_idx < h_idx < rs_idx):
            continue

        if not (h_price < ls_price and h_price < rs_price):
            continue

        shoulder_diff = abs(ls_price - rs_price) / max(ls_price, 1e-10)
        if shoulder_diff > tolerance * 2:
            continue

        nl_prices = []
        for high_idx, high_price in pivot_highs:
            if ls_idx < high_idx < rs_idx:
                nl_prices.append(high_price)

        if len(nl_prices) < 1:
            continue

        neckline = np.mean(nl_prices)
        current_price = close[-1]
        height = neckline - h_price
        target = neckline + height

        return {
            "name": "Inv. Head & Shoulders",
            "direction": "BULLISH",
            "strength": 3,
            "neckline": round(neckline, 6),
            "target": round(target, 6),
            "confirmed": current_price > neckline,
            "description": f"Ters Baş-Omuz: Baş:{h_price:.4f} Neckline:{neckline:.4f}",
        }

    return None


def detect_triangle(pivot_highs: List, pivot_lows: List,
                    close: np.ndarray, min_points: int = 3) -> Optional[Dict]:
    """
    📚 TRIANGLE (Üçgen) — Sıkışma formasyonu
    ─────────────────────────────────────────
    3 türü var:

    1. ASCENDING (Yükselen) — Bullish
       Üst çizgi düz, alt çizgi yükseliyor
       ─────────────
        ╱           → breakout yukarı beklenir
       ╱

    2. DESCENDING (Alçalan) — Bearish
       Alt çizgi düz, üst çizgi düşüyor
       ╲
        ╲           → breakout aşağı beklenir
       ─────────────

    3. SYMMETRIC (Simetrik) — Yön belirsiz
       Her iki çizgi de daralıyor
       ╲
        ╲╱          → patlama yaklaşıyor, yön belirsiz
       ╱

    Hedef: Üçgenin en geniş yerinin yüksekliği kadar.
    """
    if len(pivot_highs) < min_points or len(pivot_lows) < min_points:
        return None

    # Son N pivot'u al
    recent_highs = pivot_highs[-min_points:]
    recent_lows = pivot_lows[-min_points:]

    # Tepeler trendi (düşüyor mu, yatay mı, yükseliyor mu)
    h_prices = [p[1] for p in recent_highs]
    l_prices = [p[1] for p in recent_lows]

    if len(h_prices) < 2 or len(l_prices) < 2:
        return None

    h_slope = (h_prices[-1] - h_prices[0]) / max(len(h_prices), 1)
    l_slope = (l_prices[-1] - l_prices[0]) / max(len(l_prices), 1)

    avg_price = np.mean(close[-20:])
    h_slope_pct = h_slope / avg_price * 100
    l_slope_pct = l_slope / avg_price * 100

    triangle_type = None

    if abs(h_slope_pct) < 0.3 and l_slope_pct > 0.1:
        triangle_type = "Ascending Triangle"
        direction = "BULLISH"
    elif abs(l_slope_pct) < 0.3 and h_slope_pct < -0.1:
        triangle_type = "Descending Triangle"
        direction = "BEARISH"
    elif h_slope_pct < -0.1 and l_slope_pct > 0.1:
        triangle_type = "Symmetric Triangle"
        direction = "NEUTRAL"
    else:
        return None

    height = max(h_prices) - min(l_prices)
    current_price = close[-1]

    return {
        "name": triangle_type,
        "direction": direction,
        "strength": 2,
        "resistance": round(h_prices[-1], 6),
        "support": round(l_prices[-1], 6),
        "height": round(height, 6),
        "confirmed": False,
        "description": f"{triangle_type}: R:{h_prices[-1]:.4f} S:{l_prices[-1]:.4f}",
    }


def detect_flag(df: pd.DataFrame, lookback: int = 50) -> Optional[Dict]:
    """
    📚 FLAG (Bayrak) — Devam formasyonu
    ───────────────────────────────────
    Güçlü hareket (direk) + Hafif geri çekilme (bayrak) + Devam

    Bull Flag:        Bear Flag:
     ╱╲              ╲
    ╱  ╲╱╲            ╲  ╱╲
   ╱    ╲╱╲            ╲╱  ╲╱
  ╱                          ╲

    Direk: Son 10-20 mumda %5+ hareket
    Bayrak: Son 10-15 mumda hafif geri çekilme (dirk yönünün tersi)
    """
    if len(df) < lookback:
        return None

    close = df["close"].values
    recent = close[-lookback:]

    # Direk tespiti (ilk yarı)
    pole_end = lookback // 2
    pole = recent[:pole_end]
    pole_change = (pole[-1] - pole[0]) / pole[0] * 100

    if abs(pole_change) < 3:  # En az %3 hareket
        return None

    # Bayrak tespiti (ikinci yarı)
    flag = recent[pole_end:]
    flag_change = (flag[-1] - flag[0]) / flag[0] * 100

    if pole_change > 3 and -3 < flag_change < 0:
        return {
            "name": "Bull Flag",
            "direction": "BULLISH",
            "strength": 2,
            "pole_change": round(pole_change, 2),
            "flag_change": round(flag_change, 2),
            "confirmed": False,
            "description": f"Bull Flag: Direk +{pole_change:.1f}%, Bayrak {flag_change:.1f}%",
        }
    elif pole_change < -3 and 0 < flag_change < 3:
        return {
            "name": "Bear Flag",
            "direction": "BEARISH",
            "strength": 2,
            "pole_change": round(pole_change, 2),
            "flag_change": round(flag_change, 2),
            "confirmed": False,
            "description": f"Bear Flag: Direk {pole_change:.1f}%, Bayrak +{flag_change:.1f}%",
        }

    return None


# ═══════════════════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════════════════

def scan_chart_patterns(df: pd.DataFrame) -> Dict:
    """
    DataFrame üzerinde tüm chart pattern'leri tarar.
    Birden fazla pivot hassasiyeti dener — hem geniş hem dar.

    📚 EĞİTİM NOTU — NEDEN ÇOK SEVİYELİ PİVOT?
    left=5, right=5 → eski, onaylanmış tepeler (güvenilir ama gecikmeli)
    left=3, right=2 → taze tepeler (daha hızlı tespit, daha az güvenilir)
    İkisini birlikte kullanarak hem eski hem yeni formasyonları yakalarız.
    """
    close = df["close"].values
    found = []

    # Farklı hassasiyet seviyeleri dene
    for left, right in [(5, 5), (3, 2), (3, 1)]:
        pivot_highs, pivot_lows = find_pivots(df, left=left, right=right)

        detectors = [
            lambda ph=pivot_highs, pl=pivot_lows: detect_double_top(ph, pl, close),
            lambda ph=pivot_highs, pl=pivot_lows: detect_double_bottom(ph, pl, close),
            lambda ph=pivot_highs, pl=pivot_lows: detect_head_and_shoulders(ph, pl, close),
            lambda ph=pivot_highs, pl=pivot_lows: detect_inv_head_and_shoulders(ph, pl, close),
            lambda ph=pivot_highs, pl=pivot_lows: detect_triangle(ph, pl, close),
        ]

        for detector in detectors:
            try:
                result = detector()
                if result:
                    # Aynı isimde pattern zaten eklenmişse atla
                    if not any(p["name"] == result["name"] for p in found):
                        found.append(result)
            except Exception:
                continue

    # Flag ayrı çalışır (pivot'a bağlı değil)
    try:
        flag_result = detect_flag(df)
        if flag_result:
            found.append(flag_result)
    except Exception:
        pass

    # Skor hesapla
    if not found:
        score = 50
    else:
        bull = sum(p["strength"] for p in found if p["direction"] == "BULLISH")
        bear = sum(p["strength"] for p in found if p["direction"] == "BEARISH")
        total = bull + bear
        if total == 0:
            score = 50
        else:
            score = 50 + (bull - bear) / total * 35

    return {
        "patterns": found,
        "score": round(max(0, min(100, score)), 1),
    }
