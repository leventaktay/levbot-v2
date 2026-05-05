import time
import hmac
import hashlib
import base64
import json
import requests
import threading
import os
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ══ AYARLAR — ÇEVRE DEĞİŞKENLERİNDEN OKU ════════════════════════════════════
# NASIL AYARLANIR?
# Windows: set OKX_API_KEY=senin_key_in
# Linux  : export OKX_API_KEY=senin_key_in
# Render : Dashboard → Environment bölümünden ekle
# ASLA bu değerleri doğrudan koda yazma! Güvenlik riski oluşturur.

OKX_API_KEY      = os.environ.get("OKX_API_KEY",    "")
OKX_SECRET       = os.environ.get("OKX_SECRET",     "")
OKX_PASSPHRASE   = os.environ.get("OKX_PASSPHRASE", "")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID","")

# Credentials eksikse hata ver
if not all([OKX_API_KEY, OKX_SECRET, OKX_PASSPHRASE, TELEGRAM_TOKEN]):
    print("⚠️  UYARI: Çevre değişkenleri eksik!")
    print("    OKX_API_KEY, OKX_SECRET, OKX_PASSPHRASE, TELEGRAM_TOKEN ayarlanmamış.")
    print("    Lokalde test için: set OKX_API_KEY=... komutu kullan")

OKX_BASE = "https://www.okx.com"

# ══ BEKLEYEN İŞLEMLER ══════════════════════════════════════════
pending_orders = {}

# ══ OKX İMZA ═══════════════════════════════════════════════════
def sign(timestamp, method, path, body=''):
    msg = f"{timestamp}{method}{path}{body}"
    mac = hmac.new(OKX_SECRET.encode(), msg.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()

def headers(method, path, body=''):
    # DÜZELTME: datetime.timezone yerine timezone kullan (import'tan geliyor)
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    return {
        'OK-ACCESS-KEY':        OKX_API_KEY,
        'OK-ACCESS-SIGN':       sign(ts, method, path, body),
        'OK-ACCESS-TIMESTAMP':  ts,
        'OK-ACCESS-PASSPHRASE': OKX_PASSPHRASE,
        'Content-Type':         'application/json',
        'x-simulated-trading':  '0'
    }

# ══ OKX API ÇAĞRILARI ══════════════════════════════════════════
def get_price(symbol):
    """Anlık fiyat al"""
    try:
        r = requests.get(f"{OKX_BASE}/api/v5/market/ticker?instId={symbol}", timeout=8)
        d = r.json()
        return float(d['data'][0]['last'])
    except:
        return None

def get_balance():
    """Hesap bakiyesi"""
    try:
        path = '/api/v5/account/balance?ccy=USDT'
        r = requests.get(OKX_BASE + path, headers=headers('GET', path), timeout=8)
        d = r.json()
        return float(d['data'][0]['details'][0]['availBal'])
    except:
        return None

def set_leverage(symbol, leverage, mode='cross'):
    """Kaldıraç ayarla"""
    try:
        path = '/api/v5/account/set-leverage'
        body = json.dumps({
            'instId': symbol,
            'lever': str(leverage),
            'mgnMode': mode
        })
        r = requests.post(OKX_BASE + path, headers=headers('POST', path, body), data=body, timeout=8)
        return r.json()
    except Exception as e:
        return {'error': str(e)}

def place_order(symbol, side, size, sl_price=None, tp_price=None, leverage=10):
    """İşlem aç"""
    try:
        # Kaldıraç ayarla
        set_leverage(symbol, leverage)

        path = '/api/v5/trade/order'
        order = {
            'instId':   symbol,
            'tdMode':   'cross',
            'side':     side,        # 'buy' veya 'sell'
            'ordType':  'market',
            'sz':       str(size),
            'posSide':  'long' if side == 'buy' else 'short'
        }
        body = json.dumps(order)
        r = requests.post(OKX_BASE + path, headers=headers('POST', path, body), data=body, timeout=8)
        result = r.json()

        if result.get('code') == '0':
            ord_id = result['data'][0]['ordId']
            # SL/TP ayarla
            if sl_price or tp_price:
                time.sleep(0.5)
                set_sl_tp(symbol, ord_id, side, sl_price, tp_price, size)
            return {'ok': True, 'ordId': ord_id}
        else:
            return {'ok': False, 'error': result.get('msg', 'Bilinmeyen hata')}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def set_sl_tp(symbol, ord_id, side, sl_price, tp_price, size):
    """Stop Loss ve Take Profit ayarla"""
    try:
        path = '/api/v5/trade/order-algo'
        pos_side = 'long' if side == 'buy' else 'short'
        algo = {
            'instId':  symbol,
            'tdMode':  'cross',
            'side':    'sell' if side == 'buy' else 'buy',
            'posSide': pos_side,
            'ordType': 'oco',
            'sz':      str(size),
        }
        if sl_price:
            algo['slTriggerPx'] = str(sl_price)
            algo['slOrdPx']     = '-1'
        if tp_price:
            algo['tpTriggerPx'] = str(tp_price)
            algo['tpOrdPx']     = '-1'
        body = json.dumps(algo)
        requests.post(OKX_BASE + path, headers=headers('POST', path, body), data=body, timeout=8)
    except:
        pass

def close_position(symbol, side):
    """Pozisyonu kapat"""
    try:
        path = '/api/v5/trade/close-position'
        body = json.dumps({
            'instId':  symbol,
            'mgnMode': 'cross',
            'posSide': 'long' if side == 'buy' else 'short'
        })
        r = requests.post(OKX_BASE + path, headers=headers('POST', path, body), data=body, timeout=8)
        return r.json()
    except Exception as e:
        return {'error': str(e)}

def get_positions():
    """Açık pozisyonları getir"""
    try:
        path = '/api/v5/account/positions'
        r = requests.get(OKX_BASE + path, headers=headers('GET', path), timeout=8)
        d = r.json()
        positions = []
        for p in d.get('data', []):
            if float(p.get('pos', 0)) != 0:
                positions.append({
                    'symbol':   p['instId'],
                    'side':     p['posSide'],
                    'size':     p['pos'],
                    'entry':    p['avgPx'],
                    'pnl':      p['upl'],
                    'pnl_pct':  p['uplRatio'],
                    'liq':      p['liqPx'],
                    'leverage': p['lever'],
                })
        return positions
    except Exception as e:
        return []

# ══ HESAPLAMALAR ═══════════════════════════════════════════════
def calc_size(symbol, margin, leverage, price):
    """Coin miktarı hesapla"""
    if not price or price == 0:
        return 0
    position_value = margin * leverage
    return round(position_value / price, 6)

def calc_liq_price(entry, leverage, side):
    """Likidasyon fiyatı hesapla"""
    if leverage == 0:
        return 0
    if side == 'buy':
        return round(entry * (1 - 1/leverage), 2)
    else:
        return round(entry * (1 + 1/leverage), 2)

# ══ TELEGRAM KOMUTLARI ══════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """
🤖 *LevBot Aktif!*

📋 *Komutlar:*
/short — Short pozisyon sinyali gönder
/long — Long pozisyon sinyali gönder
/pozisyonlar — Açık pozisyonları gör
/bakiye — Hesap bakiyesi
/fiyat [sembol] — Anlık fiyat (örn: /fiyat BTC-USDT-SWAP)
/kapat [sembol] [side] — Pozisyon kapat
/yardim — Tüm komutlar

⚡ *Desteklenen semboller:*
BTC-USDT-SWAP, ETH-USDT-SWAP, SOL-USDT-SWAP
XRP-USDT-SWAP, DOGE-USDT-SWAP, LINK-USDT-SWAP
XAU-USDT-SWAP (Altın), XAG-USDT-SWAP (Gümüş)
"""
    await update.message.reply_text(msg, parse_mode='Markdown')

async def bakiye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bal = get_balance()
    if bal:
        await update.message.reply_text(f"💰 *Bakiye:* ${bal:.2f} USDT", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ Bakiye alınamadı.")

async def fiyat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Kullanım: /fiyat BTC-USDT-SWAP")
        return
    symbol = context.args[0].upper()
    price = get_price(symbol)
    if price:
        await update.message.reply_text(f"💹 *{symbol}:* ${price:,.2f}", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ {symbol} fiyatı alınamadı.")

async def pozisyonlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    positions = get_positions()
    if not positions:
        await update.message.reply_text("📭 Açık pozisyon yok.")
        return
    msg = "📊 *Açık Pozisyonlar:*\n\n"
    for p in positions:
        pnl = float(p['pnl'])
        pnl_pct = float(p['pnl_pct']) * 100
        emoji = "🟢" if pnl >= 0 else "🔴"
        msg += f"{emoji} *{p['symbol']}*\n"
        msg += f"  Yön: {p['side'].upper()} | Kaldıraç: {p['leverage']}x\n"
        msg += f"  Giriş: ${float(p['entry']):,.2f}\n"
        msg += f"  K/Z: ${pnl:+.2f} ({pnl_pct:+.2f}%)\n"
        msg += f"  Likidasyon: ${float(p['liq']):,.2f}\n\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def short_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Short sinyali gönder"""
    # Varsayılan değerler
    symbol   = context.args[0].upper() if context.args else "BTC-USDT-SWAP"
    margin   = float(context.args[1]) if len(context.args) > 1 else 50
    leverage = int(context.args[2])   if len(context.args) > 2 else 10
    sl       = float(context.args[3]) if len(context.args) > 3 else None
    tp       = float(context.args[4]) if len(context.args) > 4 else None

    price = get_price(symbol)
    if not price:
        await update.message.reply_text("❌ Fiyat alınamadı.")
        return

    size    = calc_size(symbol, margin, leverage, price)
    liq     = calc_liq_price(price, leverage, 'sell')
    risk    = margin
    max_lev = 15 if 'BTC' in symbol or 'ETH' in symbol else 10

    if leverage > max_lev:
        await update.message.reply_text(f"⚠️ {symbol} için max kaldıraç {max_lev}x!")
        return

    order_id = f"short_{int(time.time())}"
    pending_orders[order_id] = {
        'symbol': symbol, 'side': 'sell', 'size': size,
        'margin': margin, 'leverage': leverage,
        'price': price, 'sl': sl, 'tp': tp
    }

    keyboard = [
        [InlineKeyboardButton("✅ ONAYLA", callback_data=f"confirm_{order_id}"),
         InlineKeyboardButton("❌ REDDET", callback_data=f"reject_{order_id}")]
    ]
    msg = f"""
⚡ *SHORT SİNYALİ*

📍 Sembol: `{symbol}`
💰 Margin: ${margin}
⚡ Kaldıraç: {leverage}x
📊 Pozisyon: ${margin*leverage:,.0f}
🔢 Miktar: {size}
💹 Güncel Fiyat: ${price:,.2f}
⚰️ Likidasyon: ${liq:,.2f}
🛑 Stop Loss: ${sl:,.2f} if sl else "—"
🎯 Take Profit: ${tp:,.2f} if tp else "—"

_120 saniye içinde onaylamazsan iptal olur!_
"""
    reply = await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    # 120 sn sonra iptal
    async def auto_cancel():
        await asyncio.sleep(120)
        if order_id in pending_orders:
            del pending_orders[order_id]
            await reply.edit_text(f"⏱️ Süre doldu, işlem iptal edildi.\n\n{msg}", parse_mode='Markdown')

    import asyncio
    asyncio.create_task(auto_cancel())

async def long_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Long sinyali gönder"""
    symbol   = context.args[0].upper() if context.args else "BTC-USDT-SWAP"
    margin   = float(context.args[1]) if len(context.args) > 1 else 50
    leverage = int(context.args[2])   if len(context.args) > 2 else 10
    sl       = float(context.args[3]) if len(context.args) > 3 else None
    tp       = float(context.args[4]) if len(context.args) > 4 else None

    price = get_price(symbol)
    if not price:
        await update.message.reply_text("❌ Fiyat alınamadı.")
        return

    size    = calc_size(symbol, margin, leverage, price)
    liq     = calc_liq_price(price, leverage, 'buy')
    max_lev = 15 if 'BTC' in symbol or 'ETH' in symbol else 10

    if leverage > max_lev:
        await update.message.reply_text(f"⚠️ {symbol} için max kaldıraç {max_lev}x!")
        return

    order_id = f"long_{int(time.time())}"
    pending_orders[order_id] = {
        'symbol': symbol, 'side': 'buy', 'size': size,
        'margin': margin, 'leverage': leverage,
        'price': price, 'sl': sl, 'tp': tp
    }

    keyboard = [
        [InlineKeyboardButton("✅ ONAYLA", callback_data=f"confirm_{order_id}"),
         InlineKeyboardButton("❌ REDDET", callback_data=f"reject_{order_id}")]
    ]
    msg = f"""
⚡ *LONG SİNYALİ*

📍 Sembol: `{symbol}`
💰 Margin: ${margin}
⚡ Kaldıraç: {leverage}x
📊 Pozisyon: ${margin*leverage:,.0f}
🔢 Miktar: {size}
💹 Güncel Fiyat: ${price:,.2f}
⚰️ Likidasyon: ${liq:,.2f}
🛑 Stop Loss: ${sl:,.2f} if sl else "—"
🎯 Take Profit: ${tp:,.2f} if tp else "—"

_120 saniye içinde onaylamazsan iptal olur!_
"""
    reply = await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    import asyncio
    async def auto_cancel():
        await asyncio.sleep(120)
        if order_id in pending_orders:
            del pending_orders[order_id]
            await reply.edit_text(f"⏱️ Süre doldu, işlem iptal edildi.\n\n{msg}", parse_mode='Markdown')
    asyncio.create_task(auto_cancel())

async def kapat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pozisyon kapat"""
    if len(context.args) < 2:
        await update.message.reply_text("Kullanım: /kapat BTC-USDT-SWAP short")
        return
    symbol = context.args[0].upper()
    side   = context.args[1].lower()
    result = close_position(symbol, side)
    if result.get('code') == '0':
        await update.message.reply_text(f"✅ *{symbol} pozisyonu kapatıldı!*", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ Hata: {result.get('msg', str(result))}")

async def yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """
📚 *KOMUT REHBERİ*

*Temel Komutlar:*
/bakiye — Hesap bakiyesi
/pozisyonlar — Açık pozisyonlar
/fiyat BTC-USDT-SWAP — Fiyat sorgula
/trend BTC — T3 + WaveTrend analizi

*İşlem Komutları:*
/short [sembol] [margin] [kaldıraç] [sl] [tp]
/long [sembol] [margin] [kaldıraç] [sl] [tp]
/kapat [sembol] [side]

*Örnekler:*
`/short BTC-USDT-SWAP 50 10 75000 63000`
`/long ETH-USDT-SWAP 30 8 2800 3500`
`/short XAU-USDT-SWAP 50 5 3100 2800`
`/kapat BTC-USDT-SWAP short`
`/trend BTC`

*Desteklenen Semboller:*
BTC, ETH, SOL, XRP, DOGE, LINK
XAU (Altın), XAG (Gümüş), USOIL (Petrol)

*Kaldıraç Limitleri:*
BTC/ETH: max 15x
Majör altcoinler: max 10x
Emtia: max 5x
"""
    await update.message.reply_text(msg, parse_mode='Markdown')


# ══ T3 + WAVETREND HESAPLAMA (LevBot için) ══════════════════════════════════

def _ema_run(data, period):
    """Running EMA — tam liste döner"""
    if len(data) < period:
        return []
    k = 2 / (period + 1)
    e = data[0]
    result = []
    for x in data:
        e = x * k + e * (1 - k)
        result.append(e)
    return result

def bot_calc_t3(closes, period=6, v=0.7):
    """Tilson T3 — son değer + yön"""
    if len(closes) < period * 6 + 10:
        return None
    try:
        e1 = _ema_run(closes, period)
        e2 = _ema_run(e1, period)
        e3 = _ema_run(e2, period)
        e4 = _ema_run(e3, period)
        e5 = _ema_run(e4, period)
        e6 = _ema_run(e5, period)
        if not e6:
            return None
        c1 = -(v**3)
        c2 = 3*v**2 + 3*v**3
        c3 = -6*v**2 - 3*v - 3*v**3
        c4 = 1 + 3*v + v**3 + 3*v**2
        curr = c1*e6[-1] + c2*e5[-1] + c3*e4[-1] + c4*e3[-1]
        prev = c1*e6[-2] + c2*e5[-2] + c3*e4[-2] + c4*e3[-2]
        return {"value": curr, "rising": curr > prev, "price_above": closes[-1] > curr}
    except:
        return None

def bot_calc_wavetrend(highs, lows, closes, channel_len=9, avg_len=12, ma_len=3,
                       ob=53, os_lv=-53):
    """WaveTrend Oscillator — VMC Cipher B kalbi"""
    n = len(closes)
    if n < channel_len + avg_len + ma_len + 15:
        return None
    try:
        k_ch  = 2 / (channel_len + 1)
        k_avg = 2 / (avg_len + 1)
        src = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(n)]
        esa = src[0]; esa_s = []
        for x in src:
            esa = x * k_ch + esa * (1 - k_ch)
            esa_s.append(esa)
        de = abs(src[0] - esa_s[0]); de_s = []
        for i in range(n):
            d = abs(src[i] - esa_s[i])
            de = d * k_ch + de * (1 - k_ch)
            de_s.append(de)
        ci_s = [(src[i] - esa_s[i]) / (0.015 * de_s[i]) if de_s[i] != 0 else 0 for i in range(n)]
        wt1 = ci_s[0]; wt1_s = []
        for x in ci_s:
            wt1 = x * k_avg + wt1 * (1 - k_avg)
            wt1_s.append(wt1)
        wt2_s = [sum(wt1_s[max(0,i-ma_len+1):i+1])/(min(i+1,ma_len)) for i in range(n)]
        wt1_c, wt1_p = wt1_s[-1], wt1_s[-2]
        wt2_c, wt2_p = wt2_s[-1], wt2_s[-2]
        return {
            "wt1": round(wt1_c, 2), "wt2": round(wt2_c, 2),
            "cross_up":   (wt1_p < wt2_p) and (wt1_c >= wt2_c),
            "cross_down": (wt1_p > wt2_p) and (wt1_c <= wt2_c),
            "overbought": wt2_c >= ob,
            "oversold":   wt2_c <= os_lv,
            "buy_signal":  (wt1_p < wt2_p) and (wt1_c >= wt2_c) and wt2_c <= os_lv,
            "sell_signal": (wt1_p > wt2_p) and (wt1_c <= wt2_c) and wt2_c >= ob,
        }
    except:
        return None

def bot_get_candles(symbol_base, tf="4h", limit=120):
    """OKX'ten mum verisi çek — Binance fallback"""
    tf_map = {"1h":"1H","4h":"4H","1d":"1D","1w":"1W"}
    okx_tf = tf_map.get(tf.lower(), "4H")
    sym = symbol_base.replace("-","").replace("SWAP","").replace("USDT","").upper()
    inst_id = f"{sym}-USDT-SWAP"
    # OKX
    try:
        url = f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={okx_tf}&limit={limit}"
        r = requests.get(url, timeout=10)
        d = r.json()
        data = list(reversed(d.get("data", [])))
        if data:
            return ([float(x[1]) for x in data],[float(x[2]) for x in data],
                    [float(x[3]) for x in data],[float(x[4]) for x in data])
    except:
        pass
    # Binance fallback
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}USDT&interval={tf}&limit={limit}"
        r = requests.get(url, timeout=10)
        d = r.json()
        if isinstance(d, list) and d:
            return ([float(x[1]) for x in d],[float(x[2]) for x in d],
                    [float(x[3]) for x in d],[float(x[4]) for x in d])
    except:
        pass
    return None, None, None, None


async def trend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /trend [sembol] — T3 + WaveTrend analizi
    Örnek: /trend BTC
    """
    symbol = context.args[0].upper() if context.args else "BTC"
    # OKX formatını temizle (BTC-USDT-SWAP → BTC)
    symbol = symbol.replace("-USDT-SWAP","").replace("USDT","").replace("-","")

    await update.message.reply_text(f"🔍 *{symbol}* analiz ediliyor...", parse_mode='Markdown')

    # 4H mum verisi
    o4, h4, l4, c4 = bot_get_candles(symbol, "4h", 150)
    # 1H mum verisi
    o1, h1, l1, c1 = bot_get_candles(symbol, "1h", 100)

    if not c4:
        await update.message.reply_text(f"❌ {symbol} için veri alınamadı.")
        return

    price = c4[-1]

    # T3 hesapla (4H)
    t3 = bot_calc_t3(c4)
    # WaveTrend hesapla (1H — entry sinyali için)
    wt = bot_calc_wavetrend(h1, l1, c1) if c1 else None
    # WaveTrend (4H — trend teyidi)
    wt4 = bot_calc_wavetrend(h4, l4, c4)

    # ── Rapor oluştur ──
    lines = [f"📊 *{symbol}/USDT — T3 + VMC Analizi*\n"]
    lines.append(f"💹 Fiyat: `${price:,.4g}`\n")

    # T3 bölümü
    lines.append("*📈 Tilson T3 (4H):*")
    if t3:
        arrow  = "⬆️" if t3["rising"] else "⬇️"
        pos    = "Üstünde ✅" if t3["price_above"] else "Altında ❌"
        bias   = "BULL" if t3["price_above"] else "BEAR"
        lines.append(f"  T3: `${t3['value']:,.4g}` {arrow}")
        lines.append(f"  Fiyat T3 {pos}")
        lines.append(f"  Bias: *{bias}*\n")
    else:
        lines.append("  Yeterli veri yok\n")

    # WaveTrend 4H
    lines.append("*🌊 WaveTrend 4H:*")
    if wt4:
        ob_str = " 🔴 OVERBOUGHT" if wt4["overbought"] else ""
        os_str = " 🟢 OVERSOLD"   if wt4["oversold"]   else ""
        lines.append(f"  WT1: `{wt4['wt1']}` | WT2: `{wt4['wt2']}`{ob_str}{os_str}")
        if wt4["buy_signal"]:  lines.append("  🟢 *YEŞİL DAİRE — LONG sinyali!*")
        if wt4["sell_signal"]: lines.append("  🔴 *KIRMIZI DAİRE — SHORT sinyali!*")
        lines.append("")

    # WaveTrend 1H (entry)
    lines.append("*🎯 WaveTrend 1H (Entry):*")
    if wt:
        ob_str = " 🔴 OVERBOUGHT" if wt["overbought"] else ""
        os_str = " 🟢 OVERSOLD"   if wt["oversold"]   else ""
        lines.append(f"  WT1: `{wt['wt1']}` | WT2: `{wt['wt2']}`{ob_str}{os_str}")
        if wt["buy_signal"]:
            lines.append("  🟢 *YEŞİL DAİRE — GİRİŞ ZAMANI!*")
        elif wt["sell_signal"]:
            lines.append("  🔴 *KIRMIZI DAİRE — GİRİŞ ZAMANI!*")
        elif wt["cross_up"]:
            lines.append("  🔵 Yukarı kesti (oversold değil — zayıf)")
        elif wt["cross_down"]:
            lines.append("  🔵 Aşağı kesti (overbought değil — zayıf)")
        elif wt["oversold"]:
            lines.append("  🟡 Oversold — kesme bekleniyor")
        elif wt["overbought"]:
            lines.append("  🟠 Overbought — kesme bekleniyor")
        else:
            lines.append("  ➡️ Nötr bölge")
    else:
        lines.append("  Yeterli veri yok")

    # Özet yorum
    lines.append("\n*💡 Özet:*")
    if t3 and wt:
        if t3["price_above"] and wt["buy_signal"]:
            lines.append("  ✅ *LONG FIRSATI* — T3 üstünde + WaveTrend yeşil daire")
        elif not t3["price_above"] and wt["sell_signal"]:
            lines.append("  ✅ *SHORT FIRSATI* — T3 altında + WaveTrend kırmızı daire")
        elif t3["price_above"] and wt["oversold"]:
            lines.append("  🟡 *LONG HAZIRLIK* — T3 üstünde + WaveTrend oversold (kesme bekle)")
        elif not t3["price_above"] and wt["overbought"]:
            lines.append("  🟠 *SHORT HAZIRLIK* — T3 altında + WaveTrend overbought (kesme bekle)")
        else:
            lines.append("  ⏳ Net sinyal yok — bekle")

    await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

# ══ ONAY/RED HANDLER ════════════════════════════════════════════
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data     = query.data
    action   = data.split('_')[0]
    order_id = '_'.join(data.split('_')[1:])

    if order_id not in pending_orders:
        await query.edit_message_text("⏱️ Bu işlem süresi doldu veya iptal edildi.")
        return

    order = pending_orders.pop(order_id)

    if action == 'confirm':
        await query.edit_message_text(f"⏳ İşlem açılıyor: {order['symbol']} {order['side'].upper()}...")
        result = place_order(
            symbol   = order['symbol'],
            side     = order['side'],
            size     = order['size'],
            sl_price = order['sl'],
            tp_price = order['tp'],
            leverage = order['leverage']
        )
        if result.get('ok'):
            liq = calc_liq_price(order['price'], order['leverage'], order['side'])
            msg = f"""
✅ *İŞLEM AÇILDI!*

📍 {order['symbol']} {order['side'].upper()}
💰 Margin: ${order['margin']}
⚡ Kaldıraç: {order['leverage']}x
💹 Giriş: ~${order['price']:,.2f}
⚰️ Likidasyon: ${liq:,.2f}
🆔 Order ID: `{result['ordId']}`
"""
            await query.edit_message_text(msg, parse_mode='Markdown')
        else:
            await query.edit_message_text(f"❌ *Hata:* {result.get('error', 'Bilinmeyen hata')}", parse_mode='Markdown')

    elif action == 'reject':
        await query.edit_message_text(f"❌ İşlem reddedildi: {order['symbol']} {order['side'].upper()}")

# ══════════════════════════════════════════════════════════════════════════════
#  SCANNER MOTORU — tkinter olmadan, arka planda çalışır
# ══════════════════════════════════════════════════════════════════════════════

SCAN_SETTINGS = {
    "scan_interval":   30,
    "min_volume_usd":  5000000,
    "min_score":       80,
    "min_rr":          2.5,
    "btc_filter":      True,
    "btc_drop_pct":    3.0,
    "use_bingx":       True,
    "show_mode":       "Tümü",
}

# Daha önce gönderilen sinyaller — tekrar gönderme önlemi
_sent_signals = {}
RESEND_HOURS  = 4

def _should_send(coin):
    key = f"{coin['exchange']}_{coin['symbol']}_{coin.get('signal','')}"
    now = time.time()
    if key in _sent_signals and (now - _sent_signals[key]) / 3600 < RESEND_HOURS:
        return False
    _sent_signals[key] = now
    return True

def _send_scan_signal(coin):
    """Tarama sinyalini Telegram'a gönder"""
    sig   = coin.get("signal","—")
    emoji = "🟢" if sig=="LONG" else "🔴"
    warn  = "⚠️ *OB YÖN UYARISI!*\n" if coin.get("ob_dir_warning") else ""

    wt_str = ""
    wt = coin.get("wt_1h")
    if wt:
        if wt.get("buy_signal"):    wt_str = "🟢 WaveTrend: YEŞİL DAİRE!\n"
        elif wt.get("sell_signal"): wt_str = "🔴 WaveTrend: KIRMIZI DAİRE!\n"
        elif wt.get("oversold"):    wt_str = "🟡 WaveTrend: Oversold\n"
        elif wt.get("overbought"):  wt_str = "🟠 WaveTrend: Overbought\n"

    t3_str = ""
    if coin.get("t3_4h"):
        t3_str = f"📈 T3: `${coin['t3_4h']:.5g}`\n"

    msg = (
        f"{emoji} *{sig} SİNYALİ* — `{coin['symbol']}`\n"
        f"{warn}"
        f"📊 Borsa: {coin['exchange']}\n"
        f"💰 Fiyat: `${coin['price']:,.5g}`\n"
        f"🎯 Skor: *{coin.get('score',0)}/100*  Güven: {coin.get('confidence','—')}\n"
        f"📦 OB: {coin.get('ob_type','—')}\n"
        f"🌍 Trend 1D: {coin.get('trend_1d','—')}  4H: {coin.get('trend_4h','—')}\n"
        f"{t3_str}"
        f"{wt_str}"
        f"💧 Likidite: {coin.get('liquidity','—')}\n"
        f"🔴 SL: `${coin.get('sl',0):.5g}`\n"
        f"🟡 TP1: `${coin.get('tp1',0):.5g}`\n"
        f"🟢 TP2: `${coin.get('tp2',0):.5g}`\n"
        f"⚖️ R/R: {coin.get('rr','—')}\n"
        f"₿ BTC: {coin.get('btc_status','—')}\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
    )
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown"
        }, timeout=8)
    except Exception as e:
        print(f"Sinyal Telegram hatası: {e}")

def _scanner_loop():
    """
    Arka planda sürekli çalışan tarama döngüsü.
    Telegram botundan bağımsız, ayrı thread'de koşar.
    """
    # Scanner modülündeki fonksiyonları kullan
    import importlib, sys, os

    # scanner_bot.py'yi import et
    try:
        import Scanner_bot as sc
        print("✅ Scanner modülü yüklendi")
    except ImportError:
        print("❌ scanner_bot.py bulunamadı — scanner çalışmayacak")
        return

    # Başlangıç bildirimi
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": (
                "🚀 *LevBot + Scanner Aktif!*\n\n"
                f"⏱ Tarama: her {SCAN_SETTINGS['scan_interval']} dakika\n"
                f"🎯 Min skor: {SCAN_SETTINGS['min_score']}/100\n"
                f"📊 Min R/R: 1:{SCAN_SETTINGS['min_rr']}\n"
                "🔬 SMC + Tilson T3 + VMC Cipher B\n\n"
                "Sinyal bulununca buraya atacağım! 👍"
            ),
            "parse_mode": "Markdown"
        }, timeout=8)
    except: pass

    while True:
        try:
            print(f"\n🔍 Tarama başlıyor... {datetime.now().strftime('%H:%M:%S')}")
            results = sc.scan_all(SCAN_SETTINGS)

            if results:
                print(f"✅ {len(results)} sinyal bulundu")
                for coin in results:
                    if _should_send(coin):
                        _send_scan_signal(coin)
                        time.sleep(1)
            else:
                print("⏳ Sinyal yok")

        except Exception as e:
            print(f"❌ Scanner hata: {e}")

        print(f"⏸ {SCAN_SETTINGS['scan_interval']} dk bekleniyor...")
        time.sleep(SCAN_SETTINGS["scan_interval"] * 60)


# ══ ANA FONKSİYON ═══════════════════════════════════════════════
def main():
    print("🤖 LevBot + Scanner başlatılıyor...")

    # Scanner'ı ayrı thread'de başlat — bot ile aynı anda çalışır
    scanner_thread = threading.Thread(target=_scanner_loop, daemon=True)
    scanner_thread.start()
    print("✅ Scanner thread başladı")

    # Telegram botunu başlat
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("bakiye",      bakiye))
    app.add_handler(CommandHandler("fiyat",       fiyat))
    app.add_handler(CommandHandler("pozisyonlar", pozisyonlar))
    app.add_handler(CommandHandler("short",       short_signal))
    app.add_handler(CommandHandler("long",        long_signal))
    app.add_handler(CommandHandler("kapat",       kapat))
    app.add_handler(CommandHandler("yardim",      yardim))
    app.add_handler(CommandHandler("trend",       trend))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("✅ LevBot aktif! Telegram'dan /start yaz.")
    import asyncio

    async def _run():
        # Önce eski Telegram session temizle
        print("🔄 Eski Telegram session temizleniyor...")
        try:
            requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true",
                timeout=5
            )
        except: pass
        print("⏳ 45 saniye bekleniyor...")
        await asyncio.sleep(45)
        print("🚀 Bağlanıyor...")
        while True:
            try:
                async with app:
                    await app.start()
                    await app.updater.start_polling(
                        allowed_updates=Update.ALL_TYPES,
                        drop_pending_updates=True
                    )
                    await asyncio.Event().wait()
            except Exception as e:
                err = str(e)
                if "Conflict" in err:
                    print(f"⚠️ Conflict — 90 saniye bekleniyor...")
                    await asyncio.sleep(90)
                else:
                    print(f"Hata: {e} — 30 saniye sonra tekrar...")
                    await asyncio.sleep(30)

    asyncio.run(_run())

if __name__ == '__main__':
    main()