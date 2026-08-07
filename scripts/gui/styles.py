"""Feuille de style sombre pour Arch's Auto Clipping."""

APP_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Ubuntu", sans-serif;
    font-size: 13px;
}
QLabel#titleLabel {
    font-size: 20px;
    font-weight: bold;
    color: #89b4fa;
    padding: 4px 0;
}
QLabel#statusLabel {
    color: #a6adc8;
    padding: 2px 0;
}
QTextEdit#logView {
    background-color: #11111b;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 8px;
    font-family: "Consolas", "Cascadia Mono", "DejaVu Sans Mono", monospace;
    font-size: 12px;
}
QProgressBar {
    border: 1px solid #313244;
    border-radius: 6px;
    background-color: #11111b;
    text-align: center;
    color: #cdd6f4;
    height: 22px;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 5px;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
    min-width: 100px;
}
QPushButton:hover {
    background-color: #45475a;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton:disabled {
    background-color: #181825;
    color: #585b70;
    border-color: #313244;
}
QPushButton#startBtn {
    background-color: #a6e3a1;
    color: #1e1e2e;
    border-color: #a6e3a1;
}
QPushButton#startBtn:hover {
    background-color: #94e2d5;
}
QPushButton#startBtn:disabled {
    background-color: #181825;
    color: #585b70;
    border-color: #313244;
}
QPushButton#pauseBtn {
    background-color: #f9e2af;
    color: #1e1e2e;
    border-color: #f9e2af;
}
QPushButton#pauseBtn:hover {
    background-color: #f5c2e7;
}
QPushButton#pauseBtn:disabled {
    background-color: #181825;
    color: #585b70;
    border-color: #313244;
}
QPushButton#stopBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
    border-color: #f38ba8;
}
QPushButton#stopBtn:hover {
    background-color: #eba0ac;
}
QPushButton#stopBtn:disabled {
    background-color: #181825;
    color: #585b70;
    border-color: #313244;
}
"""
