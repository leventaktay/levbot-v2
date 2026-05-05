import time
import hmac
import hashlib
import base64
import json
import requests
import threading
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ══ AYARLAR — SADECE SEN DEĞİŞTİR ══════════════════════════════
import os

OKX_API_KEY      = os.environ.get("OKX_API_KEY",      "")
OKX_SECRET       = os.environ.get("OKX_SECRET",       "")
OKX_PASSPHRASE   = os.environ.get("OKX_PASSPHRASE",   "")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

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
    ts = datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
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

*İşlem Komutları:*
/short [sembol] [margin] [kaldıraç] [sl] [tp]
/long [sembol] [margin] [kaldıraç] [sl] [tp]
/kapat [sembol] [side]

*Örnekler:*
`/short BTC-USDT-SWAP 50 10 75000 63000`
`/long ETH-USDT-SWAP 30 8 2800 3500`
`/short XAU-USDT-SWAP 50 5 3100 2800`
`/kapat BTC-USDT-SWAP short`

*Desteklenen Semboller:*
BTC, ETH, SOL, XRP, DOGE, LINK
XAU (Altın), XAG (Gümüş), USOIL (Petrol)

*Kaldıraç Limitleri:*
BTC/ETH: max 15x
Majör altcoinler: max 10x
Emtia: max 5x
"""
    await update.message.reply_text(msg, parse_mode='Markdown')

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

# ══ ANA FONKSİYON ═══════════════════════════════════════════════
def main():
    print("🤖 LevBot başlatılıyor...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("bakiye",     bakiye))
    app.add_handler(CommandHandler("fiyat",      fiyat))
    app.add_handler(CommandHandler("pozisyonlar",pozisyonlar))
    app.add_handler(CommandHandler("short",      short_signal))
    app.add_handler(CommandHandler("long",       long_signal))
    app.add_handler(CommandHandler("kapat",      kapat))
    app.add_handler(CommandHandler("yardim",     yardim))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("✅ LevBot aktif! Telegram'dan /start yaz.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
