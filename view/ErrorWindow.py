import sys

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton

from network.NetworkClient import NetworkClient
from view.MainWindow import ChessClient


class ErrorWidget(QWidget):
    def __init__(self, title: str, message: str):
        super().__init__()

        self.setWindowTitle(title)
        self.setMinimumSize(300, 120)

        layout = QVBoxLayout()

        label = QLabel(message)
        label.setWordWrap(True)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)

        layout.addWidget(label)
        layout.addWidget(close_btn)

        self.setLayout(layout)
