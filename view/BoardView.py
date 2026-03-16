import os

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QGridLayout, QPushButton
)

from model.Game import Game
from network.NetworkClient import NetworkClient

class ChessBoard(QWidget):
    def __init__(self, network_client: NetworkClient):
        super().__init__()
        self.squares = [[None for _ in range(8)] for _ in range(8)]
        self.client = network_client
        self.selected_square = None
        self.current_board = None
        self.legal_moves = []

        self.square_size = 70
        self.assets_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "assets",
            "pieces"
        )

        layout = QGridLayout()
        layout.setSpacing(0)

        for row in range(8):
            for col in range(8):
                square = QPushButton()
                square.setFixedSize(self.square_size, self.square_size)

                square.setStyleSheet(self.get_square_style(row, col))

                square.clicked.connect(lambda _, r=row, c=col: self.on_square_clicked(r, c))
                layout.addWidget(square, row, col)
                self.squares[row][col] = square
                square.setIconSize(square.size())

        self.setLayout(layout)
        self.setFixedSize(self.square_size * 8, self.square_size * 8)

        self.client.board_updated.connect(self.update_board)

    def get_piece_icon(self, piece_code: str) -> QIcon:
        piece_path = os.path.join(self.assets_path, f"{piece_code}.png")
        pixmap = QPixmap(piece_path)
        return QIcon(pixmap)

    def clear_board(self):
        for row in range(8):
            for col in range(8):
                self.squares[row][col].setIcon(QIcon())
                self.squares[row][col].setText("")

    def get_base_square_color(self, row, col):
        return "#EEEED2" if (row + col) % 2 == 0 else "#769656"

    def get_square_style(self, row, col, highlight=None):
        color = self.get_base_square_color(row, col)

        if highlight == "selected":
            color = "#F6F669"
        elif highlight == "legal":
            color = "#BACA44"
        elif highlight == "check":
            color = "#F4A261"
        elif highlight == "checkmate":
            color = "#E63946"

        return f"background-color: {color};"

    def build_temp_game(self):
        if self.current_board is None:
            return None

        game = Game()
        game.board = [row[:] for row in self.current_board]

        if self.client.latest_game_status:
            turn = self.client.latest_game_status.get("turn")
            if turn in ("white", "black"):
                game.turn = turn

            en_passant_target = self.client.latest_game_status.get("en_passant_target")
            if isinstance(en_passant_target, list) and len(en_passant_target) == 2:
                game.en_passant_target = (en_passant_target[0], en_passant_target[1])
            elif isinstance(en_passant_target, tuple) and len(en_passant_target) == 2:
                game.en_passant_target = en_passant_target
            else:
                game.en_passant_target = None

            castling_rights = self.client.latest_game_status.get("castling_rights")
            if isinstance(castling_rights, dict):
                game.castling_rights = {
                    "white": {
                        "king_side": bool(castling_rights.get("white", {}).get("king_side", True)),
                        "queen_side": bool(castling_rights.get("white", {}).get("queen_side", True)),
                    },
                    "black": {
                        "king_side": bool(castling_rights.get("black", {}).get("king_side", True)),
                        "queen_side": bool(castling_rights.get("black", {}).get("queen_side", True)),
                    },
                }

        return game

    def get_legal_moves_for_square(self, from_pos):
        game = self.build_temp_game()
        if game is None:
            return []

        legal_moves = []
        for row in range(8):
            for col in range(8):
                if game.is_legal_move(from_pos, (row, col)):
                    legal_moves.append((row, col))
        return legal_moves

    def get_king_square_for_status(self):
        status_content = self.client.latest_game_status
        if not status_content:
            return None, None

        status = status_content.get("status")
        if status == "check_white":
            king_code = "wK"
            highlight = "check"
        elif status == "check_black":
            king_code = "bK"
            highlight = "check"
        elif status == "checkmate_white_wins":
            king_code = "bK"
            highlight = "checkmate"
        elif status == "checkmate_black_wins":
            king_code = "wK"
            highlight = "checkmate"
        else:
            return None, None

        if self.current_board is None:
            return None, None

        for row in range(8):
            for col in range(8):
                if self.current_board[row][col] == king_code:
                    return (row, col), highlight

        return None, None

    def apply_square_styles(self):
        king_square, king_highlight = self.get_king_square_for_status()

        for display_row in range(8):
            for display_col in range(8):
                real_row, real_col = self.to_real_coordinates(display_row, display_col)
                highlight = None

                if self.selected_square == (real_row, real_col):
                    highlight = "selected"
                elif (real_row, real_col) in self.legal_moves:
                    highlight = "legal"

                if king_square == (real_row, real_col):
                    highlight = king_highlight

                self.squares[display_row][display_col].setStyleSheet(
                    self.get_square_style(display_row, display_col, highlight)
                )

    def get_display_board(self, board):
        if self.client.my_color == "black":
            return [list(reversed(row)) for row in reversed(board)]
        return board

    def to_real_coordinates(self, row, col):
        if self.client.my_color == "black":
            return 7 - row, 7 - col
        return row, col

    def on_square_clicked(self, row, col):
        if self.current_board is None:
            return

        real_row, real_col = self.to_real_coordinates(row, col)

        if self.selected_square is None:
            piece_code = self.current_board[real_row][real_col]
            if piece_code is None:
                return

            if self.client.my_color == "white" and not piece_code.startswith("w"):
                return
            if self.client.my_color == "black" and not piece_code.startswith("b"):
                return

            status_turn = None
            if self.client.latest_game_status:
                status_turn = self.client.latest_game_status.get("turn")

            if status_turn is not None and status_turn != self.client.my_color:
                return

            self.selected_square = (real_row, real_col)
            self.legal_moves = self.get_legal_moves_for_square(self.selected_square)
            self.apply_square_styles()
            return

        from_row, from_col = self.selected_square
        to_row, to_col = real_row, real_col

        if (from_row, from_col) == (to_row, to_col):
            self.selected_square = None
            self.legal_moves = []
            self.apply_square_styles()
            return

        if (to_row, to_col) not in self.legal_moves:
            piece_code = self.current_board[real_row][real_col]
            if piece_code is not None:
                if self.client.my_color == "white" and piece_code.startswith("w"):
                    self.selected_square = (real_row, real_col)
                    self.legal_moves = self.get_legal_moves_for_square(self.selected_square)
                    self.apply_square_styles()
                    return
                if self.client.my_color == "black" and piece_code.startswith("b"):
                    self.selected_square = (real_row, real_col)
                    self.legal_moves = self.get_legal_moves_for_square(self.selected_square)
                    self.apply_square_styles()
                    return

            self.selected_square = None
            self.legal_moves = []
            self.apply_square_styles()
            return

        self.client.send_move(from_row, from_col, to_row, to_col)
        self.selected_square = None
        self.legal_moves = []
        self.apply_square_styles()

    def update_board(self, board=None):
        if board is None:
            return

        if not isinstance(board, list) or len(board) != 8:
            return

        self.current_board = board
        self.selected_square = None
        self.legal_moves = []

        display_board = self.get_display_board(board)

        self.clear_board()

        for row in range(8):
            for col in range(8):
                piece_code = display_board[row][col]
                if piece_code:
                    self.squares[row][col].setIcon(self.get_piece_icon(piece_code))

        self.apply_square_styles()