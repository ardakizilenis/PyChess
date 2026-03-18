import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout
)


class CapturedPieces(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        layout.addWidget(QLabel("White captured:"))
        self.black_row = QWidget()
        self.black_row_layout = QHBoxLayout()
        self.black_row_layout.setContentsMargins(0, 0, 0, 0)
        self.black_row_layout.setSpacing(8)
        self.black_row.setLayout(self.black_row_layout)

        self.black_container = QWidget()
        self.black_layout = QHBoxLayout()
        self.black_layout.setContentsMargins(0, 0, 0, 0)
        self.black_layout.setSpacing(4)
        self.black_container.setLayout(self.black_layout)
        self.black_row_layout.addWidget(self.black_container)

        self.black_material_label = QLabel("")
        self.black_row_layout.addWidget(self.black_material_label)
        self.black_row_layout.addStretch()
        layout.addWidget(self.black_row)

        layout.addWidget(QLabel("Black captured:"))
        self.white_row = QWidget()
        self.white_row_layout = QHBoxLayout()
        self.white_row_layout.setContentsMargins(0, 0, 0, 0)
        self.white_row_layout.setSpacing(8)
        self.white_row.setLayout(self.white_row_layout)

        self.white_container = QWidget()
        self.white_layout = QHBoxLayout()
        self.white_layout.setContentsMargins(0, 0, 0, 0)
        self.white_layout.setSpacing(4)
        self.white_container.setLayout(self.white_layout)
        self.white_row_layout.addWidget(self.white_container)

        self.white_material_label = QLabel("")
        self.white_row_layout.addWidget(self.white_material_label)
        self.white_row_layout.addStretch()
        layout.addWidget(self.white_row)


        self.white_captured = []
        self.black_captured = []
        self.icon_size = 20
        self.assets_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "pieces"
        )

        layout.addStretch()
        self.setLayout(layout)

    def update_captured_pieces(self, board):
        if not isinstance(board, list) or len(board) != 8:
            return

        initial_white = ["wP"] * 8 + ["wR"] * 2 + ["wN"] * 2 + ["wB"] * 2 + ["wQ"] + ["wK"]
        initial_black = ["bP"] * 8 + ["bR"] * 2 + ["bN"] * 2 + ["bB"] * 2 + ["bQ"] + ["bK"]

        current_white = []
        current_black = []

        for row in board:
            for piece in row:
                if piece is None:
                    continue
                if isinstance(piece, str) and piece.startswith("w"):
                    current_white.append(piece)
                elif isinstance(piece, str) and piece.startswith("b"):
                    current_black.append(piece)

        white_left = current_white.copy()
        black_left = current_black.copy()

        white_captured = []
        for piece in initial_white:
            if piece in white_left:
                white_left.remove(piece)
            else:
                white_captured.append(piece)

        black_captured = []
        for piece in initial_black:
            if piece in black_left:
                black_left.remove(piece)
            else:
                black_captured.append(piece)

        self.white_captured = white_captured
        self.black_captured = black_captured
        self.render_captured_pieces()

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def get_piece_value(self, piece_code):
        values = {
            "P": 1,
            "N": 3,
            "B": 3,
            "R": 5,
            "Q": 9,
            "K": 0,
        }
        return values.get(piece_code[1], 0)

    def get_material_text(self, own_captured, opponent_captured):
        own_value = sum(self.get_piece_value(piece) for piece in own_captured)
        opponent_value = sum(self.get_piece_value(piece) for piece in opponent_captured)
        diff = own_value - opponent_value

        if diff > 0:
            return f"+{diff}"
        return ""

    def create_piece_label(self, piece_code):
        label = QLabel()
        piece_path = os.path.join(self.assets_path, f"{piece_code}.png")
        pixmap = QPixmap(piece_path)

        if pixmap.isNull():
            label.setText(piece_code)
            return label

        label.setPixmap(
            pixmap.scaled(
                self.icon_size,
                self.icon_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )
        return label

    def render_piece_row(self, layout, pieces):
        self.clear_layout(layout)

        if not pieces:
            empty_label = QLabel("-")
            layout.addWidget(empty_label)
            return

        for piece_code in pieces:
            layout.addWidget(self.create_piece_label(piece_code))

    def render_captured_pieces(self):
        self.render_piece_row(self.white_layout, self.white_captured)
        self.render_piece_row(self.black_layout, self.black_captured)

        self.white_material_label.setText(
            self.get_material_text(self.white_captured, self.black_captured)
        )
        self.black_material_label.setText(
            self.get_material_text(self.black_captured, self.white_captured)
        )