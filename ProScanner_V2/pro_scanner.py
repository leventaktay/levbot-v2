"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    PRO CRYPTO SCANNER v1.0                                  ║
║         TradingView Kalitesinde İndikatörlerle Token Tarama                ║
║                                                                            ║
║  Yazar: Levent & Claude | Tarih: Nisan 2026                               ║
║  Veri Kaynağı: Binance Futures (Türkiye'den erişilebilir)                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

📚 EĞİTİM NOTU - TARAYICI MİMARİSİ:
─────────────────────────────────────
Profesyonel bir tarayıcı 4 katmandan oluşur:
1. VERİ KATMANI     → API'den mum verisi çekme (OHLCV)
2. İNDİKATÖR KATMANI → Teknik gösterge hesaplama
3. PUANLAMA KATMANI  → Her indikatörden sinyal çıkarma ve skorlama
4. SUNUM KATMANI     → Sonuçları filtreleme ve gösterme

Her katman bağımsız çalışır — bu "Separation of Concerns" prensibidir.
Bir indikatörü değiştirmek istersen sadece o fonksiyonu düzenlersin,
geri kalan sistem etkilenmez.
"""

import requests
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import json
import sys
import os

# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 1: YAPILANDIRMA (Configuration)
# ═══════════════════════════════════════════════════════════════════════════
"""
📚 EĞİTİM NOTU - YAPILANDIRMA:
─────────────────────────────
Tüm ayarları tek bir yerde toplamak "Single Source of Truth" prensibidir.
Bir değeri değiştirmek istediğinde kodun içinde arama yapmazsın,
buraya gelir değiştirirsin. Profesyonel yazılımda bu zorunludur.

@dataclass kullanıyoruz çünkü:
- __init__ otomatik oluşur
- __repr__ otomatik oluşur (print edilebilir)
- Tip kontrolü sağlar
- field(default_factory=...) ile mutable default'lar güvenli olur
"""

@dataclass
class ScannerConfig:
    # === Genel Ayarlar ===
    timeframes: List[str] = field(default_factory=lambda: ["4h", "1h", "15m"])
    min_volume_usdt: float = 5_000_000       # Günlük min hacim (USDT)
    min_score: int = 65                       # Minimum toplam skor
    max_coins: int = 100                      # Taranacak max coin sayısı
    top_results: int = 20                     # Gösterilecek sonuç sayısı

    # === İndikatör Parametreleri ===
    # Her birini neden bu değerde kullandığımız açıklanacak
    rsi_period: int = 14                      # RSI standart periyot
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0

    macd_fast: int = 12                       # MACD hızlı EMA
    macd_slow: int = 26                       # MACD yavaş EMA
    macd_signal: int = 9                      # MACD sinyal hattı

    bb_period: int = 20                       # Bollinger Bands periyot
    bb_std: float = 2.0                       # Standart sapma çarpanı

    stoch_rsi_period: int = 14
    stoch_rsi_k: int = 3                      # %K smoothing
    stoch_rsi_d: int = 3                      # %D smoothing

    adx_period: int = 14                      # ADX trend gücü periyodu
    adx_strong_trend: float = 25.0            # Güçlü trend eşiği

    ichimoku_tenkan: int = 9                  # Dönüşüm çizgisi
    ichimoku_kijun: int = 26                  # Temel çizgi
    ichimoku_senkou_b: int = 52               # Senkou Span B

    supertrend_period: int = 10
    supertrend_multiplier: float = 3.0

    ema_fast: int = 9
    ema_mid: int = 21
    ema_slow: int = 55
    ema_trend: int = 200

    atr_period: int = 14

    wavetrend_channel: int = 9                # WT kanal periyodu
    wavetrend_avg: int = 12                   # WT ortalama periyodu
    wavetrend_ob: float = 53.0                # Aşırı alım seviyesi
    wavetrend_os: float = -53.0               # Aşırı satım seviyesi

    t3_period: int = 5                        # Tilson T3 periyodu
    t3_vfactor: float = 0.7                   # Volume factor (0-1 arası)

    mfi_period: int = 14                      # Money Flow Index periyodu

    obv_ema_period: int = 21                  # OBV üzerine EMA

    # === Puanlama Ağırlıkları ===
    """
    📚 EĞİTİM NOTU - AĞIRLIK SİSTEMİ:
    ─────────────────────────────────
    Her indikatörün toplam skora katkısı farklıdır.
    Trend takip eden indikatörler (EMA, Supertrend) daha yüksek ağırlık alır
    çünkü "trend is your friend" — trende karşı gitmek en büyük hatadır.
    Osilatörler (RSI, Stoch RSI) daha düşük ağırlık alır çünkü
    trend piyasalarında yanıltıcı olabilirler.

    Toplam = 100 puan
    """
    weights: Dict[str, float] = field(default_factory=lambda: {
        "trend_ema":       15,   # EMA dizilimi — trend yönü
        "supertrend":      12,   # Supertrend — trend onayı
        "ichimoku":        12,   # Ichimoku — kapsamlı trend
        "macd":            10,   # MACD — momentum + trend
        "adx":              8,   # ADX — trend gücü
        "rsi":              8,   # RSI — aşırı alım/satım
        "stoch_rsi":        7,   # Stoch RSI — hassas momentum
        "bollinger":        7,   # BB — volatilite + squeeze
        "wavetrend":        7,   # WaveTrend — döngüsel momentum
        "volume_obv":       5,   # OBV — hacim onayı
        "mfi":              5,   # MFI — para akışı
        "t3_trend":         4,   # T3 — yumuşak trend
    })


config = ScannerConfig()


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 2: VERİ KATMANI (Data Layer)
# ═══════════════════════════════════════════════════════════════════════════
"""
📚 EĞİTİM NOTU - API VERİ ÇEKME:
──────────────────────────────────
Binance Futures REST API kullanıyoruz çünkü:
1. Türkiye'den erişilebilir (OKX engellenmiş)
2. Rate limit yüksek (1200 req/dakika)
3. USDT-M Futures en likit piyasa

Önemli kavramlar:
- OHLCV = Open, High, Low, Close, Volume (mum verisi)
- Kline = Japonca "çizgi" — mum çubuğu demek
- Perpetual = Vadesi olmayan sürekli kontrat (en likit)
"""

BINANCE_FUTURES_BASE = "https://fapi.binance.com"


def get_futures_symbols(min_volume_usdt: float = 5_000_000) -> List[str]:
    """
    Binance Futures'taki aktif USDT perpetual kontratları çeker.
    Düşük hacimli coinleri filtreler — düşük hacim = manipülasyon riski.

    📚 NEDEN HACİM FİLTRESİ?
    Düşük hacimli coinler:
    - Spread (alış-satış farkı) yüksek → kötü giriş fiyatı
    - Tek bir balina fiyatı %10 oynatabilir
    - Stop-loss'un kayabilir (slippage)
    - İndikatörler güvenilmez sinyal üretir
    """
    try:
        # 24 saatlik ticker verisini çek
        resp = requests.get(f"{BINANCE_FUTURES_BASE}/fapi/v1/ticker/24hr", timeout=15)
        resp.raise_for_status()
        tickers = resp.json()

        symbols = []
        for t in tickers:
            symbol = t["symbol"]
            # Sadece USDT perpetual kontratlar
            if not symbol.endswith("USDT"):
                continue
            # Stablecoin çiftlerini atla (BUSDUSDT vb.)
            if any(s in symbol for s in ["BUSD", "TUSD", "USDC", "DAI", "EUR"]):
                continue

            volume_usdt = float(t["quoteVolume"])
            if volume_usdt >= min_volume_usdt:
                symbols.append({
                    "symbol": symbol,
                    "volume": volume_usdt,
                    "price_change_pct": float(t["priceChangePercent"]),
                    "last_price": float(t["lastPrice"]),
                })

        # Hacme göre sırala — en likit olanlar önce
        symbols.sort(key=lambda x: x["volume"], reverse=True)
        return symbols

    except Exception as e:
        print(f"❌ Sembol listesi alınamadı: {e}")
        return []


def get_klines(symbol: str, interval: str, limit: int = 200) -> Optional[pd.DataFrame]:
    """
    Belirli bir coin için mum verisi çeker.

    📚 EĞİTİM NOTU - NEDEN 200 MUM?
    ─────────────────────────────────
    - EMA 200 hesaplamak için en az 200 mum gerekir
    - Ichimoku Senkou Span B = 52 periyot, ama 26 ileri kaydırıldığı için
      doğru hesap için yeterli geçmiş veri lazım
    - Daha fazla veri → daha güvenilir indikatör değerleri

    DataFrame yapısı:
    | timestamp | open | high | low | close | volume |
    Her satır bir mum çubuğudur.
    """
    try:
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        resp = requests.get(
            f"{BINANCE_FUTURES_BASE}/fapi/v1/klines",
            params=params,
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_vol",
            "taker_buy_quote_vol", "ignore"
        ])

        # Tip dönüşümleri — API string döner, sayıya çevirmemiz lazım
        for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
            df[col] = df[col].astype(float)

        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)

        return df[["open", "high", "low", "close", "volume", "quote_volume"]]

    except Exception as e:
        print(f"  ⚠ {symbol} {interval} verisi alınamadı: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 3: İNDİKATÖR KATMANI (Indicator Engine)
# ═══════════════════════════════════════════════════════════════════════════
"""
📚 GENEL EĞİTİM NOTU — İNDİKATÖR KATEGORİLERİ:
═════════════════════════════════════════════════
İndikatörler 4 ana kategoride sınıflandırılır:

1. TREND İNDİKATÖRLERİ (Trend Following)
   → Fiyatın yönünü belirler
   → EMA, Supertrend, Ichimoku, T3
   → Avantaj: Büyük hareketleri yakalar
   → Dezavantaj: Yatay piyasada yanlış sinyal verir

2. MOMENTUM İNDİKATÖRLERİ (Oscillators)
   → Fiyatın hızını ve gücünü ölçer
   → RSI, Stochastic RSI, MACD, WaveTrend
   → Avantaj: Dönüş noktalarını önceden gösterir
   → Dezavantaj: Güçlü trendde aşırı bölgede "yapışır"

3. VOLATİLİTE İNDİKATÖRLERİ
   → Fiyat dalgalanma genişliğini ölçer
   → Bollinger Bands, ATR
   → Avantaj: Patlama (breakout) öncesini gösterir
   → Dezavantaj: Yön belirtmez, sadece genişlik

4. HACİM İNDİKATÖRLERİ
   → Para akışını ve katılımı ölçer
   → OBV, MFI
   → Avantaj: Fiyat hareketini ONAYLAR veya REDDEDER
   → Dezavantaj: Kripto'da wash trading nedeniyle manipüle edilebilir

Profesyonel yaklaşım: Her kategoriden en az 1 indikatör kullan.
Tek kategori kullanan sistem "confirmation bias" tuzağına düşer.
"""


# ─── 3.1 EMA (Exponential Moving Average) ────────────────────────────────
def calc_ema(series: pd.Series, period: int) -> pd.Series:
    """
    📚 EMA NEDİR?
    ─────────────
    EMA = Üstel Hareketli Ortalama

    SMA (Simple Moving Average) tüm mumlara eşit ağırlık verir.
    EMA son mumlara DAHA FAZLA ağırlık verir → fiyata daha hızlı tepki verir.

    Formül:
      multiplier = 2 / (period + 1)
      EMA_today = (Price_today × multiplier) + (EMA_yesterday × (1 - multiplier))

    TradingView'da:
      EMA 9   → Çok kısa vadeli (scalping)
      EMA 21  → Kısa vadeli (swing)
      EMA 55  → Orta vadeli
      EMA 200 → Uzun vadeli trend çizgisi — ALTIN STANDART

    Profesyonel kullanım:
      - Fiyat > EMA 200 → Boğa piyasası (sadece long aç)
      - Fiyat < EMA 200 → Ayı piyasası (sadece short aç)
      - EMA 9 > EMA 21 > EMA 55 → "Bullish ribbon" (güçlü yükseliş)
      - EMA 9 < EMA 21 < EMA 55 → "Bearish ribbon" (güçlü düşüş)

    DİKKAT: EMA tek başına sinyal DEĞİLDİR, trend yönü belirleyicidir.
    Giriş sinyali için momentum onayı gerekir.
    """
    return series.ewm(span=period, adjust=False).mean()


# ─── 3.2 RSI (Relative Strength Index) ───────────────────────────────────
def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    📚 RSI NEDİR?
    ─────────────
    RSI = Göreceli Güç Endeksi (J. Welles Wilder, 1978)

    Ne yapar: Son N mumda yükselişlerin düşüşlere oranını ölçer.
    Sonuç: 0-100 arası bir değer.

    Formül:
      RS  = Ortalama Kazanç / Ortalama Kayıp
      RSI = 100 - (100 / (1 + RS))

    Yorumlama:
      RSI > 70 → Aşırı alım (fiyat çok hızlı yükseldi, düzeltme olabilir)
      RSI < 30 → Aşırı satım (fiyat çok hızlı düştü, toparlanma olabilir)
      RSI 50   → Nötr bölge

    ⚠️ KRİTİK HATA — YENİ TRADER'LARIN YAPTIĞI:
    "RSI 70'i geçti = hemen short aç" → YANLIŞ!
    Güçlü bir boğa trendinde RSI haftalarca 70+ kalabilir.
    RSI'ın 70'ten GERİ DÖNMESİNİ bekle, sonra divergence kontrol et.

    Divergence (Uyumsuzluk):
      Fiyat yeni zirve yapıyor AMA RSI yapmıyor → Bearish divergence
      Fiyat yeni dip yapıyor AMA RSI yapmıyor → Bullish divergence
      → Bu en güvenilir RSI sinyalidir.

    Wilder'ın orijinal formülü EMA değil, özel bir smoothing kullanır.
    Pandas'ta bunu taklit etmek için ewm(alpha=1/period) kullanırız.
    """
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    # Wilder's smoothing (RMA) — EMA'dan farklıdır
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


# ─── 3.3 MACD (Moving Average Convergence Divergence) ────────────────────
def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26,
              signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    📚 MACD NEDİR?
    ──────────────
    MACD = Hareketli Ortalama Yakınsama/Iraksama (Gerald Appel, 1979)

    Hem TREND hem MOMENTUM bilgisi verir — bu yüzden çok popülerdir.

    3 bileşeni var:
      1. MACD Line    = EMA(fast) - EMA(slow)     → iki EMA arasındaki fark
      2. Signal Line  = EMA(MACD Line, signal)     → MACD'nin ortalaması
      3. Histogram    = MACD Line - Signal Line    → farkın farkı

    Sinyaller:
      MACD Line > Signal Line → Bullish (histogram pozitif)
      MACD Line < Signal Line → Bearish (histogram negatif)
      Histogram büyüyor       → Momentum artıyor
      Histogram küçülüyor     → Momentum zayıflıyor

    Profesyonel kullanım:
      - MACD sıfır çizgisinin ÜSTÜNDE crossover → güçlü boğa sinyali
      - MACD sıfır çizgisinin ALTINDA crossover → güçlü ayı sinyali
      - Histogram divergence → En güvenilir MACD sinyali

    ⚠️ MACD gecikmelidir (lagging) çünkü EMA tabanlıdır.
    Yani hareketten SONRA sinyal verir, ÖNCE değil.
    Bu yüzden tek başına kullanma — RSI veya WaveTrend ile onay al.
    """
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ─── 3.4 Bollinger Bands ─────────────────────────────────────────────────
def calc_bollinger_bands(close: pd.Series, period: int = 20,
                         std_mult: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """
    📚 BOLLINGER BANDS NEDİR?
    ─────────────────────────
    John Bollinger (1983) — Volatilite ölçümünün altın standardı.

    Yapı:
      Middle Band = SMA(period)
      Upper Band  = Middle + (std_mult × StdDev)
      Lower Band  = Middle - (std_mult × StdDev)

    Bandwidth  = (Upper - Lower) / Middle → volatilite genişliği
    %B         = (Price - Lower) / (Upper - Lower) → fiyatın bant içi pozisyonu

    Temel prensipler:
      1. Fiyat zamanın ~%95'ini bantlar içinde geçirir (2σ)
      2. Bantlar DARALDIĞINDA (squeeze) → patlama yaklaşıyor
      3. Bantlar GENİŞLEDİĞİNDE → hareket devam ediyor

    ⚠️ SQUEEZE en önemli sinyaldir:
      Bandwidth son 6 ayın en düşüğüne yakınsa → büyük hareket geliyor
      AMA yön belirtmez! Yukarı da aşağı da olabilir.
      Yön için diğer indikatörlere bak (EMA dizilimi, RSI, MACD).

    Profesyonel BB stratejisi:
      - Squeeze tespit et
      - Yön belirle (EMA, MACD)
      - Fiyatın bandı KIRMASINI bekle
      - Kırılma yönünde giriş yap
    """
    middle = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = middle + (std_mult * std)
    lower = middle - (std_mult * std)

    # Bandwidth: Volatilite ölçüsü (daraldığında squeeze var)
    bandwidth = (upper - lower) / middle

    return upper, middle, lower, bandwidth


# ─── 3.5 Stochastic RSI ──────────────────────────────────────────────────
def calc_stochastic_rsi(close: pd.Series, rsi_period: int = 14,
                        stoch_period: int = 14, k_smooth: int = 3,
                        d_smooth: int = 3) -> Tuple[pd.Series, pd.Series]:
    """
    📚 STOCHASTIC RSI NEDİR?
    ────────────────────────
    Tushar Chande & Stanley Kroll (1994)

    Problem: RSI bazen 30-70 arasında sıkışıp sinyal vermez.
    Çözüm: RSI'ın kendisine Stochastic formülü uygula → daha hassas.

    Formül:
      StochRSI = (RSI - RSI_low) / (RSI_high - RSI_low)
      %K = SMA(StochRSI, k_smooth) × 100
      %D = SMA(%K, d_smooth)

    Yorumlama:
      %K > 80 → Aşırı alım
      %K < 20 → Aşırı satım
      %K, %D'yi yukarı kesiyor → Bullish crossover
      %K, %D'yi aşağı kesiyor → Bearish crossover

    RSI vs Stochastic RSI:
      RSI  → daha yavaş, daha az sinyal, daha güvenilir
      StochRSI → daha hızlı, daha çok sinyal, daha çok false positive

    İkisini birlikte kullan: StochRSI sinyal versin, RSI onaylasın.
    """
    rsi = calc_rsi(close, rsi_period)
    rsi_low = rsi.rolling(window=stoch_period).min()
    rsi_high = rsi.rolling(window=stoch_period).max()

    stoch_rsi = ((rsi - rsi_low) / (rsi_high - rsi_low).replace(0, np.nan)) * 100
    k = stoch_rsi.rolling(window=k_smooth).mean()
    d = k.rolling(window=d_smooth).mean()

    return k.fillna(50), d.fillna(50)


# ─── 3.6 ADX (Average Directional Index) ─────────────────────────────────
def calc_adx(high: pd.Series, low: pd.Series, close: pd.Series,
             period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    📚 ADX NEDİR?
    ─────────────
    J. Welles Wilder (1978) — RSI'ın da yaratıcısı

    ADX trendin GÜCÜNÜ ölçer, YÖNÜNÜ DEĞİL.
    ADX yüksekse trend güçlüdür — ama yükseliş mi düşüş mü bilmezsin.
    Yön bilgisi +DI ve -DI'dan gelir.

    Bileşenler:
      +DI (Plus Directional Indicator)  → Yükseliş gücü
      -DI (Minus Directional Indicator) → Düşüş gücü
      ADX → İkisinin birleşik ortalaması (trend gücü)

    Yorumlama:
      ADX < 20 → Trend yok, yatay piyasa (range)
      ADX 20-25 → Zayıf trend
      ADX 25-50 → Güçlü trend
      ADX > 50  → Çok güçlü trend (nadir)

      +DI > -DI → Boğalar dominant
      -DI > +DI → Ayılar dominant

    Profesyonel kullanım:
      ADX < 20 iken → Trend stratejisi KULLANMA, range strat kullan
      ADX > 25 VE +DI > -DI → Güçlü yükseliş trendi, long fırsatı
      ADX > 25 VE -DI > +DI → Güçlü düşüş trendi, short fırsatı
    """
    high_diff = high.diff()
    low_diff = -low.diff()  # Negatif aldık çünkü düşüş = pozitif -DI

    plus_dm = pd.Series(np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0),
                        index=high.index)
    minus_dm = pd.Series(np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0),
                         index=high.index)

    # True Range hesapla
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)

    # Wilder smoothing
    atr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, min_periods=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, min_periods=period, adjust=False).mean() / atr)

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    return adx.fillna(0), plus_di.fillna(0), minus_di.fillna(0)


# ─── 3.7 Ichimoku Cloud ──────────────────────────────────────────────────
def calc_ichimoku(high: pd.Series, low: pd.Series, close: pd.Series,
                  tenkan: int = 9, kijun: int = 26,
                  senkou_b: int = 52) -> Dict[str, pd.Series]:
    """
    📚 ICHIMOKU CLOUD NEDİR?
    ────────────────────────
    Goichi Hosoda (1968, Japonya) — "Bir bakışta denge" anlamına gelir.

    5 bileşeni var — HEPSİ birlikte kullanılır:
      1. Tenkan-sen (Dönüşüm) = (9H + 9L) / 2  → kısa vadeli orta nokta
      2. Kijun-sen  (Temel)   = (26H + 26L) / 2 → orta vadeli orta nokta
      3. Senkou A   (Span A)  = (Tenkan + Kijun) / 2, 26 ileri kaydır
      4. Senkou B   (Span B)  = (52H + 52L) / 2, 26 ileri kaydır
      5. Chikou     (Gecikme) = Kapanış, 26 geri kaydır

    Bulut (Kumo): Senkou A ile Senkou B arasındaki alan.
      - Fiyat bulutun ÜSTÜNDE → Boğa trendi
      - Fiyat bulutun İÇİNDE → Kararsızlık
      - Fiyat bulutun ALTINDA → Ayı trendi

    Profesyonel sinyaller:
      TK Cross: Tenkan > Kijun → Bullish ("Golden cross" benzeri)
      Price > Bulut + TK Cross + Chikou > Fiyat → GÜÇLÜ boğa sinyali
      Bunun tam tersi → GÜÇLÜ ayı sinyali

    ⚠️ Ichimoku kripto'da iyi çalışır çünkü 7/24 piyasa,
    orijinal parametre Japon borsası için tasarlandı (6 günlük hafta).
    Kripto için bazıları 10/30/60 kullanır ama 9/26/52 standart.
    """
    tenkan_sen = (high.rolling(tenkan).max() + low.rolling(tenkan).min()) / 2
    kijun_sen = (high.rolling(kijun).max() + low.rolling(kijun).min()) / 2

    senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun)
    senkou_b_line = ((high.rolling(senkou_b).max() + low.rolling(senkou_b).min()) / 2).shift(kijun)

    chikou = close.shift(-kijun)

    return {
        "tenkan": tenkan_sen,
        "kijun": kijun_sen,
        "senkou_a": senkou_a,
        "senkou_b": senkou_b_line,
        "chikou": chikou,
    }


# ─── 3.8 Supertrend ──────────────────────────────────────────────────────
def calc_supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
                    period: int = 10, multiplier: float = 3.0) -> Tuple[pd.Series, pd.Series]:
    """
    📚 SUPERTREND NEDİR?
    ────────────────────
    Olivier Seban — ATR tabanlı trend takip indikatörü.

    TradingView'da en çok kullanılan indikatörlerden biridir çünkü
    NET sinyal verir: Ya LONG ya SHORT — arada kalmaz.

    Mantık:
      ATR = Average True Range → piyasanın ortalama volatilitesi
      Upper Band = (High + Low) / 2 + (multiplier × ATR)
      Lower Band = (High + Low) / 2 - (multiplier × ATR)

      Fiyat Upper Band'i aşağı kırarsa → SELL
      Fiyat Lower Band'i yukarı kırarsa → BUY

    Multiplier ayarı:
      Düşük (2.0) → Daha hassas, daha çok sinyal, daha çok false alarm
      Yüksek (4.0) → Daha az sinyal, ama daha güvenilir
      Standart (3.0) → TradingView default, iyi denge noktası

    Trailing stop olarak da kullanılır:
      Long pozisyondayken Supertrend çizgisi stop-loss'un olur.
      Fiyat yükseldikçe Supertrend da yükselir → kâr korunur.
    """
    hl2 = (high + low) / 2
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)

    supertrend = pd.Series(0.0, index=close.index)
    direction = pd.Series(1, index=close.index)  # 1 = bullish, -1 = bearish

    for i in range(1, len(close)):
        # Band süreklilik kuralları
        if lower_band.iloc[i] < lower_band.iloc[i-1] and close.iloc[i-1] > lower_band.iloc[i-1]:
            pass  # lower band sadece yükselebilir (bullish modda)
        elif close.iloc[i-1] > lower_band.iloc[i-1]:
            lower_band.iloc[i] = max(lower_band.iloc[i], lower_band.iloc[i-1])

        if upper_band.iloc[i] > upper_band.iloc[i-1] and close.iloc[i-1] < upper_band.iloc[i-1]:
            pass
        elif close.iloc[i-1] < upper_band.iloc[i-1]:
            upper_band.iloc[i] = min(upper_band.iloc[i], upper_band.iloc[i-1])

        # Yön belirleme
        if supertrend.iloc[i-1] == upper_band.iloc[i-1]:
            if close.iloc[i] > upper_band.iloc[i]:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
            else:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
        else:
            if close.iloc[i] < lower_band.iloc[i]:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
            else:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1

    return supertrend, direction


# ─── 3.9 WaveTrend (VuManChu Cipher B stili) ─────────────────────────────
def calc_wavetrend(high: pd.Series, low: pd.Series, close: pd.Series,
                   channel_len: int = 9, avg_len: int = 12) -> Tuple[pd.Series, pd.Series]:
    """
    📚 WAVETREND NEDİR?
    ───────────────────
    LazyBear'ın WaveTrend Oscillator'ı — VuManChu Cipher B'nin çekirdeği.

    TradingView'da en popüler özel indikatördür. Momentum döngülerini
    çok temiz gösterir.

    Mantık:
      1. HLC3 (typical price) hesapla
      2. EMA(HLC3, channel) → yumuşatılmış fiyat
      3. EMA(|HLC3 - EMA|, channel) → ortalama sapma
      4. CI = (HLC3 - EMA) / (0.015 × sapma) → normalize edilmiş momentum
      5. WT1 = EMA(CI, avg_len) → ana çizgi
      6. WT2 = SMA(WT1, 4) → sinyal çizgisi

    Sinyaller:
      WT1 > WT2 → Bullish momentum
      WT1 < WT2 → Bearish momentum
      WT1 > 53  → Aşırı alım (overbought zone)
      WT1 < -53 → Aşırı satım (oversold zone)

    En güçlü sinyal:
      WT oversold bölgede + WT1 > WT2 crossover → Strong buy
      WT overbought bölgede + WT1 < WT2 crossover → Strong sell

    RSI'dan farkı: WaveTrend daha az gürültülü ve döngüleri daha net gösterir.
    """
    hlc3 = (high + low + close) / 3
    ema_hlc3 = calc_ema(hlc3, channel_len)
    d = calc_ema((hlc3 - ema_hlc3).abs(), channel_len)

    ci = (hlc3 - ema_hlc3) / (0.015 * d.replace(0, np.nan))
    ci = ci.fillna(0)

    wt1 = calc_ema(ci, avg_len)
    wt2 = wt1.rolling(window=4).mean()

    return wt1.fillna(0), wt2.fillna(0)


# ─── 3.10 Tilson T3 ──────────────────────────────────────────────────────
def calc_t3(close: pd.Series, period: int = 5,
            vfactor: float = 0.7) -> pd.Series:
    """
    📚 TILSON T3 NEDİR?
    ───────────────────
    Tim Tilson (1998) — "Ultra yumuşak" hareketli ortalama.

    Problem: EMA hâlâ gürültülü (noisy). Her küçük fiyat değişiminde salınır.
    Çözüm: EMA'yı 6 kez üst üste uygula, ama özel katsayılarla.

    Nasıl çalışır:
      6 adet EMA'yı iç içe geçirir (GD = Generalized DEMA).
      vfactor parametresi yumuşaklığı kontrol eder:
        vfactor = 0 → Normal EMA gibi davranır
        vfactor = 1 → Maksimum yumuşaklık (çok gecikmeli)
        vfactor = 0.7 → TradingView standart (iyi denge)

    Kullanım:
      Fiyat > T3 → Bullish
      Fiyat < T3 → Bearish
      T3 yönü yukarı → Trend yukarı
      T3 yönü aşağı → Trend aşağı

    EMA 21 vs T3(5, 0.7):
      T3 çok daha yumuşak, whipsaw (yanlış sinyal) daha az.
      AMA daha gecikmeli — hızlı giriş için uygun değil.
      Trend ONAY aracı olarak mükemmel.
    """
    # Katsayılar
    c1 = -(vfactor ** 3)
    c2 = 3 * vfactor ** 2 + 3 * vfactor ** 2
    c3 = -6 * vfactor ** 2 - 3 * vfactor - 3 * vfactor
    c4 = 1 + 3 * vfactor + vfactor ** 3 + 3 * vfactor ** 2

    e1 = calc_ema(close, period)
    e2 = calc_ema(e1, period)
    e3 = calc_ema(e2, period)
    e4 = calc_ema(e3, period)
    e5 = calc_ema(e4, period)
    e6 = calc_ema(e5, period)

    t3 = c1 * e6 + c2 * e5 + c3 * e4 + c4 * e3
    return t3


# ─── 3.11 ATR (Average True Range) ───────────────────────────────────────
def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series,
             period: int = 14) -> pd.Series:
    """
    📚 ATR NEDİR?
    ─────────────
    J. Welles Wilder (1978) — Volatilite ölçüsü.

    True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
    ATR = EMA(True Range, period)

    ATR bir YÖN göstermez. Sadece piyasanın ne kadar hareket ettiğini söyler.

    Kullanım alanları:
      1. STOP-LOSS HESAPLAMA → SL = Giriş ± (1.5 × ATR)
         Bu, piyasanın normal gürültüsünün dışına stop koyar.
      2. POZİSYON BÜYÜKLÜĞÜ → Risk / ATR = lot sayısı
      3. SUPERTREND → ATR × multiplier = bant genişliği
      4. VOLATİLİTE TAKİBİ → ATR artıyorsa piyasa hareketleniyor

    Profesyonel kural:
      Stop-loss asla 1 ATR'den yakın olmamalı — normal gürültüye takılırsın.
      İdeal: 1.5-2× ATR mesafe.
    """
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()


# ─── 3.12 MFI (Money Flow Index) ─────────────────────────────────────────
def calc_mfi(high: pd.Series, low: pd.Series, close: pd.Series,
             volume: pd.Series, period: int = 14) -> pd.Series:
    """
    📚 MFI NEDİR?
    ─────────────
    Gene Quong & Avrum Soudack — "Hacimli RSI" olarak da bilinir.

    RSI sadece fiyata bakar. MFI hem fiyata hem hacme bakar.
    Bu yüzden MFI daha güvenilirdir — hacim olmadan fiyat hareketi sahtedir.

    Formül:
      Typical Price = (H + L + C) / 3
      Money Flow = Typical Price × Volume
      Eğer TP > TP_önceki → Positive Money Flow
      Eğer TP < TP_önceki → Negative Money Flow
      Money Flow Ratio = Positive / Negative
      MFI = 100 - (100 / (1 + Ratio))

    Yorumlama (RSI ile aynı):
      MFI > 80 → Aşırı alım (para aşırı giriyor)
      MFI < 20 → Aşırı satım (para aşırı çıkıyor)

    MFI Divergence:
      Fiyat yükseliyor AMA MFI düşüyor → Para akışı zayıflıyor → Dikkat!
      Bu, büyük oyuncuların sessizce sattığı anlamına gelebilir.
    """
    typical_price = (high + low + close) / 3
    money_flow = typical_price * volume

    tp_diff = typical_price.diff()
    positive_flow = money_flow.where(tp_diff > 0, 0).rolling(period).sum()
    negative_flow = money_flow.where(tp_diff < 0, 0).rolling(period).sum()

    mfr = positive_flow / negative_flow.replace(0, np.nan)
    mfi = 100 - (100 / (1 + mfr))
    return mfi.fillna(50)


# ─── 3.13 OBV (On Balance Volume) ────────────────────────────────────────
def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """
    📚 OBV NEDİR?
    ─────────────
    Joseph Granville (1963) — En eski hacim indikatörlerinden biri.

    Mantık çok basit ama güçlü:
      Fiyat yükseldi → OBV += Volume
      Fiyat düştü → OBV -= Volume
      Fiyat değişmedi → OBV aynı

    OBV'nin MUTLAK değeri önemsiz. Önemli olan YÖN ve eğilim.

    Kullanım:
      OBV yükseliyor + Fiyat yükseliyor → Sağlıklı yükseliş (onay)
      OBV düşüyor + Fiyat yükseliyor → UYARI! Hacim desteklemiyor
      OBV yükseliyor + Fiyat düşüyor → Birikim (accumulation) olabilir

    OBV üzerine EMA koyarak trend takibi yapılır:
      OBV > OBV_EMA → Hacim trendi bullish
      OBV < OBV_EMA → Hacim trendi bearish
    """
    direction = np.where(close > close.shift(1), 1,
                np.where(close < close.shift(1), -1, 0))
    obv = (volume * direction).cumsum()
    return pd.Series(obv, index=close.index)


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 4: PUANLAMA KATMANI (Scoring Engine)
# ═══════════════════════════════════════════════════════════════════════════
"""
📚 EĞİTİM NOTU - PUANLAMA SİSTEMİ:
════════════════════════════════════
Her indikatör 0 ile 100 arası bir skor üretir:
  0-20   = Güçlü Bearish sinyal
  20-40  = Zayıf Bearish sinyal
  40-60  = Nötr
  60-80  = Zayıf Bullish sinyal
  80-100 = Güçlü Bullish sinyal

Sonra her skor kendi ağırlığıyla çarpılır ve toplanır.
Örnek: RSI skoru 80, ağırlık %8 → katkı = 80 × 0.08 = 6.4 puan

Toplam 100 puan üzerinden değerlendirme:
  85+ = A+ (Güçlü fırsat)
  75-84 = A (İyi fırsat)
  65-74 = B (Ortalama, dikkatli ol)
  <65 = Filtreden elenir
"""


def score_indicators(df: pd.DataFrame, cfg: ScannerConfig) -> Dict:
    """Tüm indikatörleri hesaplar ve puanlar."""
    c = df["close"]
    h = df["high"]
    l = df["low"]
    v = df["volume"]

    scores = {}
    details = {}

    # ── 1. EMA TREND DİZİLİMİ ──
    ema9 = calc_ema(c, cfg.ema_fast)
    ema21 = calc_ema(c, cfg.ema_mid)
    ema55 = calc_ema(c, cfg.ema_slow)
    ema200 = calc_ema(c, cfg.ema_trend)

    last_price = c.iloc[-1]
    e9, e21, e55, e200 = ema9.iloc[-1], ema21.iloc[-1], ema55.iloc[-1], ema200.iloc[-1]

    ema_score = 50  # Başlangıç nötr
    # Fiyat EMA200 üstünde mı?
    if last_price > e200:
        ema_score += 15
    else:
        ema_score -= 15
    # Ribbon dizilimi (9 > 21 > 55 = perfect bullish)
    if e9 > e21 > e55:
        ema_score += 25
    elif e9 < e21 < e55:
        ema_score -= 25
    # Fiyat EMA9 üstünde mi (kısa vadeli momentum)
    if last_price > e9:
        ema_score += 10
    else:
        ema_score -= 10

    scores["trend_ema"] = np.clip(ema_score, 0, 100)
    details["ema"] = f"9:{e9:.2f} 21:{e21:.2f} 55:{e55:.2f} 200:{e200:.2f}"

    # ── 2. SUPERTREND ──
    st_line, st_dir = calc_supertrend(h, l, c, cfg.supertrend_period, cfg.supertrend_multiplier)
    st_direction = st_dir.iloc[-1]
    st_prev = st_dir.iloc[-2] if len(st_dir) > 1 else st_direction

    if st_direction == 1:
        st_score = 75
        if st_prev == -1:  # Yeni flip — güçlü sinyal
            st_score = 90
    else:
        st_score = 25
        if st_prev == 1:
            st_score = 10

    scores["supertrend"] = st_score
    details["supertrend"] = "LONG" if st_direction == 1 else "SHORT"

    # ── 3. ICHIMOKU ──
    ichi = calc_ichimoku(h, l, c, cfg.ichimoku_tenkan, cfg.ichimoku_kijun, cfg.ichimoku_senkou_b)
    tk = ichi["tenkan"].iloc[-1]
    kj = ichi["kijun"].iloc[-1]
    sa = ichi["senkou_a"].iloc[-1] if not np.isnan(ichi["senkou_a"].iloc[-1]) else last_price
    sb = ichi["senkou_b"].iloc[-1] if not np.isnan(ichi["senkou_b"].iloc[-1]) else last_price

    cloud_top = max(sa, sb)
    cloud_bottom = min(sa, sb)

    ichi_score = 50
    if last_price > cloud_top:
        ichi_score += 20
    elif last_price < cloud_bottom:
        ichi_score -= 20
    # TK Cross
    if tk > kj:
        ichi_score += 15
    else:
        ichi_score -= 15
    # Bulut rengi (SA > SB = yeşil bulut = bullish)
    if sa > sb:
        ichi_score += 10
    else:
        ichi_score -= 10

    scores["ichimoku"] = np.clip(ichi_score, 0, 100)
    details["ichimoku"] = f"{'Bulut üstü' if last_price > cloud_top else 'Bulut altı' if last_price < cloud_bottom else 'Bulut içi'}"

    # ── 4. MACD ──
    macd_line, signal_line, histogram = calc_macd(c, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    ml = macd_line.iloc[-1]
    sl_ = signal_line.iloc[-1]
    hist = histogram.iloc[-1]
    hist_prev = histogram.iloc[-2] if len(histogram) > 1 else 0

    macd_score = 50
    if ml > sl_:
        macd_score += 15
    else:
        macd_score -= 15
    if ml > 0:
        macd_score += 10
    else:
        macd_score -= 10
    # Histogram momentum
    if hist > 0 and hist > hist_prev:
        macd_score += 15  # Artan bullish momentum
    elif hist < 0 and hist < hist_prev:
        macd_score -= 15  # Artan bearish momentum

    scores["macd"] = np.clip(macd_score, 0, 100)
    details["macd"] = f"Line:{ml:.4f} Hist:{hist:.4f}"

    # ── 5. ADX ──
    adx, plus_di, minus_di = calc_adx(h, l, c, cfg.adx_period)
    adx_val = adx.iloc[-1]
    pdi = plus_di.iloc[-1]
    mdi = minus_di.iloc[-1]

    adx_score = 50
    if adx_val > cfg.adx_strong_trend:
        if pdi > mdi:
            adx_score = 70 + min(adx_val - 25, 25)  # Max 95
        else:
            adx_score = 30 - min(adx_val - 25, 25)  # Min 5
    # ADX düşükse nötr — trend yok demek
    # Bu durumda ne bullish ne bearish güvenilir değil

    scores["adx"] = np.clip(adx_score, 0, 100)
    details["adx"] = f"ADX:{adx_val:.1f} +DI:{pdi:.1f} -DI:{mdi:.1f}"

    # ── 6. RSI ──
    rsi = calc_rsi(c, cfg.rsi_period)
    rsi_val = rsi.iloc[-1]

    if rsi_val > cfg.rsi_overbought:
        rsi_score = max(10, 50 - (rsi_val - 70) * 2)  # Aşırı alım — bearish
    elif rsi_val < cfg.rsi_oversold:
        rsi_score = min(90, 50 + (30 - rsi_val) * 2)   # Aşırı satım — bullish (dönüş fırsatı)
    elif rsi_val > 50:
        rsi_score = 50 + (rsi_val - 50) * 1.0  # Hafif bullish
    else:
        rsi_score = 50 - (50 - rsi_val) * 1.0  # Hafif bearish

    scores["rsi"] = np.clip(rsi_score, 0, 100)
    details["rsi"] = f"RSI:{rsi_val:.1f}"

    # ── 7. STOCHASTIC RSI ──
    stoch_k, stoch_d = calc_stochastic_rsi(c, cfg.stoch_rsi_period,
                                            cfg.stoch_rsi_period,
                                            cfg.stoch_rsi_k, cfg.stoch_rsi_d)
    sk = stoch_k.iloc[-1]
    sd = stoch_d.iloc[-1]

    stoch_score = 50
    if sk < 20:
        stoch_score = 75 if sk > sd else 70  # Oversold — bullish potential
    elif sk > 80:
        stoch_score = 25 if sk < sd else 30  # Overbought — bearish potential
    elif sk > sd:
        stoch_score = 60
    else:
        stoch_score = 40

    scores["stoch_rsi"] = stoch_score
    details["stoch_rsi"] = f"K:{sk:.1f} D:{sd:.1f}"

    # ── 8. BOLLINGER BANDS ──
    bb_upper, bb_middle, bb_lower, bb_bw = calc_bollinger_bands(c, cfg.bb_period, cfg.bb_std)
    bbu = bb_upper.iloc[-1]
    bbm = bb_middle.iloc[-1]
    bbl = bb_lower.iloc[-1]
    bw = bb_bw.iloc[-1]
    bw_avg = bb_bw.rolling(50).mean().iloc[-1] if len(bb_bw) > 50 else bw

    # Squeeze tespiti
    is_squeeze = bw < bw_avg * 0.75

    bb_score = 50
    if last_price > bbu:
        bb_score = 35  # Üst bandın üstünde — geri dönüş olabilir
    elif last_price < bbl:
        bb_score = 65  # Alt bandın altında — geri dönüş olabilir
    elif last_price > bbm:
        bb_score = 60
    else:
        bb_score = 40

    if is_squeeze:
        bb_score = 55  # Squeeze varsa nötre yakın tut — yön belirsiz

    scores["bollinger"] = bb_score
    details["bollinger"] = f"{'🔥SQUEEZE' if is_squeeze else 'Normal'} BW:{bw:.4f}"

    # ── 9. WAVETREND ──
    wt1, wt2 = calc_wavetrend(h, l, c, cfg.wavetrend_channel, cfg.wavetrend_avg)
    w1 = wt1.iloc[-1]
    w2 = wt2.iloc[-1]

    wt_score = 50
    if w1 < cfg.wavetrend_os:
        wt_score = 80 if w1 > w2 else 70  # Oversold + cross = güçlü buy
    elif w1 > cfg.wavetrend_ob:
        wt_score = 20 if w1 < w2 else 30  # Overbought + cross = güçlü sell
    elif w1 > w2:
        wt_score = 62
    else:
        wt_score = 38

    scores["wavetrend"] = wt_score
    details["wavetrend"] = f"WT1:{w1:.1f} WT2:{w2:.1f}"

    # ── 10. OBV ──
    obv = calc_obv(c, v)
    obv_ema = calc_ema(obv, cfg.obv_ema_period)
    obv_val = obv.iloc[-1]
    obv_ema_val = obv_ema.iloc[-1]

    obv_score = 60 if obv_val > obv_ema_val else 40
    # OBV trendi (son 5 mum)
    if len(obv) > 5:
        obv_trend = obv.iloc[-1] - obv.iloc[-5]
        price_trend = c.iloc[-1] - c.iloc[-5]
        # Divergence kontrolü
        if obv_trend > 0 and price_trend < 0:
            obv_score = 70  # Bullish divergence — birikim
        elif obv_trend < 0 and price_trend > 0:
            obv_score = 30  # Bearish divergence — dağıtım

    scores["volume_obv"] = obv_score
    details["obv"] = f"OBV{'>' if obv_val > obv_ema_val else '<'}EMA"

    # ── 11. MFI ──
    mfi = calc_mfi(h, l, c, v, cfg.mfi_period)
    mfi_val = mfi.iloc[-1]

    if mfi_val > 80:
        mfi_score = 30  # Aşırı para girişi — düzeltme riski
    elif mfi_val < 20:
        mfi_score = 70  # Aşırı para çıkışı — dönüş fırsatı
    elif mfi_val > 50:
        mfi_score = 55 + (mfi_val - 50) * 0.5
    else:
        mfi_score = 45 - (50 - mfi_val) * 0.5

    scores["mfi"] = np.clip(mfi_score, 0, 100)
    details["mfi"] = f"MFI:{mfi_val:.1f}"

    # ── 12. TILSON T3 ──
    t3 = calc_t3(c, cfg.t3_period, cfg.t3_vfactor)
    t3_val = t3.iloc[-1]
    t3_prev = t3.iloc[-2] if len(t3) > 1 else t3_val

    t3_score = 50
    if last_price > t3_val:
        t3_score += 15
    else:
        t3_score -= 15
    if t3_val > t3_prev:  # T3 yönü yukarı
        t3_score += 10
    else:
        t3_score -= 10

    scores["t3_trend"] = np.clip(t3_score, 0, 100)
    details["t3"] = f"T3:{t3_val:.2f} {'↑' if t3_val > t3_prev else '↓'}"

    # ── ATR (skorlanmaz, bilgi amaçlı) ──
    atr = calc_atr(h, l, c, cfg.atr_period)
    atr_val = atr.iloc[-1]
    atr_pct = (atr_val / last_price) * 100
    details["atr"] = f"ATR:{atr_val:.4f} ({atr_pct:.2f}%)"

    # ═══ TOPLAM SKOR HESAPLAMA ═══
    total_score = 0
    for key, weight in cfg.weights.items():
        if key in scores:
            total_score += scores[key] * (weight / 100)

    return {
        "total_score": round(total_score, 1),
        "scores": scores,
        "details": details,
        "direction": "LONG" if total_score > 55 else "SHORT" if total_score < 45 else "NEUTRAL",
        "atr_pct": atr_pct,
    }


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 5: ÇOK ZAMAN DİLİMLİ ANALİZ (Multi-Timeframe)
# ═══════════════════════════════════════════════════════════════════════════
"""
📚 EĞİTİM NOTU - NEDEN ÇOK ZAMAN DİLİMİ?
═══════════════════════════════════════════
"Timeframe alignment" profesyonel trading'in temelidir.

Kural: Büyük zaman dilimi yönünde küçük zaman diliminde giriş yap.

Örnek:
  4H → Yükseliş trendi (EMA dizilimi bullish)
  1H → Düzeltme yapıyor (pullback)
  15M → WaveTrend oversold'dan dönüyor

  → Bu 3'ü hizalandığında GİRİŞ yap.

  Eğer 4H bearish ama 15M bullish → YAPMA!
  Büyük zaman dilimine karşı gitmek en yaygın hatadır.

Ağırlıklar:
  4H = %50 (ana trend)
  1H = %30 (ara trend)
  15M = %20 (giriş zamanlama)
"""

TF_WEIGHTS = {"4h": 0.50, "1h": 0.30, "15m": 0.20}


def analyze_coin(symbol_data: Dict, cfg: ScannerConfig) -> Optional[Dict]:
    """Tek bir coin'i tüm zaman dilimlerinde analiz eder."""
    symbol = symbol_data["symbol"]
    results = {}

    for tf in cfg.timeframes:
        df = get_klines(symbol, tf, limit=200)
        if df is None or len(df) < 100:
            return None

        result = score_indicators(df, cfg)
        results[tf] = result
        time.sleep(0.05)  # Rate limit koruması

    if not results:
        return None

    # MTF (Multi-Timeframe) bileşik skor
    mtf_score = 0
    for tf, weight in TF_WEIGHTS.items():
        if tf in results:
            mtf_score += results[tf]["total_score"] * weight

    # ── MTF ÇAKIŞMA CEZASI ──
    """
    📚 Eğer zaman dilimleri farklı yönlerde sinyal veriyorsa
    toplam skoru düşürürüz. Bu "alignment penalty" olarak bilinir.
    Amaç: Çelişkili sinyallerden uzak durmak.
    """
    directions = [r["direction"] for r in results.values()]
    unique_dirs = set(directions)
    if len(unique_dirs) > 1 and "NEUTRAL" not in unique_dirs:
        mtf_score *= 0.7  # %30 ceza — zaman dilimleri çelişiyor

    # Ana timeframe (4H) yönü belirleyici
    primary_tf = cfg.timeframes[0]
    primary_dir = results[primary_tf]["direction"]

    return {
        "symbol": symbol,
        "clean_name": symbol.replace("USDT", ""),
        "price": symbol_data["last_price"],
        "volume_24h": symbol_data["volume"],
        "change_24h": symbol_data["price_change_pct"],
        "mtf_score": round(mtf_score, 1),
        "direction": primary_dir,
        "tf_results": results,
        "alignment": len(unique_dirs) == 1,  # Tüm TF'ler aynı yönde mi
    }


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 6: SUNUM KATMANI (Display)
# ═══════════════════════════════════════════════════════════════════════════

def grade(score: float) -> str:
    """Skor → harf notu dönüşümü."""
    if score >= 85: return "A+"
    if score >= 75: return " A"
    if score >= 65: return " B"
    if score >= 55: return " C"
    return " D"


def direction_emoji(d: str) -> str:
    return {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "⚪"}.get(d, "⚪")


def format_volume(vol: float) -> str:
    if vol >= 1_000_000_000:
        return f"{vol/1_000_000_000:.1f}B"
    if vol >= 1_000_000:
        return f"{vol/1_000_000:.1f}M"
    return f"{vol/1_000:.0f}K"


def print_results(results: List[Dict], cfg: ScannerConfig):
    """Sonuçları profesyonel tablo formatında yazdırır."""

    print("\n")
    print("╔═══════════════════════════════════════════════════════════════════════════════════════╗")
    print("║                          🔍 PRO CRYPTO SCANNER v1.0                                 ║")
    print("║                     TradingView Kalitesinde Teknik Analiz                            ║")
    print(f"║                     📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                    ║")
    print("╠═══════════════════════════════════════════════════════════════════════════════════════╣")
    print(f"║  Zaman Dilimleri: {', '.join(cfg.timeframes):<20}  Min Skor: {cfg.min_score:<5}  Taranan: {len(results)} coin  ║")
    print("╚═══════════════════════════════════════════════════════════════════════════════════════╝")

    # LONG sinyaller
    longs = sorted([r for r in results if r["direction"] == "LONG"],
                   key=lambda x: x["mtf_score"], reverse=True)[:cfg.top_results // 2]

    shorts = sorted([r for r in results if r["direction"] == "SHORT"],
                    key=lambda x: x["mtf_score"], reverse=False)[:cfg.top_results // 2]

    if longs:
        print("\n🟢 ═══ LONG SİNYALLERİ (En güçlüden zayıfa) ═══")
        print(f"  {'#':<3} {'Coin':<12} {'Fiyat':>12} {'Skor':>6} {'Not':>4} {'24h%':>7} {'Hacim':>10} {'Hiza':>5} {'4H':>5} {'1H':>5} {'15M':>5}")
        print(f"  {'─'*3} {'─'*12} {'─'*12} {'─'*6} {'─'*4} {'─'*7} {'─'*10} {'─'*5} {'─'*5} {'─'*5} {'─'*5}")
        for i, r in enumerate(longs, 1):
            tf_scores = " ".join(
                f"{r['tf_results'][tf]['total_score']:5.1f}" if tf in r['tf_results'] else "  N/A"
                for tf in cfg.timeframes
            )
            print(f"  {i:<3} {r['clean_name']:<12} {r['price']:>12.4f} {r['mtf_score']:>6.1f} "
                  f"{grade(r['mtf_score']):>4} {r['change_24h']:>+6.1f}% {format_volume(r['volume_24h']):>10} "
                  f"{'✅' if r['alignment'] else '⚠️':>5} {tf_scores}")

    if shorts:
        print("\n🔴 ═══ SHORT SİNYALLERİ (En güçlüden zayıfa) ═══")
        print(f"  {'#':<3} {'Coin':<12} {'Fiyat':>12} {'Skor':>6} {'Not':>4} {'24h%':>7} {'Hacim':>10} {'Hiza':>5} {'4H':>5} {'1H':>5} {'15M':>5}")
        print(f"  {'─'*3} {'─'*12} {'─'*12} {'─'*6} {'─'*4} {'─'*7} {'─'*10} {'─'*5} {'─'*5} {'─'*5} {'─'*5}")
        for i, r in enumerate(shorts, 1):
            tf_scores = " ".join(
                f"{r['tf_results'][tf]['total_score']:5.1f}" if tf in r['tf_results'] else "  N/A"
                for tf in cfg.timeframes
            )
            # Short için düşük skor = güçlü sinyal, bu yüzden 100-score yapıyoruz gösterimde
            display_score = 100 - r['mtf_score']
            print(f"  {i:<3} {r['clean_name']:<12} {r['price']:>12.4f} {display_score:>6.1f} "
                  f"{grade(display_score):>4} {r['change_24h']:>+6.1f}% {format_volume(r['volume_24h']):>10} "
                  f"{'✅' if r['alignment'] else '⚠️':>5} {tf_scores}")

    # ── DETAYLI ANALİZ (İlk 3) ──
    top3 = sorted(results, key=lambda x: abs(x["mtf_score"] - 50), reverse=True)[:3]
    if top3:
        print("\n\n📊 ═══ DETAYLI ANALİZ (En güçlü 3 sinyal) ═══")
        for r in top3:
            emoji = direction_emoji(r["direction"])
            print(f"\n  {emoji} {r['clean_name']} — Skor: {r['mtf_score']:.1f} ({r['direction']})")
            print(f"  {'─' * 55}")
            for tf in cfg.timeframes:
                if tf not in r["tf_results"]:
                    continue
                tfr = r["tf_results"][tf]
                print(f"    [{tf.upper():>3}] Skor: {tfr['total_score']:.1f} | {tfr['direction']}")
                for key, val in tfr["details"].items():
                    print(f"          {key:<12}: {val}")


# ═══════════════════════════════════════════════════════════════════════════
# BÖLÜM 7: ANA ÇALIŞTIRICI (Main Runner)
# ═══════════════════════════════════════════════════════════════════════════

def run_scanner():
    """Ana tarayıcıyı çalıştırır."""
    print("╔══════════════════════════════════════════════════╗")
    print("║        🚀 PRO CRYPTO SCANNER BAŞLIYOR...        ║")
    print("╚══════════════════════════════════════════════════╝")

    cfg = ScannerConfig()

    # 1. Sembolleri çek
    print("\n📡 Binance Futures sembol listesi alınıyor...")
    symbols = get_futures_symbols(cfg.min_volume_usdt)
    if not symbols:
        print("❌ Sembol listesi alınamadı!")
        return

    symbols = symbols[:cfg.max_coins]
    print(f"✅ {len(symbols)} coin bulundu (min hacim: ${cfg.min_volume_usdt:,.0f})")

    # 2. Paralel tarama
    """
    📚 EĞİTİM NOTU - ThreadPoolExecutor:
    ─────────────────────────────────────
    100 coin × 3 timeframe = 300 API çağrısı
    Sıralı: 300 × 0.5s = 150 saniye
    Paralel (5 thread): ~30 saniye

    ThreadPoolExecutor birden fazla "iş parçacığı" oluşturur.
    Her thread aynı anda farklı bir coin için veri çeker.
    max_workers=5 → aynı anda 5 coin analiz edilir.
    Daha fazla = daha hızlı AMA rate limit riski artar.
    """
    print(f"\n🔍 Tarama başlıyor ({len(cfg.timeframes)} zaman dilimi)...")
    results = []
    errors = 0

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(analyze_coin, s, cfg): s for s in symbols}
        total = len(futures)
        done = 0

        for future in as_completed(futures):
            done += 1
            sym = futures[future]["symbol"]
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
                    status = f"{'🟢' if result['direction'] == 'LONG' else '🔴' if result['direction'] == 'SHORT' else '⚪'} {result['mtf_score']:.0f}"
                else:
                    status = "⏭ atlandı"
                    errors += 1
            except Exception as e:
                status = f"❌ {str(e)[:30]}"
                errors += 1

            # İlerleme çubuğu
            pct = done / total * 100
            bar_len = 30
            filled = int(bar_len * done / total)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"\r  [{bar}] {pct:5.1f}% | {sym:<15} {status:<20}", end="", flush=True)

    print(f"\n\n✅ Tarama tamamlandı: {len(results)} sonuç, {errors} hata")

    # 3. Filtrele
    # Long sinyaller: yüksek skor = güçlü
    # Short sinyaller: düşük skor = güçlü
    filtered = [r for r in results
                if r["mtf_score"] >= cfg.min_score or r["mtf_score"] <= (100 - cfg.min_score)]

    if not filtered:
        print(f"\n⚠ Min skor eşiğini ({cfg.min_score}) geçen sinyal bulunamadı.")
        print("  Eşiği düşürmeyi dene: config.min_score = 55")
        # Yine de en iyileri göster
        filtered = sorted(results, key=lambda x: abs(x["mtf_score"] - 50), reverse=True)[:10]

    # 4. Sonuçları göster
    print_results(filtered, cfg)

    # 5. JSON olarak kaydet
    output = {
        "scan_time": datetime.now().isoformat(),
        "config": {
            "timeframes": cfg.timeframes,
            "min_volume": cfg.min_volume_usdt,
            "min_score": cfg.min_score,
        },
        "results": [
            {
                "symbol": r["symbol"],
                "price": r["price"],
                "mtf_score": r["mtf_score"],
                "direction": r["direction"],
                "alignment": r["alignment"],
                "change_24h": r["change_24h"],
                "volume_24h": r["volume_24h"],
                "tf_scores": {tf: r["tf_results"][tf]["total_score"]
                              for tf in cfg.timeframes if tf in r["tf_results"]},
            }
            for r in filtered
        ]
    }

    output_path = "scan_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n💾 Sonuçlar kaydedildi: {output_path}")

    print("\n" + "═" * 80)
    print("📚 HATIRLATMA: Bu tarayıcı sinyal ÖNERİR, KARAR SİZ VERİRSİNİZ.")
    print("   'Tahmin para kaybettirir, onay para kazandırır.'")
    print("   Her sinyali chart'ta ONAYLAMADAN pozisyon AÇMA!")
    print("═" * 80)


if __name__ == "__main__":
    run_scanner()
