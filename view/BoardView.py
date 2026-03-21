import os

from PySide6.QtCore import QEvent, QEasingCurve, QPoint, QPropertyAnimation, Qt, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
)

from model.Game import Game
from network.NetworkClient import NetworkClient

class PromotionDialog(QDialog):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Promotion")
        self.setModal(True)
        self.selected_piece_type = None

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Choose the piece for pawn promotion:"))

        button_row = QHBoxLayout()
        piece_types = ["Q", "R", "B", "N"]
        piece_labels = {
            "Q": "Queen",
            "R": "Rook",
            "B": "Bishop",
            "N": "Knight",
        }

        for piece_type in piece_types:
            button = QPushButton(piece_labels[piece_type])
            button.clicked.connect(lambda _, pt=piece_type: self._select_piece(pt))
            button_row.addWidget(button)

        layout.addLayout(button_row)
        self.setLayout(layout)

    def _select_piece(self, piece_type: str):
        self.selected_piece_type = piece_type
        self.accept()

    @staticmethod
    def get_promotion_piece(color: str, parent=None) -> str | None:
        dialog = PromotionDialog(color, parent)
        if dialog.exec() == QDialog.Accepted:
            return dialog.selected_piece_type
        return None

class ChessBoard(QWidget):
    BOARD_SIZE = 8
    DEFAULT_SQUARE_SIZE = 70
    DEFAULT_THEME = "Classic"

    THEME_COLORS = {
        "Classic": {
            "light": "#EEEED2",
            "dark": "#769656",
            "last_move": "#F7E36D",
            "selected": "#F6F669",
            "legal": "#BACA44",
            "check": "#F4A261",
            "checkmate": "#E63946",
            "background": "#2B2B2B",
        },
        "Walnut": {
            "light": "#EBD8B7",
            "dark": "#8B5E3C",
            "last_move": "#F4D35E",
            "selected": "#F6BD60",
            "legal": "#B5C99A",
            "check": "#EE964B",
            "checkmate": "#D1495B",
            "background": "#2A2118",
        },
        "Noir": {
            "light": "#E6D7B8",
            "dark": "#1A1A1A",
            "last_move": "#C8A95B",
            "selected": "#E6C86E",
            "legal": "#8FA27A",
            "check": "#C97A4A",
            "checkmate": "#B85C5C",
            "background": "#121212",
        },
        "Emerald": {
            "light": "#DCE7D0",
            "dark": "#4E6B50",
            "last_move": "#D8C36A",
            "selected": "#E6D36F",
            "legal": "#98B77B",
            "check": "#D08C60",
            "checkmate": "#B85C5C",
            "background": "#1A241B",
        },
        "Slate": {
            "light": "#D8DDE0",
            "dark": "#5D676F",
            "last_move": "#C9B86A",
            "selected": "#DCC86E",
            "legal": "#91A58A",
            "check": "#C88462",
            "checkmate": "#B65C5C",
            "background": "#1C2024",
        }
    }

    def __init__(self, network_client: NetworkClient):
        super().__init__()

        self.client = network_client
        self.squares = [[None for _ in range(self.BOARD_SIZE)] for _ in range(self.BOARD_SIZE)]

        self.selected_square = None
        self.current_board = self._create_initial_board_state()
        self.legal_moves = []
        self.last_move_squares = []

        self.drag_origin_square = None
        self.dragged_piece_code = None
        self.drag_start_global_pos = None
        self.drag_overlay = None
        self.drag_active = False
        self.suppress_next_click = False

        self.move_animation = None
        self.move_animation_label = None
        self.pending_animation_target = None
        self.pending_animation_piece_code = None
        self.queued_board_update = None
        self.skip_next_animation = False

        self.square_size = self.DEFAULT_SQUARE_SIZE
        self.piece_icon_size = QSize(int(self.square_size * 0.7), int(self.square_size * 0.7))
        self.theme_name = self.DEFAULT_THEME
        self.theme_colors = self.THEME_COLORS
        self.review_mode = False
        self.assets_path = os.path.join(os.path.dirname(__file__), "..", "assets", "pieces")

        self._build_board()
        self.set_theme(self.theme_name)
        self.setFixedSize(self.square_size * self.BOARD_SIZE, self.square_size * self.BOARD_SIZE)
        self.update_board(self.current_board)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _create_initial_board_state(self):
        return [
            ["bR", "bN", "bB", "bQ", "bK", "bB", "bN", "bR"],
            ["bP", "bP", "bP", "bP", "bP", "bP", "bP", "bP"],
            [None, None, None, None, None, None, None, None],
            [None, None, None, None, None, None, None, None],
            [None, None, None, None, None, None, None, None],
            [None, None, None, None, None, None, None, None],
            ["wP", "wP", "wP", "wP", "wP", "wP", "wP", "wP"],
            ["wR", "wN", "wB", "wQ", "wK", "wB", "wN", "wR"],
        ]

    def _build_board(self):
        layout = QGridLayout()
        layout.setSpacing(0)

        for row in range(self.BOARD_SIZE):
            for col in range(self.BOARD_SIZE):
                square = self._create_square_button(row, col)
                layout.addWidget(square, row, col)
                self.squares[row][col] = square

        self.setLayout(layout)

    def _create_square_button(self, row: int, col: int) -> QPushButton:
        square = QPushButton()
        square.setFixedSize(self.square_size, self.square_size)
        square.setStyleSheet(self.get_square_style(row, col))
        square.setProperty("display_row", row)
        square.setProperty("display_col", col)
        square.setIconSize(self.piece_icon_size)
        square.installEventFilter(self)
        square.clicked.connect(lambda _, r=row, c=col: self.on_square_clicked(r, c))
        return square

    # ------------------------------------------------------------------
    # Piece assets
    # ------------------------------------------------------------------

    def get_piece_icon(self, piece_code: str) -> QIcon:
        piece_path = os.path.join(self.assets_path, f"{piece_code}.png")
        return QIcon(QPixmap(piece_path))

    def get_piece_pixmap(self, piece_code: str) -> QPixmap:
        icon_size = (
            self.squares[0][0].iconSize()
            if self.squares[0][0] is not None
            else QSize(self.square_size, self.square_size)
        )
        piece_path = os.path.join(self.assets_path, f"{piece_code}.png")
        pixmap = QPixmap(piece_path)
        return pixmap.scaled(icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def to_display_coordinates_from_real(self, row, col):
        if self.client.my_color == "black":
            return 7 - row, 7 - col
        return row, col

    def to_real_coordinates(self, row, col):
        if self.client.my_color == "black":
            return 7 - row, 7 - col
        return row, col

    def get_display_board(self, board):
        if self.client.my_color == "black":
            return [list(reversed(row)) for row in reversed(board)]
        return board

    # ------------------------------------------------------------------
    # Interaction permissions
    # ------------------------------------------------------------------

    def is_players_piece(self, row, col):
        piece_code = self.get_piece_at(row, col)
        if piece_code is None:
            return False

        if self.client.my_color == "white":
            return piece_code.startswith("w")
        if self.client.my_color == "black":
            return piece_code.startswith("b")
        return False

    def can_interact_with_piece(self, row, col):
        if not self.client_can_play():
            return False

        if not self.is_players_piece(row, col):
            return False

        status_turn = self.get_status_turn()
        if status_turn is not None and status_turn != self.client.my_color:
            return False

        return True

    def client_can_play(self) -> bool:
        return bool(getattr(self.client, "can_play", False)) and not self.review_mode

    def get_status_turn(self):
        if self.client.latest_game_status:
            return self.client.latest_game_status.get("turn")
        return None

    def get_piece_at(self, row, col):
        if self.current_board is None:
            return None
        return self.current_board[row][col]

    def is_own_piece_code(self, piece_code: str | None) -> bool:
        if piece_code is None:
            return False
        if self.client.my_color == "white":
            return piece_code.startswith("w")
        if self.client.my_color == "black":
            return piece_code.startswith("b")
        return False

    # ------------------------------------------------------------------
    # Drag handling
    # ------------------------------------------------------------------

    def start_drag(self, global_pos: QPoint):
        if self.drag_origin_square is None or self.dragged_piece_code is None:
            return

        self.drag_active = True
        self.selected_square = self.drag_origin_square
        self.legal_moves = self.get_legal_moves_for_square(self.selected_square)

        display_row, display_col = self.to_display_coordinates_from_real(*self.drag_origin_square)
        self.squares[display_row][display_col].setIcon(QIcon())

        self.drag_overlay = self._create_drag_overlay(self.dragged_piece_code)
        self.update_drag_position(global_pos)
        self.apply_square_styles()

    def _create_drag_overlay(self, piece_code: str) -> QLabel:
        overlay = QLabel(self)
        overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        overlay.setAttribute(Qt.WA_TranslucentBackground, True)
        overlay.setStyleSheet("background: transparent; border: none;")
        overlay.setFixedSize(self.square_size, self.square_size)
        overlay.setAlignment(Qt.AlignCenter)
        overlay.setPixmap(self.get_piece_pixmap(piece_code))
        overlay.show()
        overlay.raise_()
        return overlay

    def update_drag_position(self, global_pos: QPoint):
        if self.drag_overlay is None:
            return

        local_pos = self.mapFromGlobal(global_pos)
        self.drag_overlay.move(
            local_pos.x() - self.square_size // 2,
            local_pos.y() - self.square_size // 2,
        )

    def clear_drag_state(self):
        if self.drag_overlay is not None:
            self.drag_overlay.deleteLater()
            self.drag_overlay = None

        self.drag_origin_square = None
        self.dragged_piece_code = None
        self.drag_start_global_pos = None
        self.drag_active = False

    def restore_dragged_piece_icon(self):
        if self.drag_origin_square is None or self.dragged_piece_code is None:
            return

        display_row, display_col = self.to_display_coordinates_from_real(*self.drag_origin_square)
        self.squares[display_row][display_col].setIcon(self.get_piece_icon(self.dragged_piece_code))

    def finish_drag(self, global_pos: QPoint):
        target_square = self._get_target_square_from_global_pos(global_pos)
        origin_square = self.drag_origin_square
        legal_moves = list(self.legal_moves)

        if (
                self.client_can_play()
                and target_square is not None
                and origin_square is not None
                and target_square in legal_moves
        ):
            promotion = self.choose_promotion_piece_type(origin_square, target_square)
            if self.is_promotion_move(origin_square, target_square) and promotion is None:
                self.restore_dragged_piece_icon()
            else:
                from_row, from_col = origin_square
                to_row, to_col = target_square
                self.skip_next_animation = True
                self.client.send_move(from_row, from_col, to_row, to_col, promotion)
        else:
            self.restore_dragged_piece_icon()

        self.clear_selection()
        self.clear_drag_state()
        self.apply_square_styles()

    def _get_target_square_from_global_pos(self, global_pos: QPoint):
        target_widget = self.childAt(self.mapFromGlobal(global_pos))
        if not isinstance(target_widget, QPushButton):
            return None

        display_row = target_widget.property("display_row")
        display_col = target_widget.property("display_col")
        if display_row is None or display_col is None:
            return None

        return self.to_real_coordinates(display_row, display_col)

    # ------------------------------------------------------------------
    # Move animation
    # ------------------------------------------------------------------

    def infer_animation_move(self, old_board, new_board):
        if old_board is None or new_board is None:
            return None

        changed = self._get_changed_squares(old_board, new_board)

        if len(changed) == 2:
            return self._infer_normal_animation_move(old_board, new_board, changed)

        if len(changed) == 4:
            return self._infer_castling_animation_move(old_board, new_board, changed)

        return None

    def _get_changed_squares(self, old_board, new_board):
        changed = []
        for row in range(self.BOARD_SIZE):
            for col in range(self.BOARD_SIZE):
                if old_board[row][col] != new_board[row][col]:
                    changed.append((row, col))
        return changed

    def _infer_normal_animation_move(self, old_board, new_board, changed):
        from_square = None
        to_square = None

        for row, col in changed:
            old_piece = old_board[row][col]
            new_piece = new_board[row][col]
            if old_piece is not None and new_piece is None:
                from_square = (row, col)
            elif old_piece != new_piece and new_piece is not None:
                to_square = (row, col)

        if from_square is None or to_square is None:
            return None

        moving_piece = old_board[from_square[0]][from_square[1]]
        final_piece = new_board[to_square[0]][to_square[1]]
        return from_square, to_square, moving_piece, final_piece

    def _infer_castling_animation_move(self, old_board, new_board, changed):
        king_from = None
        king_to = None

        for row, col in changed:
            old_piece = old_board[row][col]
            new_piece = new_board[row][col]
            if old_piece in ("wK", "bK") and new_piece is None:
                king_from = (row, col)
            elif new_piece in ("wK", "bK"):
                king_to = (row, col)

        if king_from is None or king_to is None:
            return None

        moving_piece = old_board[king_from[0]][king_from[1]]
        final_piece = new_board[king_to[0]][king_to[1]]
        return king_from, king_to, moving_piece, final_piece

    def start_move_animation(self, from_square, to_square, moving_piece_code, final_piece_code):
        if moving_piece_code is None or final_piece_code is None:
            return

        from_display_row, from_display_col = self.to_display_coordinates_from_real(*from_square)
        to_display_row, to_display_col = self.to_display_coordinates_from_real(*to_square)

        from_widget = self.squares[from_display_row][from_display_col]
        to_widget = self.squares[to_display_row][to_display_col]

        if self.move_animation_label is not None:
            self.move_animation_label.deleteLater()
            self.move_animation_label = None

        self.pending_animation_target = (to_display_row, to_display_col)
        self.pending_animation_piece_code = final_piece_code

        self.move_animation_label = self._create_animation_label(moving_piece_code, from_widget.pos())
        self.move_animation = self._create_move_animation(from_widget.pos(), to_widget.pos())
        self.move_animation.finished.connect(self.finish_move_animation)
        self.move_animation.start()

    def _create_animation_label(self, piece_code: str, start_pos):
        label = QLabel(self)
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        label.setAttribute(Qt.WA_TranslucentBackground, True)
        label.setStyleSheet("background: transparent; border: none;")
        label.setFixedSize(self.square_size, self.square_size)
        label.setAlignment(Qt.AlignCenter)
        label.setPixmap(self.get_piece_pixmap(piece_code))
        label.move(start_pos)
        label.show()
        label.raise_()
        return label

    def _create_move_animation(self, start_pos, end_pos):
        animation = QPropertyAnimation(self.move_animation_label, b"pos", self)
        animation.setDuration(300)
        animation.setStartValue(start_pos)
        animation.setEndValue(end_pos)
        animation.setEasingCurve(QEasingCurve.InOutQuad)
        return animation

    def finish_move_animation(self):
        if self.pending_animation_target is not None and self.pending_animation_piece_code is not None:
            row, col = self.pending_animation_target
            self.squares[row][col].setIcon(self.get_piece_icon(self.pending_animation_piece_code))

        if self.move_animation_label is not None:
            self.move_animation_label.deleteLater()
            self.move_animation_label = None

        self.move_animation = None
        self.pending_animation_target = None
        self.pending_animation_piece_code = None

        if self.queued_board_update is not None:
            queued_board = self.queued_board_update
            self.queued_board_update = None
            self.update_board(queued_board)

    # ------------------------------------------------------------------
    # Event filter
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if isinstance(obj, QPushButton):
            event_type = event.type()

            if event_type == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                return self._handle_mouse_press(obj, event)

            if event_type == QEvent.MouseMove:
                return self._handle_mouse_move(event)

            if event_type == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                return self._handle_mouse_release(event)

        return super().eventFilter(obj, event)

    def _handle_mouse_press(self, obj, event):
        display_row = obj.property("display_row")
        display_col = obj.property("display_col")
        if display_row is None or display_col is None:
            return False

        real_row, real_col = self.to_real_coordinates(display_row, display_col)
        if self.can_interact_with_piece(real_row, real_col):
            self.drag_origin_square = (real_row, real_col)
            self.dragged_piece_code = self.current_board[real_row][real_col]
            self.drag_start_global_pos = event.globalPosition().toPoint()

        return False

    def _handle_mouse_move(self, event):
        if self.drag_origin_square is None or self.dragged_piece_code is None:
            return False

        if not self.client_can_play():
            return False

        current_pos = event.globalPosition().toPoint()

        if not self.drag_active:
            if self.drag_start_global_pos is None:
                return False
            if (current_pos - self.drag_start_global_pos).manhattanLength() < QApplication.startDragDistance():
                return False
            self.start_drag(current_pos)

        self.update_drag_position(current_pos)
        return True

    def _handle_mouse_release(self, event):
        if self.drag_active:
            self.finish_drag(event.globalPosition().toPoint())
            self.suppress_next_click = True
            return True

        self.drag_origin_square = None
        self.dragged_piece_code = None
        self.drag_start_global_pos = None
        self.drag_active = False
        return False

    # ------------------------------------------------------------------
    # Board appearance
    # ------------------------------------------------------------------

    def clear_board(self):
        for row in range(self.BOARD_SIZE):
            for col in range(self.BOARD_SIZE):
                self.squares[row][col].setIcon(QIcon())
                self.squares[row][col].setText("")

    def get_base_square_color(self, row, col):
        theme = self.theme_colors.get(self.theme_name, self.theme_colors["Classic"])
        return theme["light"] if (row + col) % 2 == 0 else theme["dark"]

    def get_square_style(self, row, col, highlight=None):
        theme = self.theme_colors.get(self.theme_name, self.theme_colors["Classic"])
        color = self.get_base_square_color(row, col)

        if highlight == "selected":
            color = theme["selected"]
        elif highlight == "legal":
            color = theme["legal"]
        elif highlight == "last_move":
            color = theme["last_move"]
        elif highlight == "check":
            color = theme["check"]
        elif highlight == "checkmate":
            color = theme["checkmate"]

        return f"background-color: {color}; border: none;"

    def set_theme(self, theme_name: str):
        if theme_name not in self.theme_colors:
            return

        self.theme_name = theme_name
        background = self.theme_colors[theme_name]["background"]
        self.setStyleSheet(f"background-color: {background};")
        self.apply_square_styles()

    def set_review_mode(self, enabled: bool):
        self.review_mode = bool(enabled)
        if enabled:
            self.selected_square = None
            self.legal_moves = []
            self.clear_drag_state()
        self.apply_square_styles()

    def apply_square_styles(self):
        king_square, king_highlight = self.get_king_square_for_status()

        for display_row in range(self.BOARD_SIZE):
            for display_col in range(self.BOARD_SIZE):
                real_row, real_col = self.to_real_coordinates(display_row, display_col)
                highlight = self._get_square_highlight(real_row, real_col, king_square, king_highlight)

                self.squares[display_row][display_col].setStyleSheet(
                    self.get_square_style(display_row, display_col, highlight)
                )

    def _get_square_highlight(self, real_row, real_col, king_square, king_highlight):
        highlight = None

        if (real_row, real_col) in self.last_move_squares:
            highlight = "last_move"

        if self.selected_square == (real_row, real_col):
            highlight = "selected"
        elif (real_row, real_col) in self.legal_moves:
            highlight = "legal"

        if king_square == (real_row, real_col):
            highlight = king_highlight

        return highlight

    # ------------------------------------------------------------------
    # Temp game / legal moves
    # ------------------------------------------------------------------

    def build_temp_game(self):
        if self.current_board is None:
            return None

        game = Game()
        game.board = [row[:] for row in self.current_board]

        if self.client.latest_game_status:
            self._apply_status_to_temp_game(game, self.client.latest_game_status)

        return game

    def _apply_status_to_temp_game(self, game: Game, status: dict):
        turn = status.get("turn")
        if turn in ("white", "black"):
            game.turn = turn

        en_passant_target = status.get("en_passant_target")
        if isinstance(en_passant_target, list) and len(en_passant_target) == 2:
            game.en_passant_target = (en_passant_target[0], en_passant_target[1])
        elif isinstance(en_passant_target, tuple) and len(en_passant_target) == 2:
            game.en_passant_target = en_passant_target
        else:
            game.en_passant_target = None

        castling_rights = status.get("castling_rights")
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

    def get_legal_moves_for_square(self, from_pos):
        game = self.build_temp_game()
        if game is None:
            return []

        legal_moves = []
        for row in range(self.BOARD_SIZE):
            for col in range(self.BOARD_SIZE):
                if game.is_legal_move(from_pos, (row, col), "Q"):
                    legal_moves.append((row, col))
        return legal_moves

    def is_promotion_move(self, from_pos, to_pos):
        if self.current_board is None:
            return False

        from_row, from_col = from_pos
        to_row, to_col = to_pos
        piece = self.current_board[from_row][from_col]

        if piece == "wP" and to_row == 0:
            return True
        if piece == "bP" and to_row == 7:
            return True
        return False

    def choose_promotion_piece_type(self, from_pos, to_pos):
        if not self.is_promotion_move(from_pos, to_pos):
            return None

        return PromotionDialog.get_promotion_piece(self.client.my_color, self)

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def get_king_square_for_status(self):
        status_content = self.client.latest_game_status
        if not status_content or self.current_board is None:
            return None, None

        status = status_content.get("status")
        if status == "check_white":
            king_code, highlight = "wK", "check"
        elif status == "check_black":
            king_code, highlight = "bK", "check"
        elif status == "checkmate_white_wins":
            king_code, highlight = "bK", "checkmate"
        elif status == "checkmate_black_wins":
            king_code, highlight = "wK", "checkmate"
        else:
            return None, None

        for row in range(self.BOARD_SIZE):
            for col in range(self.BOARD_SIZE):
                if self.current_board[row][col] == king_code:
                    return (row, col), highlight

        return None, None

    def set_last_move(self, from_pos, to_pos):
        if from_pos is None or to_pos is None:
            self.last_move_squares = []
        else:
            self.last_move_squares = [tuple(from_pos), tuple(to_pos)]
        self.apply_square_styles()

    # ------------------------------------------------------------------
    # Click move handling
    # ------------------------------------------------------------------

    def on_square_clicked(self, row, col):
        if self.suppress_next_click:
            self.suppress_next_click = False
            return

        if not self.client_can_play():
            return

        if self.current_board is None:
            return

        real_row, real_col = self.to_real_coordinates(row, col)

        if self.selected_square is None:
            self._handle_first_click(real_row, real_col)
            return

        self._handle_second_click(real_row, real_col)

    def _handle_first_click(self, real_row, real_col):
        piece_code = self.get_piece_at(real_row, real_col)
        if piece_code is None:
            return

        if not self.is_own_piece_code(piece_code):
            return

        status_turn = self.get_status_turn()
        if status_turn is not None and status_turn != self.client.my_color:
            return

        self.selected_square = (real_row, real_col)
        self.legal_moves = self.get_legal_moves_for_square(self.selected_square)
        self.apply_square_styles()

    def _handle_second_click(self, real_row, real_col):
        from_row, from_col = self.selected_square
        to_row, to_col = real_row, real_col

        if (from_row, from_col) == (to_row, to_col):
            self.clear_selection()
            self.apply_square_styles()
            return

        if (to_row, to_col) not in self.legal_moves:
            if self._try_switch_selection_to_other_own_piece(real_row, real_col):
                return

            self.clear_selection()
            self.apply_square_styles()
            return

        promotion = self.choose_promotion_piece_type((from_row, from_col), (to_row, to_col))
        if self.is_promotion_move((from_row, from_col), (to_row, to_col)) and promotion is None:
            return

        self.client.send_move(from_row, from_col, to_row, to_col, promotion)
        self.clear_selection()
        self.apply_square_styles()

    def _try_switch_selection_to_other_own_piece(self, real_row, real_col) -> bool:
        piece_code = self.get_piece_at(real_row, real_col)
        if not self.is_own_piece_code(piece_code):
            return False

        self.selected_square = (real_row, real_col)
        self.legal_moves = self.get_legal_moves_for_square(self.selected_square)
        self.apply_square_styles()
        return True

    def clear_selection(self):
        self.selected_square = None
        self.legal_moves = []

    # ------------------------------------------------------------------
    # Board update
    # ------------------------------------------------------------------

    def update_board(self, board=None):
        if board is None:
            return

        if not isinstance(board, list) or len(board) != self.BOARD_SIZE:
            return

        if self.move_animation is not None:
            self.queued_board_update = board
            return

        old_board = self.current_board
        animation_move = self.infer_animation_move(old_board, board)

        if self.skip_next_animation:
            animation_move = None
            self.skip_next_animation = False

        self.current_board = board
        self.clear_selection()

        if old_board is None:
            self.last_move_squares = []

        display_board = self.get_display_board(board)
        skip_target = self._get_animation_skip_target(animation_move)

        self.clear_board()
        self._render_display_board(display_board, skip_target)
        self.apply_square_styles()

        if animation_move is not None:
            from_square, to_square, moving_piece_code, final_piece_code = animation_move
            self.start_move_animation(from_square, to_square, moving_piece_code, final_piece_code)
        else:
            self.queued_board_update = None

    def _get_animation_skip_target(self, animation_move):
        if animation_move is None:
            return None

        _, to_square, _, _ = animation_move
        return self.to_display_coordinates_from_real(*to_square)

    def _render_display_board(self, display_board, skip_target):
        for row in range(self.BOARD_SIZE):
            for col in range(self.BOARD_SIZE):
                piece_code = display_board[row][col]
                if not piece_code:
                    continue
                if skip_target is not None and (row, col) == skip_target:
                    continue
                self.squares[row][col].setIcon(self.get_piece_icon(piece_code))