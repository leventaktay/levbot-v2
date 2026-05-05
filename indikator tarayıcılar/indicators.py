"""
GÖSTERGELER MODÜLÜ v2.0 (indicators.py)
=========================================
v2.0 Değişiklikler:
- Overbought/Oversold ÇATIŞMA UYARI sistemi eklendi
- Risk seviyesi hesaplama eklendi
- BB band touch RSI teyitli (4H/1D)

Her indikatörün SADECE en faydalı sinyallerini alıyoruz.
"""

import math


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def ema(data, period):
    """EMA: Son verilere daha fazla ağırlık veren ortalama"""
    if len(data) < period:
        return [None] * len(data)
    k = 2.0 / (period + 1)
    result = [None] * (period - 1)
    sma_val = sum(data[:period]) / period
    result.append(sma_val)
    for i in range(period, len(data)):
        val = data[i] * k + result[-1] * (1 - k)
        result.append(val)
    return result


def sma(data, period):
    """Basit hareketli ortalama"""
    result = [None] * (period - 1)
    for i in range(period - 1, len(data)):
        result.append(sum(data[i - period + 1:i + 1]) / period)
    return result


def stdev(data, period):
    """Standart sapma"""
    result = [None] * (period - 1)
    for i in range(period - 1, len(data)):
        window = data[i - period + 1:i + 1]
        avg = sum(window) / period
        variance = sum((x - avg) ** 2 for x in window) / period
        result.append(math.sqrt(variance))
    return result


# ============================================================
# 1. RSI
# ============================================================

def calculate_rsi(closes, period=14):
    """RSI: 0-100 arası momentum göstergesi"""
    if len(closes) < period + 1:
        return [None] * len(closes)
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_values = [None] * period
    if avg_loss == 0:
        rsi_values.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi_values.append(100.0 - (100.0 / (1.0 + rs)))
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100.0 - (100.0 / (1.0 + rs)))
    return rsi_values


def detect_rsi_signals(closes, rsi_values, lookback=14):
    """RSI sinyalleri: aşırı bölge + divergence"""
    signals = []
    if len(rsi_values) < lookback or rsi_values[-1] is None:
        return signals
    current_rsi = rsi_values[-1]
    
    if current_rsi >= 75:
        signals.append({
            'type': 'RSI_OVERBOUGHT', 'direction': 'BEARISH',
            'strength': min((current_rsi - 70) / 30, 1.0),
            'detail': f'RSI = {current_rsi:.1f} (Aşırı Alım)'
        })
    elif current_rsi <= 25:
        signals.append({
            'type': 'RSI_OVERSOLD', 'direction': 'BULLISH',
            'strength': min((30 - current_rsi) / 30, 1.0),
            'detail': f'RSI = {current_rsi:.1f} (Aşırı Satım)'
        })
    
    # Divergence
    valid_rsi = [(i, rsi_values[i]) for i in range(len(rsi_values) - lookback, len(rsi_values))
                 if rsi_values[i] is not None]
    if len(valid_rsi) >= lookback:
        half = lookback // 2
        price_first = closes[-lookback:-half]
        price_second = closes[-half:]
        rsi_first = [r for _, r in valid_rsi[:half]]
        rsi_second = [r for _, r in valid_rsi[half:]]
        if price_first and price_second and rsi_first and rsi_second:
            if min(price_second) < min(price_first) * 0.998 and min(rsi_second) > min(rsi_first) + 2:
                signals.append({
                    'type': 'RSI_BULL_DIVERGENCE', 'direction': 'BULLISH',
                    'strength': 0.8, 'detail': 'Bullish Divergence (Fiyat↓ RSI↑)'
                })
            if max(price_second) > max(price_first) * 1.002 and max(rsi_second) < max(rsi_first) - 2:
                signals.append({
                    'type': 'RSI_BEAR_DIVERGENCE', 'direction': 'BEARISH',
                    'strength': 0.8, 'detail': 'Bearish Divergence (Fiyat↑ RSI↓)'
                })
    return signals


# ============================================================
# 2. VMC CIPHER B (WaveTrend Oscillator)
# ============================================================

def calculate_wavetrend(closes, highs, lows, channel_len=9, avg_len=12, ma_len=3):
    """WaveTrend: momentum + trend oscillator"""
    if len(closes) < channel_len + avg_len + ma_len:
        return [], []
    hlc3 = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(len(closes))]
    esa = ema(hlc3, channel_len)
    d_values = [abs(hlc3[i] - esa[i]) if esa[i] is not None else 0 for i in range(len(hlc3))]
    d_ema = ema(d_values, channel_len)
    ci = []
    for i in range(len(hlc3)):
        if esa[i] is not None and d_ema[i] is not None and d_ema[i] != 0:
            ci.append((hlc3[i] - esa[i]) / (0.015 * d_ema[i]))
        else:
            ci.append(0)
    wt1 = ema(ci, avg_len)
    wt2 = sma([w if w is not None else 0 for w in wt1], ma_len)
    return wt1, wt2


def detect_wavetrend_signals(closes, wt1, wt2, ob_level=60, os_level=-60):
    """WaveTrend: SADECE aşırı bölgede cross + divergence"""
    signals = []
    if len(wt1) < 3 or len(wt2) < 3:
        return signals
    if wt1[-1] is None or wt1[-2] is None or wt2[-1] is None or wt2[-2] is None:
        return signals
    
    cross_up = wt1[-2] <= wt2[-2] and wt1[-1] > wt2[-1]
    cross_down = wt1[-2] >= wt2[-2] and wt1[-1] < wt2[-1]
    
    if cross_up and wt1[-1] < os_level:
        signals.append({
            'type': 'WT_CROSS_OVERSOLD', 'direction': 'BULLISH',
            'strength': min(abs(wt1[-1]) / 100, 1.0),
            'detail': f'WaveTrend Bullish Cross @ {wt1[-1]:.0f}'
        })
    if cross_down and wt1[-1] > ob_level:
        signals.append({
            'type': 'WT_CROSS_OVERBOUGHT', 'direction': 'BEARISH',
            'strength': min(abs(wt1[-1]) / 100, 1.0),
            'detail': f'WaveTrend Bearish Cross @ {wt1[-1]:.0f}'
        })
    
    # Divergence
    lookback = 14
    if len(closes) >= lookback and len(wt1) >= lookback:
        half = lookback // 2
        wt_vals_first = [w for w in wt1[-lookback:-half] if w is not None]
        wt_vals_second = [w for w in wt1[-half:] if w is not None]
        if wt_vals_first and wt_vals_second:
            if (min(closes[-half:]) < min(closes[-lookback:-half]) * 0.998 and 
                min(wt_vals_second) > min(wt_vals_first) + 3):
                signals.append({
                    'type': 'WT_BULL_DIVERGENCE', 'direction': 'BULLISH',
                    'strength': 0.85, 'detail': 'WaveTrend Bullish Divergence'
                })
    return signals


# ============================================================
# 3. BOLLINGER BANDS - Squeeze + Band Touch (4H/1D)
# ============================================================

def calculate_bollinger(closes, period=20, std_mult=2.0):
    """BB hesaplama: orta, üst, alt bantlar ve bandwidth"""
    if len(closes) < period:
        return None, None, None, None
    mid = sma(closes, period)
    sd = stdev(closes, period)
    upper, lower, bandwidth = [], [], []
    for i in range(len(closes)):
        if mid[i] is not None and sd[i] is not None and mid[i] != 0:
            upper.append(mid[i] + std_mult * sd[i])
            lower.append(mid[i] - std_mult * sd[i])
            bandwidth.append((upper[-1] - lower[-1]) / mid[i] * 100)
        else:
            upper.append(None)
            lower.append(None)
            bandwidth.append(None)
    return mid, upper, lower, bandwidth


def detect_bb_squeeze(bandwidth, lookback=120):
    """BB Squeeze tespiti: bantlar daraldığında büyük hareket habercisi"""
    signals = []
    valid_bw = [b for b in bandwidth[-lookback:] if b is not None]
    if len(valid_bw) < 20:
        return signals
    current_bw = bandwidth[-1]
    if current_bw is None:
        return signals
    sorted_bw = sorted(valid_bw)
    p10 = sorted_bw[max(0, len(sorted_bw) // 10)]
    p25 = sorted_bw[max(0, len(sorted_bw) // 4)]
    
    if current_bw <= p10:
        signals.append({
            'type': 'BB_SQUEEZE_STRONG', 'direction': 'NEUTRAL',
            'strength': 0.9, 'detail': f'Güçlü BB Squeeze (BW: {current_bw:.2f}%)'
        })
    elif current_bw <= p25:
        signals.append({
            'type': 'BB_SQUEEZE_MODERATE', 'direction': 'NEUTRAL',
            'strength': 0.6, 'detail': f'Orta BB Squeeze (BW: {current_bw:.2f}%)'
        })
    
    recent_bw = [b for b in bandwidth[-5:] if b is not None]
    if len(recent_bw) >= 4:
        if recent_bw[-1] > recent_bw[-2] > recent_bw[-3] and recent_bw[-3] <= p25:
            signals.append({
                'type': 'BB_SQUEEZE_RELEASE', 'direction': 'NEUTRAL',
                'strength': 0.85, 'detail': f'BB Squeeze Çözülüyor! (BW: {current_bw:.2f}%)'
            })
    return signals


def detect_bb_band_touch(closes, highs, lows, upper, lower, mid,
                          bandwidth, rsi_value=None):
    """
    BB Band Touch tespiti - SADECE 4H ve 1D'de çağrılır.
    Walk the band filtreli, RSI teyitli.
    """
    signals = []
    if not upper or not lower or len(closes) < 5:
        return signals
    if upper[-1] is None or lower[-1] is None:
        return signals
    
    touch_threshold = (upper[-1] - lower[-1]) * 0.02
    
    # Walk the band filtresi
    consec_upper = sum(1 for i in range(-3, 0) 
                       if len(highs) + i >= 0 and upper[i] is not None 
                       and highs[i] >= upper[i] - touch_threshold)
    consec_lower = sum(1 for i in range(-3, 0)
                       if len(lows) + i >= 0 and lower[i] is not None
                       and lows[i] <= lower[i] + touch_threshold)
    
    # Üst band dokunması
    if highs[-1] >= upper[-1] - touch_threshold and consec_upper < 3:
        wick_rej = closes[-1] < upper[-1] and highs[-1] >= upper[-1]
        rsi_conf = rsi_value is not None and rsi_value >= 65
        strength = 0.5 + (0.15 if wick_rej else 0) + (0.2 if rsi_conf else 0)
        parts = ['Üst BB Dokunma']
        if wick_rej: parts.append('Fitil Reddi')
        if rsi_conf: parts.append(f'RSI={rsi_value:.0f}')
        signals.append({
            'type': 'BB_UPPER_TOUCH', 'direction': 'BEARISH',
            'strength': min(strength, 1.0), 'detail': ' + '.join(parts)
        })
    
    # Alt band dokunması
    if lows[-1] <= lower[-1] + touch_threshold and consec_lower < 3:
        wick_rej = closes[-1] > lower[-1] and lows[-1] <= lower[-1]
        rsi_conf = rsi_value is not None and rsi_value <= 35
        strength = 0.5 + (0.15 if wick_rej else 0) + (0.2 if rsi_conf else 0)
        parts = ['Alt BB Dokunma']
        if wick_rej: parts.append('Fitil Reddi')
        if rsi_conf: parts.append(f'RSI={rsi_value:.0f}')
        signals.append({
            'type': 'BB_LOWER_TOUCH', 'direction': 'BULLISH',
            'strength': min(strength, 1.0), 'detail': ' + '.join(parts)
        })
    return signals


# ============================================================
# 4. TILSON T3
# ============================================================

def calculate_tilson_t3(closes, period=5, v_factor=0.7):
    """T3: 6 katmanlı EMA, pürüzsüz ama hızlı trend filtresi"""
    if len(closes) < period * 6:
        return [None] * len(closes)
    # ÖĞRETİCİ: T3 katsayıları — GD(n,v) = EMA*(1+v) - EMA(EMA)*v formülünden türetilir
    # v=0.7 için: c1=-0.343, c2=1.617, c3=-2.853, c4=2.579 → toplamı 1.0 olmalı
    # ESKİ KODDA BUG VARDI: c2'de v³ yerine v², c3'te v³ yerine v yazılmıştı!
    c1 = -(v_factor ** 3)
    c2 = 3 * v_factor ** 2 + 3 * v_factor ** 3           # 3v² + 3v³ (eski: 6v² yanlıştı)
    c3 = -6 * v_factor ** 2 - 3 * v_factor - 3 * v_factor ** 3  # (eski: -6v²-6v yanlıştı)
    c4 = 1 + 3 * v_factor + v_factor ** 3 + 3 * v_factor ** 2
    e1 = ema(closes, period)
    e2 = ema([x if x is not None else 0 for x in e1], period)
    e3 = ema([x if x is not None else 0 for x in e2], period)
    e4 = ema([x if x is not None else 0 for x in e3], period)
    e5 = ema([x if x is not None else 0 for x in e4], period)
    e6 = ema([x if x is not None else 0 for x in e5], period)
    t3 = []
    for i in range(len(closes)):
        if all(x[i] is not None for x in [e3, e4, e5, e6]):
            t3.append(c1 * e6[i] + c2 * e5[i] + c3 * e4[i] + c4 * e3[i])
        else:
            t3.append(None)
    return t3


def detect_t3_trend(closes, t3_values):
    """T3 trend yönü: WHERE filtresi"""
    signals = []
    if len(t3_values) < 3 or t3_values[-1] is None or t3_values[-2] is None:
        return signals
    price_above = closes[-1] > t3_values[-1]
    t3_rising = t3_values[-1] > t3_values[-2]
    distance_pct = abs(closes[-1] - t3_values[-1]) / t3_values[-1] * 100
    
    if price_above and t3_rising:
        signals.append({
            'type': 'T3_BULLISH_TREND', 'direction': 'BULLISH',
            'strength': min(0.5 + distance_pct * 0.1, 1.0),
            'detail': f'T3 Bullish Trend (Fiyat T3 üstünde +{distance_pct:.1f}%)'
        })
    elif not price_above and not t3_rising:
        signals.append({
            'type': 'T3_BEARISH_TREND', 'direction': 'BEARISH',
            'strength': min(0.5 + distance_pct * 0.1, 1.0),
            'detail': f'T3 Bearish Trend (Fiyat T3 altında -{distance_pct:.1f}%)'
        })
    return signals


# ============================================================
# 5. VWAP + VOLUME SPIKE
# ============================================================

def calculate_vwap(closes, highs, lows, volumes):
    """VWAP: hacim ağırlıklı ortalama fiyat"""
    if not volumes or len(volumes) < 2:
        return [None] * len(closes)
    hlc3 = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(len(closes))]
    vwap, cum_vp, cum_v = [], 0, 0
    for i in range(len(closes)):
        cum_vp += hlc3[i] * volumes[i]
        cum_v += volumes[i]
        vwap.append(cum_vp / cum_v if cum_v > 0 else None)
    return vwap


def detect_volume_signals(closes, volumes, vwap_values, lookback=20):
    """Volume spike + VWAP cross tespiti"""
    signals = []
    if len(volumes) < lookback:
        return signals
    avg_vol = sum(volumes[-lookback:]) / lookback
    if avg_vol > 0:
        ratio = volumes[-1] / avg_vol
        if ratio >= 3.0:
            signals.append({
                'type': 'VOLUME_SPIKE_EXTREME', 'direction': 'NEUTRAL',
                'strength': 0.9, 'detail': f'Aşırı Volume Spike ({ratio:.1f}x)'
            })
        elif ratio >= 2.5:
            signals.append({
                'type': 'VOLUME_SPIKE', 'direction': 'NEUTRAL',
                'strength': 0.7, 'detail': f'Volume Spike ({ratio:.1f}x)'
            })
    
    if (vwap_values and len(vwap_values) >= 2 and
        vwap_values[-1] is not None and vwap_values[-2] is not None):
        prev_above = closes[-2] > vwap_values[-2]
        curr_above = closes[-1] > vwap_values[-1]
        if not prev_above and curr_above:
            signals.append({
                'type': 'VWAP_CROSS_UP', 'direction': 'BULLISH',
                'strength': 0.6, 'detail': 'Fiyat VWAP üstüne çıktı'
            })
        elif prev_above and not curr_above:
            signals.append({
                'type': 'VWAP_CROSS_DOWN', 'direction': 'BEARISH',
                'strength': 0.6, 'detail': 'Fiyat VWAP altına düştü'
            })
    return signals


# ============================================================
# 6. OVERBOUGHT/OVERSOLD ÇATIŞMA TESPİTİ (YENİ!)
# ============================================================

def detect_signal_conflicts(all_signals, rsi_value, wt_value):
    """
    ÇATIŞMA TESPİTİ - v2.0'ın en önemli yeniliği
    
    PROBLEM:
    ONT örneğindeki gibi: RSI=84, WT=94 AMA T3 bullish diye
    genel skor BULLISH çıkıyor. Bu çok tehlikeli çünkü fiyat
    aşırı alım bölgesinde → geri çekilme riski çok yüksek.
    
    ÇÖZÜM:
    Eğer trend BULLISH ama osilatörler OVERBOUGHT ise:
    → "UYARI: Trend yukarı ama aşırı alım, GİRİŞ RİSKLİ" sinyali ekle
    → Risk seviyesini yükselt
    
    Aynı mantık tersi için:
    Trend BEARISH ama osilatörler OVERSOLD ise:
    → "UYARI: Trend aşağı ama aşırı satım, SHORT RİSKLİ"
    
    Bu, senin sürekli yaptığın hatayı önler:
    "Trend yukarı, gireyim" → ama zaten tepedesin → stop.
    """
    warnings = []
    
    # Mevcut trend yönünü bul
    has_bullish_trend = any(s['type'] in ('T3_BULLISH_TREND',) for s in all_signals)
    has_bearish_trend = any(s['type'] in ('T3_BEARISH_TREND',) for s in all_signals)
    
    # ÇATIŞMA 1: Bullish trend + Overbought osilatörler
    if has_bullish_trend:
        overbought_count = 0
        if rsi_value is not None and rsi_value >= 70:
            overbought_count += 1
        if wt_value is not None and wt_value >= 53:
            overbought_count += 1
        
        if overbought_count >= 1:
            severity = 'YÜKSEK' if overbought_count >= 2 else 'ORTA'
            rsi_str = f'RSI={rsi_value:.0f}' if rsi_value else ''
            wt_str = f'WT={wt_value:.0f}' if wt_value else ''
            vals = ', '.join(filter(None, [rsi_str, wt_str]))
            
            warnings.append({
                'type': 'CONFLICT_BULL_OVERBOUGHT',
                'direction': 'WARNING',
                'strength': 0.9 if overbought_count >= 2 else 0.7,
                'detail': f'⚠️ UYARI: Trend↑ ama AŞIRI ALIM ({vals}) - Giriş riskli! [{severity}]'
            })
    
    # ÇATIŞMA 2: Bearish trend + Oversold osilatörler
    if has_bearish_trend:
        oversold_count = 0
        if rsi_value is not None and rsi_value <= 30:
            oversold_count += 1
        if wt_value is not None and wt_value <= -53:
            oversold_count += 1
        
        if oversold_count >= 1:
            severity = 'YÜKSEK' if oversold_count >= 2 else 'ORTA'
            rsi_str = f'RSI={rsi_value:.0f}' if rsi_value else ''
            wt_str = f'WT={wt_value:.0f}' if wt_value else ''
            vals = ', '.join(filter(None, [rsi_str, wt_str]))
            
            warnings.append({
                'type': 'CONFLICT_BEAR_OVERSOLD',
                'direction': 'WARNING',
                'strength': 0.9 if oversold_count >= 2 else 0.7,
                'detail': f'⚠️ UYARI: Trend↓ ama AŞIRI SATIM ({vals}) - Short riskli! [{severity}]'
            })
    
    return warnings


# ============================================================
# 7. RİSK SEVİYESİ HESAPLAMA (YENİ!)
# ============================================================

def calculate_risk_level(all_signals, rsi_value, wt_value):
    """
    Risk seviyesi: 1-5 arası (1=düşük, 5=çok yüksek)
    
    MANTIK:
    - Osilatörler aşırı bölgede → risk artar
    - Çatışma sinyali varsa → risk artar
    - BB Squeeze varsa → belirsizlik = risk artar
    - Volume spike varsa → volatilite = risk artar
    
    Bu bilgiyi tabloda renk kodu olarak gösteriyoruz:
    1-2: Yeşil (nispeten güvenli)
    3: Sarı (dikkatli ol)
    4-5: Kırmızı (çok riskli, giriş yapma)
    """
    risk = 1  # Temel risk
    
    # Osilatör aşırı bölge
    if rsi_value is not None:
        if rsi_value >= 80 or rsi_value <= 20:
            risk += 2
        elif rsi_value >= 70 or rsi_value <= 30:
            risk += 1
    
    if wt_value is not None:
        if abs(wt_value) >= 80:
            risk += 1
    
    # Çatışma sinyali
    if any(s['type'].startswith('CONFLICT_') for s in all_signals):
        risk += 1
    
    # BB Squeeze (belirsizlik)
    if any('SQUEEZE' in s['type'] for s in all_signals):
        risk += 1
    
    # Aşırı volume spike
    if any(s['type'] == 'VOLUME_SPIKE_EXTREME' for s in all_signals):
        risk += 1
    
    return min(risk, 5)


# ============================================================
# ANA SINYAL BİRLEŞTİRİCİ
# ============================================================

def analyze_all_indicators(closes, highs, lows, volumes,
                            use_rsi=True, use_wavetrend=True,
                            use_bb=True, use_t3=True, use_volume=True,
                            timeframe='1h'):
    """Tüm indikatörleri çalıştır, çatışma kontrolü yap, risk hesapla."""
    all_signals = []
    meta = {}
    rsi_current = None
    wt_current = None
    
    if use_rsi:
        rsi_values = calculate_rsi(closes)
        rsi_current = rsi_values[-1] if rsi_values and rsi_values[-1] is not None else None
        meta['rsi'] = rsi_current
        all_signals.extend(detect_rsi_signals(closes, rsi_values))
    
    if use_wavetrend:
        wt1, wt2 = calculate_wavetrend(closes, highs, lows)
        wt_current = wt1[-1] if wt1 and wt1[-1] is not None else None
        meta['wt1'] = wt_current
        all_signals.extend(detect_wavetrend_signals(closes, wt1, wt2))
    
    if use_bb:
        mid, upper, lower, bandwidth = calculate_bollinger(closes)
        meta['bb_bandwidth'] = bandwidth[-1] if bandwidth and bandwidth[-1] is not None else None
        if bandwidth:
            all_signals.extend(detect_bb_squeeze(bandwidth))
            if timeframe in ('4h', '1d', '1w'):
                all_signals.extend(detect_bb_band_touch(
                    closes, highs, lows, upper, lower, mid,
                    bandwidth, rsi_value=rsi_current
                ))
    
    if use_t3:
        t3 = calculate_tilson_t3(closes)
        meta['t3_trend'] = 'N/A'
        t3_sigs = detect_t3_trend(closes, t3)
        all_signals.extend(t3_sigs)
        for s in t3_sigs:
            if 'BULLISH' in s['type']:
                meta['t3_trend'] = 'BULLISH'
            elif 'BEARISH' in s['type']:
                meta['t3_trend'] = 'BEARISH'
    
    if use_volume:
        vwap = calculate_vwap(closes, highs, lows, volumes)
        all_signals.extend(detect_volume_signals(closes, volumes, vwap))
    
    # ★ YENİ: Çatışma tespiti
    conflict_warnings = detect_signal_conflicts(all_signals, rsi_current, wt_current)
    all_signals.extend(conflict_warnings)
    
    # ★ YENİ: Risk seviyesi
    risk_level = calculate_risk_level(all_signals, rsi_current, wt_current)
    meta['risk_level'] = risk_level
    
    # Skor hesapla
    bullish_score = sum(s['strength'] * 20 for s in all_signals if s['direction'] == 'BULLISH')
    bearish_score = sum(s['strength'] * 20 for s in all_signals if s['direction'] == 'BEARISH')
    
    # ★ YENİ: Çatışma varsa dominant skoru düşür
    # Bullish trend + overbought → bullish skoru %30 düşür
    if any(s['type'] == 'CONFLICT_BULL_OVERBOUGHT' for s in all_signals):
        bullish_score *= 0.7
    if any(s['type'] == 'CONFLICT_BEAR_OVERSOLD' for s in all_signals):
        bearish_score *= 0.7
    
    if bullish_score > bearish_score + 10:
        trend = 'BULLISH'
    elif bearish_score > bullish_score + 10:
        trend = 'BEARISH'
    else:
        trend = 'NEUTRAL'
    
    # ★ YENİ: Çatışma + trend = UYARI olarak işaretle
    has_conflict = any(s['type'].startswith('CONFLICT_') for s in all_signals)
    if has_conflict:
        meta['has_conflict'] = True
    
    return {
        'signals': all_signals,
        'bullish_score': min(bullish_score, 100),
        'bearish_score': min(bearish_score, 100),
        'trend': trend,
        **meta
    }
