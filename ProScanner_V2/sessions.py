"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              TRADING SESSIONS — Seans Analizi                              ║
║                Asia / London / New York / Overlap                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

📚 EĞİTİM NOTU — TRADİNG SESSİONLARI:
══════════════════════════════════════
Kripto 7/24 açık olsa da, hacim ve volatilite SEANS SAATLERİNE göre değişir.
Çünkü büyük oyuncular (kurumsal fonlar, bankalar) belirli saatlerde aktif.

SEANSLAR (UTC):
  🌏 ASIA     : 00:00 - 08:00 UTC  (Tokyo, Shanghai, Sydney)
  🇪🇺 LONDON  : 07:00 - 16:00 UTC  (Avrupa)
  🇺🇸 NEW YORK: 13:00 - 22:00 UTC  (Amerika)

OVERLAP (Çakışma) saatleri EN YOĞUN saatlerdir:
  London-NY Overlap: 13:00 - 16:00 UTC → En yüksek hacim + volatilite
  Asia-London Overlap: 07:00 - 08:00 UTC

Neden önemli?
  1. Asia saatlerinde hacim düşük → fake breakout riski yüksek
  2. London açılışı genellikle günün yönünü belirler
  3. NY açılışı en yüksek volatiliteyi yaratır
  4. NY kapanışından sonra → düşük hacim, yatay hareket

Türkiye saati (UTC+3):
  Asia:   03:00 - 11:00
  London: 10:00 - 19:00
  NY:     16:00 - 01:00
  Overlap: 16:00 - 19:00
"""

from datetime import datetime, timezone, timedelta
from typing import Dict
import numpy as np
import pandas as pd


# Seans tanımları (UTC saatleri)
SESSIONS = {
    "asia": {
        "name": "🌏 Asia (Tokyo)",
        "start_utc": 0,
        "end_utc": 8,
        "color": "#f59e0b",        # Sarı
        "typical_volume": "low",
        "typical_volatility": "low",
        "description": "Düşük hacim, yatay hareket baskın. Fake breakout riski yüksek.",
    },
    "london": {
        "name": "🇪🇺 London",
        "start_utc": 7,
        "end_utc": 16,
        "color": "#3b82f6",        # Mavi
        "typical_volume": "high",
        "typical_volatility": "medium-high",
        "description": "Günün yönü genelde burada belirlenir. İlk 2 saat en agresif.",
    },
    "new_york": {
        "name": "🇺🇸 New York",
        "start_utc": 13,
        "end_utc": 22,
        "color": "#22c55e",        # Yeşil
        "typical_volume": "highest",
        "typical_volatility": "highest",
        "description": "En yüksek hacim ve volatilite. Büyük haberler bu seansta gelir.",
    },
    "overlap": {
        "name": "🔥 London-NY Overlap",
        "start_utc": 13,
        "end_utc": 16,
        "color": "#ef4444",        # Kırmızı
        "typical_volume": "peak",
        "typical_volatility": "peak",
        "description": "Günün EN yoğun saatleri. En iyi giriş fırsatları burada.",
    },
}


def get_current_session() -> Dict:
    """
    Şu anda hangi seansta olduğumuzu belirler.

    📚 NEDEN ÖNEMLİ?
    Asia saatinde açılan pozisyon London açılışında stop yiyebilir.
    London saatinde açılan pozisyon NY açılışında hedefini bulabilir.
    Seans bilmek = doğru zamanda trade yapmak.
    """
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour

    active_sessions = []
    for key, session in SESSIONS.items():
        start = session["start_utc"]
        end = session["end_utc"]
        if start <= hour < end:
            active_sessions.append(key)

    # Türkiye saati
    turkey_tz = timezone(timedelta(hours=3))
    now_turkey = now_utc.astimezone(turkey_tz)

    return {
        "utc_time": now_utc.strftime("%H:%M"),
        "turkey_time": now_turkey.strftime("%H:%M"),
        "active_sessions": active_sessions,
        "is_overlap": "overlap" in active_sessions,
        "session_info": [SESSIONS[s] for s in active_sessions] if active_sessions else [{
            "name": "⏸ Off-hours",
            "description": "Düşük hacim periyodu. İdeal trade zamanı değil.",
            "color": "#64748b",
        }],
    }


def analyze_session_volume(df: pd.DataFrame) -> Dict:
    """
    DataFrame'deki mumları seanslara göre gruplar ve
    her seansın hacim + volatilite profilini çıkarır.

    📚 BU NE İŞE YARAR?
    Bir coin'in hacmi hangi seansta en yüksek?
    Eğer Asia'da düşük hacimle hareket ediyorsa → güvenilmez.
    Eğer London-NY overlap'te hareket ediyorsa → güçlü sinyal.
    """
    if df.index.tz is None:
        # Timezone yoksa UTC varsay
        df = df.copy()
        df.index = df.index.tz_localize("UTC")

    session_stats = {}

    for key, session in SESSIONS.items():
        if key == "overlap":
            continue  # Overlap ayrı hesaplanacak

        start_h = session["start_utc"]
        end_h = session["end_utc"]

        mask = (df.index.hour >= start_h) & (df.index.hour < end_h)
        session_df = df[mask]

        if len(session_df) == 0:
            session_stats[key] = {
                "name": session["name"],
                "avg_volume": 0,
                "avg_range_pct": 0,
                "candle_count": 0,
            }
            continue

        avg_vol = session_df["volume"].mean()
        avg_range = ((session_df["high"] - session_df["low"]) / session_df["close"] * 100).mean()

        session_stats[key] = {
            "name": session["name"],
            "avg_volume": round(avg_vol, 2),
            "avg_range_pct": round(avg_range, 3),
            "candle_count": len(session_df),
            "bullish_pct": round(
                (session_df["close"] > session_df["open"]).sum() / max(len(session_df), 1) * 100, 1
            ),
        }

    # En yoğun seansı belirle
    if session_stats:
        best_session = max(session_stats.items(),
                          key=lambda x: x[1]["avg_volume"] if x[1]["avg_volume"] else 0)
    else:
        best_session = ("unknown", {"name": "N/A"})

    return {
        "sessions": session_stats,
        "best_session": best_session[1]["name"],
        "current": get_current_session(),
    }


def get_session_recommendation() -> Dict:
    """
    Mevcut seansa göre trading önerisi verir.

    📚 SEANS BAZLI STRATEJİ:
    ─────────────────────────
    Asia:   → Scalp veya bekle. Büyük pozisyon AÇMA.
    London: → Trend takip et. Günün yönü burada belli olur.
    NY:     → En agresif trade. Haberler burada gelir.
    Overlap:→ En iyi fırsatlar. Breakout trade'leri burada.
    Off:    → Pozisyon kapatma zamanı, yeni açma.
    """
    current = get_current_session()
    sessions = current["active_sessions"]

    if "overlap" in sessions:
        return {
            "action": "AGRESIF TRADE",
            "emoji": "🔥",
            "message": "London-NY overlap! En yüksek hacim ve volatilite. Breakout fırsatları.",
            "risk_level": "normal",
            "color": "#ef4444",
        }
    elif "new_york" in sessions:
        return {
            "action": "AKTİF TRADE",
            "emoji": "🇺🇸",
            "message": "NY seansı aktif. Yüksek hacim, trend takip stratejisi uygula.",
            "risk_level": "normal",
            "color": "#22c55e",
        }
    elif "london" in sessions:
        return {
            "action": "AKTİF TRADE",
            "emoji": "🇪🇺",
            "message": "London seansı aktif. Günün yönü belirleniyor.",
            "risk_level": "normal",
            "color": "#3b82f6",
        }
    elif "asia" in sessions:
        return {
            "action": "DİKKATLİ OL",
            "emoji": "🌏",
            "message": "Asia seansı — düşük hacim. Fake breakout riski yüksek. Küçük pozisyon.",
            "risk_level": "high",
            "color": "#f59e0b",
        }
    else:
        return {
            "action": "BEKLE",
            "emoji": "⏸",
            "message": "Düşük hacim periyodu. Yeni pozisyon açma, mevcut olanları yönet.",
            "risk_level": "very_high",
            "color": "#64748b",
        }
