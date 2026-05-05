"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              EXCHANGE LINKS — TradingView & Borsa Linkleri                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

📚 EĞİTİM NOTU — NEDEN LİNK SİSTEMİ?
══════════════════════════════════════
Tarayıcı sinyal üretir → Sen TradingView'da ONAYLARSIN → Borsada işlem YAPARSN.
Bu "signal → confirm → execute" akışını hızlandırmak için
tek tıkla doğru sayfayı açıyoruz.

webbrowser.open() Python standart kütüphanesi — tarayıcıda URL açar.
"""

import webbrowser
from typing import Dict


def get_links(symbol: str) -> Dict[str, str]:
    """
    Bir sembol için tüm linkleri döndürür.
    
    symbol: "BTCUSDT" formatında Binance sembolü
    """
    clean = symbol.replace("USDT", "")
    
    return {
        # TradingView — chart analizi için
        "tradingview": f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}.P",
        "tradingview_ideas": f"https://www.tradingview.com/symbols/{symbol}/ideas/",
        
        # Binance Futures — trade yapmak için
        "binance_futures": f"https://www.binance.com/en/futures/{symbol}",
        
        # OKX — alternatif borsa
        "okx": f"https://www.okx.com/trade-swap/{clean.lower()}-usdt-swap",
        
        # BingX
        "bingx": f"https://bingx.com/en/futures/detail/{symbol}/",
        
        # CoinGlass — likidasyonlar, OI, long/short ratio
        "coinglass": f"https://www.coinglass.com/tv/{clean}USDT",
        "coinglass_liq": f"https://www.coinglass.com/LiquidationData/{clean}",
        
        # FastBull chart
        "fastbull": f"https://www.fastbull.com/traders/chart",
        
        # CoinMarketCap — genel bilgi
        "coinmarketcap": f"https://coinmarketcap.com/currencies/{clean.lower()}/",
    }


def open_link(symbol: str, platform: str):
    """Belirli bir platformu tarayıcıda açar."""
    links = get_links(symbol)
    url = links.get(platform)
    if url:
        webbrowser.open(url)


def open_tradingview(symbol: str):
    """TradingView'da aç — en sık kullanılacak."""
    open_link(symbol, "tradingview")


def open_exchange(symbol: str, exchange: str = "binance_futures"):
    """Borsada aç."""
    open_link(symbol, exchange)
