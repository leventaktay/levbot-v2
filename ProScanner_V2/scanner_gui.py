"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    PRO CRYPTO SCANNER v1.0 — GUI                           ║
║              TradingView Kalitesinde Token Tarama Arayüzü                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

📚 EĞİTİM NOTU — PyQt5 GUI MİMARİSİ:
══════════════════════════════════════
PyQt5'te her şey "widget" (bileşen) tabanlıdır.
Ana pencere (QMainWindow) içine layout'larla widget yerleştirirsin.

Temel kavramlar:
  QMainWindow  → Ana pencere (menü bar, status bar içerir)
  QWidget      → Temel bileşen (her şey bundan türer)
  QVBoxLayout  → Dikey dizilim (üstten alta)
  QHBoxLayout  → Yatay dizilim (soldan sağa)
  QTableWidget → Tablo (satır/sütun)
  QThread      → Arka plan işi (API çağrıları UI'ı dondurmaz)
  Signal/Slot  → Qt'nin olay sistemi (bir şey olunca bir şey yap)

Neden QThread?
  API'den veri çekerken ana thread (UI thread) meşgul olursa
  pencere donar, "yanıt vermiyor" der. QThread ile veri çekme
  işini arka plana atarız, UI akıcı kalır.
"""

import sys
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QComboBox,
    QProgressBar, QHeaderView, QAbstractItemView, QFrame, QSpinBox,
    QTextEdit, QSplitter, QGroupBox, QCheckBox, QTabWidget,
    QStyleFactory, QMenu, QAction
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QSize
)
from PyQt5.QtGui import (
    QColor, QFont, QBrush, QPalette, QIcon, QLinearGradient
)

# Yeni modüller
try:
    from candle_patterns import scan_candle_patterns
    from chart_patterns import scan_chart_patterns
    from sessions import get_current_session, get_session_recommendation, analyze_session_volume
    from links import get_links, open_tradingview, open_exchange, open_link
    HAS_EXTENSIONS = True
except ImportError:
    HAS_EXTENSIONS = False
    print("⚠ Ek modüller bulunamadı (candle_patterns, chart_patterns, sessions, links)")

# Scanner motorunu import et — aynı klasörde olmalı
from pro_scanner import (
    ScannerConfig, get_futures_symbols, get_klines,
    score_indicators, calc_ema, calc_rsi, calc_macd,
    calc_bollinger_bands, calc_supertrend, calc_wavetrend,
    calc_adx, calc_ichimoku, calc_t3, calc_atr, calc_mfi, calc_obv,
    TF_WEIGHTS
)


# ═══════════════════════════════════════════════════════════════════════════
# RENK PALETİ
# ═══════════════════════════════════════════════════════════════════════════
"""
📚 EĞİTİM NOTU — RENK SİSTEMİ:
Profesyonel trading arayüzlerinde renkler bilgi taşır.
TradingView, Binance, OKX hepsi benzer renk kodlaması kullanır:
  Yeşil tonları → Yükseliş/Pozitif/Bullish
  Kırmızı tonları → Düşüş/Negatif/Bearish
  Sarı/Turuncu → Uyarı/Dikkat
  Gri → Nötr/Veri yok

Koyu tema (dark mode) trader'lar için standarttır çünkü:
  1. Göz yorgunluğu azalır (saatlerce ekrana bakarsın)
  2. Renkli veriler koyu zeminde daha belirgin
  3. Profesyonel görünüm
"""

class Colors:
    # Ana arkaplan
    BG_DARK = "#0a0e17"          # En koyu — ana zemin
    BG_PANEL = "#111827"         # Panel arkaplanı
    BG_CARD = "#1a2235"          # Kart/satır arkaplanı
    BG_HOVER = "#1f2b3d"         # Üzerine gelince

    # Metin
    TEXT_PRIMARY = "#e2e8f0"     # Ana metin
    TEXT_SECONDARY = "#94a3b8"   # İkincil metin
    TEXT_MUTED = "#64748b"       # Soluk metin

    # Vurgular
    GREEN_BRIGHT = "#22c55e"     # Güçlü bullish
    GREEN_DIM = "#16a34a"        # Normal bullish
    GREEN_BG = "#052e16"         # Yeşil arkaplan
    RED_BRIGHT = "#ef4444"       # Güçlü bearish
    RED_DIM = "#dc2626"          # Normal bearish
    RED_BG = "#2d0a0a"           # Kırmızı arkaplan
    YELLOW = "#eab308"           # Uyarı
    YELLOW_BG = "#2d2305"        # Sarı arkaplan
    BLUE = "#3b82f6"             # Bilgi/Vurgu
    BLUE_BG = "#0c1a3d"         # Mavi arkaplan
    PURPLE = "#a855f7"           # Özel vurgu
    ORANGE = "#f97316"           # Dikkat

    # Border
    BORDER = "#1e293b"
    BORDER_ACTIVE = "#3b82f6"


def score_color(score: float) -> str:
    """Skora göre renk döndürür."""
    if score >= 80: return Colors.GREEN_BRIGHT
    if score >= 70: return Colors.GREEN_DIM
    if score >= 60: return "#6ee7b7"  # Açık yeşil
    if score >= 40: return Colors.TEXT_SECONDARY
    if score >= 30: return "#fca5a5"  # Açık kırmızı
    if score >= 20: return Colors.RED_DIM
    return Colors.RED_BRIGHT


def score_bg(score: float) -> str:
    """Skora göre arkaplan rengi döndürür."""
    if score >= 70: return Colors.GREEN_BG
    if score >= 55: return "transparent"
    if score <= 35: return Colors.RED_BG
    return "transparent"


def change_color(pct: float) -> str:
    """Yüzde değişime göre renk."""
    if pct > 5: return Colors.GREEN_BRIGHT
    if pct > 0: return Colors.GREEN_DIM
    if pct < -5: return Colors.RED_BRIGHT
    if pct < 0: return Colors.RED_DIM
    return Colors.TEXT_SECONDARY


# ═══════════════════════════════════════════════════════════════════════════
# TARAMA THREAD'İ
# ═══════════════════════════════════════════════════════════════════════════
"""
📚 EĞİTİM NOTU — QThread ve Signal/Slot:
═════════════════════════════════════════
Qt'de UI güncellemeleri SADECE ana thread'den yapılabilir.
Arka plan thread'inden direkt widget güncellersen CRASH olur.

Çözüm: Signal/Slot mekanizması
  1. Arka plan thread sinyaller gönderir (pyqtSignal)
  2. Ana thread bu sinyalleri yakalar (slot fonksiyonları)
  3. Slot fonksiyonu UI'ı güvenle günceller

Örnek akış:
  ScanThread → progress_signal.emit(50, "BTC taranıyor")
       ↓
  MainWindow → on_progress(50, "BTC taranıyor")  → ProgressBar güncelle
"""

class ScanThread(QThread):
    """Arka planda coin taraması yapan thread."""

    # Sinyaller — thread'den ana pencereye mesaj gönderir
    progress_signal = pyqtSignal(int, str)       # (yüzde, mesaj)
    coin_result_signal = pyqtSignal(dict)         # Tek coin sonucu
    finished_signal = pyqtSignal(list)             # Tüm sonuçlar
    error_signal = pyqtSignal(str)                 # Hata mesajı

    def __init__(self, config: ScannerConfig):
        super().__init__()
        self.config = config
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        """Thread'in ana çalışma fonksiyonu."""
        try:
            cfg = self.config
            self.progress_signal.emit(0, "Sembol listesi alınıyor...")

            symbols = get_futures_symbols(cfg.min_volume_usdt)
            if not symbols:
                self.error_signal.emit("Sembol listesi alınamadı! İnternet bağlantınızı kontrol edin.")
                return

            symbols = symbols[:cfg.max_coins]
            self.progress_signal.emit(5, f"{len(symbols)} coin bulundu, tarama başlıyor...")

            results = []
            total = len(symbols)

            for i, sym_data in enumerate(symbols):
                if self._is_cancelled:
                    self.progress_signal.emit(0, "Tarama iptal edildi.")
                    return

                symbol = sym_data["symbol"]
                pct = int(5 + (i / total) * 90)
                self.progress_signal.emit(pct, f"[{i+1}/{total}] {symbol} taranıyor...")

                try:
                    result = self._analyze_coin(sym_data, cfg)
                    if result:
                        results.append(result)
                        self.coin_result_signal.emit(result)
                except Exception as e:
                    pass  # Sessizce atla, diğer coinlere devam et

                time.sleep(0.02)

            self.progress_signal.emit(100, f"Tarama tamamlandı! {len(results)} sonuç.")
            self.finished_signal.emit(results)

        except Exception as e:
            self.error_signal.emit(f"Tarama hatası: {str(e)}")

    def _analyze_coin(self, symbol_data: Dict, cfg: ScannerConfig) -> Optional[Dict]:
        """Tek coin analizi — pattern tespiti dahil."""
        symbol = symbol_data["symbol"]
        results = {}
        dataframes = {}  # DataFrame'leri sakla, pattern tespitinde yeniden kullanacağız

        for tf in cfg.timeframes:
            df = get_klines(symbol, tf, limit=200)
            if df is None or len(df) < 100:
                return None
            result = score_indicators(df, cfg)
            results[tf] = result
            dataframes[tf] = df  # Sakla!
            time.sleep(0.03)

        if not results:
            return None

        mtf_score = 0
        for tf, weight in TF_WEIGHTS.items():
            if tf in results:
                mtf_score += results[tf]["total_score"] * weight

        directions = [r["direction"] for r in results.values()]
        unique_dirs = set(directions)
        if len(unique_dirs) > 1 and "NEUTRAL" not in unique_dirs:
            mtf_score *= 0.7

        primary_tf = cfg.timeframes[0]
        primary_dir = results[primary_tf]["direction"]

        coin_result = {
            "symbol": symbol,
            "clean_name": symbol.replace("USDT", ""),
            "price": symbol_data["last_price"],
            "volume_24h": symbol_data["volume"],
            "change_24h": symbol_data["price_change_pct"],
            "mtf_score": round(mtf_score, 1),
            "direction": primary_dir,
            "tf_results": results,
            "alignment": len(unique_dirs) == 1,
        }

        # Candle & Chart pattern tespiti — zaten çekilmiş verileri kullan
        if HAS_EXTENSIONS:
            all_candle = {"patterns": [], "bullish_count": 0, "bearish_count": 0, "score": 50}
            all_chart = {"patterns": [], "score": 50}

            for tf, tf_df in dataframes.items():
                try:
                    if len(tf_df) < 50:
                        continue

                    cp = scan_candle_patterns(tf_df, lookback=3)
                    for p in cp["patterns"]:
                        p["timeframe"] = tf
                    all_candle["patterns"].extend(cp["patterns"])
                    all_candle["bullish_count"] += cp["bullish_count"]
                    all_candle["bearish_count"] += cp["bearish_count"]

                    chp = scan_chart_patterns(tf_df)
                    for p in chp["patterns"]:
                        p["timeframe"] = tf
                    all_chart["patterns"].extend(chp["patterns"])
                except Exception:
                    continue

            if all_candle["patterns"]:
                bull_s = sum(p["strength"] for p in all_candle["patterns"] if p["direction"] == "BULLISH")
                bear_s = sum(p["strength"] for p in all_candle["patterns"] if p["direction"] == "BEARISH")
                total_s = bull_s + bear_s
                all_candle["score"] = round(50 + (bull_s - bear_s) / max(total_s, 1) * 40, 1)

            if all_chart["patterns"]:
                bull_c = sum(p["strength"] for p in all_chart["patterns"] if p["direction"] == "BULLISH")
                bear_c = sum(p["strength"] for p in all_chart["patterns"] if p["direction"] == "BEARISH")
                total_c = bull_c + bear_c
                all_chart["score"] = round(50 + (bull_c - bear_c) / max(total_c, 1) * 35, 1)

            seen = set()
            unique_chart = []
            for p in all_chart["patterns"]:
                key = p["name"]
                if key not in seen:
                    seen.add(key)
                    unique_chart.append(p)
            all_chart["patterns"] = unique_chart

            coin_result["candle_patterns"] = all_candle
            coin_result["chart_patterns"] = all_chart

        return coin_result


# ═══════════════════════════════════════════════════════════════════════════
# DETAY PANELİ
# ═══════════════════════════════════════════════════════════════════════════

class DetailPanel(QFrame):
    """Seçilen coin'in detaylı indikatör bilgilerini gösteren panel."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_PANEL};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # Başlık
        self.title_label = QLabel("Coin seçin →")
        self.title_label.setFont(QFont("Consolas", 14, QFont.Bold))
        self.title_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; border: none;")
        layout.addWidget(self.title_label)

        # Skor çubuğu
        self.score_bar = QProgressBar()
        self.score_bar.setRange(0, 100)
        self.score_bar.setTextVisible(True)
        self.score_bar.setFixedHeight(24)
        self.score_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Colors.BG_DARK};
                border: 1px solid {Colors.BORDER};
                border-radius: 4px;
                text-align: center;
                color: {Colors.TEXT_PRIMARY};
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background-color: {Colors.GREEN_DIM};
                border-radius: 3px;
            }}
        """)
        layout.addWidget(self.score_bar)

        # İndikatör detayları
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setFont(QFont("Consolas", 10))
        self.details_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Colors.BG_DARK};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 4px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.details_text)

    def update_detail(self, coin_data: dict):
        """Seçilen coin'in detaylarını gösterir."""
        name = coin_data["clean_name"]
        score = coin_data["mtf_score"]
        direction = coin_data["direction"]
        emoji = "🟢" if direction == "LONG" else "🔴" if direction == "SHORT" else "⚪"

        self.title_label.setText(f"{emoji}  {name}  —  {direction}  ({score:.1f})")

        # Skor çubuğu
        self.score_bar.setValue(int(score))
        if score >= 70:
            chunk_color = Colors.GREEN_DIM
        elif score <= 35:
            chunk_color = Colors.RED_DIM
        else:
            chunk_color = Colors.YELLOW
        self.score_bar.setStyleSheet(self.score_bar.styleSheet().replace(
            "background-color: " + Colors.GREEN_DIM,
            "background-color: " + chunk_color
        ))

        # Detay metni
        html = f"""
        <table style='width:100%; color:{Colors.TEXT_PRIMARY};'>
        <tr><td colspan='4' style='padding:4px; color:{Colors.BLUE}; font-size:13px;'>
            <b>═══ ZAMAN DİLİMİ SKORLARI ═══</b></td></tr>
        <tr style='color:{Colors.TEXT_SECONDARY};'>
            <td><b>TF</b></td><td><b>Skor</b></td><td><b>Yön</b></td><td><b>Not</b></td>
        </tr>
        """

        for tf in ["4h", "1h", "15m"]:
            if tf not in coin_data["tf_results"]:
                continue
            tfr = coin_data["tf_results"][tf]
            ts = tfr["total_score"]
            td = tfr["direction"]
            tc = score_color(ts)
            grade = "A+" if ts >= 85 else "A" if ts >= 75 else "B" if ts >= 65 else "C" if ts >= 55 else "D"
            html += f"""
            <tr>
                <td style='padding:3px; color:{Colors.BLUE};'><b>{tf.upper()}</b></td>
                <td style='color:{tc};'><b>{ts:.1f}</b></td>
                <td>{'🟢' if td=='LONG' else '🔴' if td=='SHORT' else '⚪'} {td}</td>
                <td style='color:{tc};'>{grade}</td>
            </tr>"""

        html += "</table><br>"

        # İndikatör detayları (4H — ana timeframe)
        primary_tf = "4h"
        if primary_tf in coin_data["tf_results"]:
            tfr = coin_data["tf_results"][primary_tf]
            scores = tfr["scores"]
            details = tfr["details"]

            html += f"""
            <table style='width:100%; color:{Colors.TEXT_PRIMARY};'>
            <tr><td colspan='3' style='padding:4px; color:{Colors.PURPLE}; font-size:13px;'>
                <b>═══ İNDİKATÖR DETAYLARI (4H) ═══</b></td></tr>
            <tr style='color:{Colors.TEXT_SECONDARY};'>
                <td><b>İndikatör</b></td><td><b>Skor</b></td><td><b>Detay</b></td>
            </tr>
            """

            indicator_names = {
                "trend_ema": ("📊 EMA Trend", "ema"),
                "supertrend": ("📈 Supertrend", "supertrend"),
                "ichimoku": ("☁️ Ichimoku", "ichimoku"),
                "macd": ("📉 MACD", "macd"),
                "adx": ("💪 ADX", "adx"),
                "rsi": ("🔄 RSI", "rsi"),
                "stoch_rsi": ("⚡ Stoch RSI", "stoch_rsi"),
                "bollinger": ("🎯 Bollinger", "bollinger"),
                "wavetrend": ("🌊 WaveTrend", "wavetrend"),
                "volume_obv": ("📦 OBV", "obv"),
                "mfi": ("💰 MFI", "mfi"),
                "t3_trend": ("〰️ Tilson T3", "t3"),
            }

            for key, (label, detail_key) in indicator_names.items():
                if key in scores:
                    s = scores[key]
                    sc = score_color(s)
                    d = details.get(detail_key, "")
                    # Skor çubuğu ASCII
                    bar_len = 10
                    filled = int(bar_len * s / 100)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    html += f"""
                    <tr>
                        <td style='padding:2px;'>{label}</td>
                        <td style='color:{sc}; font-family:Consolas;'>
                            <b>{s:.0f}</b> <span style='font-size:9px;'>{bar}</span>
                        </td>
                        <td style='color:{Colors.TEXT_SECONDARY}; font-size:11px;'>{d}</td>
                    </tr>"""

            # ATR bilgisi
            if "atr" in details:
                html += f"""
                <tr><td colspan='3' style='padding:4px; color:{Colors.ORANGE}; font-size:11px;'>
                    ⚠️ {details['atr']}  (Stop-loss mesafesi için kullan)
                </td></tr>"""

            html += "</table>"

        # Hizalama uyarısı
        if not coin_data["alignment"]:
            html += f"""<br><div style='background:{Colors.YELLOW_BG}; padding:8px; border-radius:4px;
                         color:{Colors.YELLOW};'>
                ⚠️ UYARI: Zaman dilimleri farklı yönde sinyal veriyor!
                Bu durumda pozisyon açmak risklidir.
            </div>"""

        # ── MUM FORMASYONLARI ──
        if HAS_EXTENSIONS and "candle_patterns" in coin_data:
            cp = coin_data["candle_patterns"]
            if cp["patterns"]:
                html += f"""<br><table style='width:100%; color:{Colors.TEXT_PRIMARY};'>
                <tr><td colspan='3' style='padding:4px; color:{Colors.ORANGE}; font-size:13px;'>
                    <b>═══ 🕯 MUM FORMASYONLARI ═══</b></td></tr>"""
                for p in cp["patterns"]:
                    dc = Colors.GREEN_BRIGHT if p["direction"] == "BULLISH" else Colors.RED_BRIGHT if p["direction"] == "BEARISH" else Colors.TEXT_SECONDARY
                    stars = "⭐" * p["strength"]
                    tf_tag = f"[{p.get('timeframe','').upper()}]" if p.get('timeframe') else ""
                    ago = f"{p['bars_ago']} mum önce" if p["bars_ago"] > 0 else "ŞİMDİ"
                    html += f"""<tr>
                        <td style='color:{dc};'><b>{p['name']}</b> {tf_tag}</td>
                        <td>{stars}</td>
                        <td style='color:{Colors.TEXT_MUTED};'>{ago}</td>
                    </tr>"""
                html += f"""<tr><td colspan='3' style='color:{Colors.TEXT_MUTED}; font-size:10px; padding-top:4px;'>
                    Bullish: {cp['bullish_count']} | Bearish: {cp['bearish_count']} | Skor: {cp['score']:.0f}
                </td></tr></table>"""

        # ── CHART FORMASYONLARI ──
        if HAS_EXTENSIONS and "chart_patterns" in coin_data:
            chp = coin_data["chart_patterns"]
            if chp["patterns"]:
                html += f"""<br><table style='width:100%; color:{Colors.TEXT_PRIMARY};'>
                <tr><td colspan='2' style='padding:4px; color:#a855f7; font-size:13px;'>
                    <b>═══ 📐 CHART FORMASYONLARI ═══</b></td></tr>"""
                for p in chp["patterns"]:
                    dc = Colors.GREEN_BRIGHT if p["direction"] == "BULLISH" else Colors.RED_BRIGHT if p["direction"] == "BEARISH" else Colors.TEXT_SECONDARY
                    conf = "✅ ONAYLANDI" if p.get("confirmed") else "⏳ Oluşuyor"
                    tf_tag = f"[{p.get('timeframe','').upper()}]" if p.get('timeframe') else ""
                    html += f"""<tr>
                        <td style='color:{dc};'><b>{p['name']}</b> {tf_tag} — {conf}</td>
                        <td style='color:{Colors.TEXT_MUTED}; font-size:10px;'>{p.get('description','')}</td>
                    </tr>"""
                    if "target" in p:
                        html += f"""<tr><td colspan='2' style='color:{Colors.YELLOW}; font-size:11px; padding-left:12px;'>
                            🎯 Hedef: {p['target']}</td></tr>"""
                html += "</table>"

        # ── HIZLI LİNKLER ──
        if HAS_EXTENSIONS:
            symbol = coin_data["symbol"]
            links = get_links(symbol)
            html += f"""<br><div style='padding:6px; background:{Colors.BG_CARD}; border-radius:6px;'>
                <span style='color:{Colors.BLUE}; font-size:12px;'><b>🔗 Hızlı Linkler</b></span><br>
                <span style='font-size:11px; color:{Colors.TEXT_SECONDARY};'>
                Sağ tık → menüden de açabilirsin
                </span>
            </div>"""

        self.details_text.setHtml(html)


# ═══════════════════════════════════════════════════════════════════════════
# ANA PENCERE
# ═══════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🔍 Pro Crypto Scanner v2.0 — Patterns + Sessions + Links")
        self.setMinimumSize(1400, 720)
        self.resize(1600, 900)

        self.config = ScannerConfig()
        self.scan_thread = None
        self.all_results = []

        self._setup_ui()
        self._apply_dark_theme()

    def _apply_dark_theme(self):
        """
        📚 EĞİTİM NOTU — Qt StyleSheet:
        Qt'de CSS'e benzer StyleSheet sistemi var.
        QSS (Qt Style Sheet) ile tüm widget'ların görünümünü kontrol edersin.
        Selector: QWidget sınıf adı
        Property: CSS property'lerine benzer ama tam aynı değil
        """
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {Colors.BG_DARK};
            }}
            QWidget {{
                background-color: {Colors.BG_DARK};
                color: {Colors.TEXT_PRIMARY};
                font-family: 'Segoe UI', 'Consolas', monospace;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
            QPushButton {{
                background-color: {Colors.BG_CARD};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_HOVER};
                border-color: {Colors.BORDER_ACTIVE};
            }}
            QPushButton:pressed {{
                background-color: {Colors.BLUE_BG};
            }}
            QPushButton:disabled {{
                color: {Colors.TEXT_MUTED};
                background-color: {Colors.BG_DARK};
            }}
            QComboBox, QSpinBox {{
                background-color: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                color: {Colors.TEXT_PRIMARY};
                min-height: 24px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Colors.BG_CARD};
                color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.BLUE_BG};
            }}
            QTableWidget {{
                background-color: {Colors.BG_DARK};
                alternate-background-color: {Colors.BG_PANEL};
                gridline-color: {Colors.BORDER};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                selection-background-color: {Colors.BLUE_BG};
                font-size: 12px;
            }}
            QTableWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {Colors.BORDER};
            }}
            QTableWidget::item:selected {{
                background-color: {Colors.BLUE_BG};
            }}
            QHeaderView::section {{
                background-color: {Colors.BG_PANEL};
                color: {Colors.TEXT_SECONDARY};
                border: none;
                border-bottom: 2px solid {Colors.BORDER};
                padding: 6px 8px;
                font-weight: bold;
                font-size: 11px;
            }}
            QProgressBar {{
                background-color: {Colors.BG_DARK};
                border: 1px solid {Colors.BORDER};
                border-radius: 4px;
                text-align: center;
                color: {Colors.TEXT_PRIMARY};
                font-weight: bold;
                font-size: 11px;
            }}
            QProgressBar::chunk {{
                background-color: {Colors.BLUE};
                border-radius: 3px;
            }}
            QGroupBox {{
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 14px;
                font-weight: bold;
                color: {Colors.TEXT_SECONDARY};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }}
            QCheckBox {{
                color: {Colors.TEXT_PRIMARY};
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {Colors.BORDER};
                border-radius: 3px;
                background: {Colors.BG_CARD};
            }}
            QCheckBox::indicator:checked {{
                background: {Colors.BLUE};
                border-color: {Colors.BLUE};
            }}
            QSplitter::handle {{
                background: {Colors.BORDER};
                width: 2px;
            }}
        """)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(8)

        # ── ÜSTBAR: Başlık + Kontroller ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        # Logo / Başlık
        title = QLabel("🔍 PRO CRYPTO SCANNER")
        title.setFont(QFont("Consolas", 16, QFont.Bold))
        title.setStyleSheet(f"color: {Colors.BLUE}; font-size: 16px;")
        top_bar.addWidget(title)

        version = QLabel("v1.0")
        version.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        top_bar.addWidget(version)

        top_bar.addStretch()

        # Ayarlar
        top_bar.addWidget(QLabel("Max Coin:"))
        self.max_coins_spin = QSpinBox()
        self.max_coins_spin.setRange(10, 200)
        self.max_coins_spin.setValue(self.config.max_coins)
        self.max_coins_spin.setSingleStep(10)
        top_bar.addWidget(self.max_coins_spin)

        top_bar.addWidget(QLabel("Min Skor:"))
        self.min_score_spin = QSpinBox()
        self.min_score_spin.setRange(30, 90)
        self.min_score_spin.setValue(self.config.min_score)
        self.min_score_spin.setSingleStep(5)
        top_bar.addWidget(self.min_score_spin)

        top_bar.addWidget(QLabel("Min Hacim:"))
        self.volume_combo = QComboBox()
        self.volume_combo.addItems(["1M", "5M", "10M", "25M", "50M"])
        self.volume_combo.setCurrentText("5M")
        top_bar.addWidget(self.volume_combo)

        # Tarama butonu
        self.scan_btn = QPushButton("🚀 TARAMAYI BAŞLAT")
        self.scan_btn.setFixedSize(200, 36)
        self.scan_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BLUE};
                color: white;
                font-size: 13px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #2563eb;
            }}
            QPushButton:disabled {{
                background-color: {Colors.TEXT_MUTED};
            }}
        """)
        self.scan_btn.clicked.connect(self.start_scan)
        top_bar.addWidget(self.scan_btn)

        # İptal butonu
        self.cancel_btn = QPushButton("⏹ İptal")
        self.cancel_btn.setFixedSize(80, 36)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.RED_DIM};
                color: white;
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{ background-color: {Colors.RED_BRIGHT}; }}
            QPushButton:disabled {{ background-color: {Colors.BG_CARD}; color: {Colors.TEXT_MUTED}; }}
        """)
        self.cancel_btn.clicked.connect(self.cancel_scan)
        top_bar.addWidget(self.cancel_btn)

        main_layout.addLayout(top_bar)

        # ── PROGRESS BAR ──
        self.progress = QProgressBar()
        self.progress.setFixedHeight(22)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p% — %v")
        main_layout.addWidget(self.progress)

        # Status label
        self.status_label = QLabel("Hazır. Taramayı başlatmak için butona tıkla.")
        self.status_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; padding: 2px;")
        main_layout.addWidget(self.status_label)

        # ── FİLTRE BARI ──
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        filter_bar.addWidget(QLabel("Filtre:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Tümü", "🟢 Sadece LONG", "🔴 Sadece SHORT", "✅ Sadece Hizalı", "🔥 Skor 75+", "📐 Formasyonlu"])
        self.filter_combo.currentIndexChanged.connect(self.apply_filter)
        filter_bar.addWidget(self.filter_combo)

        filter_bar.addWidget(QLabel("Sıralama:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Skor (Yüksek→Düşük)", "Skor (Düşük→Yüksek)", "Hacim", "24h Değişim", "İsim (A-Z)"])
        self.sort_combo.currentIndexChanged.connect(self.apply_filter)
        filter_bar.addWidget(self.sort_combo)

        filter_bar.addStretch()

        self.result_count_label = QLabel("")
        self.result_count_label.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        filter_bar.addWidget(self.result_count_label)

        main_layout.addLayout(filter_bar)

        # ── ANA İÇERİK: Tablo + Detay Paneli ──
        splitter = QSplitter(Qt.Horizontal)

        # Sol: Tablo
        table_frame = QFrame()
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels([
            "Coin", "Yön", "Skor", "Not", "Fiyat",
            "24h %", "Hacim", "4H", "1H", "15M",
            "🕯 Mum", "📐 Chart"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(False)

        # Sütun genişlikleri
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)      # Coin
        self.table.setColumnWidth(0, 100)
        header.setSectionResizeMode(1, QHeaderView.Fixed)      # Yön
        self.table.setColumnWidth(1, 60)
        header.setSectionResizeMode(2, QHeaderView.Fixed)      # Skor
        self.table.setColumnWidth(2, 60)
        header.setSectionResizeMode(3, QHeaderView.Fixed)      # Not
        self.table.setColumnWidth(3, 40)
        header.setSectionResizeMode(4, QHeaderView.Stretch)    # Fiyat
        header.setSectionResizeMode(5, QHeaderView.Fixed)      # 24h%
        self.table.setColumnWidth(5, 75)
        header.setSectionResizeMode(6, QHeaderView.Fixed)      # Hacim
        self.table.setColumnWidth(6, 85)
        for col in [7, 8, 9]:  # TF skorları
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, 55)
        for col in [10, 11]:  # Pattern sütunları
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, 160)

        self.table.cellClicked.connect(self.on_row_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.on_right_click)
        self.table.cellDoubleClicked.connect(self.on_double_click)
        table_layout.addWidget(self.table)
        splitter.addWidget(table_frame)

        # Sağ: Detay paneli
        self.detail_panel = DetailPanel()
        self.detail_panel.setMinimumWidth(380)
        splitter.addWidget(self.detail_panel)

        splitter.setSizes([900, 400])
        main_layout.addWidget(splitter, 1)

        # ── SEANS BİLGİ BARI ──
        if HAS_EXTENSIONS:
            session_bar = QHBoxLayout()
            session_bar.setSpacing(8)
            rec = get_session_recommendation()
            current = get_current_session()

            self.session_label = QLabel(
                f"  {rec['emoji']} {rec['action']}  |  "
                f"🕐 TR: {current['turkey_time']}  UTC: {current['utc_time']}  |  "
                f"{rec['message']}"
            )
            self.session_label.setStyleSheet(
                f"color: {rec['color']}; background: {Colors.BG_PANEL}; "
                f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
                f"padding: 6px 10px; font-size: 11px;"
            )
            session_bar.addWidget(self.session_label, 1)
            main_layout.addLayout(session_bar)

        # ── ALT BAR: Özet istatistikler ──
        bottom_bar = QHBoxLayout()

        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        bottom_bar.addWidget(self.stats_label)

        bottom_bar.addStretch()

        # JSON kaydet butonu
        self.save_btn = QPushButton("💾 JSON Kaydet")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_results)
        bottom_bar.addWidget(self.save_btn)

        # Zaman
        self.time_label = QLabel("")
        self.time_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        bottom_bar.addWidget(self.time_label)

        main_layout.addLayout(bottom_bar)

        # Timer — saat güncelleme
        timer = QTimer(self)
        timer.timeout.connect(self._update_time)
        timer.start(1000)
        self._update_time()

    def _update_time(self):
        self.time_label.setText(datetime.now().strftime("🕐 %H:%M:%S"))
        # Seans bilgisini de güncelle (her dakika yeterli ama timer 1sn)
        if HAS_EXTENSIONS and hasattr(self, 'session_label'):
            rec = get_session_recommendation()
            current = get_current_session()
            self.session_label.setText(
                f"  {rec['emoji']} {rec['action']}  |  "
                f"🕐 TR: {current['turkey_time']}  UTC: {current['utc_time']}  |  "
                f"{rec['message']}"
            )
            self.session_label.setStyleSheet(
                f"color: {rec['color']}; background: {Colors.BG_PANEL}; "
                f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
                f"padding: 6px 10px; font-size: 11px;"
            )
        # Seans bilgisini güncelle
        if HAS_EXTENSIONS and hasattr(self, 'session_label'):
            rec = get_session_recommendation()
            current = get_current_session()
            self.session_label.setText(
                f"  {rec['emoji']} {rec['action']}  |  "
                f"🕐 TR: {current['turkey_time']}  UTC: {current['utc_time']}  |  "
                f"{rec['message']}"
            )
            self.session_label.setStyleSheet(
                f"color: {rec['color']}; background: {Colors.BG_PANEL}; "
                f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
                f"padding: 6px 10px; font-size: 11px;"
            )

    # ── TARAMA KONTROL ──

    def start_scan(self):
        """Taramayı başlatır."""
        # Config güncelle
        self.config.max_coins = self.max_coins_spin.value()
        self.config.min_score = self.min_score_spin.value()

        vol_map = {"1M": 1_000_000, "5M": 5_000_000, "10M": 10_000_000,
                    "25M": 25_000_000, "50M": 50_000_000}
        self.config.min_volume_usdt = vol_map.get(self.volume_combo.currentText(), 5_000_000)

        # UI kilitle
        self.scan_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.save_btn.setEnabled(False)
        self.table.setRowCount(0)
        self.all_results = []
        self.progress.setValue(0)

        # Thread başlat
        self.scan_thread = ScanThread(self.config)
        self.scan_thread.progress_signal.connect(self.on_progress)
        self.scan_thread.coin_result_signal.connect(self.on_coin_result)
        self.scan_thread.finished_signal.connect(self.on_scan_finished)
        self.scan_thread.error_signal.connect(self.on_error)
        self.scan_thread.start()

    def cancel_scan(self):
        if self.scan_thread:
            self.scan_thread.cancel()
            self.scan_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.status_label.setText("⏹ Tarama iptal edildi.")

    def on_progress(self, pct: int, msg: str):
        self.progress.setValue(pct)
        self.status_label.setText(msg)

    def on_coin_result(self, result: dict):
        """Her coin geldiğinde tabloya ekle — canlı güncelleme."""
        self.all_results.append(result)
        self._add_row_to_table(result)
        self.result_count_label.setText(f"Bulunan: {len(self.all_results)}")

    def on_scan_finished(self, results: list):
        self.all_results = results
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.save_btn.setEnabled(True)
        self.apply_filter()
        self._update_stats()

    def on_error(self, msg: str):
        self.status_label.setText(f"❌ {msg}")
        self.status_label.setStyleSheet(f"color: {Colors.RED_BRIGHT}; font-size: 11px;")
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    # ── TABLO İŞLEMLERİ ──

    def _add_row_to_table(self, r: dict):
        """Tabloya tek bir satır ekler."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 32)

        # 0: Coin adı
        item = QTableWidgetItem(r["clean_name"])
        item.setFont(QFont("Consolas", 11, QFont.Bold))
        item.setForeground(QBrush(QColor(Colors.TEXT_PRIMARY)))
        item.setData(Qt.UserRole, r)  # Veriyi satıra göm
        self.table.setItem(row, 0, item)

        # 1: Yön
        d = r["direction"]
        dir_item = QTableWidgetItem("🟢 LONG" if d == "LONG" else "🔴 SHORT" if d == "SHORT" else "⚪")
        dir_item.setForeground(QBrush(QColor(
            Colors.GREEN_BRIGHT if d == "LONG" else Colors.RED_BRIGHT if d == "SHORT" else Colors.TEXT_MUTED
        )))
        self.table.setItem(row, 1, dir_item)

        # 2: MTF Skor
        score = r["mtf_score"]
        score_item = QTableWidgetItem(f"{score:.1f}")
        score_item.setForeground(QBrush(QColor(score_color(score))))
        score_item.setFont(QFont("Consolas", 11, QFont.Bold))
        score_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 2, score_item)

        # 3: Not
        if score >= 85: grade = "A+"
        elif score >= 75: grade = "A"
        elif score >= 65: grade = "B"
        elif score >= 55: grade = "C"
        else: grade = "D"
        grade_item = QTableWidgetItem(grade)
        grade_item.setForeground(QBrush(QColor(score_color(score))))
        grade_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 3, grade_item)

        # 4: Fiyat
        price = r["price"]
        if price >= 1000:
            fmt = f"${price:,.2f}"
        elif price >= 1:
            fmt = f"${price:.4f}"
        else:
            fmt = f"${price:.6f}"
        price_item = QTableWidgetItem(fmt)
        price_item.setForeground(QBrush(QColor(Colors.TEXT_PRIMARY)))
        price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 4, price_item)

        # 5: 24h Değişim
        chg = r["change_24h"]
        chg_item = QTableWidgetItem(f"{chg:+.1f}%")
        chg_item.setForeground(QBrush(QColor(change_color(chg))))
        chg_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 5, chg_item)

        # 6: Hacim
        vol = r["volume_24h"]
        if vol >= 1e9: vol_str = f"${vol/1e9:.1f}B"
        elif vol >= 1e6: vol_str = f"${vol/1e6:.0f}M"
        else: vol_str = f"${vol/1e3:.0f}K"
        vol_item = QTableWidgetItem(vol_str)
        vol_item.setForeground(QBrush(QColor(Colors.TEXT_SECONDARY)))
        vol_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 6, vol_item)

        # 7-9: TF skorları
        for col, tf in enumerate(["4h", "1h", "15m"], 7):
            if tf in r["tf_results"]:
                ts = r["tf_results"][tf]["total_score"]
                tf_item = QTableWidgetItem(f"{ts:.0f}")
                tf_item.setForeground(QBrush(QColor(score_color(ts))))
                tf_item.setTextAlignment(Qt.AlignCenter)
            else:
                tf_item = QTableWidgetItem("—")
                tf_item.setForeground(QBrush(QColor(Colors.TEXT_MUTED)))
            self.table.setItem(row, col, tf_item)

        # 10: Mum formasyonları — detaylı gösterim
        if "candle_patterns" in r and r["candle_patterns"]["patterns"]:
            cp = r["candle_patterns"]
            # En güçlü pattern'i öne koy, max 2 göster
            sorted_patterns = sorted(cp["patterns"], key=lambda x: x["strength"], reverse=True)
            parts = []
            for p in sorted_patterns[:2]:
                emoji = "🟢" if p["direction"] == "BULLISH" else "🔴" if p["direction"] == "BEARISH" else "⚪"
                tf_tag = p.get("timeframe", "").upper()
                parts.append(f"{emoji}{p['name']}[{tf_tag}]")
            cp_text = " ".join(parts)
            cp_item = QTableWidgetItem(cp_text)
            bull = cp["bullish_count"]
            bear = cp["bearish_count"]
            if bull > bear:
                cp_item.setForeground(QBrush(QColor(Colors.GREEN_DIM)))
            elif bear > bull:
                cp_item.setForeground(QBrush(QColor(Colors.RED_DIM)))
            else:
                cp_item.setForeground(QBrush(QColor(Colors.TEXT_SECONDARY)))
            # Tooltip: tüm formasyonların listesi
            tip_lines = [f"{'🟢' if p['direction']=='BULLISH' else '🔴' if p['direction']=='BEARISH' else '⚪'} "
                         f"{p['name']} — {'⭐'*p['strength']} [{p.get('timeframe','').upper()}]"
                         for p in sorted_patterns]
            cp_item.setToolTip("\n".join(tip_lines))
        else:
            cp_item = QTableWidgetItem("—")
            cp_item.setForeground(QBrush(QColor(Colors.TEXT_MUTED)))
        self.table.setItem(row, 10, cp_item)

        # 11: Chart formasyonları — detaylı gösterim
        if "chart_patterns" in r and r["chart_patterns"]["patterns"]:
            chp = r["chart_patterns"]
            p0 = chp["patterns"][0]
            conf = "✅" if p0.get("confirmed") else "⏳"
            tf_tag = p0.get("timeframe", "").upper()
            emoji = "🟢" if p0["direction"] == "BULLISH" else "🔴" if p0["direction"] == "BEARISH" else "🔶"
            chp_text = f"{emoji}{p0['name']} {conf}"
            if tf_tag:
                chp_text += f" [{tf_tag}]"
            chp_item = QTableWidgetItem(chp_text)
            if p0["direction"] == "BULLISH":
                chp_item.setForeground(QBrush(QColor(Colors.GREEN_BRIGHT)))
            elif p0["direction"] == "BEARISH":
                chp_item.setForeground(QBrush(QColor(Colors.RED_BRIGHT)))
            else:
                chp_item.setForeground(QBrush(QColor(Colors.YELLOW)))
            # Tooltip: açıklama + hedef
            tip = f"{p0['name']}\n{p0.get('description','')}"
            if "target" in p0:
                tip += f"\n🎯 Hedef: {p0['target']}"
            if "neckline" in p0:
                tip += f"\nNeckline: {p0['neckline']}"
            chp_item.setToolTip(tip)
        else:
            chp_item = QTableWidgetItem("—")
            chp_item.setForeground(QBrush(QColor(Colors.TEXT_MUTED)))
        self.table.setItem(row, 11, chp_item)

    def apply_filter(self):
        """Filtreleme ve sıralama uygular."""
        if not self.all_results:
            return

        filtered = list(self.all_results)
        filter_idx = self.filter_combo.currentIndex()

        # Filtrele
        if filter_idx == 1:    # Sadece LONG
            filtered = [r for r in filtered if r["direction"] == "LONG"]
        elif filter_idx == 2:  # Sadece SHORT
            filtered = [r for r in filtered if r["direction"] == "SHORT"]
        elif filter_idx == 3:  # Sadece Hizalı
            filtered = [r for r in filtered if r["alignment"]]
        elif filter_idx == 4:  # Skor 75+
            filtered = [r for r in filtered if r["mtf_score"] >= 75 or r["mtf_score"] <= 25]
        elif filter_idx == 5:  # Formasyonlu — chart veya mum pattern bulunanlar
            filtered = [r for r in filtered if
                        (r.get("chart_patterns", {}).get("patterns", [])) or
                        (r.get("candle_patterns", {}).get("patterns", []))]

        # Sırala
        sort_idx = self.sort_combo.currentIndex()
        if sort_idx == 0:
            filtered.sort(key=lambda x: x["mtf_score"], reverse=True)
        elif sort_idx == 1:
            filtered.sort(key=lambda x: x["mtf_score"])
        elif sort_idx == 2:
            filtered.sort(key=lambda x: x["volume_24h"], reverse=True)
        elif sort_idx == 3:
            filtered.sort(key=lambda x: abs(x["change_24h"]), reverse=True)
        elif sort_idx == 4:
            filtered.sort(key=lambda x: x["clean_name"])

        # Tabloyu yeniden doldur
        self.table.setRowCount(0)
        for r in filtered:
            self._add_row_to_table(r)

        self.result_count_label.setText(f"Gösterilen: {len(filtered)} / {len(self.all_results)}")

    def on_row_clicked(self, row, col):
        """Tıklanan satırın detaylarını gösterir."""
        item = self.table.item(row, 0)
        if item:
            coin_data = item.data(Qt.UserRole)
            if coin_data:
                self.detail_panel.update_detail(coin_data)

    def on_double_click(self, row, col):
        """
        📚 EĞİTİM NOTU — ÇİFT TIKLA TradingView AÇ:
        Çift tık = en hızlı yol. Sinyal gördün → çift tıkla → chart'ta onayla.
        webbrowser.open() sisteminizin varsayılan tarayıcısında URL açar.
        """
        if not HAS_EXTENSIONS:
            return
        item = self.table.item(row, 0)
        if item:
            coin_data = item.data(Qt.UserRole)
            if coin_data:
                open_tradingview(coin_data["symbol"])

    def on_right_click(self, position):
        """
        📚 EĞİTİM NOTU — SAĞ TIK MENÜSÜ (Context Menu):
        QMenu ile sağ tık menüsü oluştururuz.
        Her menü öğesi bir QAction'dır ve tıklanınca
        lambda fonksiyonu çalıştırır.

        Lambda neden gerekli?
          menu.addAction("Text", fonksiyon) şeklinde bağlarız.
          Ama fonksiyona parametre geçirmek için lambda kullanırız:
          lambda: open_link(symbol, "binance") gibi.
        """
        if not HAS_EXTENSIONS:
            return

        row = self.table.rowAt(position.y())
        if row < 0:
            return

        item = self.table.item(row, 0)
        if not item:
            return

        coin_data = item.data(Qt.UserRole)
        if not coin_data:
            return

        symbol = coin_data["symbol"]
        clean = coin_data["clean_name"]

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Colors.BG_PANEL};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 4px;
                font-size: 12px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {Colors.BLUE_BG};
            }}
            QMenu::separator {{
                height: 1px;
                background: {Colors.BORDER};
                margin: 4px 8px;
            }}
        """)

        # Başlık
        title_action = menu.addAction(f"📊 {clean}/USDT")
        title_action.setEnabled(False)
        menu.addSeparator()

        # Chart & Analiz
        menu.addAction("📈 TradingView'da Aç", lambda: open_link(symbol, "tradingview"))
        menu.addAction("💡 TradingView Fikirler", lambda: open_link(symbol, "tradingview_ideas"))
        menu.addAction("📊 FastBull Chart", lambda: open_link(symbol, "fastbull"))
        menu.addSeparator()

        # Borsalar
        menu.addAction("🔶 Binance Futures", lambda: open_link(symbol, "binance_futures"))
        menu.addAction("🟢 OKX", lambda: open_link(symbol, "okx"))
        menu.addAction("🔵 BingX", lambda: open_link(symbol, "bingx"))
        menu.addSeparator()

        # Veri & Analiz
        menu.addAction("🔥 CoinGlass (Likidasyonlar)", lambda: open_link(symbol, "coinglass_liq"))
        menu.addAction("📊 CoinGlass (OI/Funding)", lambda: open_link(symbol, "coinglass"))
        menu.addAction("🌐 CoinMarketCap", lambda: open_link(symbol, "coinmarketcap"))

        menu.exec_(self.table.viewport().mapToGlobal(position))

    def on_double_click(self, row, col):
        """
        📚 EĞİTİM NOTU — ÇİFT TIKLA TRADINGVİEW AÇ:
        Çift tıklama en doğal "aç" aksiyonudur.
        webbrowser.open() varsayılan tarayıcıda URL açar.
        """
        if not HAS_EXTENSIONS:
            return
        item = self.table.item(row, 0)
        if item:
            coin_data = item.data(Qt.UserRole)
            if coin_data:
                open_tradingview(coin_data["symbol"])

    def on_right_click(self, position):
        """
        📚 EĞİTİM NOTU — CONTEXT MENU (Sağ Tık Menüsü):
        QMenu ile sağ tıklayınca açılan menü oluşturursun.
        addAction() ile menüye öğe eklersin.
        triggered.connect() ile tıklayınca ne olacağını belirlersin.

        Lambda kullanıyoruz çünkü her action'a farklı parametre geçmemiz lazım.
        lambda: func(param) → o anda param'ı yakalar ve saklar.
        """
        if not HAS_EXTENSIONS:
            return

        row = self.table.rowAt(position.y())
        if row < 0:
            return

        item = self.table.item(row, 0)
        if not item:
            return

        coin_data = item.data(Qt.UserRole)
        if not coin_data:
            return

        symbol = coin_data["symbol"]
        clean = coin_data["clean_name"]
        links = get_links(symbol)

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Colors.BG_PANEL};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 4px;
                font-size: 12px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {Colors.BLUE_BG};
            }}
            QMenu::separator {{
                height: 1px;
                background: {Colors.BORDER};
                margin: 4px 8px;
            }}
        """)

        # Başlık
        title_action = menu.addAction(f"📊 {clean}/USDT")
        title_action.setEnabled(False)
        menu.addSeparator()

        # TradingView
        tv_action = menu.addAction("📈 TradingView'da Aç")
        tv_action.triggered.connect(lambda: open_link(symbol, "tradingview"))

        tv_ideas = menu.addAction("💡 TradingView Fikirler")
        tv_ideas.triggered.connect(lambda: open_link(symbol, "tradingview_ideas"))

        menu.addSeparator()

        # Borsalar
        binance_action = menu.addAction("🟡 Binance Futures")
        binance_action.triggered.connect(lambda: open_link(symbol, "binance_futures"))

        okx_action = menu.addAction("⚫ OKX")
        okx_action.triggered.connect(lambda: open_link(symbol, "okx"))

        bingx_action = menu.addAction("🔵 BingX")
        bingx_action.triggered.connect(lambda: open_link(symbol, "bingx"))

        menu.addSeparator()

        # Analiz araçları
        cg_action = menu.addAction("🔍 CoinGlass (OI & Liq)")
        cg_action.triggered.connect(lambda: open_link(symbol, "coinglass"))

        cg_liq = menu.addAction("🌊 Likidasyon Haritası")
        cg_liq.triggered.connect(lambda: open_link(symbol, "coinglass_liq"))

        fb_action = menu.addAction("⚡ FastBull Chart")
        fb_action.triggered.connect(lambda: open_link(symbol, "fastbull"))

        cmc_action = menu.addAction("ℹ️ CoinMarketCap")
        cmc_action.triggered.connect(lambda: open_link(symbol, "coinmarketcap"))

        menu.exec_(self.table.viewport().mapToGlobal(position))

    def _update_stats(self):
        """Alt bardaki istatistikleri günceller."""
        total = len(self.all_results)
        longs = sum(1 for r in self.all_results if r["direction"] == "LONG")
        shorts = sum(1 for r in self.all_results if r["direction"] == "SHORT")
        aligned = sum(1 for r in self.all_results if r["alignment"])
        avg_score = sum(r["mtf_score"] for r in self.all_results) / total if total else 0

        self.stats_label.setText(
            f"📊 Toplam: {total}  |  🟢 Long: {longs}  |  🔴 Short: {shorts}  |  "
            f"✅ Hizalı: {aligned}  |  📈 Ort. Skor: {avg_score:.1f}"
        )

    def save_results(self):
        """Sonuçları JSON olarak kaydeder."""
        output = {
            "scan_time": datetime.now().isoformat(),
            "results": [
                {
                    "symbol": r["symbol"],
                    "price": r["price"],
                    "mtf_score": r["mtf_score"],
                    "direction": r["direction"],
                    "alignment": r["alignment"],
                    "change_24h": r["change_24h"],
                    "volume_24h": r["volume_24h"],
                }
                for r in self.all_results
            ]
        }
        path = "scan_results.json"
        with open(path, "w") as f:
            json.dump(output, f, indent=2)
        self.status_label.setText(f"💾 Kaydedildi: {path}")


# ═══════════════════════════════════════════════════════════════════════════
# BAŞLATICI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """
    📚 EĞİTİM NOTU — QApplication:
    Her Qt uygulamasında TAM BİR adet QApplication olmalıdır.
    sys.argv komut satırı argümanlarını Qt'ye iletir.
    app.exec_() olay döngüsünü (event loop) başlatır —
    pencere kapanana kadar program burada kalır.
    """
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
