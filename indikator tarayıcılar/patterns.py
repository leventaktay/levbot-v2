"""
MUM FORMASYONLARI MODÜLÜ (patterns.py)
=======================================
Her formasyonun tespit mantığını açıklayarak yazıyoruz.

GENEL KURAL:
Mum formasyonları TEK BAŞINA sinyal değildir!
Bağlam (context) çok önemli:
- Hammer → düşüş trendinin DİBİNDE anlamlı
- Hanging Man → yükseliş trendinin TEPESİNDE anlamlı
- Morning Star → düşüş sonrası anlamlı
- Evening Star → yükseliş sonrası anlamlı

Bu yüzden her formasyon için "bağlam kontrolü" yapıyoruz.
"""


def _body_size(open_p, close):
    """Mum gövde büyüklüğü (mutlak)"""
    return abs(close - open_p)


def _upper_wick(high, open_p, close):
    """Üst fitil uzunluğu"""
    return high - max(open_p, close)


def _lower_wick(low, open_p, close):
    """Alt fitil uzunluğu"""
    return min(open_p, close) - low


def _candle_range(high, low):
    """Toplam mum aralığı"""
    return high - low


def _is_bullish(open_p, close):
    """Yeşil mum mu?"""
    return close > open_p


def _is_bearish(open_p, close):
    """Kırmızı mum mu?"""
    return close < open_p


def _trend_direction(closes, lookback=10):
    """
    Son N mumun genel trend yönünü belirle.
    
    Basit ama etkili yöntem:
    Son kapanış ile lookback önceki kapanışı karşılaştır.
    %2+ fark varsa trend var, yoksa yan trend.
    """
    if len(closes) < lookback:
        return 'NEUTRAL'
    
    start = closes[-lookback]
    end = closes[-1]
    
    if start == 0:
        return 'NEUTRAL'
    
    change_pct = (end - start) / start * 100
    
    if change_pct > 2:
        return 'UP'
    elif change_pct < -2:
        return 'DOWN'
    else:
        return 'NEUTRAL'


def _avg_body(opens, closes, count=10):
    """Son N mumun ortalama gövde büyüklüğü"""
    bodies = [_body_size(opens[i], closes[i]) for i in range(-count, 0)]
    return sum(bodies) / len(bodies) if bodies else 0


# ============================================================
# 1. HAMMER (Çekiç)
# ============================================================

def detect_hammer(opens, highs, lows, closes):
    """
    HAMMER (Çekiç) Tespiti
    
    GÖRÜNÜM (5 yaşına anlatır gibi):
    Küçük gövdeli, UZUN ALT FİTİLLİ mum. Üst fitil yok veya çok kısa.
    Çekiç gibi görünür: küçük kafa, uzun sap.
    
    ANLAMI:
    Fiyat çok düştü ama alıcılar geri itti. 
    "Düşüşü reddettiler" → potansiyel dönüş sinyali.
    
    KOŞULLAR:
    1. Alt fitil, gövdenin EN AZ 2 katı uzunluğunda
    2. Üst fitil, toplam aralığın %10'undan kısa
    3. Gövde küçük (toplam aralığın %35'inden az)
    4. BAĞLAM: Düşüş trendi sonrasında oluşmalı!
    """
    signals = []
    
    if len(closes) < 12:
        return signals
    
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    cr = _candle_range(h, l)
    
    if cr == 0:
        return signals
    
    body = _body_size(o, c)
    lower_w = _lower_wick(l, o, c)
    upper_w = _upper_wick(h, o, c)
    
    # Koşullar
    is_hammer = (
        lower_w >= body * 2 and        # Alt fitil gövdenin 2x+
        upper_w <= cr * 0.10 and        # Üst fitil çok kısa
        body <= cr * 0.35 and           # Küçük gövde
        body > cr * 0.02                # Ama tamamen gövdesiz değil (o doji olur)
    )
    
    if is_hammer:
        trend = _trend_direction(closes[:-1], 10)
        
        if trend == 'DOWN':  # Sadece düşüş sonrası anlamlı
            strength = min(lower_w / (body + 0.0001) * 0.2, 1.0)
            signals.append({
                'type': 'HAMMER',
                'direction': 'BULLISH',
                'strength': strength,
                'detail': f'Hammer (Çekiç) - Düşüş sonrası dönüş sinyali'
            })
    
    return signals


# ============================================================
# 2. HANGING MAN (Asılan Adam)
# ============================================================

def detect_hanging_man(opens, highs, lows, closes):
    """
    HANGING MAN (Asılan Adam) Tespiti
    
    GÖRÜNÜM:
    Hammer ile AYNI şekil! Fark BAĞLAMDA:
    Hammer → düşüş sonrası (bullish)
    Hanging Man → yükseliş sonrası (bearish)
    
    ANLAMI:
    Yükseliş trendinde oluşursa: "Birileri satmaya başladı,
    fiyat düştü ama geri geldi. Ama bu satış baskısı uyarı sinyali."
    
    KOŞULLAR: Hammer ile aynı şekil, AMA yükseliş trendi sonrası.
    """
    signals = []
    
    if len(closes) < 12:
        return signals
    
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    cr = _candle_range(h, l)
    
    if cr == 0:
        return signals
    
    body = _body_size(o, c)
    lower_w = _lower_wick(l, o, c)
    upper_w = _upper_wick(h, o, c)
    
    is_hanging = (
        lower_w >= body * 2 and
        upper_w <= cr * 0.10 and
        body <= cr * 0.35 and
        body > cr * 0.02
    )
    
    if is_hanging:
        trend = _trend_direction(closes[:-1], 10)
        
        if trend == 'UP':  # Sadece yükseliş sonrası anlamlı
            strength = min(lower_w / (body + 0.0001) * 0.2, 1.0)
            signals.append({
                'type': 'HANGING_MAN',
                'direction': 'BEARISH',
                'strength': strength,
                'detail': f'Hanging Man (Asılan Adam) - Yükseliş sonrası uyarı'
            })
    
    return signals


# ============================================================
# 3. DOJI
# ============================================================

def detect_doji(opens, highs, lows, closes):
    """
    DOJI Tespiti
    
    GÖRÜNÜM:
    Gövde neredeyse YOK - açılış ≈ kapanış. Artı (+) işareti gibi.
    
    ANLAMI:
    Alıcılar ve satıcılar eşit güçte → KARARSIZLIK.
    Trend sonunda doji = potansiyel dönüş.
    Yan trendde doji = devam.
    
    TÜRLER:
    - Standart Doji: Fitiller eşit
    - Dragonfly Doji: Uzun alt fitil (hammer gibi ama gövdesiz)
    - Gravestone Doji: Uzun üst fitil (shooting star gibi ama gövdesiz)
    
    KOŞULLAR:
    Gövde, toplam aralığın %5'inden küçük.
    """
    signals = []
    
    if len(closes) < 12:
        return signals
    
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    cr = _candle_range(h, l)
    
    if cr == 0:
        return signals
    
    body = _body_size(o, c)
    
    # Doji koşulu: çok küçük gövde
    if body > cr * 0.05:
        return signals
    
    lower_w = _lower_wick(l, o, c)
    upper_w = _upper_wick(h, o, c)
    
    trend = _trend_direction(closes[:-1], 10)
    
    # Dragonfly Doji (uzun alt fitil) → bullish bias
    if lower_w > upper_w * 3 and trend == 'DOWN':
        signals.append({
            'type': 'DRAGONFLY_DOJI',
            'direction': 'BULLISH',
            'strength': 0.65,
            'detail': 'Dragonfly Doji - Düşüş sonrası olası dönüş'
        })
    # Gravestone Doji (uzun üst fitil) → bearish bias
    elif upper_w > lower_w * 3 and trend == 'UP':
        signals.append({
            'type': 'GRAVESTONE_DOJI',
            'direction': 'BEARISH',
            'strength': 0.65,
            'detail': 'Gravestone Doji - Yükseliş sonrası olası dönüş'
        })
    # Standart Doji → kararsızlık
    elif trend != 'NEUTRAL':
        signals.append({
            'type': 'DOJI',
            'direction': 'NEUTRAL',
            'strength': 0.5,
            'detail': f'Doji - Kararsızlık ({trend} trend sonunda)'
        })
    
    return signals


# ============================================================
# 4. MARUBOZU
# ============================================================

def detect_marubozu(opens, highs, lows, closes):
    """
    MARUBOZU Tespiti
    
    GÖRÜNÜM:
    Fitili YOK veya çok kısa, TAMAMEN GÖVDE olan mum.
    
    ANLAMI:
    Tek taraf tamamen hakim. Bullish marubozu = alıcılar
    hiç geri adım atmadı. Bearish marubozu = satıcılar
    hiç geri adım atmadı.
    
    KOŞULLAR:
    1. Gövde, toplam aralığın %80'inden büyük
    2. Gövde, ortalama gövdenin 1.5x+ büyüklüğünde (gerçekten güçlü mum)
    """
    signals = []
    
    if len(closes) < 12:
        return signals
    
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    cr = _candle_range(h, l)
    
    if cr == 0:
        return signals
    
    body = _body_size(o, c)
    avg_b = _avg_body(opens, closes, 10)
    
    # Marubozu koşulları
    is_marubozu = (
        body >= cr * 0.80 and            # Gövde çok büyük
        body >= avg_b * 1.5 and           # Ortalamanın üstünde
        cr > 0
    )
    
    if is_marubozu:
        if _is_bullish(o, c):
            signals.append({
                'type': 'BULLISH_MARUBOZU',
                'direction': 'BULLISH',
                'strength': min(body / (avg_b + 0.0001) * 0.3, 1.0),
                'detail': f'Bullish Marubozu - Güçlü alıcı hakimiyeti'
            })
        else:
            signals.append({
                'type': 'BEARISH_MARUBOZU',
                'direction': 'BEARISH',
                'strength': min(body / (avg_b + 0.0001) * 0.3, 1.0),
                'detail': f'Bearish Marubozu - Güçlü satıcı hakimiyeti'
            })
    
    return signals


# ============================================================
# 5. MORNING STAR (Sabah Yıldızı)
# ============================================================

def detect_morning_star(opens, highs, lows, closes):
    """
    MORNING STAR (Sabah Yıldızı) Tespiti - 3 MUMLU FORMASYON
    
    GÖRÜNÜM:
    Mum 1: Büyük kırmızı (bearish) mum
    Mum 2: Küçük gövdeli mum (renk farketmez) - "yıldız"
    Mum 3: Büyük yeşil (bullish) mum
    
    ANLAMI (5 yaşına anlatır gibi):
    Karanlık gece (büyük düşüş) → Sabah yıldızı görünür (küçük mum,
    kararsızlık) → Güneş doğar (büyük yükseliş).
    = Düşüş trendi bitiyor, yükseliş başlıyor.
    
    KOŞULLAR:
    1. Mum 1: Bearish, gövde ortalama üstü
    2. Mum 2: Küçük gövde (Mum 1'in %40'ından az)
    3. Mum 3: Bullish, gövde ortalama üstü
    4. Mum 3 kapanışı, Mum 1 gövdesinin en az %50'sine ulaşmalı
    5. BAĞLAM: Düşüş trendi sonrası
    """
    signals = []
    
    if len(closes) < 13:
        return signals
    
    # Son 3 mum
    o1, h1, l1, c1 = opens[-3], highs[-3], lows[-3], closes[-3]
    o2, h2, l2, c2 = opens[-2], highs[-2], lows[-2], closes[-2]
    o3, h3, l3, c3 = opens[-1], highs[-1], lows[-1], closes[-1]
    
    body1 = _body_size(o1, c1)
    body2 = _body_size(o2, c2)
    body3 = _body_size(o3, c3)
    avg_b = _avg_body(opens, closes, 10)
    
    is_morning_star = (
        _is_bearish(o1, c1) and           # Mum 1 bearish
        body1 >= avg_b * 0.8 and           # Mum 1 büyük
        body2 < body1 * 0.40 and           # Mum 2 küçük
        _is_bullish(o3, c3) and            # Mum 3 bullish
        body3 >= avg_b * 0.8 and           # Mum 3 büyük
        c3 >= o1 - (body1 * 0.5)           # Mum 3 yeterince yükselmiş
    )
    
    if is_morning_star:
        trend = _trend_direction(closes[:-3], 10)
        if trend == 'DOWN':
            signals.append({
                'type': 'MORNING_STAR',
                'direction': 'BULLISH',
                'strength': 0.85,
                'detail': 'Morning Star (Sabah Yıldızı) - Güçlü dönüş sinyali'
            })
    
    return signals


# ============================================================
# 6. EVENING STAR (Akşam Yıldızı)
# ============================================================

def detect_evening_star(opens, highs, lows, closes):
    """
    EVENING STAR (Akşam Yıldızı) - Morning Star'ın tersi
    
    Mum 1: Büyük yeşil (bullish)
    Mum 2: Küçük gövdeli "yıldız"
    Mum 3: Büyük kırmızı (bearish)
    
    ANLAMI:
    Güneşli gün (yükseliş) → Akşam yıldızı (kararsızlık) → Gece (düşüş)
    = Yükseliş trendi bitiyor.
    """
    signals = []
    
    if len(closes) < 13:
        return signals
    
    o1, h1, l1, c1 = opens[-3], highs[-3], lows[-3], closes[-3]
    o2, h2, l2, c2 = opens[-2], highs[-2], lows[-2], closes[-2]
    o3, h3, l3, c3 = opens[-1], highs[-1], lows[-1], closes[-1]
    
    body1 = _body_size(o1, c1)
    body2 = _body_size(o2, c2)
    body3 = _body_size(o3, c3)
    avg_b = _avg_body(opens, closes, 10)
    
    is_evening_star = (
        _is_bullish(o1, c1) and
        body1 >= avg_b * 0.8 and
        body2 < body1 * 0.40 and
        _is_bearish(o3, c3) and
        body3 >= avg_b * 0.8 and
        c3 <= o1 + (body1 * 0.5)
    )
    
    if is_evening_star:
        trend = _trend_direction(closes[:-3], 10)
        if trend == 'UP':
            signals.append({
                'type': 'EVENING_STAR',
                'direction': 'BEARISH',
                'strength': 0.85,
                'detail': 'Evening Star (Akşam Yıldızı) - Güçlü dönüş sinyali'
            })
    
    return signals


# ============================================================
# ANA FORMASYON TARAYICI
# ============================================================

def analyze_all_patterns(opens, highs, lows, closes,
                          use_hammer=True, use_hanging=True,
                          use_doji=True, use_marubozu=True,
                          use_morning=True, use_evening=True):
    """
    Tüm formasyonları tara ve sinyalleri birleştir.
    """
    all_signals = []
    
    if use_hammer:
        all_signals.extend(detect_hammer(opens, highs, lows, closes))
    
    if use_hanging:
        all_signals.extend(detect_hanging_man(opens, highs, lows, closes))
    
    if use_doji:
        all_signals.extend(detect_doji(opens, highs, lows, closes))
    
    if use_marubozu:
        all_signals.extend(detect_marubozu(opens, highs, lows, closes))
    
    if use_morning:
        all_signals.extend(detect_morning_star(opens, highs, lows, closes))
    
    if use_evening:
        all_signals.extend(detect_evening_star(opens, highs, lows, closes))
    
    return all_signals
