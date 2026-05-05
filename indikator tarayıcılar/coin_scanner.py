"""
COIN SCANNER v3.0 - Ana Uygulama
====================================
v3.0 Yenilikler:
- OKX + BingX borsa desteği (Otomatik fallback)
- Borsa seçici dropdown (Ayarlarda)
- Funding Rate sütunu (tabloda + detay popup)
- OKX'te Aç butonu (detay popup)
- T3 katsayı bugfix (indicators.py'de)
- requests kütüphanesi (daha güvenilir API bağlantısı)
- Detay popup'ta borsa bilgisi

ÖĞRETİCİ:
═══════════
Bu dosya sadece UI'dır — tarama mantığı scanner_engine.py'dedir.
PyQt5 ile yazılmış masaüstü uygulaması.
MVC pattern: Model=scanner_engine, View=bu dosya, Controller=butonlar/sinyaller.
"""

import sys
import json
import os
import threading
import webbrowser
import csv
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QGroupBox,
    QSpinBox, QCheckBox, QComboBox, QProgressBar, QTabWidget,
    QTextEdit, QHeaderView, QDialog, QGridLayout, QMessageBox,
    QFrame, QSplitter, QDoubleSpinBox, QFileDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QUrl
from PyQt5.QtGui import QColor, QFont, QDesktopServices

from scanner_engine import run_full_scan, export_to_csv


# ============================================================
# AYARLAR
# ============================================================

SETTINGS_FILE = "scanner_settings.json"

DEFAULT_SETTINGS = {
    'min_volume_usdt': 10_000_000,
    'min_market_cap': 0,
    'max_market_cap': 0,
    'max_coins': 50,
    'scan_interval_min': 10,
    'timeframes': ['1h', '4h', '1d'],
    'use_rsi': True, 'use_wavetrend': True, 'use_bb': True,
    'use_t3': True, 'use_volume': True,
    'use_hammer': True, 'use_hanging': True, 'use_doji': True,
    'use_marubozu': True, 'use_morning': True, 'use_evening': True,
    'min_signal_count': 2,
    'sound_alerts': True,
    'exchange': 'Otomatik',   # YENİ: Borsa seçimi
}


def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
    except:
        pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except:
        pass


# ============================================================
# THREAD SİNYALLERİ
# ============================================================

class ScanSignals(QObject):
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)


# ============================================================
# AYARLAR PANELİ
# ============================================================

class SettingsPanel(QGroupBox):
    def __init__(self, settings):
        super().__init__("⚙️ Tarama Ayarları")
        self.settings = settings
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(6)

        # ── Borsa Seçimi (YENİ!) ──────────────────────────────
        eg = QGroupBox("📡 Borsa")
        el = QGridLayout()

        el.addWidget(QLabel("Veri Kaynağı:"), 0, 0)
        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(['Otomatik', 'OKX', 'Binance', 'BingX'])
        # Mevcut ayardan seç
        current_ex = self.settings.get('exchange', 'Otomatik')
        idx = self.exchange_combo.findText(current_ex)
        if idx >= 0:
            self.exchange_combo.setCurrentIndex(idx)
        self.exchange_combo.setToolTip(
            "Otomatik: Sırayla dener (OKX → Binance → BingX)\n"
            "OKX: Senin ana borsan, perpetual futures\n"
            "Binance: En büyük borsa (TR'den erişim sorunu olabilir)\n"
            "BingX: Yedek, her zaman çalışır"
        )
        el.addWidget(self.exchange_combo, 0, 1)

        eg.setLayout(el)
        layout.addWidget(eg)

        # ── Filtreler ─────────────────────────────────────────
        fg = QGroupBox("📊 Filtreler")
        fl = QGridLayout()

        fl.addWidget(QLabel("Min Volume ($):"), 0, 0)
        self.volume_spin = QDoubleSpinBox()
        self.volume_spin.setRange(0, 10_000_000_000)
        self.volume_spin.setSingleStep(1_000_000)
        self.volume_spin.setDecimals(0)
        self.volume_spin.setSuffix(" USDT")
        self.volume_spin.setValue(self.settings['min_volume_usdt'])
        fl.addWidget(self.volume_spin, 0, 1)

        # Market Cap dropdown
        fl.addWidget(QLabel("Market Cap:"), 1, 0)
        self.mcap_combo = QComboBox()
        self.mcap_combo.addItems([
            "Filtre Yok", "Mega Cap (>$50B)", "Large Cap ($10B-$50B)",
            "Mid Cap ($1B-$10B)", "Small Cap ($100M-$1B)",
            "Micro Cap (<$100M)", "Özel Aralık..."
        ])
        self._set_mcap_from_settings()
        self.mcap_combo.currentIndexChanged.connect(self._on_mcap_changed)
        fl.addWidget(self.mcap_combo, 1, 1)

        self.mcap_min_spin = QDoubleSpinBox()
        self.mcap_min_spin.setRange(0, 1e12)
        self.mcap_min_spin.setSingleStep(1e8)
        self.mcap_min_spin.setDecimals(0)
        self.mcap_min_spin.setPrefix("Min $")
        self.mcap_min_spin.setValue(self.settings['min_market_cap'])
        self.mcap_min_spin.setVisible(False)
        fl.addWidget(self.mcap_min_spin, 2, 0)

        self.mcap_max_spin = QDoubleSpinBox()
        self.mcap_max_spin.setRange(0, 1e12)
        self.mcap_max_spin.setSingleStep(1e8)
        self.mcap_max_spin.setDecimals(0)
        self.mcap_max_spin.setPrefix("Max $")
        self.mcap_max_spin.setValue(self.settings['max_market_cap'])
        self.mcap_max_spin.setVisible(False)
        fl.addWidget(self.mcap_max_spin, 2, 1)

        fl.addWidget(QLabel("Max Coin:"), 3, 0)
        self.max_coins_spin = QSpinBox()
        self.max_coins_spin.setRange(5, 300)
        self.max_coins_spin.setValue(self.settings['max_coins'])
        fl.addWidget(self.max_coins_spin, 3, 1)

        fl.addWidget(QLabel("Tarama Aralığı:"), 4, 0)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.setValue(self.settings['scan_interval_min'])
        self.interval_spin.setSuffix(" dk")
        fl.addWidget(self.interval_spin, 4, 1)

        fl.addWidget(QLabel("Min Sinyal:"), 5, 0)
        self.min_sig_spin = QSpinBox()
        self.min_sig_spin.setRange(1, 10)
        self.min_sig_spin.setValue(self.settings['min_signal_count'])
        fl.addWidget(self.min_sig_spin, 5, 1)

        fg.setLayout(fl)
        layout.addWidget(fg)

        # ── Zaman Dilimleri ───────────────────────────────────
        tg = QGroupBox("⏱️ Zaman Dilimleri")
        tl = QVBoxLayout()
        self.tf_checks = {}
        for k, label in [('15m','15dk'), ('30m','30dk'), ('1h','1 Saat'), ('4h','4 Saat'), ('1d','1 Gün')]:
            cb = QCheckBox(label)
            cb.setChecked(k in self.settings['timeframes'])
            self.tf_checks[k] = cb
            tl.addWidget(cb)
        tg.setLayout(tl)
        layout.addWidget(tg)

        # ── İndikatörler ─────────────────────────────────────
        ig = QGroupBox("📈 İndikatörler")
        il = QVBoxLayout()
        self.ind_checks = {}
        for k, label in [('use_rsi','RSI (Aşırı Bölge + Divergence)'),
                         ('use_wavetrend','VMC Cipher B (WaveTrend)'),
                         ('use_bb','Bollinger Bands (Squeeze+Touch)'),
                         ('use_t3','Tilson T3 (Trend Filtresi)'),
                         ('use_volume','VWAP + Volume Spike')]:
            cb = QCheckBox(label)
            cb.setChecked(self.settings[k])
            self.ind_checks[k] = cb
            il.addWidget(cb)
        ig.setLayout(il)
        layout.addWidget(ig)

        # ── Formasyonlar ─────────────────────────────────────
        pg = QGroupBox("🕯️ Mum Formasyonları")
        pl = QVBoxLayout()
        self.pat_checks = {}
        for k, label in [('use_hammer','Hammer'), ('use_hanging','Hanging Man'),
                         ('use_doji','Doji'), ('use_marubozu','Marubozu'),
                         ('use_morning','Morning Star'), ('use_evening','Evening Star')]:
            cb = QCheckBox(label)
            cb.setChecked(self.settings[k])
            self.pat_checks[k] = cb
            pl.addWidget(cb)
        pg.setLayout(pl)
        layout.addWidget(pg)

        # Ses bildirimi
        self.sound_cb = QCheckBox("🔔 Ses Bildirimi")
        self.sound_cb.setChecked(self.settings.get('sound_alerts', True))
        layout.addWidget(self.sound_cb)

        layout.addStretch()
        self.setLayout(layout)
        self.setMaximumWidth(300)

    def _set_mcap_from_settings(self):
        presets = {
            (0,0):0, (50e9,0):1, (10e9,50e9):2, (1e9,10e9):3, (100e6,1e9):4, (0,100e6):5
        }
        key = (self.settings.get('min_market_cap',0), self.settings.get('max_market_cap',0))
        self.mcap_combo.setCurrentIndex(presets.get(key, 6))

    def _on_mcap_changed(self, idx):
        presets = {0:(0,0),1:(50e9,0),2:(10e9,50e9),3:(1e9,10e9),4:(100e6,1e9),5:(0,100e6)}
        if idx in presets:
            self.mcap_min_spin.setValue(presets[idx][0])
            self.mcap_max_spin.setValue(presets[idx][1])
            self.mcap_min_spin.setVisible(False)
            self.mcap_max_spin.setVisible(False)
        else:
            self.mcap_min_spin.setVisible(True)
            self.mcap_max_spin.setVisible(True)

    def _get_mcap(self):
        presets = {0:(0,0),1:(50e9,0),2:(10e9,50e9),3:(1e9,10e9),4:(100e6,1e9),5:(0,100e6)}
        idx = self.mcap_combo.currentIndex()
        return presets.get(idx, (int(self.mcap_min_spin.value()), int(self.mcap_max_spin.value())))

    def get_settings(self):
        mn, mx = self._get_mcap()
        s = {
            'min_volume_usdt': int(self.volume_spin.value()),
            'min_market_cap': int(mn), 'max_market_cap': int(mx),
            'max_coins': self.max_coins_spin.value(),
            'scan_interval_min': self.interval_spin.value(),
            'timeframes': [k for k,v in self.tf_checks.items() if v.isChecked()],
            'min_signal_count': self.min_sig_spin.value(),
            'sound_alerts': self.sound_cb.isChecked(),
            'exchange': self.exchange_combo.currentText(),  # YENİ
        }
        for k,cb in self.ind_checks.items(): s[k] = cb.isChecked()
        for k,cb in self.pat_checks.items(): s[k] = cb.isChecked()
        return s


# ============================================================
# SİNYAL DETAY DİYALOĞU (OKX butonu eklendi)
# ============================================================

class SignalDetailDialog(QDialog):
    def __init__(self, scan_result, parent=None):
        super().__init__(parent)
        self.result = scan_result
        self.setWindowTitle(f"📊 {scan_result['symbol']} - Sinyal Detayları")
        self.setMinimumSize(750, 600)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Başlık + grafik butonları
        header_layout = QHBoxLayout()

        symbol_label = QLabel(f"<h2>{self.result['symbol']}</h2>")
        header_layout.addWidget(symbol_label)

        # Borsa + Funding bilgisi
        exchange = self.result.get('exchange', '?')
        funding = self.result.get('funding_rate')
        funding_str = f"{funding:+.4f}%" if funding is not None else "—"
        funding_color = '#FF1744' if funding and funding > 0.01 else '#00C853' if funding and funding < -0.01 else '#FFC107'
        info_label = QLabel(
            f"<span style='font-size:12px; color:#90CAF9'>📡 {exchange}</span>"
            f" &nbsp;|&nbsp; "
            f"<span style='font-size:12px; color:{funding_color}'>💰 Funding: {funding_str}</span>"
        )
        header_layout.addWidget(info_label)

        header_layout.addStretch()

        # ★ TradingView butonu
        chart_btn = QPushButton("📈 TradingView'da Aç")
        chart_btn.setStyleSheet(
            "QPushButton { background-color: #2962FF; color: white; "
            "font-size: 13px; padding: 8px 16px; border-radius: 5px; }"
            "QPushButton:hover { background-color: #1E88E5; }"
        )
        chart_btn.clicked.connect(self.open_tradingview)
        header_layout.addWidget(chart_btn)

        # ★ OKX butonu (YENİ!)
        okx_btn = QPushButton("🔵 OKX'te Aç")
        okx_btn.setStyleSheet(
            "QPushButton { background-color: #121212; color: white; "
            "font-size: 13px; padding: 8px 16px; border-radius: 5px; "
            "border: 1px solid #555; }"
            "QPushButton:hover { background-color: #333; }"
        )
        okx_btn.clicked.connect(self.open_okx)
        header_layout.addWidget(okx_btn)

        # Binance butonu
        binance_btn = QPushButton("🟡 Binance'de Aç")
        binance_btn.setStyleSheet(
            "QPushButton { background-color: #F0B90B; color: black; "
            "font-size: 13px; padding: 8px 16px; border-radius: 5px; }"
            "QPushButton:hover { background-color: #D4A50A; }"
        )
        binance_btn.clicked.connect(self.open_binance)
        header_layout.addWidget(binance_btn)

        layout.addLayout(header_layout)

        # Özet satırı
        r = self.result
        trend_colors = {'BULLISH': '#00C853', 'BEARISH': '#FF1744', 'NEUTRAL': '#FFC107'}
        tc = trend_colors.get(r['dominant_trend'], '#FFC107')

        risk = r.get('risk_level', 1)
        risk_emoji = ['🟢','🟢','🟡','🟠','🔴'][min(risk-1, 4)]
        risk_text = ['Düşük','Düşük','Orta','Yüksek','Çok Yüksek'][min(risk-1, 4)]

        conflict_text = ""
        if r.get('has_conflict'):
            conflict_text = " | <b style='color:#FF6D00'>⚠️ ÇATIŞMA UYARISI</b>"

        summary = QLabel(
            f"<p style='font-size:13px;'>"
            f"Trend: <b style='color:{tc}'>{r['dominant_trend']}</b> | "
            f"Bull: <b style='color:#00C853'>{r['total_bullish']:.0f}</b> | "
            f"Bear: <b style='color:#FF1744'>{r['total_bearish']:.0f}</b> | "
            f"Sinyal: <b>{r['signal_count']}</b> | "
            f"Risk: {risk_emoji} <b>{risk_text}</b>"
            f"{conflict_text}</p>"
        )
        summary.setAlignment(Qt.AlignCenter)
        layout.addWidget(summary)

        # Tab'lar
        tabs = QTabWidget()
        for tf, tf_data in r.get('timeframe_results', {}).items():
            tab = QTextEdit()
            tab.setReadOnly(True)
            text = f"<h3>{tf.upper()} Analizi</h3>"
            text += f"<p>Trend: <b>{tf_data.get('trend', 'N/A')}</b></p>"

            for key, label in [('rsi','RSI'), ('wt1','WaveTrend'),
                                ('bb_bandwidth','BB Bandwidth'), ('t3_trend','T3 Trend')]:
                val = tf_data.get(key)
                if val is not None:
                    if isinstance(val, float):
                        text += f"<p>{label}: <b>{val:.1f}</b></p>"
                    else:
                        text += f"<p>{label}: <b>{val}</b></p>"

            tf_risk = tf_data.get('risk_level', 1)
            text += f"<p>Risk: <b>{tf_risk}/5</b></p>"

            text += "<hr><h4>Sinyaller:</h4>"
            for sig in tf_data.get('signals', []):
                if sig['direction'] == 'WARNING':
                    color = '#FF6D00'
                elif sig['direction'] == 'BULLISH':
                    color = '#00C853'
                elif sig['direction'] == 'BEARISH':
                    color = '#FF1744'
                else:
                    color = '#FFC107'
                text += f"<p style='color:{color}'>● {sig['detail']} (Güç: {sig['strength']:.0%})</p>"

            if not tf_data.get('signals'):
                text += "<p style='color:gray'>Sinyal bulunamadı</p>"

            tab.setHtml(text)
            tabs.addTab(tab, tf.upper())

        layout.addWidget(tabs)

        # Alt butonlar
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def open_tradingview(self):
        """
        ÖĞRETİCİ: TradingView URL formatı
        ─────────────────────────────────
        Borsa prefix'i + sembol + .P (perpetual suffix)
        OKX: OKX:BTCUSDT.P
        Binance: BINANCE:BTCUSDT.P
        """
        symbol = self.result['symbol']
        exchange = self.result.get('exchange', 'Binance')
        exchange_map = {
            'OKX': 'OKX',
            'Binance': 'BINANCE',
            'BingX': 'BINANCE',  # BingX TradingView'da yok, Binance göster
        }
        tv_exchange = exchange_map.get(exchange, 'BINANCE')
        url = f"https://www.tradingview.com/chart/?symbol={tv_exchange}:{symbol}.P"
        webbrowser.open(url)

    def open_okx(self):
        """
        ÖĞRETİCİ: OKX web URL formatı
        ──────────────────────────────
        https://www.okx.com/trade-swap/btc-usdt
        Sembol küçük harf, tire ile ayrılmış
        """
        symbol = self.result['symbol']
        base = symbol.replace('USDT', '').lower()
        url = f"https://www.okx.com/trade-swap/{base}-usdt"
        webbrowser.open(url)

    def open_binance(self):
        symbol = self.result['symbol']
        url = f"https://www.binance.com/en/futures/{symbol}"
        webbrowser.open(url)


# ============================================================
# ANA PENCERE
# ============================================================

class CoinScannerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.scan_results = []
        self.is_scanning = False
        self.auto_scan_active = False
        self.scan_signals = ScanSignals()

        self.setWindowTitle("🔍 Coin Scanner v3.0 — OKX + Binance + BingX")
        self.setMinimumSize(1400, 780)

        self.init_ui()
        self.connect_signals()
        self.auto_timer = QTimer()
        self.auto_timer.timeout.connect(self.start_scan)

    def init_ui(self):
        central = QWidget()
        main_layout = QVBoxLayout()

        # Üst bar
        top = QHBoxLayout()

        self.scan_btn = QPushButton("🔍 Taramayı Başlat")
        self.scan_btn.setStyleSheet(
            "QPushButton{background:#1976D2;color:white;font-size:14px;padding:8px 20px;border-radius:5px}"
            "QPushButton:hover{background:#1565C0}QPushButton:disabled{background:#555}")
        self.scan_btn.clicked.connect(self.start_scan)
        top.addWidget(self.scan_btn)

        self.auto_btn = QPushButton("⏰ Otomatik: KAPALI")
        self.auto_btn.setStyleSheet("QPushButton{background:#388E3C;color:white;font-size:13px;padding:8px 16px;border-radius:5px}")
        self.auto_btn.clicked.connect(self.toggle_auto_scan)
        top.addWidget(self.auto_btn)

        self.stop_btn = QPushButton("⏹ Durdur")
        self.stop_btn.setStyleSheet("QPushButton{background:#D32F2F;color:white;font-size:13px;padding:8px 16px;border-radius:5px}")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_scan)
        top.addWidget(self.stop_btn)

        self.export_btn = QPushButton("💾 CSV Kaydet")
        self.export_btn.setStyleSheet("QPushButton{background:#6A1B9A;color:white;font-size:13px;padding:8px 16px;border-radius:5px}")
        self.export_btn.clicked.connect(self.export_csv)
        self.export_btn.setEnabled(False)
        top.addWidget(self.export_btn)

        top.addStretch()

        # Filtre butonları
        for text, filt in [("Tümü",'ALL'), ("🟢 Bullish",'BULLISH'),
                            ("🔴 Bearish",'BEARISH'), ("⚠️ Çatışma",'CONFLICT')]:
            btn = QPushButton(text)
            btn.clicked.connect(lambda checked, f=filt: self.filter_results(f))
            top.addWidget(btn)

        self.count_label = QLabel("Sonuç: 0")
        self.count_label.setStyleSheet("font-size:13px;font-weight:bold;")
        top.addWidget(self.count_label)

        # Aktif borsa göstergesi
        self.exchange_label = QLabel("📡 —")
        self.exchange_label.setStyleSheet("font-size:12px;color:#90CAF9;")
        top.addWidget(self.exchange_label)

        main_layout.addLayout(top)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        main_layout.addWidget(self.progress)

        # Ana içerik
        splitter = QSplitter(Qt.Horizontal)

        self.settings_panel = SettingsPanel(self.settings)
        splitter.addWidget(self.settings_panel)

        right = QWidget()
        rl = QVBoxLayout()
        rl.setContentsMargins(0,0,0,0)

        # Tablo — 13 sütun (Funding eklendi)
        self.table = QTableWidget()
        self.table.setColumnCount(13)
        self.table.setHorizontalHeaderLabels([
            'Sembol', 'Fiyat', '%', 'Trend', 'Risk',
            'Bull', 'Bear', 'Sinyal', 'RSI(4H)',
            'BB Squeeze', 'Funding%', 'MCap', 'Vol(24H)'
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.show_detail)
        self.table.setStyleSheet("""
            QTableWidget{gridline-color:#333;font-size:12px;alternate-background-color:#1a1a2e;
                         background-color:#0f0f23;color:#e0e0e0;}
            QHeaderView::section{background-color:#16213e;color:#e0e0e0;padding:6px;
                                  font-weight:bold;border:1px solid #333;}
        """)
        rl.addWidget(self.table, stretch=3)

        # Log
        lg = QGroupBox("📋 Log")
        ll = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(140)
        self.log_text.setStyleSheet("QTextEdit{background:#0a0a1a;color:#00ff88;font-family:Consolas;font-size:11px;}")
        ll.addWidget(self.log_text)
        lg.setLayout(ll)
        rl.addWidget(lg, stretch=1)

        right.setLayout(rl)
        splitter.addWidget(right)
        splitter.setSizes([280, 1120])
        main_layout.addWidget(splitter)

        central.setLayout(main_layout)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Hazır. BASLAT'a tıklayın veya otomatik taramayı açın.")

        # Dark theme
        self.setStyleSheet("""
            QMainWindow,QWidget{background-color:#0f0f23;color:#e0e0e0;}
            QGroupBox{border:1px solid #333;border-radius:5px;margin-top:10px;padding-top:15px;font-weight:bold;color:#90CAF9;}
            QGroupBox::title{subcontrol-origin:margin;padding:0 5px;}
            QCheckBox{spacing:5px;padding:2px;} QCheckBox::indicator{width:15px;height:15px;}
            QSpinBox,QDoubleSpinBox,QComboBox{background:#1a1a2e;border:1px solid #333;padding:3px;border-radius:3px;color:#e0e0e0;}
            QProgressBar{border:1px solid #333;border-radius:3px;text-align:center;background:#1a1a2e;color:white;font-weight:bold;}
            QProgressBar::chunk{background:#1976D2;}
            QPushButton{border-radius:4px;padding:5px 12px;}
        """)

    def connect_signals(self):
        self.scan_signals.progress.connect(self.on_progress)
        self.scan_signals.finished.connect(self.on_finished)
        self.scan_signals.error.connect(self.on_error)

    def log(self, msg):
        self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    # --- Tarama ---

    def start_scan(self):
        if self.is_scanning:
            return
        self.is_scanning = True
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        settings = self.settings_panel.get_settings()
        save_settings(settings)

        exchange = settings.get('exchange', 'Otomatik')
        self.log(f"🔍 Tarama başlatılıyor... (Borsa: {exchange})")
        self.log(f"   Max {settings['max_coins']} coin | TF: {', '.join(settings['timeframes'])}")

        def scan_thread():
            try:
                ind = {k:v for k,v in settings.items() if k in [
                    'use_rsi','use_wavetrend','use_bb','use_t3','use_volume']}
                pat = {k:v for k,v in settings.items() if k in [
                    'use_hammer','use_hanging','use_doji','use_marubozu','use_morning','use_evening']}

                results = run_full_scan(
                    min_volume_usdt=settings['min_volume_usdt'],
                    min_market_cap=settings.get('min_market_cap', 0),
                    max_market_cap=settings.get('max_market_cap', 0),
                    max_coins=settings['max_coins'],
                    timeframes=settings['timeframes'],
                    indicator_settings=ind, pattern_settings=pat,
                    progress_callback=lambda s,c,t: self.scan_signals.progress.emit(s,c,t),
                    exchange=exchange,
                )
                filtered = [r for r in results if r['signal_count'] >= settings.get('min_signal_count', 1)]
                self.scan_signals.finished.emit(filtered)
            except Exception as e:
                self.scan_signals.error.emit(str(e))

        threading.Thread(target=scan_thread, daemon=True).start()

    def stop_scan(self):
        self.is_scanning = False
        self.auto_scan_active = False
        self.auto_timer.stop()
        self.auto_btn.setText("⏰ Otomatik: KAPALI")
        self.auto_btn.setStyleSheet("QPushButton{background:#388E3C;color:white;font-size:13px;padding:8px 16px;border-radius:5px}")
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress.setVisible(False)
        self.log("⏹ Durduruldu.")

    def toggle_auto_scan(self):
        if self.auto_scan_active:
            self.auto_scan_active = False
            self.auto_timer.stop()
            self.auto_btn.setText("⏰ Otomatik: KAPALI")
            self.auto_btn.setStyleSheet("QPushButton{background:#388E3C;color:white;font-size:13px;padding:8px 16px;border-radius:5px}")
            self.log("⏰ Otomatik tarama kapatıldı.")
        else:
            self.auto_scan_active = True
            interval = self.settings_panel.interval_spin.value()
            self.auto_timer.start(interval * 60 * 1000)
            self.auto_btn.setText(f"⏰ Otomatik: AÇIK ({interval}dk)")
            self.auto_btn.setStyleSheet("QPushButton{background:#F57F17;color:white;font-size:13px;padding:8px 16px;border-radius:5px}")
            self.log(f"⏰ Otomatik tarama açıldı ({interval} dk aralıklarla).")
            self.start_scan()

    def on_progress(self, symbol, current, total):
        pct = int(current / total * 100) if total > 0 else 0
        self.progress.setValue(pct)
        self.progress.setFormat(f"{symbol} ({current}/{total})")

    def on_finished(self, results):
        self.is_scanning = False
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress.setVisible(False)
        self.export_btn.setEnabled(True)

        self.scan_results = results
        self.update_table(results)

        bull = sum(1 for r in results if r['dominant_trend'] == 'BULLISH')
        bear = sum(1 for r in results if r['dominant_trend'] == 'BEARISH')
        conflicts = sum(1 for r in results if r.get('has_conflict'))

        # Aktif borsa
        active_ex = results[0].get('exchange', '?') if results else '?'
        self.exchange_label.setText(f"📡 {active_ex}")

        self.log(f"✅ {len(results)} coin sinyal verdi. 🟢{bull} 🔴{bear} ⚠️{conflicts} çatışma ({active_ex})")
        self.statusBar().showMessage(
            f"Son tarama: {datetime.now().strftime('%H:%M:%S')} | "
            f"{len(results)} sonuç | 🟢{bull} 🔴{bear} ⚠️{conflicts} | 📡{active_ex}")

        if self.settings_panel.sound_cb.isChecked() and len(results) > 0:
            self._play_alert_sound()

    def on_error(self, msg):
        self.is_scanning = False
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress.setVisible(False)
        self.log(f"❌ HATA: {msg}")

    def _play_alert_sound(self):
        try:
            if sys.platform == 'win32':
                import winsound
                winsound.Beep(800, 300)
                winsound.Beep(1000, 200)
        except:
            print('\a')

    # --- Tablo ---

    def update_table(self, results):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(results))

        for row, r in enumerate(results):
            col = 0

            # Sembol
            item = QTableWidgetItem(r['symbol'].replace('USDT', ''))
            item.setFont(QFont('Consolas', 11, QFont.Bold))
            if r.get('has_conflict'):
                item.setForeground(QColor('#FF6D00'))
            self.table.setItem(row, col, item); col += 1

            # Fiyat
            price = r.get('price', 0)
            item = QTableWidgetItem(f"${price:,.4f}" if price < 1 else f"${price:,.2f}")
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, col, item); col += 1

            # Değişim
            chg = r.get('price_change_pct', 0)
            item = QTableWidgetItem(f"{chg:+.2f}%")
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item.setForeground(QColor('#00C853') if chg >= 0 else QColor('#FF1744'))
            self.table.setItem(row, col, item); col += 1

            # Trend
            trend = r['dominant_trend']
            item = QTableWidgetItem(trend)
            item.setTextAlignment(Qt.AlignCenter)
            tc = {'BULLISH':'#00C853', 'BEARISH':'#FF1744'}.get(trend, '#FFC107')
            item.setForeground(QColor(tc))
            if trend == 'BULLISH':
                item.setBackground(QColor(0,200,83,30))
            elif trend == 'BEARISH':
                item.setBackground(QColor(255,23,68,30))
            self.table.setItem(row, col, item); col += 1

            # Risk
            risk = r.get('risk_level', 1)
            risk_labels = ['1-Düşük','2-Düşük','3-Orta','4-Yüksek','5-Çok Yüksek']
            item = QTableWidgetItem(risk_labels[min(risk-1, 4)])
            item.setData(Qt.UserRole, risk)
            item.setTextAlignment(Qt.AlignCenter)
            risk_colors = ['#00C853','#00C853','#FFC107','#FF6D00','#FF1744']
            item.setForeground(QColor(risk_colors[min(risk-1, 4)]))
            if risk >= 4:
                item.setFont(QFont('Consolas', 10, QFont.Bold))
            self.table.setItem(row, col, item); col += 1

            # Bullish
            item = QTableWidgetItem(f"{r['total_bullish']:.0f}")
            item.setData(Qt.UserRole, r['total_bullish'])
            item.setTextAlignment(Qt.AlignCenter)
            if r['total_bullish'] > 50:
                item.setForeground(QColor('#00C853'))
                item.setFont(QFont('Consolas', 11, QFont.Bold))
            self.table.setItem(row, col, item); col += 1

            # Bearish
            item = QTableWidgetItem(f"{r['total_bearish']:.0f}")
            item.setData(Qt.UserRole, r['total_bearish'])
            item.setTextAlignment(Qt.AlignCenter)
            if r['total_bearish'] > 50:
                item.setForeground(QColor('#FF1744'))
                item.setFont(QFont('Consolas', 11, QFont.Bold))
            self.table.setItem(row, col, item); col += 1

            # Sinyal sayısı
            item = QTableWidgetItem(str(r['signal_count']))
            item.setData(Qt.UserRole, r['signal_count'])
            item.setTextAlignment(Qt.AlignCenter)
            if r['signal_count'] >= 5:
                item.setForeground(QColor('#FFD600'))
                item.setFont(QFont('Consolas', 11, QFont.Bold))
            self.table.setItem(row, col, item); col += 1

            # RSI (4H)
            rsi = None
            if '4h' in r.get('timeframe_results', {}):
                rsi = r['timeframe_results']['4h'].get('rsi')
            item = QTableWidgetItem(f"{rsi:.1f}" if rsi else "—")
            item.setTextAlignment(Qt.AlignCenter)
            if rsi:
                item.setData(Qt.UserRole, rsi)
                if rsi >= 70: item.setForeground(QColor('#FF1744'))
                elif rsi <= 30: item.setForeground(QColor('#00C853'))
            self.table.setItem(row, col, item); col += 1

            # BB Squeeze
            has_sq = any('SQUEEZE' in s['type'] for s in r['all_signals'])
            bb_bw = None
            if '4h' in r.get('timeframe_results', {}):
                bb_bw = r['timeframe_results']['4h'].get('bb_bandwidth')
            sq_text = f"{bb_bw:.2f}%" if bb_bw else "—"
            if has_sq: sq_text += " 🔥"
            item = QTableWidgetItem(sq_text)
            item.setTextAlignment(Qt.AlignCenter)
            if has_sq:
                item.setForeground(QColor('#FFD600'))
                item.setFont(QFont('Consolas', 10, QFont.Bold))
            self.table.setItem(row, col, item); col += 1

            # ★ Funding Rate (YENİ!)
            funding = r.get('funding_rate')
            if funding is not None:
                item = QTableWidgetItem(f"{funding:+.4f}%")
                item.setData(Qt.UserRole, funding)
                # Pozitif funding = long'lar ödüyor (bearish sinyal)
                # Negatif funding = short'lar ödüyor (bullish sinyal)
                if funding > 0.05:
                    item.setForeground(QColor('#FF1744'))
                    item.setFont(QFont('Consolas', 10, QFont.Bold))
                elif funding < -0.05:
                    item.setForeground(QColor('#00C853'))
                    item.setFont(QFont('Consolas', 10, QFont.Bold))
                else:
                    item.setForeground(QColor('#FFC107'))
            else:
                item = QTableWidgetItem("—")
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col, item); col += 1

            # Market Cap
            mc = r.get('market_cap', 0)
            if mc >= 1e9: mc_text = f"${mc/1e9:.1f}B"
            elif mc >= 1e6: mc_text = f"${mc/1e6:.0f}M"
            elif mc > 0: mc_text = f"${mc/1e3:.0f}K"
            else: mc_text = "—"
            item = QTableWidgetItem(mc_text)
            item.setData(Qt.UserRole, mc)
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, col, item); col += 1

            # Volume
            vol = r.get('volume_usdt', 0)
            if vol >= 1e9: v_text = f"${vol/1e9:.1f}B"
            elif vol >= 1e6: v_text = f"${vol/1e6:.0f}M"
            else: v_text = f"${vol/1e3:.0f}K"
            item = QTableWidgetItem(v_text)
            item.setData(Qt.UserRole, vol)
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, col, item)

        self.table.setSortingEnabled(True)
        self.count_label.setText(f"Sonuç: {len(results)}")

    def filter_results(self, direction):
        if direction == 'ALL':
            self.update_table(self.scan_results)
        elif direction == 'CONFLICT':
            self.update_table([r for r in self.scan_results if r.get('has_conflict')])
        else:
            self.update_table([r for r in self.scan_results if r['dominant_trend'] == direction])

    def show_detail(self, index):
        row = index.row()
        sym_item = self.table.item(row, 0)
        if not sym_item:
            return
        symbol = sym_item.text() + "USDT"
        for r in self.scan_results:
            if r['symbol'] == symbol:
                SignalDetailDialog(r, self).exec_()
                break

    def export_csv(self):
        if not self.scan_results:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "CSV Olarak Kaydet",
            f"scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            "CSV Files (*.csv)"
        )
        if filepath:
            export_to_csv(self.scan_results, filepath)
            self.log(f"💾 CSV kaydedildi: {filepath}")

    def closeEvent(self, event):
        save_settings(self.settings_panel.get_settings())
        event.accept()


# ============================================================
# BAŞLATICI
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = CoinScannerApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
