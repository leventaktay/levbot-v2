"""
TARAMA MOTORU v3.0 (scanner_engine.py)
========================================
v3.0 Değişiklikler:
- OKX API desteği (SWAP perpetual futures)
- BingX API desteği (Türkiye yedek)
- Çoklu borsa: Binance / OKX / BingX / Otomatik fallback
- Funding rate çekme
- requests kütüphanesi (urllib yerine, daha güvenilir)
- CSV export geliştirildi (funding rate + borsa bilgisi)

ÖĞRETİCİ NOTLAR:
═══════════════════
1. Her borsanın API formatı farklıdır:
   - Binance: BTCUSDT (sembol birleşik, küçük harf TF: 1h, 4h)
   - OKX:     BTC-USDT-SWAP (tire ayraçlı, büyük harf TF: 1H, 4H)
   - BingX:   BTC-USDT (tire ayraçlı, küçük harf TF: 1h, 4h)

2. Neden çoklu borsa?
   - Türkiye'den Binance erişimi zaman zaman sorunlu
   - OKX senin ana borsan, oradan veri çekmek mantıklı
   - BingX her zaman açık, güvenilir yedek

3. Fallback mantığı:
   Birincil borsa başarısız → ikincil dene → üçüncül dene
   Bu sayede tarama asla boş dönmez.
"""

import json
import time
import csv
import os
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from indicators import analyze_all_indicators
from patterns import analyze_all_patterns


# ============================================================
# HTTP SESSION — Güvenilir bağlantı
# ============================================================

def create_session():
    """
    ÖĞRETİCİ: requests.Session neden kullanılır?
    ─────────────────────────────────────────────
    1. Connection pooling: her istekte yeni bağlantı açmaz, mevcut olanı kullanır → hızlı
    2. Retry: 429 (rate limit) veya 5xx hatalarında otomatik tekrar dener
    3. Timeout: yanıt gelmezse sonsuza kadar beklemez
    """
    s = requests.Session()
    retry = Retry(
        total=3,                                    # max 3 deneme
        backoff_factor=0.5,                         # her denemede 0.5s, 1s, 2s bekle
        status_forcelist=[429, 500, 502, 503, 504]  # bu kodlarda tekrar dene
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({'User-Agent': 'CoinScanner/3.0'})
    return s


# Tek global session — her fonksiyon bunu kullanır
_session = create_session()


def api_get(url, params=None, timeout=10):
    """
    Güvenli HTTP GET — hata yutmaz, detaylı log verir.
    
    ÖĞRETİCİ: Eski kodda urllib kullanılıyordu. requests avantajları:
    - params dict olarak verilir, URL encoding otomatik
    - JSON parse otomatik (.json())
    - Session ile connection reuse
    - Retry built-in
    """
    try:
        r = _session.get(url, params=params, timeout=timeout)
        r.raise_for_status()  # 4xx/5xx → exception
        return r.json()
    except requests.exceptions.HTTPError as e:
        print(f"  [HTTP HATA] {url}: {e}")
        return None
    except requests.exceptions.ConnectionError:
        print(f"  [BAĞLANTI HATASI] {url} — erişilemiyor (VPN/blok?)")
        return None
    except requests.exceptions.Timeout:
        print(f"  [TIMEOUT] {url} — {timeout}s içinde yanıt gelmedi")
        return None
    except Exception as e:
        print(f"  [HATA] {url}: {type(e).__name__}: {str(e)[:80]}")
        return None


# ============================================================
# BORSA API'LERİ — Sembol Listeleri
# ============================================================

# ── BINANCE ──────────────────────────────────────────────────

BINANCE_FAPI = "https://fapi.binance.com"

def get_binance_symbols():
    """Binance Futures USDT perpetual sembollerini çek"""
    data = api_get(f"{BINANCE_FAPI}/fapi/v1/exchangeInfo")
    if not data:
        return []
    return [
        {'symbol': s['symbol'], 'base': s['baseAsset'],
         'quote': s['quoteAsset'], 'exchange': 'Binance',
         'pricePrecision': s.get('pricePrecision', 2)}
        for s in data.get('symbols', [])
        if s.get('contractType') == 'PERPETUAL'
        and s.get('quoteAsset') == 'USDT'
        and s.get('status') == 'TRADING'
    ]


def get_binance_tickers():
    """Binance 24H ticker"""
    data = api_get(f"{BINANCE_FAPI}/fapi/v1/ticker/24hr")
    if not data:
        return {}
    return {
        t['symbol']: {
            'price': float(t.get('lastPrice', 0)),
            'volume_usdt': float(t.get('quoteVolume', 0)),
            'price_change_pct': float(t.get('priceChangePercent', 0)),
        }
        for t in data
    }


def get_binance_klines(symbol, interval='1h', limit=200):
    """
    Binance mum verisi.
    
    ÖĞRETİCİ: Binance kline formatı:
    [timestamp, open, high, low, close, volume, close_time, quote_volume, ...]
    Index 0-5 bize lazım. Kronolojik sırada gelir (eskiden yeniye).
    """
    data = api_get(
        f"{BINANCE_FAPI}/fapi/v1/klines",
        params={'symbol': symbol, 'interval': interval, 'limit': limit}
    )
    if not data:
        return None
    return _parse_binance_klines(data)


def get_binance_funding(symbol):
    """Binance funding rate"""
    data = api_get(
        f"{BINANCE_FAPI}/fapi/v1/premiumIndex",
        params={'symbol': symbol}
    )
    if not data:
        return None
    return float(data.get('lastFundingRate', 0)) * 100  # % olarak


def get_binance_all_funding():
    """Tüm coinlerin funding rate'i — tek API çağrısı ile"""
    data = api_get(f"{BINANCE_FAPI}/fapi/v1/premiumIndex")
    if not data:
        return {}
    return {
        d['symbol']: float(d.get('lastFundingRate', 0)) * 100
        for d in data
        if 'lastFundingRate' in d
    }


# ── OKX ──────────────────────────────────────────────────────

OKX_BASE = "https://www.okx.com"

# OKX timeframe dönüşüm tablosu
# Binance: 1h, 4h, 1d  →  OKX: 1H, 4H, 1D
OKX_TF_MAP = {
    '1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m',
    '1h': '1H', '4h': '4H', '1d': '1D', '1w': '1W',
}


def get_okx_symbols():
    """
    OKX SWAP (perpetual futures) sembollerini çek.
    
    ÖĞRETİCİ: OKX'te sembol formatı farklıdır:
    - instId: "BTC-USDT-SWAP" (tire ayraçlı + SWAP suffix)
    - Biz bunu Binance formatına çevireceğiz (BTCUSDT) internal kullanım için
    - Ama API çağrılarında OKX formatını kullanacağız
    """
    data = api_get(
        f"{OKX_BASE}/api/v5/public/instruments",
        params={'instType': 'SWAP'}
    )
    if not data or data.get('code') != '0':
        return []

    symbols = []
    for s in data.get('data', []):
        inst_id = s.get('instId', '')        # BTC-USDT-SWAP
        settle = s.get('settleCcy', '')       # USDT
        state = s.get('state', '')            # live
        if settle == 'USDT' and state == 'live' and inst_id.endswith('-SWAP'):
            parts = inst_id.replace('-SWAP', '').split('-')  # ['BTC', 'USDT']
            if len(parts) == 2:
                symbols.append({
                    'symbol': parts[0] + parts[1],          # BTCUSDT (internal)
                    'okx_inst_id': inst_id,                  # BTC-USDT-SWAP (API için)
                    'base': parts[0],                        # BTC
                    'quote': parts[1],                       # USDT
                    'exchange': 'OKX',
                    'pricePrecision': int(s.get('tickSz', '0.01').count('0') + 1) if '.' in s.get('tickSz', '0.01') else 2,
                })
    return symbols


def get_okx_tickers():
    """
    OKX 24H ticker verileri.
    
    ÖĞRETİCİ: OKX ticker response yapısı:
    {
      "code": "0",
      "data": [{
        "instId": "BTC-USDT-SWAP",
        "last": "67500.5",         ← son fiyat
        "volCcy24h": "12345.67",   ← 24h hacim (coin cinsinden)
        "vol24h": "1234567",       ← 24h hacim (kontrat cinsinden)
        "sodUtc0": "67000.0",      ← günün açılış fiyatı (UTC 00:00)
      }]
    }
    
    DİKKAT: OKX direkt quoteVolume (USDT cinsinden hacim) vermez!
    Biz hesaplıyoruz: volCcy24h × last = USDT hacim (yaklaşık)
    """
    data = api_get(
        f"{OKX_BASE}/api/v5/market/tickers",
        params={'instType': 'SWAP'}
    )
    if not data or data.get('code') != '0':
        return {}

    tickers = {}
    for t in data.get('data', []):
        inst_id = t.get('instId', '')
        if not inst_id.endswith('-USDT-SWAP'):
            continue

        base = inst_id.replace('-USDT-SWAP', '')
        symbol = base + 'USDT'  # Internal format

        last_price = float(t.get('last', 0) or 0)
        vol_ccy = float(t.get('volCcy24h', 0) or 0)      # coin cinsinden hacim
        open_utc = float(t.get('sodUtc0', 0) or 0)        # günün açılışı

        volume_usdt = vol_ccy * last_price  # USDT cinsinden hacim tahmini

        # Fiyat değişim yüzdesi
        price_change_pct = 0
        if open_utc > 0:
            price_change_pct = ((last_price - open_utc) / open_utc) * 100

        tickers[symbol] = {
            'price': last_price,
            'volume_usdt': volume_usdt,
            'price_change_pct': round(price_change_pct, 2),
        }
    return tickers


def get_okx_klines(symbol_or_instid, interval='1h', limit=200):
    """
    OKX mum verisi.
    
    ÖĞRETİCİ: OKX kline'ların iki ÖNEMLİ farkı var:
    1. instId formatı: "BTC-USDT-SWAP" (symbol değil!)
    2. Veriler TERS sırada gelir (yeniden eskiye) → reverse gerekiyor
    3. Kline formatı: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
    """
    # symbol → instId dönüşümü
    if '-' not in symbol_or_instid:
        # BTCUSDT → BTC-USDT-SWAP
        base = symbol_or_instid.replace('USDT', '')
        inst_id = f"{base}-USDT-SWAP"
    else:
        inst_id = symbol_or_instid

    okx_tf = OKX_TF_MAP.get(interval, interval)

    data = api_get(
        f"{OKX_BASE}/api/v5/market/candles",
        params={'instId': inst_id, 'bar': okx_tf, 'limit': str(limit)}
    )
    if not data or data.get('code') != '0':
        return None

    raw = data.get('data', [])
    if not raw:
        return None

    # ÖNEMLİ: OKX verileri ters sırada gelir → reverse
    raw.reverse()

    candles = {'opens': [], 'highs': [], 'lows': [], 'closes': [],
               'volumes': [], 'timestamps': []}
    for k in raw:
        candles['timestamps'].append(int(k[0]))
        candles['opens'].append(float(k[1]))
        candles['highs'].append(float(k[2]))
        candles['lows'].append(float(k[3]))
        candles['closes'].append(float(k[4]))
        candles['volumes'].append(float(k[5]))  # kontrat cinsinden hacim
    return candles


def get_okx_funding(symbol_or_instid):
    """OKX funding rate — tek coin"""
    if '-' not in symbol_or_instid:
        base = symbol_or_instid.replace('USDT', '')
        inst_id = f"{base}-USDT-SWAP"
    else:
        inst_id = symbol_or_instid

    data = api_get(
        f"{OKX_BASE}/api/v5/public/funding-rate",
        params={'instId': inst_id}
    )
    if not data or data.get('code') != '0':
        return None
    items = data.get('data', [])
    if not items:
        return None
    return float(items[0].get('fundingRate', 0)) * 100  # % olarak


def get_okx_all_funding():
    """OKX tüm funding rate'ler — tek çağrı yok, batch yapmamız lazım (sınırlı)"""
    # OKX tek seferde tüm funding'leri vermiyor, bu yüzden None dönüyoruz
    # Tek coin bazında get_okx_funding kullanılacak
    return {}


# ── BingX ─────────────────────────────────────────────────────

BINGX_BASE = "https://open-api.bingx.com"


def get_bingx_symbols():
    """BingX USDT-M perpetual semboller"""
    data = api_get(f"{BINGX_BASE}/openApi/swap/v2/quote/contracts")
    if not data:
        return []
    contracts = data.get('data', [])
    if not contracts:
        return []
    return [
        {'symbol': c['symbol'].replace('-', ''),  # BTC-USDT → BTCUSDT
         'bingx_symbol': c['symbol'],              # BTC-USDT (API için)
         'base': c['symbol'].split('-')[0],
         'quote': 'USDT',
         'exchange': 'BingX',
         'pricePrecision': 2}
        for c in contracts
        if c.get('currency') == 'USDT' and c.get('status') == 1  # aktif
    ]


def get_bingx_tickers():
    """BingX 24H ticker"""
    data = api_get(f"{BINGX_BASE}/openApi/swap/v2/quote/ticker")
    if not data:
        return {}
    tickers = {}
    for t in data.get('data', []):
        sym = t.get('symbol', '').replace('-', '')
        if not sym.endswith('USDT'):
            continue
        tickers[sym] = {
            'price': float(t.get('lastPrice', 0) or 0),
            'volume_usdt': float(t.get('quoteVolume', 0) or 0),
            'price_change_pct': float(t.get('priceChangePercent', 0) or 0),
        }
    return tickers


def get_bingx_klines(symbol, interval='1h', limit=200):
    """BingX mum verisi"""
    bingx_sym = symbol.replace('USDT', '-USDT') if '-' not in symbol else symbol
    data = api_get(
        f"{BINGX_BASE}/openApi/swap/v2/quote/klines",
        params={'symbol': bingx_sym, 'interval': interval, 'limit': str(limit)}
    )
    if not data:
        return None
    raw = data.get('data', [])
    if not raw:
        return None

    candles = {'opens': [], 'highs': [], 'lows': [], 'closes': [],
               'volumes': [], 'timestamps': []}
    for k in raw:
        candles['timestamps'].append(int(k.get('time', 0)))
        candles['opens'].append(float(k.get('open', 0)))
        candles['highs'].append(float(k.get('high', 0)))
        candles['lows'].append(float(k.get('low', 0)))
        candles['closes'].append(float(k.get('close', 0)))
        candles['volumes'].append(float(k.get('volume', 0)))
    return candles


# ============================================================
# ÇOKLU BORSA DISPATCHER
# ============================================================

def get_symbols(exchange='Otomatik'):
    """
    ÖĞRETİCİ: Dispatcher Pattern
    ─────────────────────────────
    Kullanıcı "OKX" seçtiyse → OKX'ten çek
    "Binance" seçtiyse → Binance'ten çek
    "Otomatik" seçtiyse → hepsini dene, çalışanı kullan
    
    Bu pattern sayesinde yeni borsa eklemek çok kolay:
    Sadece get_xxx_symbols() yaz, buraya ekle.
    """
    if exchange == 'OKX':
        symbols = get_okx_symbols()
        if symbols:
            return symbols, 'OKX'
        print("  ⚠️ OKX erişilemedi, Binance deneniyor...")

    if exchange == 'Binance':
        symbols = get_binance_symbols()
        if symbols:
            return symbols, 'Binance'
        print("  ⚠️ Binance erişilemedi, BingX deneniyor...")

    if exchange == 'BingX':
        symbols = get_bingx_symbols()
        if symbols:
            return symbols, 'BingX'

    # Otomatik: sırayla dene
    for name, func in [('OKX', get_okx_symbols),
                        ('Binance', get_binance_symbols),
                        ('BingX', get_bingx_symbols)]:
        print(f"  {name} deneniyor...")
        symbols = func()
        if symbols:
            print(f"  ✅ {name}: {len(symbols)} sembol bulundu")
            return symbols, name

    return [], 'Yok'


def get_tickers(exchange='Otomatik'):
    """Ticker dispatcher"""
    if exchange == 'OKX':
        return get_okx_tickers() or get_binance_tickers() or get_bingx_tickers()
    elif exchange == 'Binance':
        return get_binance_tickers() or get_okx_tickers() or get_bingx_tickers()
    elif exchange == 'BingX':
        return get_bingx_tickers() or get_okx_tickers() or get_binance_tickers()
    else:
        # Otomatik
        for func in [get_okx_tickers, get_binance_tickers, get_bingx_tickers]:
            result = func()
            if result:
                return result
        return {}


def get_klines(symbol, interval='1h', limit=200, exchange='Otomatik', extra_info=None):
    """
    Kline dispatcher — borsaya göre doğru fonksiyonu çağırır.
    
    extra_info: symbol dict'indeki ek bilgiler (okx_inst_id, bingx_symbol vs.)
    """
    if exchange == 'OKX':
        inst_id = extra_info.get('okx_inst_id', symbol) if extra_info else symbol
        return get_okx_klines(inst_id, interval, limit)
    elif exchange == 'Binance':
        return get_binance_klines(symbol, interval, limit)
    elif exchange == 'BingX':
        return get_bingx_klines(symbol, interval, limit)
    else:
        # Otomatik fallback
        for func, arg in [(get_okx_klines, symbol),
                          (get_binance_klines, symbol),
                          (get_bingx_klines, symbol)]:
            result = func(arg, interval, limit)
            if result:
                return result
        return None


def get_all_funding(exchange='Otomatik'):
    """Tüm coinlerin funding rate'leri"""
    if exchange == 'Binance':
        return get_binance_all_funding()
    # OKX toplu funding desteklemiyor, Binance'i yedek olarak kullan
    result = get_binance_all_funding()
    if result:
        return result
    return {}


# ============================================================
# MARKET CAP — Çoklu Kaynak
# ============================================================

_mcap_cache = {'data': {}, 'timestamp': 0, 'ttl': 3600}


def _fetch_mcap_coingecko():
    mcap = {}
    try:
        for page in range(1, 3):
            data = api_get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={'vs_currency': 'usd', 'order': 'market_cap_desc',
                        'per_page': 250, 'page': page},
                timeout=8
            )
            if not data:
                break
            for coin in data:
                sym = coin.get('symbol', '').upper()
                mc = coin.get('market_cap', 0)
                if sym and mc:
                    mcap[sym] = mc
            if page < 2:
                time.sleep(1.5)
        if mcap:
            print(f"  CoinGecko: {len(mcap)} coin")
    except Exception as e:
        print(f"  CoinGecko hatası: {e}")
    return mcap


def _fetch_mcap_coinpaprika():
    mcap = {}
    try:
        data = api_get(
            "https://api.coinpaprika.com/v1/tickers",
            params={'limit': 300}, timeout=8
        )
        if data:
            for coin in data:
                sym = coin.get('symbol', '').upper()
                mc = coin.get('quotes', {}).get('USD', {}).get('market_cap', 0)
                if sym and mc:
                    mcap[sym] = mc
            if mcap:
                print(f"  CoinPaprika: {len(mcap)} coin")
    except Exception as e:
        print(f"  CoinPaprika hatası: {e}")
    return mcap


def get_market_caps():
    """Market cap verisi — cache + fallback"""
    global _mcap_cache
    now = time.time()
    if _mcap_cache['data'] and (now - _mcap_cache['timestamp']) < _mcap_cache['ttl']:
        return _mcap_cache['data']

    print("Market cap verisi çekiliyor...")
    mcap = _fetch_mcap_coingecko()
    if len(mcap) < 50:
        mcap_alt = _fetch_mcap_coinpaprika()
        if len(mcap_alt) > len(mcap):
            mcap = mcap_alt
    if mcap:
        _mcap_cache['data'] = mcap
        _mcap_cache['timestamp'] = now
    return mcap


# ============================================================
# TARAMA
# ============================================================

def scan_coin(symbol, timeframes=None, indicator_settings=None,
              pattern_settings=None, exchange='Otomatik', extra_info=None):
    """Tek coini tüm TF'lerde tara"""
    if timeframes is None:
        timeframes = ['1h', '4h', '1d']
    if indicator_settings is None:
        indicator_settings = {
            'use_rsi': True, 'use_wavetrend': True,
            'use_bb': True, 'use_t3': True, 'use_volume': True
        }
    if pattern_settings is None:
        pattern_settings = {
            'use_hammer': True, 'use_hanging': True, 'use_doji': True,
            'use_marubozu': True, 'use_morning': True, 'use_evening': True
        }

    tf_weights = {'15m': 0.5, '30m': 0.7, '1h': 1.0, '4h': 1.5, '1d': 2.0, '1w': 2.5}

    result = {
        'symbol': symbol, 'timeframe_results': {},
        'total_bullish': 0, 'total_bearish': 0, 'all_signals': [],
        'dominant_trend': 'NEUTRAL', 'signal_count': 0,
        'risk_level': 1, 'has_conflict': False,
        'scan_time': datetime.now().strftime('%H:%M:%S'),
        'exchange': exchange,
    }

    max_risk = 1

    for tf in timeframes:
        candles = get_klines(symbol, tf, exchange=exchange, extra_info=extra_info)
        if not candles or len(candles['closes']) < 30:
            continue

        weight = tf_weights.get(tf, 1.0)

        ind_result = analyze_all_indicators(
            candles['closes'], candles['highs'],
            candles['lows'], candles['volumes'],
            **indicator_settings, timeframe=tf
        )

        pat_signals = analyze_all_patterns(
            candles['opens'], candles['highs'],
            candles['lows'], candles['closes'],
            **pattern_settings
        )

        tf_signals = []
        for sig in ind_result['signals'] + pat_signals:
            sig['timeframe'] = tf
            sig['weighted_strength'] = sig['strength'] * weight
            tf_signals.append(sig)

        result['timeframe_results'][tf] = {
            'bullish_score': ind_result['bullish_score'] * weight,
            'bearish_score': ind_result['bearish_score'] * weight,
            'trend': ind_result['trend'],
            'rsi': ind_result.get('rsi'),
            'wt1': ind_result.get('wt1'),
            'bb_bandwidth': ind_result.get('bb_bandwidth'),
            't3_trend': ind_result.get('t3_trend'),
            'risk_level': ind_result.get('risk_level', 1),
            'has_conflict': ind_result.get('has_conflict', False),
            'signals': tf_signals,
            'current_price': candles['closes'][-1],
        }

        result['all_signals'].extend(tf_signals)
        result['total_bullish'] += ind_result['bullish_score'] * weight
        result['total_bearish'] += ind_result['bearish_score'] * weight
        max_risk = max(max_risk, ind_result.get('risk_level', 1))

        if ind_result.get('has_conflict'):
            result['has_conflict'] = True

    result['signal_count'] = len(result['all_signals'])
    result['risk_level'] = max_risk

    if result['total_bullish'] > result['total_bearish'] + 15:
        result['dominant_trend'] = 'BULLISH'
    elif result['total_bearish'] > result['total_bullish'] + 15:
        result['dominant_trend'] = 'BEARISH'

    if result['timeframe_results']:
        first_tf = list(result['timeframe_results'].values())[0]
        result['current_price'] = first_tf.get('current_price', 0)

    return result


def run_full_scan(min_volume_usdt=10_000_000, min_market_cap=0,
                  max_market_cap=0, max_coins=100,
                  timeframes=None, indicator_settings=None,
                  pattern_settings=None, progress_callback=None,
                  exchange='Otomatik'):
    """
    Tam tarama: borsa seç → filtrele → tara → skorla
    
    ÖĞRETİCİ: Tarama akışı
    ────────────────────────
    1. Sembol listesini çek (exchange'e göre)
    2. 24H ticker'ları çek (fiyat, hacim, değişim)
    3. Hacim filtresi uygula
    4. Market cap filtresi uygula (opsiyonel)
    5. Her coini indikatör + formasyon analizi yap
    6. Funding rate çek
    7. Sonuçları skorla ve sırala
    """
    if timeframes is None:
        timeframes = ['1h', '4h', '1d']

    results = []

    # 1. Sembol listesi
    if progress_callback:
        progress_callback("Sembol listesi çekiliyor...", 0, 1)
    symbols, active_exchange = get_symbols(exchange)
    if not symbols:
        print("❌ Hiçbir borsadan sembol çekilemedi!")
        return results
    print(f"📡 Aktif borsa: {active_exchange} ({len(symbols)} sembol)")

    # 2. Ticker'lar
    if progress_callback:
        progress_callback("Ticker verileri çekiliyor...", 0, 1)
    tickers = get_tickers(active_exchange)
    if not tickers:
        print("❌ Ticker verisi çekilemedi!")
        return results

    # 3. Funding rate
    funding_data = get_all_funding(active_exchange)

    # 4. Market cap
    mcap_data = get_market_caps()
    use_mcap = min_market_cap > 0 or max_market_cap > 0

    # 5. Filtrele
    filtered = []
    for s in symbols:
        sym = s['symbol']  # internal format: BTCUSDT
        if sym not in tickers:
            continue
        vol = tickers[sym]['volume_usdt']
        if vol < min_volume_usdt:
            continue

        base = s['base']
        coin_mcap = mcap_data.get(base, 0)
        if use_mcap:
            if min_market_cap > 0 and coin_mcap < min_market_cap:
                continue
            if max_market_cap > 0 and coin_mcap > max_market_cap:
                continue
            if coin_mcap == 0:
                continue

        filtered.append({
            **s,
            'volume_usdt': vol,
            'price': tickers[sym]['price'],
            'price_change_pct': tickers[sym]['price_change_pct'],
            'market_cap': coin_mcap,
            'funding_rate': funding_data.get(sym, None),
        })

    filtered.sort(key=lambda x: x['volume_usdt'], reverse=True)
    filtered = filtered[:max_coins]
    total = len(filtered)
    print(f"🔍 {total} coin taranacak ({active_exchange})")

    # 6. Tara
    for idx, coin in enumerate(filtered):
        if progress_callback:
            progress_callback(coin['symbol'], idx + 1, total)
        try:
            scan_result = scan_coin(
                coin['symbol'], timeframes,
                indicator_settings, pattern_settings,
                exchange=active_exchange,
                extra_info=coin,  # okx_inst_id, bingx_symbol vs.
            )
            scan_result['volume_usdt'] = coin['volume_usdt']
            scan_result['price'] = coin['price']
            scan_result['price_change_pct'] = coin['price_change_pct']
            scan_result['market_cap'] = coin.get('market_cap', 0)
            scan_result['funding_rate'] = coin.get('funding_rate')
            scan_result['exchange'] = active_exchange
            results.append(scan_result)

            # Rate limit koruması
            if (idx + 1) % 5 == 0:
                time.sleep(0.5)
        except Exception as e:
            print(f"  Tarama hatası ({coin['symbol']}): {e}")
            continue

    results.sort(key=lambda x: max(x['total_bullish'], x['total_bearish']), reverse=True)
    return results


# ============================================================
# CSV EXPORT
# ============================================================

def export_to_csv(results, filepath=None):
    """Tarama sonuçlarını CSV'ye kaydet — v3'te funding rate + borsa eklendi"""
    if filepath is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = f"scan_results_{timestamp}.csv"

    headers = [
        'Sembol', 'Borsa', 'Fiyat', 'Değişim%', 'Trend', 'Bullish', 'Bearish',
        'Sinyal', 'Risk', 'RSI_4H', 'WT_4H', 'BB_Squeeze', 'Funding%',
        'Market_Cap', 'Volume_24H', 'Çatışma', 'Sinyaller', 'Tarama_Zamanı'
    ]

    rows = []
    for r in results:
        rsi_4h = ''
        wt_4h = ''
        if '4h' in r.get('timeframe_results', {}):
            rsi_val = r['timeframe_results']['4h'].get('rsi')
            wt_val = r['timeframe_results']['4h'].get('wt1')
            if rsi_val: rsi_4h = f"{rsi_val:.1f}"
            if wt_val: wt_4h = f"{wt_val:.1f}"

        funding = r.get('funding_rate')
        funding_str = f"{funding:.4f}" if funding is not None else ''

        signal_texts = [s['detail'] for s in r.get('all_signals', [])[:5]]

        rows.append([
            r['symbol'], r.get('exchange', ''), r.get('price', ''),
            f"{r.get('price_change_pct', 0):.2f}",
            r['dominant_trend'], f"{r['total_bullish']:.0f}", f"{r['total_bearish']:.0f}",
            r['signal_count'], r.get('risk_level', 1), rsi_4h, wt_4h,
            any('SQUEEZE' in s['type'] for s in r['all_signals']),
            funding_str,
            r.get('market_cap', 0), r.get('volume_usdt', 0),
            r.get('has_conflict', False), ' | '.join(signal_texts),
            r.get('scan_time', '')
        ])

    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    return filepath
