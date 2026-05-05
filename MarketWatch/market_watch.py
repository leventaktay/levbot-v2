import sys
import os
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, Qt
from PyQt5.QtGui import QIcon

def resource_path(filename):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

class MarketWatch(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Global Market Watch')
        self.setFixedWidth(440)
        self.resize(440, 900)

        # Her zaman üstte
        

        # WebView
        self.browser = QWebEngineView()
        html_path = resource_path('market_watch.html')
        self.browser.setUrl(QUrl.fromLocalFile(html_path))
        self.setCentralWidget(self.browser)

        # Sağ alt köşeye yerleştir
        from PyQt5.QtWidgets import QDesktopWidget
        screen = QDesktopWidget().screenGeometry()
        self.move(screen.width() - 460, screen.height() - 950)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName('MarketWatch')
    window = MarketWatch()
    window.show()
    sys.exit(app.exec_())
