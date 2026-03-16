from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout
)

from network.NetworkClient import NetworkClient
from view.BoardView import ChessBoard
from view.ChatView import ChatWidget
from view.CapturedListView import CapturedPieces


class ChessClient(QMainWindow):

    def __init__(self, client: NetworkClient):
        super().__init__()

        self.setWindowTitle("PyChess")

        self.client = client

        main_widget = QWidget()
        main_layout = QHBoxLayout()

        # Chessboard
        self.board = ChessBoard(client)

        # Right panel
        right_panel = QVBoxLayout()

        self.captured = CapturedPieces()
        self.client.captured_pieces_updated.connect(self.captured.update_captured_pieces)
        self.chat = ChatWidget(self.client)

        right_panel.addWidget(self.captured)
        right_panel.addWidget(self.chat)

        main_layout.addWidget(self.board)
        main_layout.addLayout(right_panel)

        main_widget.setLayout(main_layout)

        self.setCentralWidget(main_widget)