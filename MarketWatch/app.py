import sys, os, time, threading, requests, webbrowser, json, atexit
from flask import Flask, jsonify, send_file, request as freq

flask_app = Flask(__name__)

NEWS_API_KEY    = 'f92d3244b3484720a3f60d322379f495'
CRYPTOPANIC_KEY = '31208d5ee60c0516af82c61331bbc8e0e904be3e'

alarms      = []
alarm_lock  = threading.Lock()
triggered_ids = set()
portfolio   = []
journal     = []
port_lock   = threading.Lock()

_futures_symbols = []
_symbols_ts = 0

# ── Persistent storage ──────────────────────────────────────────
# Exe yanındaki klasör veya kullanıcı dizini
if hasattr(sys, '_MEIPASS'):
    DATA_DIR = os.path.join(os.path.dirname(sys.executable), 'MarketWatchData')
else:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MarketWatchData')
os.makedirs(DATA_DIR, exist_ok=True)
ALARMS_FILE    = os.path.join(DATA_DIR, 'alarms.json')
PORTFOLIO_FILE = os.path.join(DATA_DIR, 'portfolio.json')
JOURNAL_FILE   = os.path.join(DATA_DIR, 'journal.json')

def load_data():
    global alarms, portfolio, journal
    for path, target in [(ALARMS_FILE, 'alarms'), (PORTFOLIO_FILE, 'portfolio'), (JOURNAL_FILE, 'journal')]:
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if target == 'alarms':
                        alarms = data
                        # Reset triggered state on load
                        for a in alarms:
                            a['triggered'] = False
                    elif target == 'portfolio':
                        portfolio = data
                    elif target == 'journal':
                        journal = data
        except Exception as e:
            print(f'Load error {path}: {e}')

def save_alarms():
    try:
        with alarm_lock:
            data = list(alarms)
        with open(ALARMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'Save alarms error: {e}')

def save_portfolio():
    try:
        with port_lock:
            port_data = list(portfolio)
            jour_data = list(journal)
        with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f:
            json.dump(port_data, f, ensure_ascii=False, indent=2)
        with open(JOURNAL_FILE, 'w', encoding='utf-8') as f:
            json.dump(jour_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'Save portfolio error: {e}')

def save_all():
    save_alarms()
    save_portfolio()

# Load on startup
load_data()
# Save on exit
atexit.register(save_all)
# Auto-save every 60 seconds
def auto_save():
    while True:
        time.sleep(60)
        save_all()
threading.Thread(target=auto_save, daemon=True).start()

def resource_path(f):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, f)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), f)

@flask_app.route('/')
def index():
    return send_file(resource_path('index.html'))

@flask_app.route('/api/open')
def open_url():
    url = freq.args.get('url', '')
    if url and url.startswith('http'):
        webbrowser.open(url)
        return jsonify({'ok': True})
    return jsonify({'ok': False}), 400

# ── Futures symbols ─────────────────────────────────────────────
@flask_app.route('/api/futures/symbols')
def futures_symbols():
    global _futures_symbols, _symbols_ts
    now = time.time()
    if _futures_symbols and (now - _symbols_ts) < 3600:
        return jsonify(_futures_symbols)
    try:
        r = requests.get('https://fapi.binance.com/fapi/v1/exchangeInfo', timeout=10)
        syms = []
        for s in r.json().get('symbols', []):
            if s.get('status') == 'TRADING' and s.get('contractType') == 'PERPETUAL':
                syms.append({'symbol': s['symbol'], 'base': s['baseAsset'], 'quote': s['quoteAsset']})
        syms.sort(key=lambda x: x['base'])
        _futures_symbols = syms
        _symbols_ts = now
        return jsonify(syms)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── Futures price batch ─────────────────────────────────────────
@flask_app.route('/api/portfolio/prices', methods=['POST'])
def portfolio_prices():
    symbols = freq.json.get('symbols', [])
    result = {}
    for sym in set(symbols):
        try:
            r = requests.get(f'https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={sym}', timeout=6)
            if r.status_code == 200:
                d = r.json()
                result[sym] = {'price': float(d.get('lastPrice', 0)), 'change24h': float(d.get('priceChangePercent', 0))}
            else:
                r2 = requests.get(f'https://api.binance.com/api/v3/ticker/24hr?symbol={sym}', timeout=6)
                if r2.status_code == 200:
                    d2 = r2.json()
                    result[sym] = {'price': float(d2.get('lastPrice', 0)), 'change24h': float(d2.get('priceChangePercent', 0))}
        except:
            pass
    return jsonify(result)

# ── Recent trades check (fat finger / FOMO guard) ───────────────
@flask_app.route('/api/portfolio/recent_check')
def recent_check():
    symbol = freq.args.get('symbol', '').upper()
    minutes = int(req.args.get('minutes', 5)) if False else 5
    now = time.time() * 1000
    with port_lock:
        recent = [p for p in portfolio if p['symbol'] == symbol and (now - p['id']) < 5 * 60 * 1000]
    return jsonify({'found': len(recent) > 0, 'count': len(recent)})

# ── Portfolio CRUD ──────────────────────────────────────────────
@flask_app.route('/api/portfolio', methods=['GET'])
def get_portfolio():
    with port_lock:
        return jsonify(portfolio)

@flask_app.route('/api/portfolio', methods=['POST'])
def add_position():
    data = freq.json
    with port_lock:
        pos_id = int(time.time() * 1000)
        margin = float(data.get('margin', 0))
        lev    = float(data.get('leverage', 1))
        entry  = float(data.get('entry', 0))
        # Calculate coin qty from margin
        coin_qty = (margin * lev / entry) if entry > 0 else 0
        # Estimated liquidation price
        direction = data.get('direction', 'long')
        if lev > 0:
            liq_price = entry * (1 - 1/lev) if direction == 'long' else entry * (1 + 1/lev)
        else:
            liq_price = 0
        pos = {
            'id':           pos_id,
            'exchange':     data.get('exchange', 'Binance'),
            'symbol':       data.get('symbol', '').upper(),
            'base':         data.get('base', '').upper(),
            'direction':    direction,
            'margin':       margin,
            'leverage':     lev,
            'coin_qty':     round(coin_qty, 8),
            'entry':        entry,
            'liq_price':    round(liq_price, 6),
            'entry_date':   data.get('entry_date', ''),
            'reason':       data.get('reason', ''),
            'reason_custom':data.get('reason_custom', ''),
            'notes':        data.get('notes', ''),
            'checklist':    data.get('checklist', {}),
        }
        portfolio.append(pos)
    save_portfolio()
    return jsonify({'ok': True, 'id': pos_id})

@flask_app.route('/api/portfolio/<int:pos_id>', methods=['DELETE'])
def delete_position(pos_id):
    with port_lock:
        global portfolio
        portfolio = [p for p in portfolio if p['id'] != pos_id]
    save_portfolio()
    return jsonify({'ok': True})

@flask_app.route('/api/portfolio/<int:pos_id>', methods=['PATCH'])
def edit_position(pos_id):
    data = freq.json
    with port_lock:
        for p in portfolio:
            if p['id'] == pos_id:
                if 'margin'   in data: p['margin']   = float(data['margin'])
                if 'entry'    in data: p['entry']     = float(data['entry'])
                if 'leverage' in data:
                    p['leverage'] = float(data['leverage'])
                    # Recalculate
                    if p['entry'] > 0:
                        p['coin_qty'] = round(p['margin'] * p['leverage'] / p['entry'], 8)
                        lev = p['leverage']
                        p['liq_price'] = round(p['entry']*(1-1/lev) if p['direction']=='long' else p['entry']*(1+1/lev), 6)
                if 'reason'   in data: p['reason']   = data['reason']
                if 'notes'    in data: p['notes']     = data['notes']
                break
    save_portfolio()
    return jsonify({'ok': True})

@flask_app.route('/api/portfolio/<int:pos_id>/close', methods=['POST'])
def close_position(pos_id):
    data = freq.json
    exit_price   = float(data.get('exit_price', 0))
    exit_reason  = data.get('exit_reason', '')
    exit_notes   = data.get('exit_notes', '')
    exit_date    = data.get('exit_date', '')
    is_liq       = bool(data.get('is_liquidation', False))
    mistakes     = data.get('mistakes', [])

    with port_lock:
        global portfolio
        pos = next((p for p in portfolio if p['id'] == pos_id), None)
        if not pos:
            return jsonify({'error': 'not found'}), 404

        margin    = pos['margin']
        lev       = pos['leverage']
        entry     = pos['entry']
        direction = pos['direction']
        coin_qty  = pos['coin_qty']

        # PnL = margin * leverage * price_change_pct * direction_sign
        if entry > 0:
            pct = (exit_price - entry) / entry
            sign = 1 if direction == 'long' else -1
            realized_pnl = margin * lev * pct * sign
        else:
            realized_pnl = 0

        pnl_pct = (realized_pnl / margin * 100) if margin > 0 else 0

        journal_entry = {
            **pos,
            'close_id':      int(time.time() * 1000),
            'exit_price':    exit_price,
            'exit_date':     exit_date,
            'exit_reason':   exit_reason,
            'exit_notes':    exit_notes,
            'is_liquidation': is_liq,
            'mistakes':      mistakes,
            'realized_pnl':  round(realized_pnl, 4),
            'pnl_pct':       round(pnl_pct, 2),
        }
        journal.append(journal_entry)
        portfolio = [p for p in portfolio if p['id'] != pos_id]

    save_portfolio()
    return jsonify({'ok': True, 'pnl': realized_pnl, 'pnl_pct': pnl_pct})

# ── Journal ─────────────────────────────────────────────────────
@flask_app.route('/api/journal', methods=['GET'])
def get_journal():
    with port_lock:
        return jsonify(list(reversed(journal)))

@flask_app.route('/api/journal/<int:close_id>', methods=['DELETE'])
def delete_journal(close_id):
    with port_lock:
        global journal
        journal = [j for j in journal if j['close_id'] != close_id]
    save_portfolio()
    return jsonify({'ok': True})

# ── Standard market endpoints ────────────────────────────────────
@flask_app.route('/api/crypto')
def crypto():
    try:
        r = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,ripple&vs_currencies=usd&include_24hr_change=true', timeout=10)
        data = r.json()
        prices = {'btc': data.get('bitcoin',{}).get('usd',0), 'eth': data.get('ethereum',{}).get('usd',0), 'xrp': data.get('ripple',{}).get('usd',0)}
        check_price_alarms(prices)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/api/chart/<symbol>')
def chart(symbol):
    sym_map = {'btc':'BTCUSDT','eth':'ETHUSDT','xrp':'XRPUSDT'}
    bs = sym_map.get(symbol.lower(), symbol.upper())
    try:
        r = requests.get(f'https://api.binance.com/api/v3/klines?symbol={bs}&interval=4h&limit=60', timeout=10)
        return jsonify([{'t':int(c[0]//1000),'o':float(c[1]),'h':float(c[2]),'l':float(c[3]),'c':float(c[4]),'v':float(c[5])} for c in r.json()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/api/feargreed')
def feargreed():
    try:
        r = requests.get('https://api.alternative.me/fng/?limit=1', timeout=10)
        d = r.json()['data'][0]
        val = int(d['value'])
        check_fg_alarms(val)
        return jsonify({'value': val, 'label': d['value_classification']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/api/funding')
def funding():
    try:
        r = requests.get('https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT', timeout=10)
        rate = float(r.json().get('lastFundingRate', 0)) * 100
        return jsonify({'rate': round(rate, 4)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/api/dominance')
def dominance():
    try:
        r = requests.get('https://api.coingecko.com/api/v3/global', timeout=10)
        d = r.json()['data']
        return jsonify({'btc_dominance': round(d['market_cap_percentage']['btc'], 2), 'total_mcap': d['total_market_cap']['usd']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/api/market')
def market():
    syms = {'^GSPC':('sp500','S&P 500'),'GC=F':('gold','Altin (XAU)'),'SI=F':('silver','Gumus (XAG)'),'CL=F':('oil','Ham Petrol'),'DX-Y.NYB':('dxy','DXY')}
    result = {}
    hdrs = {'User-Agent': 'Mozilla/5.0'}
    for sym, (key, name) in syms.items():
        try:
            r = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2d', headers=hdrs, timeout=10)
            meta = r.json()['chart']['result'][0]['meta']
            price = float(meta.get('regularMarketPrice', 0))
            prev  = float(meta.get('chartPreviousClose', price))
            result[key] = {'name': name, 'price': round(price, 3), 'prev': round(prev, 3)}
        except:
            result[key] = {'name': name, 'price': 0, 'prev': 0}
    check_market_alarms(result)
    return jsonify(result)

@flask_app.route('/api/news')
def news():
    try:
        r = requests.get('https://newsapi.org/v2/everything', params={
            'q': '("Federal Reserve" OR "Fed rate" OR "interest rate" OR "rate cut" OR "rate hike" OR "inflation" OR "CPI" OR "NFP" OR "GDP" OR "S&P 500" OR "stock market" OR "Wall Street" OR "recession" OR "Treasury" OR "bond yield" OR "gold price" OR "oil price" OR "dollar index" OR "tariff" OR "trade war")',
            'language': 'en', 'sortBy': 'publishedAt', 'pageSize': 30, 'apiKey': NEWS_API_KEY
        }, timeout=12)
        articles = r.json().get('articles', [])
        result = []
        BLACKLIST = ['entertainment','gossip','sport','celebrity','music','film','movie','lifestyle','fashion','food','travel','health','fitness','gaming']
        MARKET_WORDS = ['market','stock','fed','rate','inflation','gold','oil','dollar','economy','gdp','cpi','nfp','bond','yield','recession','treasury','wall street','nasdaq','s&p','dow','equity','trade','tariff','silver','commodity']
        for a in articles:
            title = (a.get('title') or '').strip()
            desc  = (a.get('description') or '').strip()
            src   = (a.get('source',{}).get('name') or '').strip()
            pub   = a.get('publishedAt','') or ''
            url   = a.get('url','') or ''
            if '[Removed]' in title or not title: continue
            if any(b in src.lower() for b in BLACKLIST): continue
            if not any(w in (title+' '+desc).lower() for w in MARKET_WORDS): continue
            score = impact_score(title + ' ' + desc)
            if score['score'] < 2: continue
            result.append({'title': title[:130], 'source': src, 'published': pub, 'url': url, 'score': score['score'], 'level': score['level'], 'tags': score['tags'], 'direction': score['direction']})
        result.sort(key=lambda x: x['score'], reverse=True)
        return jsonify(result[:15])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/api/cryptonews')
def cryptonews():
    try:
        r = requests.get('https://cryptopanic.com/api/v1/posts/', params={'auth_token': CRYPTOPANIC_KEY, 'public': 'true', 'kind': 'news', 'filter': 'hot'}, timeout=12)
        posts = r.json().get('results', [])
        result = []
        for p in posts[:20]:
            title = (p.get('title') or '').strip()
            src   = (p.get('source',{}).get('title') or '').strip()
            pub   = p.get('published_at','') or ''
            url   = p.get('url','') or ''
            if not title: continue
            votes = p.get('votes',{}) or {}
            panic = int(votes.get('negative',0) or 0)
            bull  = int(votes.get('positive',0) or 0)
            score = impact_score(title)
            boosted = min(10, score['score'] + (panic + bull) // 5)
            if boosted < 1: continue
            result.append({'title': title[:130], 'source': src, 'published': pub, 'url': url, 'score': boosted, 'level': score_to_level(boosted), 'tags': score['tags'], 'direction': score['direction'], 'bull': bull, 'bear': panic})
        result.sort(key=lambda x: x['score'], reverse=True)
        return jsonify(result[:12])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── Alarms ──────────────────────────────────────────────────────
@flask_app.route('/api/alarms', methods=['GET'])
def get_alarms():
    with alarm_lock:
        return jsonify(alarms)

@flask_app.route('/api/alarms', methods=['POST'])
def add_alarm():
    data = freq.json
    with alarm_lock:
        alarm_id = int(time.time() * 1000)
        alarms.append({'id': alarm_id, 'type': data.get('type'), 'asset': data.get('asset',''), 'condition': data.get('condition'), 'value': float(data.get('value', 0)), 'label': data.get('label',''), 'active': True, 'triggered': False})
    save_alarms()
    return jsonify({'ok': True, 'id': alarm_id})

@flask_app.route('/api/alarms/<int:alarm_id>', methods=['DELETE'])
def delete_alarm(alarm_id):
    with alarm_lock:
        global alarms
        alarms = [a for a in alarms if a['id'] != alarm_id]
        triggered_ids.discard(alarm_id)
    save_alarms()
    return jsonify({'ok': True})

@flask_app.route('/api/alarms/<int:alarm_id>/toggle', methods=['POST'])
def toggle_alarm(alarm_id):
    with alarm_lock:
        for a in alarms:
            if a['id'] == alarm_id:
                a['active'] = not a['active']
                if a['active']: triggered_ids.discard(alarm_id)
                break
    save_alarms()
    return jsonify({'ok': True})

@flask_app.route('/api/alarms/triggered', methods=['GET'])
def get_triggered():
    with alarm_lock:
        fired = [a for a in alarms if a.get('triggered') and a['id'] not in triggered_ids]
        for a in fired: triggered_ids.add(a['id'])
        return jsonify(fired)

@flask_app.route('/api/alarms/<int:alarm_id>/reset', methods=['POST'])
def reset_alarm(alarm_id):
    with alarm_lock:
        for a in alarms:
            if a['id'] == alarm_id:
                a['triggered'] = False
                triggered_ids.discard(alarm_id)
                break
    return jsonify({'ok': True})

def check_price_alarms(prices):
    with alarm_lock:
        for a in alarms:
            if not a['active'] or a['triggered'] or a['type'] != 'price': continue
            current = prices.get(a['asset'], 0)
            if a['condition'] == 'above' and current >= a['value']: a['triggered'] = True
            elif a['condition'] == 'below' and current <= a['value']: a['triggered'] = True

def check_market_alarms(market_data):
    with alarm_lock:
        for a in alarms:
            if not a['active'] or a['triggered'] or a['type'] != 'price': continue
            current = market_data.get(a['asset'], {}).get('price', 0)
            if current == 0: continue
            if a['condition'] == 'above' and current >= a['value']: a['triggered'] = True
            elif a['condition'] == 'below' and current <= a['value']: a['triggered'] = True

def check_fg_alarms(value):
    with alarm_lock:
        for a in alarms:
            if not a['active'] or a['triggered'] or a['type'] != 'fg': continue
            if a['condition'] == 'above' and value >= a['value']: a['triggered'] = True
            elif a['condition'] == 'below' and value <= a['value']: a['triggered'] = True

HIGH_BEARISH=['rate hike','hawkish','tightening','recession','crash','collapse','default','bankruptcy','ban','crackdown','war','sanctions','selloff','panic','dump','liquidation','tariff','trade war']
HIGH_BULLISH=['rate cut','dovish','stimulus','easing','bailout','ath','all-time high','surge','rally','breakout','approval','etf approved','institutional','adoption','upgrade','beat expectations','strong jobs','gdp growth','soft landing']
MED_BEARISH=['warning','concern','risk','uncertainty','bearish','decline','drop','fall','loss','weak','miss','downgrade','volatility','regulation','sec','lawsuit','hack','exploit']
MED_BULLISH=['recovery','growth','positive','bullish','gain','rise','increase','accumulation','buy','support','demand','investment','launch','integration']
LOW_WORDS=['fed','fomc','cpi','nfp','gdp','ecb','boj','inflation','jobs','bitcoin','crypto','market','stocks','gold','oil','dollar','tariff','trade']

def impact_score(text):
    t=text.lower(); score=0; tags=[]; bull_pts=0; bear_pts=0
    for w in HIGH_BEARISH:
        if w in t: bear_pts+=4; tags.append(w.upper())
    for w in HIGH_BULLISH:
        if w in t: bull_pts+=4; tags.append(w.upper())
    for w in MED_BEARISH:
        if w in t: bear_pts+=2
    for w in MED_BULLISH:
        if w in t: bull_pts+=2
    for w in LOW_WORDS:
        if w in t: score+=1
    score+=max(bull_pts,bear_pts); score=min(10,score)
    direction='bullish' if bull_pts>bear_pts else 'bearish' if bear_pts>bull_pts else 'neutral'
    return{'score':score,'level':score_to_level(score),'tags':tags[:3],'direction':direction}

def score_to_level(s):
    if s>=7: return 'HIGH'
    if s>=4: return 'MED'
    return 'LOW'

# ── PyQt5 — resizable window ────────────────────────────────────
from PyQt5.QtWidgets import QApplication, QMainWindow, QDesktopWidget
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, QSize

PORT = 5678

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Global Market Watch v10')
        self.resize(520, 900)
        self.setMinimumSize(QSize(440, 600))
        v = QWebEngineView()
        v.setUrl(QUrl(f'http://127.0.0.1:{PORT}'))
        self.setCentralWidget(v)
        try:
            sg = QDesktopWidget().screenGeometry()
            self.move(sg.width() - 540, sg.height() - 940)
        except:
            pass

if __name__ == '__main__':
    t = threading.Thread(target=lambda: flask_app.run('127.0.0.1', PORT, debug=False, use_reloader=False), daemon=True)
    t.start()
    time.sleep(0.9)
    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec_())
