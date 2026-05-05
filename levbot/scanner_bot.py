# ══════════════════════════════════════════════════════════════════════════════
#  KRIPTO TARAYICI v9.0 — T3 + VMC CIPHER B EDİTİONU
#  Binance + BingX | 1D+4H+1H | Min R/R 1:2.5
#  SMC | OI | Fear&Greed | BB Sweep | MFI | Tilson T3 | WaveTrend
# ══════════════════════════════════════════════════════════════════════════════

import tkinter as tk
from tkinter import ttk, messagebox
import threading, time, json, csv, os, webbrowser, math
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests as req_lib
import queue

# ─── HTTP SESSION ─────────────────────────────────────────────────────────────
def create_session():
    session = req_lib.Session()
    retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[429,500,502,503,504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session

def safe_get(url, timeout=10, params=None):
    try:
        s = create_session()
        r = s.get(url, timeout=timeout, params=params)
        result = r.json()
        return result if result is not None else {}
    except Exception:
        return {}

# ─── AYARLAR ──────────────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "scan_interval":     30,       # dakika (swing trade — daha uzun aralık)
    "min_volume_usd":    5000000,  # $5M minimum hacim (swing için likidite şart)
    "min_score":         80,       # daha yüksek kalite eşiği
    "min_rr":            2.5,      # minimum R/R
    "ob_lookback_1d":    60,       # 1D'de kaç muma bak
    "ob_lookback_4h":    100,      # 4H'ta kaç muma bak
    "ob_lookback_1h":    60,       # 1H'ta kaç muma bak
    "weekly_lookback":   20,       # Haftalık S/R için kaç haftalık mum
    "btc_filter":        True,     # BTC korelasyon filtresi
    "btc_drop_pct":      3.0,      # BTC bu kadar düşüşte long engelle
    "sound_alert":       True,
    "use_okx":           False,  # Binance ile değiştirildi
    "use_bingx":         True,
    "show_mode":         "Tümü",
    "telegram_token":    "",
    "telegram_chat_id":  "",
    "telegram_active":   False,
    "coinglass_api_key": "",    # CoinGlass API key
    "use_coinglass":     False,  # API key gelince True yap
    # ── v9.0: Tilson T3 ──────────────────────────────────────────────────────
    "t3_period":         6,        # T3 periyodu (default 6 — standart)
    "t3_v_factor":       0.7,      # T3 v faktörü (0.5=yumuşak, 0.9=reaktif)
    "use_t3":            True,     # T3 trend filtresi aktif mi?
    # ── v9.0: VMC Cipher B WaveTrend ─────────────────────────────────────────
    "wt_channel_len":    9,        # WaveTrend kanal uzunluğu
    "wt_avg_len":        12,       # WaveTrend ortalama uzunluğu
    "wt_ob_level":       53,       # Overbought seviyesi
    "wt_os_level":       -53,      # Oversold seviyesi
    "use_vmc":           True,     # VMC WaveTrend aktif mi?
}
SETTINGS_FILE = "settings_v7.json"
LOG_FILE      = "tarama_v7.csv"

TF_MAP_OKX = {"1h":"1H","4h":"4H","1d":"1D","1w":"1W"}
TF_MAP_BX  = {"1h":"1h","4h":"4h","1d":"1d","1w":"1w"}

# ─── RENKLER ──────────────────────────────────────────────────────────────────
BG="#060c18"; BG2="#0b1422"; BG3="#111e32"; BG4="#172540"
ACCENT="#00cfff"; GREEN="#00f07a"; RED="#ff2550"
YELLOW="#ffd60a"; PURPLE="#c084fc"; ORANGE="#fb923c"
TEAL="#2dd4bf"; PINK="#f472b6"; GOLD="#f59e0b"
TEXT="#e2e8f4"; TEXT_DIM="#475569"; BORDER="#1e3a5f"
LONG_BG="#051a0d"; SHORT_BG="#1a0508"

# ─── AYAR YÖNETİMİ ────────────────────────────────────────────────────────────
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            s = DEFAULT_SETTINGS.copy()
            s.update(json.load(open(SETTINGS_FILE)))
            return s
        except: pass
    return DEFAULT_SETTINGS.copy()

def save_settings(s):
    json.dump(s, open(SETTINGS_FILE,"w"), indent=2)

# ─── LOG ──────────────────────────────────────────────────────────────────────
def log_result(c):
    exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE,"a",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "zaman","borsa","sembol","sinyal","skor","guven",
            "ob_tip","ob_yon_uyari","fiyat","sl","tp1","tp2",
            "rr","trailing","haftalik_sr","btc_durum"])
        if not exists: w.writeheader()
        w.writerow({
            "zaman":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "borsa":         c.get("exchange",""),
            "sembol":        c.get("symbol",""),
            "sinyal":        c.get("signal","—"),
            "skor":          c.get("score",0),
            "guven":         c.get("confidence","—"),
            "ob_tip":        c.get("ob_type","—"),
            "ob_yon_uyari":  c.get("ob_dir_warning",False),
            "fiyat":         c.get("price",0),
            "sl":            round(c.get("sl",0),6),
            "tp1":           round(c.get("tp1",0),6),
            "tp2":           round(c.get("tp2",0),6),
            "rr":            c.get("rr","—"),
            "trailing":      c.get("trailing_stop","—"),
            "haftalik_sr":   c.get("weekly_sr_near","—"),
            "btc_durum":     c.get("btc_status","—"),
        })

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────
def send_telegram(token, chat_id, coin):
    try:
        sig   = coin.get("signal","—")
        emoji = "🟢" if sig=="LONG" else "🔴"
        warn  = "⚠️ OB YÖN UYARISI!\n" if coin.get("ob_dir_warning") else ""
        msg = (
            f"{emoji} *{sig} — SWING TRADEˀ* `{coin['symbol']}`\n"
            f"{warn}"
            f"📊 Borsa: {coin['exchange']}\n"
            f"💰 Fiyat: ${coin['price']:,.5g}\n"
            f"🎯 Skor: {coin.get('score',0)}/100  |  Güven: {coin.get('confidence','—')}\n"
            f"📦 OB: {coin.get('ob_type','—')}\n"
            f"📅 Haftalık S/R: {coin.get('weekly_sr_near','—')}\n"
            f"🔴 Stop Loss: ${coin.get('sl',0):.5g}\n"
            f"🟡 TP1 (%50): ${coin.get('tp1',0):.5g}\n"
            f"🟢 TP2 (tam): ${coin.get('tp2',0):.5g}\n"
            f"⚖️ R/R: {coin.get('rr','—')}\n"
            f"📈 Trailing Stop: {coin.get('trailing_stop','—')}\n"
            f"₿ BTC: {coin.get('btc_status','—')}"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        req_lib.post(url, json={"chat_id":chat_id,"text":msg,"parse_mode":"Markdown"}, timeout=8)
    except Exception as e:
        print(f"Telegram hata: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  TEKNİK YARDIMCILAR
# ══════════════════════════════════════════════════════════════════════════════
def safe_float(v, default=0.0):
    try: return float(v)
    except: return default

def calc_atr(highs, lows, closes, period=14):
    if len(closes) < period+1: return None
    trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
           for i in range(1,len(closes))]
    if len(trs) < period: return None
    atr = sum(trs[:period])/period
    for tr in trs[period:]: atr = (atr*(period-1)+tr)/period
    return atr

def calc_rsi(closes, period=14):
    if len(closes) < period+1: return None
    gains,losses = [],[]
    for i in range(1,len(closes)):
        d = closes[i]-closes[i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    ag = sum(gains[:period])/period; al = sum(losses[:period])/period
    for i in range(period,len(gains)):
        ag=(ag*(period-1)+gains[i])/period; al=(al*(period-1)+losses[i])/period
    if al==0: return 100.0
    try: return round(100-(100/(1+ag/al)),2)
    except: return None

def calc_ema(closes, period):
    if len(closes) < period: return None
    k=2/(period+1); ema=sum(closes[:period])/period
    for p in closes[period:]: ema=p*k+ema*(1-k)
    return ema

def calc_macd(closes):
    if len(closes) < 35: return None,None,None
    try:
        ml=[]
        for i in range(25,len(closes)):
            ef=calc_ema(closes[:i+1],12); es=calc_ema(closes[:i+1],26)
            if ef and es: ml.append(ef-es)
        if len(ml)<9: return None,None,None
        sig=calc_ema(ml,9)
        if not sig: return None,None,None
        return round(ml[-1],6),round(sig,6),round(ml[-1]-sig,6)
    except: return None,None,None

# ══════════════════════════════════════════════════════════════════════════════
#  YENİ İNDİKATÖRLER — v8.0
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
#  YENİ İNDİKATÖRLER — v9.0  (Tilson T3 + VMC Cipher B)
# ══════════════════════════════════════════════════════════════════════════════

def calc_tilson_t3(closes, period=6, v=0.7):
    """
    Tilson T3 Moving Average — düşük lag, pürüzsüz trend filtresi
    Tim Tillson (1998)

    Nasıl çalışır?
    - Normal EMA'yı 6 kez üst üste uygular
    - Sonra matematiksel katsayılarla geri dönüş gecikmesini (lag) iptal eder
    - v faktörü: 0.7 = standart | 0.5 = daha yumuşak | 0.9 = daha reaktif

    Döndürür: dict veya None
      value       → güncel T3 değeri
      prev        → önceki mum T3 değeri (trend yönü için)
      rising      → T3 yükseliyor mu?
      price_above → fiyat T3 üstünde mi?
    """
    n = len(closes)
    # 6 katmanlı EMA için yeterli mum gerekli
    if n < period * 6 + 10:
        return None
    try:
        k = 2 / (period + 1)   # EMA katsayısı

        def run_ema(data):
            """Tüm seriyi EMA ile işle — tam liste döner"""
            # İlk değer olarak dizinin ilk elemanını kullan (warm-up)
            e = data[0]
            series = []
            for x in data:
                # EMA formülü: yeni = x * k + eski * (1 - k)
                e = x * k + e * (1 - k)
                series.append(e)
            return series

        # 6 katmanlı EMA zinciri
        e1 = run_ema(closes)   # 1. katman
        e2 = run_ema(e1)       # 2. katman (e1'in EMA'sı)
        e3 = run_ema(e2)       # 3. katman
        e4 = run_ema(e3)       # 4. katman
        e5 = run_ema(e4)       # 5. katman
        e6 = run_ema(e5)       # 6. katman

        # Tillson katsayıları — lag'i matematiksel olarak iptal eder
        c1 = -(v ** 3)
        c2 = 3 * v**2 + 3 * v**3
        c3 = -6 * v**2 - 3 * v - 3 * v**3
        c4 = 1 + 3 * v + v**3 + 3 * v**2

        # Son ve önceki T3 değerleri
        t3_curr = c1*e6[-1] + c2*e5[-1] + c3*e4[-1] + c4*e3[-1]
        t3_prev = c1*e6[-2] + c2*e5[-2] + c3*e4[-2] + c4*e3[-2]

        return {
            "value":       round(t3_curr, 8),
            "prev":        round(t3_prev, 8),
            "rising":      t3_curr > t3_prev,      # T3 yükseliyor mu?
            "price_above": closes[-1] > t3_curr,   # Fiyat T3 üstünde mi?
        }
    except:
        return None


def calc_wavetrend(highs, lows, closes, channel_len=9, avg_len=12, ma_len=3,
                   ob=53, os_lv=-53):
    """
    WaveTrend Oscillator — VMC Cipher B'nin kalbi
    LazyBear'ın TradingView scripti üzerinden Python'a çevrildi

    Nasıl çalışır?
    - src    = HLC3 (High+Low+Close ortalaması — fiyatın "merkezi")
    - esa    = EMA(src) — gürültüyü filtreler
    - de     = EMA(|src - esa|) — sapma büyüklüğü
    - ci     = (src - esa) / (0.015 * de) — normalize edilmiş kanal
    - wt1    = EMA(ci) — ana dalga
    - wt2    = SMA(wt1) — sinyal çizgisi (wt1'in daha yavaş hali)
    - Çapraz kesme + seviye = sinyal

    Döndürür: dict veya None
      wt1, wt2        → dalga değerleri
      cross_up/down   → wt1 wt2'yi bu mumda kesti mi?
      overbought      → wt2 >= ob (+53)?
      oversold        → wt2 <= os_lv (-53)?
      buy_signal      → yeşil daire: oversold bölgede yukarı kesme
      sell_signal     → kırmızı daire: overbought bölgede aşağı kesme
    """
    n = len(closes)
    # Yeterli mum yok mu? None dön
    if n < channel_len + avg_len + ma_len + 15:
        return None
    try:
        k_ch  = 2 / (channel_len + 1)   # kanal EMA katsayısı
        k_avg = 2 / (avg_len + 1)       # ortalama EMA katsayısı

        # Adım 1: HLC3 — fiyatın ağırlık merkezi
        src = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(n)]

        # Adım 2: ESA = EMA(src, channel_len)
        esa = src[0]
        esa_s = []
        for x in src:
            esa = x * k_ch + esa * (1 - k_ch)
            esa_s.append(esa)

        # Adım 3: DE = EMA(|src - esa|, channel_len)
        # Sapmanın ne kadar büyük olduğunu ölçer
        de = abs(src[0] - esa_s[0])
        de_s = []
        for i in range(n):
            diff = abs(src[i] - esa_s[i])
            de = diff * k_ch + de * (1 - k_ch)
            de_s.append(de)

        # Adım 4: CI = (src - esa) / (0.015 * de) — normalize
        # 0.015 sabiti TradingView'in orijinal formülünden
        ci_s = []
        for i in range(n):
            denom = 0.015 * de_s[i]
            ci_s.append((src[i] - esa_s[i]) / denom if denom != 0 else 0)

        # Adım 5: WT1 = EMA(ci, avg_len) — ana dalga
        wt1 = ci_s[0]
        wt1_s = []
        for x in ci_s:
            wt1 = x * k_avg + wt1 * (1 - k_avg)
            wt1_s.append(wt1)

        # Adım 6: WT2 = SMA(wt1, ma_len) — sinyal çizgisi
        wt2_s = []
        for i in range(n):
            start = max(0, i - ma_len + 1)
            wt2_s.append(sum(wt1_s[start:i+1]) / (i - start + 1))

        # Son 2 değer — crossover tespiti için ikisi de lazım
        wt1_curr, wt1_prev = wt1_s[-1], wt1_s[-2]
        wt2_curr, wt2_prev = wt2_s[-1], wt2_s[-2]

        # Çapraz kesme: bir önceki mumda hangi taraftaydı, şimdi nerede?
        cross_up   = (wt1_prev < wt2_prev) and (wt1_curr >= wt2_curr)
        cross_down = (wt1_prev > wt2_prev) and (wt1_curr <= wt2_curr)
        overbought = wt2_curr >= ob
        oversold   = wt2_curr <= os_lv

        return {
            "wt1":          round(wt1_curr, 2),
            "wt2":          round(wt2_curr, 2),
            "cross_up":     cross_up,
            "cross_down":   cross_down,
            "overbought":   overbought,
            "oversold":     oversold,
            # 🟢 Yeşil daire: oversold bölgede yukarı kesme
            "buy_signal":   cross_up and oversold,
            # 🔴 Kırmızı daire: overbought bölgede aşağı kesme
            "sell_signal":  cross_down and overbought,
        }
    except:
        return None


def calc_vmc_rsimfi(highs, lows, closes, opens, period=60, multiplier=150):
    """
    VMC Cipher B — RSI+MFI para akışı göstergesi
    Orijinal Pine Script: sma(((close-open)/(high-low))*multiplier, period)

    Nasıl çalışır?
    - Her mumun gövdesini (close-open) fitillerine (high-low) böler
    - multiplier ile ölçekler
    - Son period mumun ortalaması → para akış yönü ve gücü

    Döndürür: float veya None
      > 0 → Yeşil: para giriyor (bullish)
      < 0 → Kırmızı: para çıkıyor (bearish)
      Mutlak büyüklük → güç seviyesi (örn: +50 güçlü giriş)
    """
    n = len(closes)
    if n < period:
        return None
    try:
        values = []
        for i in range(n):
            rng = highs[i] - lows[i]    # fitil aralığı
            if rng > 0:
                # Gövde / Fitil = mumun ne kadar kararlı kapandığı
                values.append((closes[i] - opens[i]) / rng * multiplier)
            else:
                values.append(0)   # doji mumu — sıfır

        # Son period mumun ortalaması
        rsimfi = sum(values[-period:]) / period
        return round(rsimfi, 4)
    except:
        return None

def calc_bollinger_bands(closes, period=20, std_dev=2.0):
    """Bollinger Bands hesapla"""
    if len(closes) < period: return None, None, None
    upper, mid, lower = [], [], []
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        m = sum(window) / period
        variance = sum((x - m) ** 2 for x in window) / period
        std = variance ** 0.5
        mid.append(round(m, 8))
        upper.append(round(m + std_dev * std, 8))
        lower.append(round(m - std_dev * std, 8))
    return upper, mid, lower

def calc_mfi(highs, lows, closes, volumes, period=14):
    """Money Flow Index — para akışı"""
    if len(closes) < period + 1: return None
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    pos_flow, neg_flow = 0.0, 0.0
    for i in range(1, period + 1):
        raw_mf = tp[i] * volumes[i]
        if tp[i] > tp[i - 1]:
            pos_flow += raw_mf
        else:
            neg_flow += raw_mf
    if neg_flow == 0: return 100.0
    try:
        mfr = pos_flow / neg_flow
        return round(100 - (100 / (1 + mfr)), 2)
    except:
        return None

def detect_bb_sweep(highs, lows, closes, volumes):
    """
    Bollinger Bands sweep tespiti:
    - Fiyat alt banda dokunup geri döndüyse → Bullish sweep (SSL alındı)
    - Fiyat üst banda dokunup geri döndüyse → Bearish sweep (BSL alındı)
    """
    results = []
    upper, mid, lower = calc_bollinger_bands(closes)
    if upper is None or len(upper) < 5: return results

    # BB dizisini closes ile hizala
    offset = len(closes) - len(upper)
    n = len(upper)

    # Son 5 mumu kontrol et
    for i in range(max(0, n - 5), n - 1):
        ci = i + offset  # closes indeksi
        if ci < 1 or ci >= len(closes): continue

        avg_vol = sum(volumes[max(0, ci - 10):ci]) / 10 if ci >= 10 else volumes[ci]
        vol_ratio = volumes[ci] / avg_vol if avg_vol > 0 else 1

        # Bullish BB Sweep: alt bandın altına indi, kapanış alt bandın üstünde
        if lows[ci] < lower[i] and closes[ci] > lower[i]:
            strength = 85 if vol_ratio > 1.5 else 70
            results.append((f"💥 BB Bullish Sweep (Alt Band)", "LONG", strength))

        # Bearish BB Sweep: üst bandın üstüne çıktı, kapanış üst bandın altında
        elif highs[ci] > upper[i] and closes[ci] < upper[i]:
            strength = 85 if vol_ratio > 1.5 else 70
            results.append((f"💥 BB Bearish Sweep (Üst Band)", "SHORT", strength))

    return results

def detect_volume_spike(volumes, threshold=2.0):
    """Hacim spike tespiti — son mumda anormal hacim var mı?"""
    if len(volumes) < 10: return False, 0.0
    avg = sum(volumes[-11:-1]) / 10
    if avg == 0: return False, 0.0
    ratio = volumes[-1] / avg
    return ratio >= threshold, round(ratio, 2)

def find_swing_points(highs, lows, lookback=3):
    n=len(highs); sh=[]; sl=[]
    for i in range(lookback,n-lookback):
        if all(highs[i]>=highs[i-j] for j in range(1,lookback+1)) and \
           all(highs[i]>=highs[i+j] for j in range(1,lookback+1)):
            sh.append((i,highs[i]))
        if all(lows[i]<=lows[i-j] for j in range(1,lookback+1)) and \
           all(lows[i]<=lows[i+j] for j in range(1,lookback+1)):
            sl.append((i,lows[i]))
    return sh,sl

# ══════════════════════════════════════════════════════════════════════════════
#  SMC TEMEL FONKSİYONLAR
# ══════════════════════════════════════════════════════════════════════════════
def detect_bos_choch(opens, highs, lows, closes):
    n=len(closes)
    if n<20: return None,None,None
    sh,sl=find_swing_points(highs,lows,lookback=3)
    if len(sh)<2 or len(sl)<2: return None,None,None
    price=closes[-1]
    bos=None; choch=None
    if price>sh[-2][1] and sl[-1][1]>sl[-2][1]: bos="YUKARI"
    elif price<sl[-2][1] and sh[-1][1]<sh[-2][1]: bos="AŞAĞI"
    if sh[-1][1]<sh[-2][1] and price>sh[-1][1]: choch="YUKARI"
    elif sl[-1][1]>sl[-2][1] and price<sl[-1][1]: choch="AŞAĞI"
    struct="YUKARI" if sh[-1][0]>sl[-1][0] else "AŞAĞI"
    return bos,choch,struct

def find_order_blocks(opens, highs, lows, closes, volumes, lookback=5):
    n=len(closes); obs=[]; atr=calc_atr(highs,lows,closes) or 1
    for i in range(3,n-3):
        body=abs(closes[i]-opens[i])
        if body<atr*0.3: continue
        avg_vol=sum(volumes[max(0,i-10):i])/10 if i>=10 else 1
        vol_ratio=volumes[i]/avg_vol if avg_vol>0 else 1

        # Bullish OB
        if closes[i]<opens[i]:
            nm=max(highs[i+1:i+4]) if i+4<=n else 0
            if nm-closes[i]>atr*1.5:
                mitigated=any(lows[j]<closes[i] for j in range(i+1,n))
                tested=sum(1 for j in range(i+1,n) if lows[j]<=highs[i] and highs[j]>=lows[i])
                if not mitigated or tested<=1:
                    s=60+(20 if not mitigated else 0)+(15 if tested==0 else 8 if tested==1 else 0)+(10 if vol_ratio>1.5 else 0)
                    obs.append({"type":"Bullish OB","direction":"LONG","high":highs[i],"low":lows[i],
                                 "open":opens[i],"close":closes[i],"index":i,
                                 "strength":min(s,100),"tested":tested,"mitigated":mitigated,"vol_ratio":vol_ratio})

        # Bearish OB
        elif closes[i]>opens[i]:
            nd=closes[i]-min(lows[i+1:i+4]) if i+4<=n else 0
            if nd>atr*1.5:
                mitigated=any(highs[j]>opens[i] for j in range(i+1,n))
                tested=sum(1 for j in range(i+1,n) if highs[j]>=lows[i] and lows[j]<=highs[i])
                if not mitigated or tested<=1:
                    s=60+(20 if not mitigated else 0)+(15 if tested==0 else 8 if tested==1 else 0)+(10 if vol_ratio>1.5 else 0)
                    obs.append({"type":"Bearish OB","direction":"SHORT","high":highs[i],"low":lows[i],
                                 "open":opens[i],"close":closes[i],"index":i,
                                 "strength":min(s,100),"tested":tested,"mitigated":mitigated,"vol_ratio":vol_ratio})

    obs.sort(key=lambda x:x["strength"],reverse=True)
    return obs

def find_fvg(opens, highs, lows, closes):
    n=len(closes); fvgs=[]
    for i in range(1,n-1):
        if lows[i+1]>highs[i-1]:
            filled=any(lows[j]<=highs[i-1]+(lows[i+1]-highs[i-1])*0.5 for j in range(i+2,n))
            if not filled:
                fvgs.append({"type":"Bullish FVG","direction":"LONG","high":lows[i+1],"low":highs[i-1],"index":i})
        elif highs[i+1]<lows[i-1]:
            filled=any(highs[j]>=lows[i-1]-(lows[i-1]-highs[i+1])*0.5 for j in range(i+2,n))
            if not filled:
                fvgs.append({"type":"Bearish FVG","direction":"SHORT","high":lows[i-1],"low":highs[i+1],"index":i})
    return fvgs

def find_liquidity(highs, lows, closes):
    try:
        sh,sl=find_swing_points(highs,lows,lookback=2)
        price=closes[-1]
        bsl=[v for _,v in sh[-5:]] if sh else []
        ssl=[v for _,v in sl[-5:]] if sl else []
        return {
            "bsl":bsl,"ssl":ssl,
            "bsl_taken":any(price>lvl for lvl in bsl),
            "ssl_taken":any(price<lvl for lvl in ssl),
        }
    except:
        return {"bsl":[],"ssl":[],"bsl_taken":False,"ssl_taken":False}

def find_premium_discount(highs, lows, closes, lookback=50):
    if len(closes)<lookback: lookback=len(closes)
    hi=max(highs[-lookback:]); lo=min(lows[-lookback:])
    price=closes[-1]
    if hi==lo: return {"zone":"Value","pct":50,"mid":(hi+lo)/2}
    pct=(price-lo)/(hi-lo)*100
    if pct<=30:   zone="Derin Discount"
    elif pct<=50: zone="Discount"
    elif pct<=70: zone="Premium"
    else:         zone="Derin Premium"
    return {"zone":zone,"pct":round(pct,1),"mid":round((hi+lo)/2,6)}

def detect_divergence(highs, lows, closes, rsi_period=14):
    n=len(closes)
    if n<rsi_period+20: return []
    rsi_series=[]
    for i in range(rsi_period+1,n+1):
        r=calc_rsi(closes[:i],rsi_period)
        if r: rsi_series.append(r)
    if len(rsi_series)<10: return []
    sh,sl=find_swing_points(highs,lows,lookback=3)
    divs=[]
    if len(sl)>=2:
        i1,p1=sl[-2]; i2,p2=sl[-1]
        if i1<len(rsi_series) and i2<len(rsi_series):
            r1=rsi_series[i1]; r2=rsi_series[i2]
            if p2<p1 and r2>r1: divs.append(("🟢 Bullish Div.","LONG",85))
            elif p2>p1 and r2<r1: divs.append(("🟢 Hidden Bull Div.","LONG",72))
    if len(sh)>=2:
        i1,p1=sh[-2]; i2,p2=sh[-1]
        if i1<len(rsi_series) and i2<len(rsi_series):
            r1=rsi_series[i1]; r2=rsi_series[i2]
            if p2>p1 and r2<r1: divs.append(("🔴 Bearish Div.","SHORT",85))
            elif p2<p1 and r2>r1: divs.append(("🔴 Hidden Bear Div.","SHORT",72))
    return divs

def detect_sweep_reversal(highs, lows, closes, volumes, atr):
    if not atr or len(closes)<5: return []
    results=[]
    sh,sl=find_swing_points(highs,lows,lookback=3)
    n=len(closes)
    if sl:
        last_sl=sl[-1][1]
        for i in range(max(0,n-3),n):
            if lows[i]<last_sl and closes[i]>last_sl:
                avg_v=sum(volumes[max(0,i-10):i])/10 if i>=10 else volumes[i]
                vr=volumes[i]/avg_v if avg_v>0 else 1
                results.append((f"💥 Bullish Sweep","LONG",80 if vr>1.5 else 65))
                break
    if sh:
        last_sh=sh[-1][1]
        for i in range(max(0,n-3),n):
            if highs[i]>last_sh and closes[i]<last_sh:
                avg_v=sum(volumes[max(0,i-10):i])/10 if i>=10 else volumes[i]
                vr=volumes[i]/avg_v if avg_v>0 else 1
                results.append((f"💥 Bearish Sweep","SHORT",80 if vr>1.5 else 65))
                break
    return results

# ══════════════════════════════════════════════════════════════════════════════
#  HAFTALIK S/R SEVİYELERİ
# ══════════════════════════════════════════════════════════════════════════════
def find_weekly_sr(highs_1w, lows_1w, closes_1w, price, atr):
    """Haftalık mumlardan S/R seviyeleri çıkar"""
    if not highs_1w or len(highs_1w)<3: return []
    levels=[]
    for i in range(len(highs_1w)):
        levels.append(("R",highs_1w[i]))
        levels.append(("S",lows_1w[i]))
    # Fiyata yakın seviyeleri bul
    nearby=[]
    for typ,lvl in levels:
        if atr and abs(price-lvl)<atr*3:
            nearby.append({"type":typ,"level":round(lvl,6),
                           "dist":round(abs(price-lvl)/price*100,2)})
    nearby.sort(key=lambda x:x["dist"])
    return nearby[:4]

# ══════════════════════════════════════════════════════════════════════════════
#  BTC DURUM KONTROLÜ
# ══════════════════════════════════════════════════════════════════════════════
_btc_cache = {"price":0,"change":0,"trend":"—","ts":0}

def get_btc_status():
    """BTC anlık durum — 5 dakikada bir güncelle"""
    global _btc_cache
    now=time.time()
    if now-_btc_cache["ts"]<300:
        return _btc_cache
    try:
        d=safe_get("https://open-api.bingx.com/openApi/swap/v2/quote/ticker",timeout=8)
        if not d or not isinstance(d, dict): return _btc_cache
        tickers=d.get("data",[]) or []
        if isinstance(tickers,dict): tickers=tickers.get("tickers",[]) or []
        for t in (tickers or []):
            if not isinstance(t, dict): continue
            sym = t.get("symbol","") or ""
            if "BTC-USDT" in sym or "BTCUSDT" in sym:
                price=safe_float(t.get("lastPrice",0))
                change=safe_float(t.get("priceChangePercent",0))
                ema=None
                cd=get_candles_safe("BingX","BTC","4h",210)
                if cd and len(cd)>3 and cd[3]:
                    ema=calc_ema(cd[3],200)
                trend="YUKARI" if (ema and price>ema) else ("AŞAĞI" if ema else "—")
                _btc_cache={"price":price,"change":change,"trend":trend,"ts":now}
                return _btc_cache
    except: pass
    return _btc_cache

# ══════════════════════════════════════════════════════════════════════════════
#  MUM VERİSİ ÇEKİMİ — GÜVENLİ
# ══════════════════════════════════════════════════════════════════════════════
def get_candles_safe(exchange, symbol, tf="4h", limit=100):
    """Güvenli mum çekimi — SSL hataları sessizce yakalanır"""
    sym_clean=symbol.replace("/USD","")
    try:
        if exchange=="Binance":
            # Binance Futures direkt
            return get_candles_binance(sym_clean, tf, limit)

        elif exchange=="OKX":
            okx_tf=TF_MAP_OKX.get(tf.lower(),"4H")
            inst_id=f"{sym_clean}-USDT-SWAP"
            for url in [
                f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={okx_tf}&limit={limit}",
                f"https://www.okx.com/api/v5/market/history-candles?instId={inst_id}&bar={okx_tf}&limit={limit}",
            ]:
                try:
                    d=safe_get(url,timeout=10)
                    data=list(reversed(d.get("data",[])))
                    if data:
                        return ([float(x[1]) for x in data],[float(x[2]) for x in data],
                                [float(x[3]) for x in data],[float(x[4]) for x in data],
                                [float(x[5]) for x in data])
                except: continue
            # OKX başarısız → Binance fallback
            return get_candles_binance(sym_clean,tf,limit)

        elif exchange=="BingX":
            bx_tf=TF_MAP_BX.get(tf.lower(),"4h")
            sym_fmt=f"{sym_clean}-USDT"
            d=safe_get(
                f"https://open-api.bingx.com/openApi/swap/v3/quote/klines"
                f"?symbol={sym_fmt}&interval={bx_tf}&limit={limit}",timeout=10)
            if not d or not isinstance(d, dict): return None
            data=d.get("data",[]) or []
            if data and isinstance(data[0], dict):
                try:
                    return ([float(x.get("open",0)) for x in data],
                            [float(x.get("high",0)) for x in data],
                            [float(x.get("low",0))  for x in data],
                            [float(x.get("close",0))for x in data],
                            [float(x.get("volume",0))for x in data])
                except: return None
    except: pass
    return None

def get_candles_binance(symbol, tf="4h", limit=100):
    """Binance Futures fallback"""
    try:
        tf_map={"1h":"1h","4h":"4h","1d":"1d","1w":"1w"}
        interval=tf_map.get(tf.lower(),"4h")
        sym=symbol+"USDT"
        d=safe_get(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval={interval}&limit={limit}",timeout=10)
        if isinstance(d,list) and d:
            return ([float(x[1]) for x in d],[float(x[2]) for x in d],
                    [float(x[3]) for x in d],[float(x[4]) for x in d],
                    [float(x[5]) for x in d])
    except: pass
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  ANA ANALİZ MOTORU — SWING TRADE
# ══════════════════════════════════════════════════════════════════════════════
def analyze_swing(coin, settings, c1d, c4h, c1h, c1w, btc_status, fng=None, btc_ls=None, btc_oi=None, cg_api_key=""):
    """
    3 katmanlı swing trade analizi — güvenli wrapper ile
    Katman 1: 1D — Ana trend, haftalık S/R, büyük OB
    Katman 2: 4H — Orta vadeli yapı, giriş bölgesi
    Katman 3: 1H — Giriş onayı, formasyon
    """
    result={
        "signal":"BEKLE","score":0,"confidence":"—",
        "ob_type":"—","ob_high":0,"ob_low":0,"ob_strength":0,"ob_tested":0,
        "ob_dir_warning":False,
        "bos_1d":"—","choch_1d":"—","trend_1d":"—",
        "bos_4h":"—","choch_4h":"—","trend_4h":"—",
        "choch_1h":"—",
        "pd_zone":"—","pd_pct":0,
        "fvg_active":False,"liquidity":"—",
        "weekly_sr_near":"—","weekly_levels":[],
        "divergences":[],"sweeps":[],
        "btc_status":"—","btc_ok":True,
        "sl":0,"tp1":0,"tp2":0,"rr":"—","trailing_stop":"—",
        "reasons":[],"all_obs":[],"all_fvgs":[],
        "mtf_align":False,
    }

    if c4h is None: return result
    o4,h4,l4,c4,v4=c4h
    if len(c4)<20: return result

    price=coin.get("price",c4[-1])
    atr4=calc_atr(h4,l4,c4) or price*0.01
    funding=coin.get("funding",0) or 0

    long_pts=0; short_pts=0; reasons=[]

    # ── KATMAN 1: 1D TREND ───────────────────────────────────────────
    trend_1d="—"; ema200_1d=None
    if c1d:
        o1,h1d_arr,l1d_arr,c1d_arr,v1d_arr=c1d
        bos1d,choch1d,struct1d=detect_bos_choch(o1,h1d_arr,l1d_arr,c1d_arr)
        result["bos_1d"]=bos1d or "—"
        result["choch_1d"]=choch1d or "—"
        ema200_1d=calc_ema(c1d_arr,200) if len(c1d_arr)>=200 else calc_ema(c1d_arr,50)
        ema50_1d =calc_ema(c1d_arr,50)  if len(c1d_arr)>=50  else None

        if ema200_1d:
            if price>ema200_1d:
                trend_1d="YUKARI"
                long_pts+=20; reasons.append("📅 1D EMA200 üstünde — ana trend yukarı")
                if ema50_1d and ema50_1d>ema200_1d:
                    long_pts+=10; reasons.append("📅 1D EMA50>EMA200 — güçlü yükseliş")
            else:
                trend_1d="AŞAĞI"
                short_pts+=20; reasons.append("📅 1D EMA200 altında — ana trend aşağı")
                if ema50_1d and ema50_1d<ema200_1d:
                    short_pts+=10; reasons.append("📅 1D EMA50<EMA200 — güçlü düşüş")

        if bos1d=="YUKARI":   long_pts+=12;  reasons.append("📅 1D BOS Yukarı")
        elif bos1d=="AŞAĞI":  short_pts+=12; reasons.append("📅 1D BOS Aşağı")
        if choch1d=="YUKARI": long_pts+=15;  reasons.append("📅 1D CHoCH Yukarı — dönüş!")
        elif choch1d=="AŞAĞI":short_pts+=15; reasons.append("📅 1D CHoCH Aşağı — dönüş!")

        result["trend_1d"]=trend_1d

        # 1D OB
        obs_1d=find_order_blocks(o1,h1d_arr,l1d_arr,c1d_arr,v1d_arr)
        for ob in obs_1d[:3]:
            margin=(ob["high"]-ob["low"])*0.1
            if ob["low"]-margin<=price<=ob["high"]+margin:
                bonus=int(ob["strength"]*0.3)
                if ob["direction"]=="LONG":
                    long_pts+=bonus; reasons.append(f"📅 1D {ob['type']} içinde (güç:{ob['strength']}%)")
                else:
                    short_pts+=bonus; reasons.append(f"📅 1D {ob['type']} içinde (güç:{ob['strength']}%)")
                break

        # Haftalık S/R
        if c1w:
            _,h1w,l1w,c1w_arr,_=c1w
            atr1d=calc_atr(h1d_arr,l1d_arr,c1d_arr) or atr4
            weekly=find_weekly_sr(list(h1w),list(l1w),list(c1w_arr),price,atr1d)
            result["weekly_levels"]=weekly
            if weekly:
                nearest=weekly[0]
                result["weekly_sr_near"]=f"{nearest['type']} ${nearest['level']:.4f} ({nearest['dist']:.1f}%)"
                if nearest["type"]=="S" and nearest["dist"]<1.5:
                    long_pts+=10; reasons.append(f"📊 Haftalık destek yakın (${nearest['level']:.4f})")
                elif nearest["type"]=="R" and nearest["dist"]<1.5:
                    short_pts+=10; reasons.append(f"📊 Haftalık direnç yakın (${nearest['level']:.4f})")

    # ── KATMAN 2: 4H YAPI ────────────────────────────────────────────
    bos4,choch4,struct4=detect_bos_choch(o4,h4,l4,c4)
    result["bos_4h"]=bos4 or "—"; result["choch_4h"]=choch4 or "—"
    ema200_4h=calc_ema(c4,200) if len(c4)>=200 else calc_ema(c4,50)
    trend_4h="YUKARI" if (ema200_4h and price>ema200_4h) else "AŞAĞI" if ema200_4h else "—"
    result["trend_4h"]=trend_4h

    if bos4=="YUKARI":   long_pts+=10;  reasons.append("4H BOS Yukarı")
    elif bos4=="AŞAĞI":  short_pts+=10; reasons.append("4H BOS Aşağı")
    if choch4=="YUKARI": long_pts+=12;  reasons.append("4H CHoCH Yukarı")
    elif choch4=="AŞAĞI":short_pts+=12; reasons.append("4H CHoCH Aşağı")

    # 4H OB
    obs_4h=find_order_blocks(o4,h4,l4,c4,v4)
    result["all_obs"]=obs_4h[:5]
    active_ob=None
    for ob in obs_4h:
        margin=(ob["high"]-ob["low"])*0.15
        if ob["low"]-margin<=price<=ob["high"]+margin:
            active_ob=ob; break

    ob_dir_warning=False
    if active_ob:
        bonus=int(active_ob["strength"]*0.35)
        result["ob_type"]=active_ob["type"]
        result["ob_high"]=active_ob["high"]
        result["ob_low"]=active_ob["low"]
        result["ob_strength"]=active_ob["strength"]
        result["ob_tested"]=active_ob["tested"]

        if active_ob["direction"]=="LONG":
            long_pts+=bonus
            reasons.append(f"📦 4H {active_ob['type']} (güç:{active_ob['strength']}%, test:{active_ob['tested']}x)")
            if active_ob["tested"]==0: long_pts+=12; reasons.append("✨ Taze OB")
            elif active_ob["tested"]==1: long_pts+=6; reasons.append("✅ OB 1x test tuttu")
            # OB yönü uyarısı
            if short_pts>long_pts:
                ob_dir_warning=True
                reasons.append("⚠️ UYARI: Bullish OB içindesin ama sinyal SHORT!")
        else:
            short_pts+=bonus
            reasons.append(f"📦 4H {active_ob['type']} (güç:{active_ob['strength']}%, test:{active_ob['tested']}x)")
            if active_ob["tested"]==0: short_pts+=12; reasons.append("✨ Taze OB")
            elif active_ob["tested"]==1: short_pts+=6; reasons.append("✅ OB 1x test tuttu")
            if long_pts>short_pts:
                ob_dir_warning=True
                reasons.append("⚠️ UYARI: Bearish OB içindesin ama sinyal LONG!")

    result["ob_dir_warning"]=ob_dir_warning

    # 4H FVG
    fvgs=find_fvg(o4,h4,l4,c4)
    result["all_fvgs"]=fvgs[-3:]
    for fvg in reversed(fvgs[-3:]):
        if fvg["low"]-atr4*0.5<=price<=fvg["high"]+atr4*0.5:
            result["fvg_active"]=True
            if fvg["direction"]=="LONG":
                long_pts+=12; reasons.append("🌊 4H Bullish FVG bölgesinde")
                if active_ob and active_ob["direction"]=="LONG":
                    long_pts+=10; reasons.append("💎 OB + FVG örtüşümü!")
            else:
                short_pts+=12; reasons.append("🌊 4H Bearish FVG bölgesinde")
                if active_ob and active_ob["direction"]=="SHORT":
                    short_pts+=10; reasons.append("💎 OB + FVG örtüşümü!")
            break

    # 4H Likidite
    liq=find_liquidity(h4,l4,c4) or {"bsl":[],"ssl":[],"bsl_taken":False,"ssl_taken":False}
    if liq["bsl_taken"]:  short_pts+=10; reasons.append("💧 BSL alındı → Short fırsatı"); result["liquidity"]="BSL Alındı"
    elif liq["ssl_taken"]: long_pts+=10; reasons.append("💧 SSL alındı → Long fırsatı"); result["liquidity"]="SSL Alındı"

    # 4H Premium/Discount
    pd=find_premium_discount(h4,l4,c4)
    result["pd_zone"]=pd["zone"]; result["pd_pct"]=pd["pct"]
    if pd["zone"]=="Derin Discount":
        long_pts+=15; reasons.append(f"💎 Derin Discount (%{pd['pct']:.0f}) — kurumsal alım bölgesi")
        if active_ob and active_ob["direction"]=="LONG":
            long_pts+=8; reasons.append("🏆 OB + Derin Discount örtüşümü!")
    elif pd["zone"]=="Discount":
        long_pts+=8; reasons.append(f"💎 Discount (%{pd['pct']:.0f})")
    elif pd["zone"]=="Derin Premium":
        short_pts+=15; reasons.append(f"💎 Derin Premium (%{pd['pct']:.0f}) — kurumsal satış bölgesi")
        if active_ob and active_ob["direction"]=="SHORT":
            short_pts+=8; reasons.append("🏆 OB + Derin Premium örtüşümü!")
    elif pd["zone"]=="Premium":
        short_pts+=8; reasons.append(f"💎 Premium (%{pd['pct']:.0f})")

    # 4H Divergence
    divs=detect_divergence(h4,l4,c4)
    result["divergences"]=divs
    for name,direction,strength in divs:
        bonus=int(strength*0.18)
        if direction=="LONG":   long_pts+=bonus;  reasons.append(f"📐 {name}")
        elif direction=="SHORT": short_pts+=bonus; reasons.append(f"📐 {name}")

    # 4H Sweep+Reversal (mevcut)
    sweeps=detect_sweep_reversal(h4,l4,c4,v4,atr4)

    # 4H BB Sweep (YENİ)
    bb_sweeps=detect_bb_sweep(h4,l4,c4,v4)
    sweeps.extend(bb_sweeps)

    result["sweeps"]=sweeps
    for name,direction,strength in sweeps:
        bonus=int(strength*0.2)
        if direction=="LONG":   long_pts+=bonus;  reasons.append(f"{name}")
        elif direction=="SHORT": short_pts+=bonus; reasons.append(f"{name}")

    # 4H MFI (YENİ)
    mfi4=calc_mfi(h4,l4,c4,v4)
    if mfi4 is not None:
        if mfi4<20:   long_pts+=12;  reasons.append(f"💰 MFI aşırı satım ({mfi4:.1f}) — para girişi bekleniyor")
        elif mfi4<35: long_pts+=6;   reasons.append(f"💰 MFI düşük ({mfi4:.1f})")
        elif mfi4>80: short_pts+=12; reasons.append(f"💰 MFI aşırı alım ({mfi4:.1f}) — para çıkışı bekleniyor")
        elif mfi4>65: short_pts+=6;  reasons.append(f"💰 MFI yüksek ({mfi4:.1f})")

    # 4H Hacim Spike (YENİ)
    vol_spike, vol_ratio=detect_volume_spike(v4)
    if vol_spike:
        if long_pts>=short_pts:
            long_pts+=8; reasons.append(f"📊 Hacim spike ({vol_ratio:.1f}x) — Long momentum")
        else:
            short_pts+=8; reasons.append(f"📊 Hacim spike ({vol_ratio:.1f}x) — Short momentum")

    # 4H Bollinger Bands durumu (YENİ)
    bb_upper, bb_mid, bb_lower=calc_bollinger_bands(c4)
    if bb_upper and len(bb_upper)>0:
        curr_price=c4[-1]
        if curr_price<bb_lower[-1]:
            long_pts+=10; reasons.append(f"📉 Fiyat BB alt bandın altında — oversold")
        elif curr_price>bb_upper[-1]:
            short_pts+=10; reasons.append(f"📈 Fiyat BB üst bandın üstünde — overbought")
        # BB sıkışma (düşük volatilite = büyük hareket yakın)
        bb_width=(bb_upper[-1]-bb_lower[-1])/bb_mid[-1]*100 if bb_mid[-1]>0 else 0
        if bb_width<3.0:
            reasons.append(f"🔀 BB Sıkışma ({bb_width:.1f}%) — büyük hareket yakın")

    # 4H RSI
    rsi4=calc_rsi(c4)
    if rsi4:
        if rsi4<30:   long_pts+=12;  reasons.append(f"RSI aşırı satım ({rsi4:.1f})")
        elif rsi4<40: long_pts+=6;   reasons.append(f"RSI düşük ({rsi4:.1f})")
        elif rsi4>70: short_pts+=12; reasons.append(f"RSI aşırı alım ({rsi4:.1f})")
        elif rsi4>60: short_pts+=6;  reasons.append(f"RSI yüksek ({rsi4:.1f})")

    # ── v9.0: TILSON T3 TREND FİLTRESİ ──────────────────────────────────────
    # T3, EMA200'den daha az gecikmeyle trend yönünü söyler
    # Fiyat T3 üstündeyse → bullish bias | altındaysa → bearish bias
    t3_4h = calc_tilson_t3(c4)
    if t3_4h:
        result["t3_4h"] = t3_4h["value"]
        if t3_4h["price_above"] and t3_4h["rising"]:
            long_pts  += 12
            reasons.append(f"📈 T3 üstünde & yükseliyor (T3:{t3_4h['value']:.5g}) — güçlü bull trend")
        elif t3_4h["price_above"] and not t3_4h["rising"]:
            long_pts  += 5
            reasons.append(f"📈 T3 üstünde ama düzleşiyor (T3:{t3_4h['value']:.5g})")
        elif not t3_4h["price_above"] and not t3_4h["rising"]:
            short_pts += 12
            reasons.append(f"📉 T3 altında & düşüyor (T3:{t3_4h['value']:.5g}) — güçlü bear trend")
        elif not t3_4h["price_above"] and t3_4h["rising"]:
            short_pts += 5
            reasons.append(f"📉 T3 altında ama düzleşiyor (T3:{t3_4h['value']:.5g})")

    # ── v9.0: VMC CIPHER B — RSI+MFI PARA AKIŞI ─────────────────────────────
    # Para giriyor mu, çıkıyor mu? Trend yönünü teyit eder
    rsimfi_4h = calc_vmc_rsimfi(h4, l4, c4, o4)
    if rsimfi_4h is not None:
        result["rsimfi_4h"] = rsimfi_4h
        if rsimfi_4h > 20:
            long_pts  += 10
            reasons.append(f"💚 VMC MFI güçlü pozitif ({rsimfi_4h:.1f}) — para giriyor")
        elif rsimfi_4h > 0:
            long_pts  += 5
            reasons.append(f"💚 VMC MFI pozitif ({rsimfi_4h:.1f})")
        elif rsimfi_4h < -20:
            short_pts += 10
            reasons.append(f"❤️ VMC MFI güçlü negatif ({rsimfi_4h:.1f}) — para çıkıyor")
        elif rsimfi_4h < 0:
            short_pts += 5
            reasons.append(f"❤️ VMC MFI negatif ({rsimfi_4h:.1f})")

    # Fonlama
    if funding<-0.03:  long_pts+=12;  reasons.append(f"💸 Fonlama çok negatif ({funding:.4f}%)")
    elif funding<0:    long_pts+=6;   reasons.append(f"💸 Fonlama negatif ({funding:.4f}%)")
    elif funding>0.03: short_pts+=12; reasons.append(f"💸 Fonlama çok pozitif ({funding:.4f}%)")
    elif funding>0:    short_pts+=4

    # ── KATMAN 3: 1H GİRİŞ ONAYI ─────────────────────────────────────
    if c1h:
        o1h,h1h,l1h,c1h_arr,v1h=c1h
        if len(c1h_arr)>=10:
            _,choch1h,_=detect_bos_choch(o1h,h1h,l1h,c1h_arr)
            result["choch_1h"]=choch1h or "—"
            if choch1h=="YUKARI" and long_pts>=short_pts:
                long_pts+=15; reasons.append("✅ 1H CHoCH Yukarı — giriş onayı")
            elif choch1h=="AŞAĞI" and short_pts>=long_pts:
                short_pts+=15; reasons.append("✅ 1H CHoCH Aşağı — giriş onayı")

            # 1H OB
            obs1h=find_order_blocks(o1h,h1h,l1h,c1h_arr,v1h)
            for ob1h in obs1h[:2]:
                margin=(ob1h["high"]-ob1h["low"])*0.15
                if ob1h["low"]-margin<=price<=ob1h["high"]+margin:
                    if ob1h["direction"]=="LONG" and long_pts>=short_pts:
                        long_pts+=10; reasons.append(f"📦 1H Bullish OB teyidi")
                    elif ob1h["direction"]=="SHORT" and short_pts>=long_pts:
                        short_pts+=10; reasons.append(f"📦 1H Bearish OB teyidi")
                    break

            # 1H FVG
            fvgs1h=find_fvg(o1h,h1h,l1h,c1h_arr)
            atr1h=calc_atr(h1h,l1h,c1h_arr) or atr4*0.25
            for fvg1h in reversed(fvgs1h[-2:]):
                if fvg1h["low"]-atr1h<=price<=fvg1h["high"]+atr1h:
                    if fvg1h["direction"]=="LONG" and long_pts>=short_pts:
                        long_pts+=8; reasons.append("🌊 1H Bullish FVG teyidi")
                    elif fvg1h["direction"]=="SHORT" and short_pts>=long_pts:
                        short_pts+=8; reasons.append("🌊 1H Bearish FVG teyidi")
                    break

            # ── v9.0: VMC CIPHER B — WAVETREND GİRİŞ SİNYALİ ───────────────
            # En güçlü sinyal: oversold bölgede yukarı kesme (🟢 yeşil daire)
            # En güçlü sinyal: overbought bölgede aşağı kesme (🔴 kırmızı daire)
            wt_1h = calc_wavetrend(h1h, l1h, c1h_arr)
            if wt_1h:
                result["wt_1h"] = wt_1h
                if wt_1h["buy_signal"] and long_pts >= short_pts:
                    # 🟢 Yeşil daire: oversold'da yukarı kesme → güçlü giriş onayı
                    long_pts  += 22
                    reasons.append(f"🟢 VMC WaveTrend LONG! Oversold'dan yukarı kesti (WT:{wt_1h['wt2']:.1f})")
                elif wt_1h["sell_signal"] and short_pts >= long_pts:
                    # 🔴 Kırmızı daire: overbought'ta aşağı kesme → güçlü giriş onayı
                    short_pts += 22
                    reasons.append(f"🔴 VMC WaveTrend SHORT! Overbought'tan aşağı kesti (WT:{wt_1h['wt2']:.1f})")
                elif wt_1h["cross_up"] and long_pts >= short_pts:
                    # Kesme var ama oversold değil — zayıf sinyal
                    long_pts  += 8
                    reasons.append(f"🔵 WaveTrend yukarı kesti (WT:{wt_1h['wt2']:.1f})")
                elif wt_1h["cross_down"] and short_pts >= long_pts:
                    short_pts += 8
                    reasons.append(f"🔵 WaveTrend aşağı kesti (WT:{wt_1h['wt2']:.1f})")
                elif wt_1h["oversold"] and long_pts >= short_pts:
                    # Henüz kesmedi ama oversold bölgede — hazırlanıyor olabilir
                    long_pts  += 8
                    reasons.append(f"🟡 WaveTrend oversold bölgede ({wt_1h['wt2']:.1f}) — kesme bekle")
                elif wt_1h["overbought"] and short_pts >= long_pts:
                    short_pts += 8
                    reasons.append(f"🟠 WaveTrend overbought bölgede ({wt_1h['wt2']:.1f}) — kesme bekle")

    # ── MTF UYUM KONTROLÜ ─────────────────────────────────────────────
    mtf_conflict = False
    if trend_1d!="—" and trend_4h!="—":
        if trend_1d==trend_4h:
            result["mtf_align"]=True
            if trend_1d=="YUKARI": long_pts+=15; reasons.append("🌐 MTF Tam Uyum: 1D+4H YUKARI")
            else:                  short_pts+=15; reasons.append("🌐 MTF Tam Uyum: 1D+4H AŞAĞI")
        else:
            mtf_conflict = True
            # MTF uyumsuzlukta puan %40 azalt — swing trade için kritik
            long_pts  = int(long_pts  * 0.6)
            short_pts = int(short_pts * 0.6)
            reasons.append(f"❌ MTF Uyumsuzluk: 1D={trend_1d}, 4H={trend_4h} — puan azaltıldı")

    # ── BTC KORELASYON FİLTRESİ ──────────────────────────────────────
    btc=btc_status or {}
    btc_change=btc.get("change",0)
    btc_trend=btc.get("trend","—")
    btc_ok=True
    btc_str=f"${btc.get('price',0):,.0f} ({btc_change:+.1f}%) {btc_trend}"
    result["btc_status"]=btc_str

    drop_limit=settings.get("btc_drop_pct",3.0)
    if settings.get("btc_filter",True):
        if btc_change<-drop_limit and long_pts>short_pts:
            long_pts=int(long_pts*0.5)
            reasons.append(f"⚠️ BTC {btc_change:.1f}% düşüşte — Long sinyali zayıflatıldı")
            btc_ok=False
        elif btc_change>drop_limit and short_pts>long_pts:
            short_pts=int(short_pts*0.5)
            reasons.append(f"⚠️ BTC {btc_change:.1f}% yükselişte — Short sinyali zayıflatıldı")
            btc_ok=False
        elif btc_trend=="YUKARI" and long_pts>short_pts:
            long_pts+=8; reasons.append("₿ BTC trendi Long yönünde")
        elif btc_trend=="AŞAĞI" and short_pts>long_pts:
            short_pts+=8; reasons.append("₿ BTC trendi Short yönünde")
    result["btc_ok"]=btc_ok

    # ── V7: FEAR & GREED ─────────────────────────────────────────────
    if fng:
        result["fear_greed"]    = fng.get("value",50)
        result["fear_greed_lbl"]= fng.get("label","—")
        fng_val = fng.get("value",50)
        if fng_val <= 25 and long_pts > short_pts:
            long_pts  += 10; reasons.append(f"😱 Aşırı Korku ({fng_val}) — kontra long fırsatı")
        elif fng_val >= 75 and short_pts > long_pts:
            short_pts += 10; reasons.append(f"🤑 Aşırı Açgözlülük ({fng_val}) — kontra short fırsatı")
        elif fng_val <= 40 and long_pts > short_pts:
            long_pts  += 5; reasons.append(f"😨 Korku ortamı ({fng_val}) — long destekli")
        elif fng_val >= 60 and short_pts > long_pts:
            short_pts += 5; reasons.append(f"😏 Açgözlülük ortamı ({fng_val}) — short destekli")

    # ── V7: LONG/SHORT ORANI ────────────────────────────────────────
    if btc_ls:
        result["ls_long"]   = btc_ls.get("long_pct",50)
        result["ls_short"]  = btc_ls.get("short_pct",50)
        result["ls_status"] = btc_ls.get("status","—")
        lp = btc_ls.get("long_pct",50)
        if lp > 65 and short_pts > long_pts:
            short_pts += 12; reasons.append(f"⚠️ Aşırı Long (%{lp}) — short kontra sinyal")
        elif lp < 35 and long_pts > short_pts:
            long_pts  += 12; reasons.append(f"⚠️ Aşırı Short (%{100-lp}) — long kontra sinyal")
        elif 45 <= lp <= 55:
            reasons.append(f"✅ L/S Dengeli (%{lp}/%{100-lp})")

    # ── V7: OI DEĞİŞİMİ ────────────────────────────────────────────
    if btc_oi:
        result["oi_change"] = btc_oi.get("change_pct",0)
        result["oi_status"] = btc_oi.get("status","—")
        oi_chg = btc_oi.get("change_pct",0)
        if oi_chg > 3 and long_pts > short_pts:
            long_pts  += 8; reasons.append(f"📈 OI artıyor (+%{oi_chg:.1f}) — long momentum")
        elif oi_chg > 3 and short_pts > long_pts:
            short_pts += 8; reasons.append(f"📈 OI artıyor (+%{oi_chg:.1f}) — short momentum")
        elif oi_chg < -3:
            reasons.append(f"📉 OI azalıyor (%{oi_chg:.1f}) — pozisyon kapanıyor, dikkat!")

    # ── V7: COINGLASS LİKİDASYON SEVİYELERİ ───────────────────────
    if cg_api_key and cg_api_key.strip():
        try:
            cg_liq = get_liquidation_levels(coin.get("symbol","BTC"), cg_api_key)
            if cg_liq and isinstance(cg_liq, dict):
                result["liq_levels"] = cg_liq.get("levels",[]) or []
                reasons.append("🔥 CoinGlass Heatmap verisi mevcut")
        except: pass

    # ── ÇELİŞKİ KONTROLÜ ─────────────────────────────────────────────
    conflict_long=False; conflict_short=False
    if long_pts>short_pts:
        cf=sum([
            any(f["direction"]=="SHORT" and f["high"]>price for f in result["all_fvgs"])*2,
            any(d=="SHORT" for _,d,_ in result["sweeps"])*2,
            (trend_1d=="AŞAĞI" and trend_4h=="AŞAĞI")*3,
            ("Premium" in result["pd_zone"])*1,
        ])
        if cf>=4: conflict_long=True; reasons.append(f"❌ Long iptal — {cf} çelişki faktörü")
        elif cf>=2: long_pts=int(long_pts*0.65); reasons.append(f"⚠️ Long zayıflatıldı — {cf} çelişki")
    elif short_pts>long_pts:
        cf=sum([
            any(f["direction"]=="LONG" and f["low"]<price for f in result["all_fvgs"])*2,
            any(d=="LONG" for _,d,_ in result["sweeps"])*2,
            (trend_1d=="YUKARI" and trend_4h=="YUKARI")*3,
            ("Discount" in result["pd_zone"])*1,
        ])
        if cf>=4: conflict_short=True; reasons.append(f"❌ Short iptal — {cf} çelişki faktörü")
        elif cf>=2: short_pts=int(short_pts*0.65); reasons.append(f"⚠️ Short zayıflatıldı — {cf} çelişki")

    # ── KARAR ─────────────────────────────────────────────────────────
    min_score=settings.get("min_score",80)
    min_rr=settings.get("min_rr",2.5)

    # Yapısal temel zorunlu
    has_structure=(active_ob is not None) or result["fvg_active"] or len(result["sweeps"])>0

    if long_pts>short_pts and long_pts>=min_score and not conflict_long and has_structure:
        result["signal"]="LONG"
        result["score"]=min(long_pts,100)
        pct=round(long_pts/max(long_pts+short_pts,1)*100)
        result["confidence"]=f"%{pct}"

        # Stop Loss: OB altı veya swing low
        sh_all,sl_all=find_swing_points(h4,l4,lookback=3)
        sl_base=active_ob["low"] if active_ob else (sl_all[-1][1] if sl_all else price-atr4*2)
        result["sl"]=round(sl_base-atr4*0.15,6)

        # TP1 (%50 pozisyon kapat), TP2 (tam hedef)
        tp_base=price+atr4*min_rr*1.5
        bsl_levels=[v for v in (liq.get("bsl",[]) or []) if v>price]
        raw_tp2=min(bsl_levels) if bsl_levels else tp_base
        # TP2 kesinlikle fiyatın üstünde olmalı
        result["tp2"]=round(max(raw_tp2, price*1.01),6)
        result["tp1"]=round(price+(result["tp2"]-price)*0.5,6)

        # Trailing stop
        result["trailing_stop"]=f"${round(result['sl']+atr4*0.5,6):.5g} → Kâr arttıkça 1.5x ATR takip"

    elif short_pts>long_pts and short_pts>=min_score and not conflict_short and has_structure:
        result["signal"]="SHORT"
        result["score"]=min(short_pts,100)
        pct=round(short_pts/max(long_pts+short_pts,1)*100)
        result["confidence"]=f"%{pct}"

        sh_all,sl_all=find_swing_points(h4,l4,lookback=3)
        sl_base=active_ob["high"] if active_ob else (sh_all[-1][1] if sh_all else price+atr4*2)
        # SL mutlaka fiyatın üstünde olmalı
        result["sl"]=round(max(sl_base+atr4*0.15, price*1.005),6)

        # TP seviyeleri mutlaka fiyatın altında olmalı
        ssl_levels=[v for v in (liq.get("ssl",[]) or []) if v<price and v>0]
        tp_base=price-atr4*min_rr*1.5
        # tp_base negatife düşmesin
        tp_base=max(tp_base, price*0.3)
        raw_tp2=max(ssl_levels) if ssl_levels else tp_base
        # TP2 kesinlikle fiyatın altında olmalı
        result["tp2"]=round(min(raw_tp2, price*0.99),6)
        result["tp1"]=round(price-(price-result["tp2"])*0.5,6)
        # TP1 de fiyatın altında olmalı
        if result["tp1"]>=price: result["tp1"]=round(price-(price-result["tp2"])*0.4,6)

        result["trailing_stop"]=f"${round(result['sl']-atr4*0.5,6):.5g} → Kâr arttıkça 1.5x ATR takip"

    else:
        result["signal"]="BEKLE"
        result["score"]=max(long_pts,short_pts)
        return result

    # R/R kontrolü
    risk=abs(price-result["sl"])
    reward=abs(result["tp2"]-price)
    if risk>0:
        rr_ratio=reward/risk
        result["rr"]=f"1:{round(rr_ratio,2)}"
        if rr_ratio<min_rr:
            result["signal"]="BEKLE"
            result["score"]=int(result["score"]*0.4)
            reasons.append(f"❌ R/R {rr_ratio:.2f} — min {min_rr} gerekli")
        elif rr_ratio>12:
            # Çok yüksek R/R = TP çok uzakta, güvenilirliği düşük
            result["score"]=int(result["score"]*0.85)
            reasons.append(f"⚠️ R/R çok yüksek (1:{rr_ratio:.1f}) — TP seviyeleri kontrol et")
    # TP negatif veya mantıksız kontrolü
    if result["signal"]=="SHORT" and result["tp2"]>=price:
        result["signal"]="BEKLE"
        reasons.append("❌ TP hesaplama hatası — sinyal iptal")
    if result["signal"]=="LONG" and result["tp2"]<=price:
        result["signal"]="BEKLE"
        reasons.append("❌ TP hesaplama hatası — sinyal iptal")

    result["reasons"]=reasons
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  V7 — KURUMSAL VERİ MODÜLLERİ
# ══════════════════════════════════════════════════════════════════════════════

# ─── FEAR & GREED INDEX ──────────────────────────────────────────────────────
_fng_cache = {"value": 50, "label": "Nötr", "ts": 0}

def get_fear_greed():
    global _fng_cache
    if time.time() - _fng_cache["ts"] < 3600:  # 1 saat cache
        return _fng_cache
    try:
        d = safe_get("https://api.alternative.me/fng/?limit=1", timeout=8)
        if not d or not isinstance(d, dict): return _fng_cache
        fng_list = d.get("data", []) or []
        data = fng_list[0] if fng_list and isinstance(fng_list[0], dict) else {}
        val = int(data.get("value", 50))
        label_map = {
            range(0,25):   "Aşırı Korku 😱",
            range(25,45):  "Korku 😨",
            range(45,55):  "Nötr 😐",
            range(55,75):  "Açgözlülük 😏",
            range(75,101): "Aşırı Açgözlülük 🤑",
        }
        label = next((v for k,v in label_map.items() if val in k), "Nötr")
        _fng_cache = {"value": val, "label": label, "ts": time.time()}
    except: pass
    return _fng_cache

# ─── BINANCE LONG/SHORT ORANI ────────────────────────────────────────────────
_ls_cache = {}

def get_long_short_ratio(symbol="BTC"):
    key = symbol
    if key in _ls_cache and time.time()-_ls_cache[key]["ts"]<300:
        return _ls_cache[key]
    try:
        sym = symbol.replace("/USD","") + "USDT"
        d = safe_get(
            f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
            f"?symbol={sym}&period=1h&limit=1", timeout=8)
        if isinstance(d, list) and d and isinstance(d[0], dict):
            ls = float(d[0].get("longShortRatio", 1) or 1)
            long_pct = round(ls/(1+ls)*100, 1)
            short_pct = round(100-long_pct, 1)
            status = "Aşırı Long ⚠️" if long_pct>65 else ("Aşırı Short ⚠️" if short_pct>65 else "Dengeli ✅")
            result = {"long_pct": long_pct, "short_pct": short_pct,
                      "ratio": round(ls,2), "status": status, "ts": time.time()}
            _ls_cache[key] = result
            return result
    except: pass
    return {"long_pct": 50, "short_pct": 50, "ratio": 1.0, "status": "—", "ts": 0}

# ─── BINANCE OI DEĞİŞİMİ ─────────────────────────────────────────────────────
_oi_cache = {}

def get_oi_change(symbol="BTC"):
    key = symbol
    if key in _oi_cache and time.time()-_oi_cache[key]["ts"]<300:
        return _oi_cache[key]
    try:
        sym = symbol.replace("/USD","") + "USDT"
        d = safe_get(
            f"https://fapi.binance.com/futures/data/openInterestHist"
            f"?symbol={sym}&period=1h&limit=5", timeout=8)
        if isinstance(d, list) and len(d)>=2 and isinstance(d[-1], dict):
            oi_now  = float(d[-1].get("sumOpenInterest", 0) or 0)
            oi_prev = float(d[0].get("sumOpenInterest", 1) or 1)
            change_pct = round((oi_now-oi_prev)/oi_prev*100, 2) if oi_prev else 0
            status = "📈 OI Artıyor" if change_pct>2 else ("📉 OI Azalıyor" if change_pct<-2 else "➡️ OI Stabil")
            result = {"oi_now": oi_now, "change_pct": change_pct,
                      "status": status, "ts": time.time()}
            _oi_cache[key] = result
            return result
    except: pass
    return {"oi_now": 0, "change_pct": 0, "status": "—", "ts": 0}

# ─── COINGLASS LİKİDASYON HEATMAP (API KEY GEREKLİ) ─────────────────────────
_liq_cache = {}

def get_liquidation_levels(symbol="BTC", api_key=""):
    """CoinGlass API ile likidite seviyeleri — API key gerekli"""
    if not api_key or api_key.strip() == "":
        return None
    key = symbol
    if key in _liq_cache and time.time()-_liq_cache[key]["ts"]<600:
        return _liq_cache[key]
    try:
        sym = symbol.replace("/USD","") + "USDT"
        s = create_session()
        # v3 API endpoint dene
        for url in [
            "https://open-api.coinglass.com/api/pro/v3/futures/liquidation-heatmap",
            "https://open-api.coinglass.com/api/pro/v1/futures/liquidation_heatmap",
            "https://open-api.coinglass.com/public/v2/liqHeatmap",
        ]:
            try:
                r = s.get(url,
                    headers={
                        "CG-API-KEY": api_key.strip(),
                        "coinglassSecret": api_key.strip()
                    },
                    params={"symbol": sym, "interval": "12h"},
                    timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if data and isinstance(data, dict):
                        code = data.get("code","")
                        if str(code) in ["0","200"] or data.get("data"):
                            levels = data.get("data", {}) or {}
                            result = {"levels": levels, "ts": time.time(), "ok": True}
                            _liq_cache[key] = result
                            return result
            except: continue
    except: pass
    return None

# ─── BİNANCE TİCKER ──────────────────────────────────────────────────────────
def get_binance_tickers(settings):
    """Binance Futures ticker verisi — OKX yerine kullanılıyor"""
    results = []
    try:
        d = safe_get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=12)
        if not isinstance(d, list): return []
        for t in d:
            sym_raw = t.get("symbol","")
            if not sym_raw.endswith("USDT"): continue
            sym = sym_raw.replace("USDT","")
            last  = safe_float(t.get("lastPrice",0))
            vol   = safe_float(t.get("quoteVolume",0))
            chg   = safe_float(t.get("priceChangePercent",0))
            min_vol = settings.get("min_volume_usd", 5000000)
            if last==0 or vol < min_vol: continue
            results.append({
                "exchange": "Binance",
                "symbol":   sym,
                "price":    last,
                "volume_usd": vol,
                "change_pct": chg,
                "funding":  0.0,
                "asset_type": "Kripto"
            })
    except Exception as e:
        print(f"Binance ticker hata: {e}")
    return results

# ══════════════════════════════════════════════════════════════════════════════
#  API VERİ ÇEKİMİ
# ══════════════════════════════════════════════════════════════════════════════
def get_tickers(settings):
    tickers=[]
    res={}

    def run_binance():
        """Binance Futures — OKX yerine ana kaynak"""
        try:
            binance_tickers = get_binance_tickers(settings)
            if binance_tickers:
                res.setdefault("okx", []).extend(binance_tickers)
                print(f"Binance: {len(binance_tickers)} sembol alındı")
            else:
                print("Binance: Veri gelmedi!")
        except Exception as e: print(f"Binance ticker hata: {e}")

    def run_bingx():
        if not settings["use_bingx"]: return
        try:
            d=safe_get("https://open-api.bingx.com/openApi/swap/v2/quote/ticker",timeout=12)
            data=d.get("data",[])
            if isinstance(data,dict): data=data.get("tickers",[])
            funding_map={}
            try:
                d2=safe_get("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex",timeout=10)
                items=d2.get("data",[])
                if isinstance(items,dict): items=items.get("premiumIndex",[])
                for item in items:
                    sym=item.get("symbol","").replace("-USDT","").replace("_USDT","")
                    try: funding_map[sym]=float(item.get("lastFundingRate",0) or 0)*100
                    except: pass
            except: pass

            COMM=["XAU","XAG","USOIL","UKOIL","NATGAS","COPPER"]
            for t in data:
                sym_raw=t.get("symbol","")
                is_usdt="USDT" in sym_raw
                is_comm=any(sym_raw.startswith(p) for p in COMM)
                if not is_usdt and not is_comm: continue
                sym=sym_raw.replace("-USDT","").replace("_USDT","").replace("USDT","") if is_usdt else \
                    sym_raw.replace("-USD","").replace("_USD","")+"/USD"
                last=safe_float(t.get("lastPrice",t.get("last",0)))
                vol=safe_float(t.get("quoteVolume",t.get("volume",0)))
                if last==0: continue
                min_v=settings["min_volume_usd"]/20 if not is_usdt else settings["min_volume_usd"]
                if vol<min_v: continue
                fund=funding_map.get(sym_raw.replace("-USD","").replace("_USD",""),0.0)
                res.setdefault("bingx",[]).append({
                    "exchange":"BingX","symbol":sym,"price":last,
                    "volume_usd":vol,"funding":fund,
                    "asset_type":"Emtia" if not is_usdt else "Kripto"})
        except Exception as e: print(f"BingX ticker: {e}")

    t1=threading.Thread(target=run_binance)
    t2=threading.Thread(target=run_bingx)
    t1.start(); t2.start(); t1.join(); t2.join()
    okx_t=res.get("okx",[]); bingx_t=res.get("bingx",[])
    return okx_t+bingx_t, {"okx":len(okx_t),"bingx":len(bingx_t)}

def scan_all(settings):
    tickers,counts=get_tickers(settings)
    if not tickers: return [],counts

    # BTC durumu al
    btc=get_btc_status() or {"price":0,"change":0,"trend":"—","ts":0}

    # V7 — Kurumsal veriler al
    fng=get_fear_greed() or {"value":50,"label":"—","ts":0}
    btc_ls=get_long_short_ratio("BTC") or {"long_pct":50,"short_pct":50,"ratio":1.0,"status":"—","ts":0}
    btc_oi=get_oi_change("BTC") or {"oi_now":0,"change_pct":0,"status":"—","ts":0}

    # Mum verileri paralel çek — rate limit için sınırlı thread
    candle_cache={}
    sem=threading.Semaphore(8)  # max 8 paralel istek

    def fetch(coin):
        with sem:
            sym=coin["symbol"]; ex=coin["exchange"]
            time.sleep(0.05)
            candle_cache[f"{ex}_{sym}_4h"] =get_candles_safe(ex,sym,"4h",100)
            candle_cache[f"{ex}_{sym}_1d"] =get_candles_safe(ex,sym,"1d",100)
            candle_cache[f"{ex}_{sym}_1h"] =get_candles_safe(ex,sym,"1h",60)
            candle_cache[f"{ex}_{sym}_1w"] =get_candles_safe(ex,sym,"1w",20)

    threads=[threading.Thread(target=fetch,args=(c,)) for c in tickers]
    for t in threads: t.start()
    for t in threads: t.join()

    results=[]
    for coin in tickers:
        sym=coin["symbol"]; ex=coin["exchange"]
        c4h=candle_cache.get(f"{ex}_{sym}_4h")
        c1d=candle_cache.get(f"{ex}_{sym}_1d")
        c1h=candle_cache.get(f"{ex}_{sym}_1h")
        c1w=candle_cache.get(f"{ex}_{sym}_1w")

        analysis=analyze_swing(coin,settings,c1d,c4h,c1h,c1w,btc,fng,btc_ls,btc_oi,settings.get("coinglass_api_key",""))
        if analysis["signal"]!="BEKLE" and analysis["score"]>=settings.get("min_score",80):
            coin.update(analysis)
            results.append(coin)

    mode=settings.get("show_mode","Tümü")
    if mode=="Sadece LONG":  results=[c for c in results if c.get("signal")=="LONG"]
    elif mode=="Sadece SHORT": results=[c for c in results if c.get("signal")=="SHORT"]
    results.sort(key=lambda x:x.get("score",0),reverse=True)
    return results,counts

# ══════════════════════════════════════════════════════════════════════════════
#  DETAY PENCERESİ
# ══════════════════════════════════════════════════════════════════════════════
class DetailWindow(tk.Toplevel):
    def __init__(self,parent,coin):
        super().__init__(parent)
        self.title(f"  {coin['symbol']} — Swing Trade Analizi")
        self.configure(bg=BG); self.geometry("920x740"); self.resizable(True,True)

        sig=coin.get("signal","—")
        sig_color=GREEN if sig=="LONG" else (RED if sig=="SHORT" else YELLOW)
        warn=coin.get("ob_dir_warning",False)

        # Başlık
        hdr=tk.Frame(self,bg=BG,pady=10); hdr.pack(fill="x",padx=16)
        tk.Label(hdr,text=f"◈ {coin['symbol']} / USDT  [{coin['exchange']}]",
                 font=("Courier New",14,"bold"),fg=ACCENT,bg=BG).pack(side="left")
        tk.Label(hdr,text=f"${coin['price']:,.5g}",
                 font=("Courier New",13,"bold"),fg=TEXT,bg=BG).pack(side="right")

        # OB Yön Uyarısı
        if warn:
            wb=tk.Frame(self,bg=YELLOW,pady=6,padx=16)
            wb.pack(fill="x",padx=16,pady=(0,4))
            tk.Label(wb,text="⚠️  OB YÖN UYARISI — Sinyal yönü OB yönüyle çelişiyor! Dikkatli ol.",
                     font=("Courier New",10,"bold"),fg=BG,bg=YELLOW).pack()

        # Sinyal kutusu
        sb=tk.Frame(self,bg=sig_color if sig!="BEKLE" else BG4,pady=8,padx=16)
        sb.pack(fill="x",padx=16,pady=(0,6))
        txt="🟢 LONG — SWING İŞLEMİ AÇ" if sig=="LONG" else "🔴 SHORT — SWING İŞLEMİ AÇ"
        tk.Label(sb,text=txt,font=("Courier New",12,"bold"),fg=BG,bg=sig_color).pack(side="left")
        tk.Label(sb,text=f"Skor: {coin.get('score',0)}/100  Güven: {coin.get('confidence','—')}",
                 font=("Courier New",11),fg=BG,bg=sig_color).pack(side="right")

        # 3 kolon
        body=tk.Frame(self,bg=BG); body.pack(fill="both",expand=True,padx=16,pady=(0,50))

        # Sol — Analiz verileri
        left=tk.Frame(body,bg=BG2,padx=12,pady=8)
        left.pack(side="left",fill="both",expand=True,padx=(0,4))

        sections=[
            ("TREND ANALİZİ", GOLD,[
                ("1D Trend",   coin.get("trend_1d","—"),  GREEN if coin.get("trend_1d")=="YUKARI" else RED),
                ("4H Trend",   coin.get("trend_4h","—"),  GREEN if coin.get("trend_4h")=="YUKARI" else RED),
                ("MTF Uyum",   "✅ Tam" if coin.get("mtf_align") else "⚠️ Kısmi", GREEN if coin.get("mtf_align") else YELLOW),
                ("1D BOS",     coin.get("bos_1d","—"),    GREEN if coin.get("bos_1d")=="YUKARI" else RED),
                ("1D CHoCH",   coin.get("choch_1d","—"),  GREEN if coin.get("choch_1d")=="YUKARI" else RED),
                ("4H CHoCH",   coin.get("choch_4h","—"),  GREEN if coin.get("choch_4h")=="YUKARI" else RED),
                ("1H CHoCH",   coin.get("choch_1h","—"),  GREEN if coin.get("choch_1h")=="YUKARI" else RED),
            ]),
            ("ORDER BLOCK", ORANGE,[
                ("4H OB",      coin.get("ob_type","—"),   GREEN if "Bullish" in coin.get("ob_type","") else RED),
                ("OB Bölgesi", f"${coin.get('ob_low',0):.4f}—${coin.get('ob_high',0):.4f}", YELLOW),
                ("OB Güç",     f"{coin.get('ob_strength',0)}%", ORANGE),
                ("OB Test",    f"{coin.get('ob_tested',0)}x", TEXT),
                ("P/D Zonu",   coin.get("pd_zone","—"),   GREEN if "Discount" in coin.get("pd_zone","") else RED),
                ("FVG",        "✅ Aktif" if coin.get("fvg_active") else "—", TEAL if coin.get("fvg_active") else TEXT_DIM),
                ("Likidite",   coin.get("liquidity","—"), PURPLE),
            ]),
            ("SWING STOP/TP", GREEN,[
                ("Stop Loss",     f"${coin.get('sl',0):.5g}", RED),
                ("TP1 (%50 kapat)",f"${coin.get('tp1',0):.5g}", YELLOW),
                ("TP2 (tam hedef)",f"${coin.get('tp2',0):.5g}", GREEN),
                ("Risk/Ödül",     coin.get("rr","—"), ACCENT),
                ("Trailing Stop", coin.get("trailing_stop","—")[:35] if coin.get("trailing_stop") else "—", TEAL),
                ("Haftalık S/R",  coin.get("weekly_sr_near","—"), GOLD),
                ("BTC Durumu",    coin.get("btc_status","—")[:30] if coin.get("btc_status") else "—", ACCENT),
            ]),
            ("KURUMSAL GÖRÜŞ", PURPLE,[
                ("Fear & Greed",  f"{coin.get('fear_greed',50)} — {coin.get('fear_greed_lbl','—')}",
                 GREEN if coin.get("fear_greed",50)<=30 else (RED if coin.get("fear_greed",50)>=70 else YELLOW)),
                ("BTC Long Oranı",f"%{coin.get('ls_long',50):.1f}",
                 RED if coin.get("ls_long",50)>65 else (GREEN if coin.get("ls_long",50)<35 else TEAL)),
                ("BTC Short Oranı",f"%{coin.get('ls_short',50):.1f}", TEXT),
                ("L/S Durum",     coin.get("ls_status","—"),
                 RED if "Aşırı Long" in coin.get("ls_status","") else (GREEN if "Aşırı Short" in coin.get("ls_status","") else TEAL)),
                ("OI Değişimi",   f"{coin.get('oi_change',0):+.1f}%", 
                 GREEN if coin.get("oi_change",0)>2 else (RED if coin.get("oi_change",0)<-2 else TEXT_DIM)),
                ("OI Durum",      coin.get("oi_status","—"), ORANGE),
                ("Heatmap",       "✅ Mevcut" if coin.get("liq_levels") else "⏳ API Key Bekleniyor",
                 GREEN if coin.get("liq_levels") else TEXT_DIM),
            ]),
        ]

        for sec_title,title_color,items in sections:
            tk.Frame(left,bg=BORDER,height=1).pack(fill="x",pady=4)
            tk.Label(left,text=sec_title,font=("Courier New",8,"bold"),fg=title_color,bg=BG2).pack(anchor="w")
            for label,val,color in items:
                row=tk.Frame(left,bg=BG2); row.pack(fill="x",pady=1)
                tk.Label(row,text=label,font=("Courier New",9),fg=TEXT_DIM,bg=BG2,width=18,anchor="w").pack(side="left")
                tk.Label(row,text=str(val),font=("Courier New",9,"bold"),fg=color,bg=BG2).pack(side="left")

        # Orta — OB'ler + Haftalık S/R
        mid=tk.Frame(body,bg=BG3,padx=12,pady=8)
        mid.pack(side="left",fill="both",expand=True,padx=4)

        tk.Label(mid,text="ORDER BLOCKS",font=("Courier New",8,"bold"),fg=ORANGE,bg=BG3).pack(anchor="w",pady=(0,4))
        for ob in coin.get("all_obs",[])[:5]:
            row=tk.Frame(mid,bg=BG3); row.pack(fill="x",pady=2)
            clr=GREEN if ob["direction"]=="LONG" else RED
            active="◄" if ob["low"]<=coin["price"]<=ob["high"] else ""
            tk.Label(row,text=f"{ob['type']} {active}",font=("Courier New",9,"bold"),fg=clr,bg=BG3).pack(anchor="w")
            tk.Label(row,text=f"  ${ob['low']:.4f}—${ob['high']:.4f} | Güç:{ob['strength']}% Test:{ob['tested']}x",
                     font=("Courier New",8),fg=TEXT_DIM,bg=BG3).pack(anchor="w")

        tk.Frame(mid,bg=BORDER,height=1).pack(fill="x",pady=6)
        tk.Label(mid,text="HAFTALIK S/R",font=("Courier New",8,"bold"),fg=GOLD,bg=BG3).pack(anchor="w",pady=(0,4))
        for lvl in coin.get("weekly_levels",[])[:4]:
            row=tk.Frame(mid,bg=BG3); row.pack(fill="x",pady=2)
            clr=GREEN if lvl["type"]=="S" else RED
            tk.Label(row,text=f"{'Destek' if lvl['type']=='S' else 'Direnç'}: ${lvl['level']:.4f}  ({lvl['dist']:.1f}% uzak)",
                     font=("Courier New",9),fg=clr,bg=BG3).pack(anchor="w")

        tk.Frame(mid,bg=BORDER,height=1).pack(fill="x",pady=6)
        tk.Label(mid,text="DIV / SWEEP",font=("Courier New",8,"bold"),fg=PURPLE,bg=BG3).pack(anchor="w",pady=(0,4))
        for name,direction,strength in (coin.get("divergences",[])+coin.get("sweeps",[]))[:4]:
            row=tk.Frame(mid,bg=BG3); row.pack(fill="x",pady=2)
            clr=GREEN if direction=="LONG" else RED
            tk.Label(row,text=f"{name} ({strength}%)",font=("Courier New",8),fg=clr,bg=BG3).pack(anchor="w")

        # Sağ — Gerekçeler
        right=tk.Frame(body,bg=BG4,padx=12,pady=8)
        right.pack(side="left",fill="both",expand=True,padx=(4,0))
        tk.Label(right,text="SİNYAL GEREKÇELERİ",font=("Courier New",8,"bold"),fg=TEXT_DIM,bg=BG4).pack(anchor="w",pady=(0,4))
        for r in (coin.get("reasons",[]) or ["Yeterli sinyal yok"]):
            row=tk.Frame(right,bg=BG4); row.pack(fill="x",pady=2)
            clr=YELLOW if "⚠️" in r or "❌" in r else (GREEN if sig=="LONG" else (RED if sig=="SHORT" else TEXT_DIM))
            tk.Label(row,text="►",font=("Courier New",9),fg=clr,bg=BG4).pack(side="left")
            tk.Label(row,text=r,font=("Courier New",8),fg=TEXT,bg=BG4,
                     wraplength=195,justify="left").pack(side="left",padx=3)

        def open_chart():
            sym=coin["symbol"].replace("/USD","")
            ex=coin["exchange"]
            if ex=="Binance":
                webbrowser.open(f"https://www.tradingview.com/chart/?symbol=BINANCE%3A{sym}USDT.P")
            elif ex=="BingX":
                webbrowser.open(f"https://www.tradingview.com/chart/?symbol=BINGX%3A{sym}USDT")
            else:
                webbrowser.open(f"https://www.tradingview.com/chart/?symbol=BINANCE%3A{sym}USDT.P")

        btn_frame=tk.Frame(self,bg=BG); btn_frame.pack(side="bottom",pady=8)
        tk.Button(btn_frame,text="📈  TradingView'de Aç",font=("Courier New",10,"bold"),
                  fg=BG,bg=ACCENT,activebackground=ACCENT,relief="flat",
                  padx=14,pady=6,command=open_chart,cursor="hand2").pack(side="left",padx=5)
        def open_binance():
            sym=coin["symbol"].replace("/USD","")
            webbrowser.open(f"https://www.binance.com/en/futures/{sym}USDT")
        tk.Button(btn_frame,text="🟡  Binance",font=("Courier New",10,"bold"),
                  fg=BG,bg=YELLOW,activebackground=YELLOW,relief="flat",
                  padx=14,pady=6,command=open_binance,cursor="hand2").pack(side="left",padx=5)
        def open_bingx():
            sym=coin["symbol"].replace("/USD","")
            webbrowser.open(f"https://bingx.com/en/perpetual/{sym}-USDT/")
        tk.Button(btn_frame,text="🔵  BingX",font=("Courier New",10,"bold"),
                  fg=BG,bg=TEAL,activebackground=TEAL,relief="flat",
                  padx=14,pady=6,command=open_bingx,cursor="hand2").pack(side="left",padx=5)

# ══════════════════════════════════════════════════════════════════════════════
#  AYARLAR DİYALOĞU
# ══════════════════════════════════════════════════════════════════════════════
class SettingsDialog(tk.Toplevel):
    def __init__(self,parent,settings,on_save):
        super().__init__(parent)
        self.title("⚙  Ayarlar v6"); self.configure(bg=BG); self.geometry("500x700")
        self.resizable(False,False); self.on_save=on_save; self.settings=settings.copy()
        self._build(); self.grab_set()

    def _row(self,p,label,var,row,suffix=""):
        tk.Label(p,text=label,font=("Courier New",10),fg=TEXT,bg=BG3,anchor="w").grid(row=row,column=0,sticky="w",padx=12,pady=5)
        tk.Entry(p,textvariable=var,font=("Courier New",10),bg=BG4,fg=ACCENT,insertbackground=ACCENT,relief="flat",width=12).grid(row=row,column=1,padx=8,pady=5)
        if suffix: tk.Label(p,text=suffix,font=("Courier New",9),fg=TEXT_DIM,bg=BG3).grid(row=row,column=2,sticky="w")

    def _build(self):
        tk.Label(self,text="⚙  AYARLAR v6.0 — SWING",font=("Courier New",13,"bold"),fg=ACCENT,bg=BG).pack(pady=(14,8))
        frm=tk.Frame(self,bg=BG3,pady=8); frm.pack(fill="x",padx=20); frm.columnconfigure(1,weight=1)
        s=self.settings
        self.v_interval =tk.IntVar(value=s["scan_interval"])
        self.v_minvol   =tk.DoubleVar(value=s["min_volume_usd"])
        self.v_minscore =tk.IntVar(value=s.get("min_score",80))
        self.v_minrr    =tk.DoubleVar(value=s.get("min_rr",2.5))
        self.v_btcdrop  =tk.DoubleVar(value=s.get("btc_drop_pct",3.0))

        tk.Label(frm,text="─── TARAMA ───",font=("Courier New",8),fg=TEXT_DIM,bg=BG3).grid(row=0,column=0,columnspan=3,sticky="w",padx=12)
        self._row(frm,"Tarama Aralığı", self.v_interval, 1,"dakika")
        self._row(frm,"Min Hacim USD",  self.v_minvol,   2,"$")
        self._row(frm,"Min Skor",       self.v_minscore, 3,"/100")
        self._row(frm,"Min R/R",        self.v_minrr,    4,"(1:X)")
        self._row(frm,"BTC Düşüş Eşiği",self.v_btcdrop, 5,"% (long engel)")

        # CoinGlass API
        cg=tk.Frame(self,bg=BG3,pady=8,padx=12); cg.pack(fill="x",padx=20,pady=(6,0))
        tk.Label(cg,text="─── COINGLASS API ───",font=("Courier New",8),fg=TEAL,bg=BG3).pack(anchor="w")
        cg_row=tk.Frame(cg,bg=BG3); cg_row.pack(fill="x",pady=3)
        tk.Label(cg_row,text="API Key",font=("Courier New",9),fg=TEXT_DIM,bg=BG3,width=10,anchor="w").pack(side="left")
        self.v_cg_key=tk.StringVar(value=s.get("coinglass_api_key",""))
        tk.Entry(cg_row,textvariable=self.v_cg_key,font=("Courier New",9),bg=BG4,fg=TEAL,
                 insertbackground=TEAL,relief="flat",width=32,show="*").pack(side="left")
        self.v_use_cg=tk.BooleanVar(value=s.get("use_coinglass",False))
        tk.Checkbutton(cg,text="CoinGlass Heatmap Aktif",variable=self.v_use_cg,fg=TEAL,bg=BG3,
                       selectcolor=BG2,font=("Courier New",10),activebackground=BG3).pack(anchor="w",pady=2)

        # Telegram
        tg=tk.Frame(self,bg=BG3,pady=8,padx=12); tg.pack(fill="x",padx=20,pady=(6,0))
        tk.Label(tg,text="─── TELEGRAM ───",font=("Courier New",8),fg=YELLOW,bg=BG3).pack(anchor="w")
        self.v_tg=tk.BooleanVar(value=s.get("telegram_active",False))
        tk.Checkbutton(tg,text="Telegram Aktif",variable=self.v_tg,fg=YELLOW,bg=BG3,selectcolor=BG2,font=("Courier New",10),activebackground=BG3).pack(anchor="w",pady=4)
        for lbl,key in [("Bot Token","telegram_token"),("Chat ID","telegram_chat_id")]:
            row=tk.Frame(tg,bg=BG3); row.pack(fill="x",pady=3)
            tk.Label(row,text=lbl,font=("Courier New",9),fg=TEXT_DIM,bg=BG3,width=10,anchor="w").pack(side="left")
            var=tk.StringVar(value=s.get(key,""))
            setattr(self,f"v_{key}",var)
            tk.Entry(row,textvariable=var,font=("Courier New",9),bg=BG4,fg=YELLOW,
                     insertbackground=YELLOW,relief="flat",width=28,
                     show="*" if "token" in key else "").pack(side="left")

        # Borsalar + filtreler
        ex=tk.Frame(self,bg=BG,pady=6); ex.pack(fill="x",padx=20)
        tk.Label(ex,text="Borsa:",font=("Courier New",10),fg=TEXT,bg=BG).pack(side="left")
        self.v_okx=tk.BooleanVar(value=s["use_okx"]); self.v_bingx=tk.BooleanVar(value=s["use_bingx"])
        self.v_btc=tk.BooleanVar(value=s.get("btc_filter",True))
        for text,var in [("OKX",self.v_okx),("BingX",self.v_bingx)]:
            tk.Checkbutton(ex,text=text,variable=var,fg=ACCENT,bg=BG,selectcolor=BG2,font=("Courier New",10),activebackground=BG).pack(side="left",padx=8)

        flt=tk.Frame(self,bg=BG,pady=4); flt.pack(fill="x",padx=20)
        tk.Checkbutton(flt,text="BTC Korelasyon Filtresi",variable=self.v_btc,fg=GOLD,bg=BG,selectcolor=BG2,font=("Courier New",10),activebackground=BG).pack(side="left")

        mode_f=tk.Frame(self,bg=BG,pady=4); mode_f.pack(fill="x",padx=20)
        tk.Label(mode_f,text="Mod:",font=("Courier New",10),fg=TEXT,bg=BG).pack(side="left")
        self.v_mode=tk.StringVar(value=s.get("show_mode","Tümü"))
        for m in ["Tümü","Sadece LONG","Sadece SHORT"]:
            tk.Radiobutton(mode_f,text=m,variable=self.v_mode,value=m,fg=ACCENT,bg=BG,selectcolor=BG2,activebackground=BG,font=("Courier New",9)).pack(side="left",padx=6)

        snd=tk.Frame(self,bg=BG,pady=2); snd.pack(fill="x",padx=20)
        self.v_sound=tk.BooleanVar(value=s.get("sound_alert",True))
        tk.Checkbutton(snd,text="Ses uyarısı",variable=self.v_sound,fg=TEXT,bg=BG,selectcolor=BG2,font=("Courier New",10),activebackground=BG).pack(side="left")

        btns=tk.Frame(self,bg=BG,pady=14); btns.pack()
        tk.Button(btns,text="  KAYDET  ",font=("Courier New",11,"bold"),fg=BG,bg=GREEN,activebackground=GREEN,relief="flat",padx=16,pady=6,command=self._save).pack(side="left",padx=8)
        tk.Button(btns,text="  İPTAL  ",font=("Courier New",11),fg=TEXT,bg=BG3,activebackground=BG4,relief="flat",padx=16,pady=6,command=self.destroy).pack(side="left")

    def _save(self):
        try:
            self.settings.update({
                "scan_interval":   max(1,self.v_interval.get()),
                "min_volume_usd":  self.v_minvol.get(),
                "min_score":       max(1,self.v_minscore.get()),
                "min_rr":          self.v_minrr.get(),
                "btc_drop_pct":    self.v_btcdrop.get(),
                "btc_filter":      self.v_btc.get(),
                "show_mode":       self.v_mode.get(),
                "sound_alert":     self.v_sound.get(),
                "use_okx":         self.v_okx.get(),
                "use_bingx":       self.v_bingx.get(),
                "telegram_active":   self.v_tg.get(),
                "telegram_token":    self.v_telegram_token.get(),
                "telegram_chat_id":  self.v_telegram_chat_id.get(),
                "coinglass_api_key": self.v_cg_key.get(),
                "use_coinglass":     self.v_use_cg.get(),
            })
            save_settings(self.settings); self.on_save(self.settings); self.destroy()
        except Exception as e: messagebox.showerror("Hata",f"Geçersiz değer: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  ANA UYGULAMA
# ══════════════════════════════════════════════════════════════════════════════
class CryptoScanner(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Kripto Tarayıcı v8.0 — BB Sweep | Binance+BingX | SMC+BB+MFI+OI+L/S")
        self.geometry("1440x780"); self.configure(bg=BG); self.resizable(True,True)
        self.settings=load_settings(); self.results=[]
        self.scan_count=0; self.q=queue.Queue(); self.scanning=False
        self.countdown=self.settings["scan_interval"]*60
        self._sort_col="Skor"; self._sort_desc=True; self._coin_map={}
        self._style(); self._build_ui(); self._start_timer(); self._process_queue()
        threading.Thread(target=self._do_scan,daemon=True).start()

    def _style(self):
        s=ttk.Style(); s.theme_use("clam")
        s.configure("Treeview",background=BG2,foreground=TEXT,rowheight=28,fieldbackground=BG2,font=("Courier New",10))
        s.configure("Treeview.Heading",background=BG3,foreground=ACCENT,font=("Courier New",9,"bold"),relief="flat")
        s.map("Treeview",background=[("selected",BG4)],foreground=[("selected",ACCENT)])

    def _btn(self,parent,text,bg,cmd,fg=BG):
        return tk.Button(parent,text=text,font=("Courier New",9,"bold"),fg=fg,bg=bg,
                         activebackground=bg,relief="flat",padx=10,pady=5,cursor="hand2",command=cmd)

    def _build_ui(self):
        # Header
        hdr=tk.Frame(self,bg=BG,pady=10); hdr.pack(fill="x",padx=18)
        tk.Label(hdr,text="◈ KRIPTO TARAYICI",font=("Courier New",17,"bold"),fg=ACCENT,bg=BG).pack(side="left")
        tk.Label(hdr,text=" v8.0 — BB SWEEP | 1D+4H+1H | SMC+BB+MFI+OI+L/S",font=("Courier New",10),fg=TEXT_DIM,bg=BG).pack(side="left",pady=4)
        right=tk.Frame(hdr,bg=BG); right.pack(side="right")
        self.status_lbl=tk.Label(right,text="● Hazır",font=("Courier New",10),fg=GREEN,bg=BG); self.status_lbl.pack(side="right",padx=(8,0))
        self.timer_lbl=tk.Label(right,text="⏱ --:--",font=("Courier New",11),fg=TEXT_DIM,bg=BG); self.timer_lbl.pack(side="right",padx=(0,10))
        self._btn(right,"▶  TARA",ACCENT,self._manual_scan).pack(side="right",padx=3)
        self._btn(right,"⚙  AYARLAR",BG4,self._open_settings,fg=TEXT).pack(side="right",padx=3)
        self._btn(right,"📋  GEÇMİŞ",BG4,self._open_log,fg=TEXT).pack(side="right",padx=3)

        # BTC bar
        btc_bar=tk.Frame(self,bg=BG3,pady=5); btc_bar.pack(fill="x",padx=18,pady=(0,4))
        tk.Label(btc_bar,text="₿ BTC:",font=("Courier New",9,"bold"),fg=GOLD,bg=BG3).pack(side="left",padx=10)
        self.btc_lbl=tk.Label(btc_bar,text="Yükleniyor...",font=("Courier New",9),fg=TEXT_DIM,bg=BG3)
        self.btc_lbl.pack(side="left",padx=(0,20))
        tk.Label(btc_bar,text="😱 F&G:",font=("Courier New",9,"bold"),fg=PURPLE,bg=BG3).pack(side="left")
        self.fng_lbl=tk.Label(btc_bar,text="—",font=("Courier New",9),fg=TEXT_DIM,bg=BG3)
        self.fng_lbl.pack(side="left",padx=(0,20))
        tk.Label(btc_bar,text="L/S:",font=("Courier New",9,"bold"),fg=TEAL,bg=BG3).pack(side="left")
        self.ls_lbl=tk.Label(btc_bar,text="—",font=("Courier New",9),fg=TEXT_DIM,bg=BG3)
        self.ls_lbl.pack(side="left",padx=(0,20))
        tk.Label(btc_bar,text="OI:",font=("Courier New",9,"bold"),fg=ORANGE,bg=BG3).pack(side="left")
        self.oi_lbl=tk.Label(btc_bar,text="—",font=("Courier New",9),fg=TEXT_DIM,bg=BG3)
        self.oi_lbl.pack(side="left")

        # Mod bar
        mbar=tk.Frame(self,bg=BG2,pady=5); mbar.pack(fill="x",padx=18,pady=(0,4))
        tk.Label(mbar,text="GÖRÜNÜM:",font=("Courier New",8),fg=TEXT_DIM,bg=BG2).pack(side="left",padx=10)
        self.v_mode=tk.StringVar(value=self.settings.get("show_mode","Tümü"))
        for m,color in [("Tümü",ACCENT),("Sadece LONG",GREEN),("Sadece SHORT",RED)]:
            tk.Radiobutton(mbar,text=m,variable=self.v_mode,value=m,fg=color,bg=BG2,
                           selectcolor=BG3,activebackground=BG2,font=("Courier New",9,"bold"),
                           command=self._mode_changed).pack(side="left",padx=8)
        self.match_lbl=tk.Label(mbar,text="— eşleşme",font=("Courier New",10,"bold"),fg=TEXT_DIM,bg=BG2)
        self.match_lbl.pack(side="right",padx=12)
        self.scan_info_lbl=tk.Label(mbar,text="",font=("Courier New",9),fg=TEXT_DIM,bg=BG2)
        self.scan_info_lbl.pack(side="right",padx=12)

        # Tablo
        tf=tk.Frame(self,bg=BG); tf.pack(fill="both",expand=True,padx=18,pady=(0,6))
        cols=("Skor","Sinyal","OB Uyarı","Borsa","Sembol","Fiyat",
              "1D Trend","4H Trend","MTF","P/D Zonu","4H OB",
              "F&G","L/S","OI","SL","TP1","TP2","R/R")
        widths=[55,80,75,70,88,100,75,75,55,105,110,90,100,90,95,95,95,55]
        self.tree=ttk.Treeview(tf,columns=cols,show="headings",height=24)
        for col,w in zip(cols,widths):
            self.tree.heading(col,text=col,command=lambda c=col:self._sort(c))
            self.tree.column(col,width=w,anchor="center",minwidth=w)
        self.tree.tag_configure("long",   background=LONG_BG,  foreground=GREEN)
        self.tree.tag_configure("short",  background=SHORT_BG, foreground=RED)
        self.tree.tag_configure("warn",   background="#1a1500", foreground=YELLOW)
        self.tree.tag_configure("empty",  background=BG2,      foreground=TEXT_DIM)
        sb=ttk.Scrollbar(tf,orient="vertical",command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set); sb.pack(side="right",fill="y"); self.tree.pack(fill="both",expand=True)
        self.tree.bind("<Double-1>",self._open_detail)

        footer=tk.Frame(self,bg=BG,pady=5); footer.pack(fill="x",padx=18)
        self.scan_count_lbl=tk.Label(footer,text="Tarama: 0",font=("Courier New",8),fg=TEXT_DIM,bg=BG)
        self.scan_count_lbl.pack(side="left")
        tk.Label(footer,text="Çift tıkla → Kurumsal Analiz  |  1D+4H+1H  |  SMC+OI+Long/Short+Fear&Greed  |  CoinGlass Heatmap",
                 font=("Courier New",8),fg=TEXT_DIM,bg=BG).pack()
        self.last_scan_lbl=tk.Label(footer,text="",font=("Courier New",8),fg=TEXT_DIM,bg=BG)
        self.last_scan_lbl.pack(side="right")

    def _sort(self,col):
        if self._sort_col==col: self._sort_desc=not self._sort_desc
        else: self._sort_col=col; self._sort_desc=True
        items=[(self.tree.set(k,col),k) for k in self.tree.get_children("")]
        try: items.sort(key=lambda x:float(x[0].replace("$","").replace("%","").replace(",","").replace("▼","").replace("▲","").replace("M","").replace("K","").replace("—","0").replace("x","").replace("✅","1").replace("⚠️","0").strip()),reverse=self._sort_desc)
        except: items.sort(key=lambda x:x[0],reverse=self._sort_desc)
        for i,(_,k) in enumerate(items): self.tree.move(k,"",i)

    def _open_detail(self,event):
        item=self.tree.focus()
        if not item: return
        vals=self.tree.item(item,"values")
        if not vals or len(vals)<5: return
        key=f"{vals[3]}_{vals[4]}"
        coin=self._coin_map.get(key)
        if coin: DetailWindow(self,coin)

    def _mode_changed(self):
        self.settings["show_mode"]=self.v_mode.get(); save_settings(self.settings)
        if self.results: self._render_table(self._filter_mode(self.results))

    def _filter_mode(self,results):
        mode=self.settings.get("show_mode","Tümü")
        if mode=="Sadece LONG":  return [c for c in results if c.get("signal")=="LONG"]
        if mode=="Sadece SHORT": return [c for c in results if c.get("signal")=="SHORT"]
        return results

    def _manual_scan(self):
        if not self.scanning:
            self.countdown=self.settings["scan_interval"]*60
            threading.Thread(target=self._do_scan,daemon=True).start()

    def _do_scan(self):
        self.scanning=True; self.q.put(("status","● Taranıyor... (1D+4H+1H)",YELLOW))
        try:
            import traceback
            results,counts=scan_all(self.settings)
            self.scan_count+=1; self.results=results
            self._coin_map={f"{c['exchange']}_{c['symbol']}":c for c in results}
            btc=get_btc_status()
            btc_str=f"${btc.get('price',0):,.0f}  {btc.get('change',0):+.1f}%  {btc.get('trend','—')}"
            self.q.put(("btc",btc_str))
            # F&G, L/S, OI cek ve guncelle
            fng=get_fear_greed()
            btc_ls=get_long_short_ratio("BTC")
            btc_oi=get_oi_change("BTC")
            fng_str=f"{fng.get('value',50)} — {fng.get('label','—')}"
            ls_str=f"Long %{btc_ls.get('long_pct',50)} / Short %{btc_ls.get('short_pct',50)}"
            oi_str=f"{btc_oi.get('status','—')} ({btc_oi.get('change_pct',0):+.1f}%)"
            self.q.put(("fng",fng_str,fng.get("value",50)))
            self.q.put(("ls",ls_str,btc_ls.get("long_pct",50)))
            self.q.put(("oi",oi_str,btc_oi.get("change_pct",0)))
            for coin in results:
                log_result(coin)
                if self.settings.get("telegram_active") and self.settings.get("telegram_token"):
                    threading.Thread(target=send_telegram,
                        args=(self.settings["telegram_token"],self.settings["telegram_chat_id"],coin),daemon=True).start()
            if results and self.settings.get("sound_alert",True):
                try: import winsound; winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except: pass
            self.q.put(("results",results,counts))
        except Exception as e:
            import traceback
            err_detail = traceback.format_exc()
            print(f"SCAN HATA DETAYI:\n{err_detail}")
            self.q.put(("error",str(e)))
        self.scanning=False

    def _start_timer(self):
        def loop():
            while True:
                time.sleep(1)
                if not self.scanning:
                    self.countdown-=1
                    m,s=divmod(max(0,self.countdown),60)
                    self.q.put(("timer",f"⏱ {m:02d}:{s:02d}"))
                    if self.countdown<=0:
                        self.countdown=self.settings["scan_interval"]*60
                        threading.Thread(target=self._do_scan,daemon=True).start()
        threading.Thread(target=loop,daemon=True).start()

    def _process_queue(self):
        try:
            while True:
                msg=self.q.get_nowait()
                if msg[0]=="status": self.status_lbl.config(text=msg[1],fg=msg[2])
                elif msg[0]=="timer": self.timer_lbl.config(text=msg[1])
                elif msg[0]=="btc":  self.btc_lbl.config(text=msg[1],fg=GOLD)
                elif msg[0]=="fng":
                    val=msg[2]
                    clr=GREEN if val<=30 else (RED if val>=70 else YELLOW)
                    self.fng_lbl.config(text=msg[1],fg=clr)
                elif msg[0]=="ls":
                    lp=msg[2]
                    clr=RED if lp>65 else (GREEN if lp<35 else TEAL)
                    self.ls_lbl.config(text=msg[1],fg=clr)
                elif msg[0]=="oi":
                    chg=msg[2]
                    clr=GREEN if chg>2 else (RED if chg<-2 else TEXT_DIM)
                    self.oi_lbl.config(text=msg[1],fg=clr)
                elif msg[0]=="results": self._update_table(msg[1],msg[2])
                elif msg[0]=="error": self.status_lbl.config(text=f"✕ {msg[1][:60]}",fg=RED)
        except queue.Empty: pass
        self.after(200,self._process_queue)

    def _update_table(self,results,counts):
        now=datetime.now().strftime("%H:%M:%S")
        total=counts.get("okx",0)+counts.get("bingx",0)
        self.last_scan_lbl.config(text=f"Son tarama: {now}")
        self.scan_count_lbl.config(text=f"Tarama: {self.scan_count}")
        self.status_lbl.config(text="● Aktif",fg=GREEN)
        shown=self._filter_mode(results)
        self.match_lbl.config(text=f"{len(shown)} eşleşme",fg=ACCENT if shown else TEXT_DIM)
        self.scan_info_lbl.config(text=f"Binance:{counts.get('okx',0)}  BingX:{counts.get('bingx',0)}  Toplam:{total}")
        self._render_table(shown)

    def _render_table(self,shown):
        for item in self.tree.get_children(): self.tree.delete(item)
        if not shown:
            self.tree.insert("","end",values=("—","—","—","—","Swing koşulunu karşılayan yok",
                "","","","","","","","","","","",""),tags=("empty",))
            return
        for c in shown:
            sig=c.get("signal","—")
            warn=c.get("ob_dir_warning",False)
            tag="warn" if warn else ("long" if sig=="LONG" else "short")
            sig_icon="🟢 LONG" if sig=="LONG" else "🔴 SHORT"
            warn_str="⚠️ UYARI" if warn else "✅ Uyumlu"
            mtf="✅" if c.get("mtf_align") else "⚠️"
            sl=c.get("sl",0); tp1=c.get("tp1",0); tp2=c.get("tp2",0)
            ex_name = "Binance" if c['exchange']=="Binance" else c['exchange']
            ex=f"{ex_name} {'🥇' if c.get('asset_type')=='Emtia' else ''}".strip()
            sr=c.get("weekly_sr_near","—")
            if sr and len(sr)>18: sr=sr[:18]+"…"
            fng_str=f"{c.get('fear_greed',50)} {c.get('fear_greed_lbl','—').split()[0]}"
            ls_str=f"L%{c.get('ls_long',50):.0f}/S%{c.get('ls_short',50):.0f}"
            oi_str=f"{c.get('oi_change',0):+.1f}%"
            self.tree.insert("","end",values=(
                f"{c.get('score',0)}",sig_icon,warn_str,ex,c["symbol"],
                f"${c['price']:,.5g}",
                c.get("trend_1d","—"), c.get("trend_4h","—"), mtf,
                c.get("pd_zone","—"), c.get("ob_type","—"),
                fng_str, ls_str, oi_str,
                f"${sl:.4g}" if sl else "—",
                f"${tp1:.4g}" if tp1 else "—",
                f"${tp2:.4g}" if tp2 else "—",
                c.get("rr","—"),
            ),tags=(tag,))

    def _open_settings(self):
        def on_save(new_s):
            self.settings=new_s
            self.countdown=new_s["scan_interval"]*60
            self.v_mode.set(new_s.get("show_mode","Tümü"))
        SettingsDialog(self,self.settings,on_save)

    def _open_log(self):
        if not os.path.exists(LOG_FILE): messagebox.showinfo("Geçmiş","Henüz kayıt yok."); return
        win=tk.Toplevel(self); win.title("📋  Swing Trade Geçmişi")
        win.configure(bg=BG); win.geometry("1100x500")
        cols=("Zaman","Borsa","Sembol","Sinyal","Skor","OB","OB Uyarı","Fiyat","SL","TP1","TP2","R/R","Haf.S/R","BTC")
        tree=ttk.Treeview(win,columns=cols,show="headings")
        for col in cols: tree.heading(col,text=col); tree.column(col,width=80,anchor="center")
        sb=ttk.Scrollbar(win,orient="vertical",command=tree.yview)
        tree.configure(yscrollcommand=sb.set); sb.pack(side="right",fill="y"); tree.pack(fill="both",expand=True)
        try:
            with open(LOG_FILE,encoding="utf-8") as f: rows=list(csv.DictReader(f))
            for row in reversed(rows[-300:]):
                tag="long" if row.get("sinyal")=="LONG" else "short"
                tree.insert("","end",values=(
                    row.get("zaman",""),row.get("borsa",""),row.get("sembol",""),
                    row.get("sinyal",""),row.get("skor",""),row.get("ob_tip",""),
                    row.get("ob_yon_uyari",""),row.get("fiyat",""),
                    row.get("sl",""),row.get("tp1",""),row.get("tp2",""),
                    row.get("rr",""),row.get("haftalik_sr",""),row.get("btc_durum",""),
                ),tags=(tag,))
            tree.tag_configure("long",background=LONG_BG,foreground=GREEN)
            tree.tag_configure("short",background=SHORT_BG,foreground=RED)
        except Exception as e: tk.Label(win,text=f"Log okunamadı: {e}",fg=RED,bg=BG).pack()

if __name__=="__main__":
    app=CryptoScanner()
    app.mainloop()
