from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QToolBar,
    QPushButton, QLabel, QComboBox, QGridLayout, QSizePolicy
)

from network.NetworkClient import NetworkClient
from view.BoardView import ChessBoard
from view.ChatView import ChatWidget
from view.CapturedListView import CapturedPieces
from view.ClockView import ClockWidget


class ChessClient(QMainWindow):
    WINDOW_TITLE = "PyChess"
    WINDOW_SIZE = (1080, 720)

    BOARD_THEMES = ["Classic", "Walnut", "Noir", "Emerald", "Slate"]
    TIME_CONTROLS = ["1 min", "3 min", "5 min", "10 min", "15 min", "20 min", "30 min", "60 min"]

    GAME_RESULT_TEXTS = {
        "checkmate_white_wins": ("Checkmate 1 - 0 (White wins)", "white"),
        "checkmate_black_wins": ("Checkmate 0 - 1 (Black wins)", "black"),
        "timeout_white_wins": ("Time out 1 - 0 (White wins)", "white"),
        "timeout_black_wins": ("Time out 0 - 1 (Black wins)", "black"),
        "resignation_white_wins": ("Resign 1 - 0 (White wins)", "white"),
        "resignation_black_wins": ("Resign 0 - 1 (Black wins)", "black"),
        "disconnect_white_wins": ("Disconnect 1 - 0 (White wins)", "white"),
        "disconnect_black_wins": ("Disconnect 0 - 1 (Black wins)", "black"),
        "stalemate": ("Remis 1/2 - 1/2 (Stalemate)", None),
        "draw_fifty_move_rule": ("Remis 1/2 - 1/2 (50 moves)", None),
        "draw_threefold_repetition": ("Remis 1/2 - 1/2 (Repetition)", None),
        "draw_insufficient_material": ("Remis 1/2 - 1/2 (Insufficient Material)", None),
        "draw_by_agreement": ("Remis 1/2 - 1/2 (Agreement)", None),
    }

    WINDOW_THEME_STYLES = {
        "Classic": "QMainWindow { background-color: #2B2B2B; } QWidget { color: white; }",
        "Blue": "QMainWindow { background-color: #1F2A38; } QWidget { color: white; }",
        "Walnut": "QMainWindow { background-color: #2A2118; } QWidget { color: white; }",
        "Gray": "QMainWindow { background-color: #262626; } QWidget { color: white; }",
        "Purple": "QMainWindow { background-color: #241B35; } QWidget { color: white; }",
    }

    DEFAULT_UI_FONT_FAMILY = "Helvetica Neue"
    DEFAULT_UI_FONT_SIZE = 11

    def __init__(self, client: NetworkClient):
        super().__init__()

        self.client = client
        self.is_host = bool(getattr(self.client, "is_host", False))
        self.game_in_progress = False
        self.last_move = None
        self.other_clients_count = 0

        self.selected_time_control = "10 min"
        self.selected_left_ai_level = 10
        self.selected_right_ai_level = 10
        self.selected_board_theme = "Classic"
        self.human_opponent_connected = False
        self.history_snapshots = []
        self.history_index = -1

        self.sounds_enabled = True

        self._configure_window()
        self._setup_sound_effects()
        self._create_ui()
        self._connect_signals()
        self._initialize_ui_state()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _configure_window(self):
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setFixedSize(*self.WINDOW_SIZE)
        self.setFont(QFont(self.DEFAULT_UI_FONT_FAMILY, self.DEFAULT_UI_FONT_SIZE))

    def _setup_sound_effects(self):
        sounds_dir = Path(__file__).resolve().parent.parent / "assets" / "sounds"
        self._sound_players = {}

        sound_files = {
            "game_start": sounds_dir / "game_start.mp3",
            "move_piece": sounds_dir / "move_piece.mp3",
            "capture": sounds_dir / "capture.mp3",
            "check": sounds_dir / "check.mp3",
            "notify": sounds_dir / "notify.mp3",
            "you_won": sounds_dir / "you_won.mp3",
            "you_lost": sounds_dir / "you_lost.mp3",
        }

        for sound_name, sound_path in sound_files.items():
            if not sound_path.exists():
                continue

            audio_output = QAudioOutput(self)
            audio_output.setVolume(0.65)

            player = QMediaPlayer(self)
            player.setAudioOutput(audio_output)
            player.setSource(QUrl.fromLocalFile(str(sound_path)))

            self._sound_players[sound_name] = (player, audio_output)

    def _is_capture_move(self, old_board, new_board) -> bool:
        if not self._is_valid_board_pair(old_board, new_board):
            return False

        old_piece_count = sum(1 for row in old_board for piece in row if piece is not None)
        new_piece_count = sum(1 for row in new_board for piece in row if piece is not None)
        return new_piece_count < old_piece_count

    def _is_normal_move(self, old_board, new_board) -> bool:
        if not self._is_valid_board_pair(old_board, new_board):
            return False

        changed_squares = self._get_changed_squares(old_board, new_board)
        return len(changed_squares) in (2, 4)

    def play_sound(self, sound_name: str):
        if not getattr(self, "sounds_enabled", True):
            return

        sound_entry = self._sound_players.get(sound_name)
        if sound_entry is None:
            return

        player, _audio_output = sound_entry
        player.stop()
        player.play()

    def _create_ui(self):
        self._create_toolbar()
        self._create_main_content()

    def _create_toolbar(self):
        toolbar = QToolBar("Game Controls")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setStyleSheet(
            "QToolBar {"
            " background-color: #202020;"
            " border: none;"
            " spacing: 6px;"
            " padding: 6px 8px;"
            "}"
            "QToolBar::separator {"
            " background-color: #3A3A3A;"
            " width: 1px;"
            " margin: 4px 8px;"
            "}"
            "QLabel {"
            " color: #D0D0D0;"
            " font-family: 'Courier New', 'Consolas', 'Menlo', monospace;"
            " padding: 0px 2px;"
            "}"
            "QPushButton {"
            " border: 1px solid #4A4A4A;"
            " border-radius: 4px;"
            " background-color: #1A1A1A;"
            " color: #E0E0E0;"
            " padding: 4px 10px;"
            " font-family: 'Courier New', 'Consolas', 'Menlo', monospace;"
            " min-height: 24px;"
            "}"
            "QPushButton:hover {"
            " border: 1px solid #6A6A6A;"
            " background-color: #222222;"
            "}"
            "QPushButton:disabled {"
            " background-color: #1A1A1A;"
            " color: #7A7A7A;"
            " border: 1px solid #3A3A3A;"
            "}"
            "QComboBox {"
            " background-color: #111111;"
            " color: #E0E0E0;"
            " border: 1px solid #4A4A4A;"
            " border-radius: 4px;"
            " padding: 4px 26px 4px 8px;"
            " font-family: 'Courier New', 'Consolas', 'Menlo', monospace;"
            " min-height: 24px;"
            "}"
            "QComboBox:hover {"
            " border: 1px solid #6A6A6A;"
            "}"
            "QComboBox:disabled {"
            " background-color: #1A1A1A;"
            " color: #7A7A7A;"
            " border: 1px solid #3A3A3A;"
            "}"
            "QComboBox::drop-down {"
            " subcontrol-origin: padding;"
            " subcontrol-position: top right;"
            " width: 22px;"
            " border: none;"
            " background: transparent;"
            "}"
            "QComboBox::down-arrow {"
            " image: none;"
            " width: 0px;"
            " height: 0px;"
            " border-left: 5px solid transparent;"
            " border-right: 5px solid transparent;"
            " border-top: 6px solid #A8A8A8;"
            " margin-right: 8px;"
            "}"
            "QComboBox QAbstractItemView {"
            " background-color: #111111;"
            " color: #E0E0E0;"
            " border: 1px solid #4A4A4A;"
            " outline: none;"
            " selection-background-color: #2E2E2E;"
            " selection-color: #FFFFFF;"
            " font-family: 'Courier New', 'Consolas', 'Menlo', monospace;"
            "}"
        )
        self.addToolBar(toolbar)

        self.start_button = QPushButton("Play")
        toolbar.addWidget(self.start_button)

        self.decline_game_button = QPushButton("Decline")
        self.decline_game_button.setEnabled(False)
        self.decline_game_action = toolbar.addWidget(self.decline_game_button)
        self.decline_game_button.hide()
        self.decline_game_action.setVisible(False)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel(" Time: "))
        self.time_control_box = QComboBox()
        self.time_control_box.addItems(self.TIME_CONTROLS)
        self.time_control_box.setCurrentText(self.selected_time_control)
        toolbar.addWidget(self.time_control_box)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel(" Theme: "))
        self.theme_box = QComboBox()
        self.theme_box.addItems(self.BOARD_THEMES)
        self.theme_box.setCurrentText(self.selected_board_theme)
        toolbar.addWidget(self.theme_box)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self.history_back_button = QPushButton("←")
        self.history_back_button.setToolTip("Show previous move")
        self.history_back_button.setEnabled(False)
        toolbar.addWidget(self.history_back_button)

        self.history_forward_button = QPushButton("→")
        self.history_forward_button.setToolTip("Show next move")
        self.history_forward_button.setEnabled(False)
        toolbar.addWidget(self.history_forward_button)

    def _create_main_content(self):
        main_widget = QWidget()
        main_layout = QHBoxLayout()

        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        self.match_label = QLabel("Waiting for game start...")
        self.match_label.setAlignment(Qt.AlignCenter)

        self.lobby_status_label = QLabel("Role: Spectator")
        self.lobby_status_label.setAlignment(Qt.AlignCenter)

        self.result_label = QLabel("")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.show_result_label("", "")

        self.board = ChessBoard(self.client)
        self.board.set_theme(self.selected_board_theme)

        self.clock = ClockWidget()
        self.captured = CapturedPieces()
        self.chat = ChatWidget(self.client)
        self.command_help_label = QLabel(
            "Chat Commands\n"
            "\\rename <name>        \\list\n"
            "\\mute <username>      \\muteall\n"
            "\\ao <username>        \\host <username>\n"
            "\\kick <username>      \\quit\n"
        )
        self.command_help_label.setWordWrap(True)
        self.command_help_label.setAlignment(Qt.AlignLeft)
        self.command_help_label.setStyleSheet(
            "padding: 6px 8px; "
            "color: #A8A8A8; "
            "background-color: transparent; "
            "font-family: 'Courier New', 'Consolas', 'Menlo', monospace;"
        )

        self.matchup_controls_widget = QWidget()
        matchup_grid = QGridLayout()
        matchup_grid.setContentsMargins(0, 0, 0, 0)
        matchup_grid.setHorizontalSpacing(10)
        matchup_grid.setVerticalSpacing(6)

        column_box_style = (
            "QWidget {"
            " border: 1px solid #555555;"
            " border-radius: 6px;"
            " padding: 6px;"
            "}"
            "QLabel {"
            " border: none;"
            " padding: 0px;"
            " font-family: 'Courier New', 'Consolas', 'Menlo', monospace;"
            " color: #D0D0D0;"
            "}"
            "QComboBox {"
            " background-color: #111111;"
            " color: #E0E0E0;"
            " border: 1px solid #4A4A4A;"
            " border-radius: 4px;"
            " padding: 4px 26px 4px 8px;"
            " font-family: 'Courier New', 'Consolas', 'Menlo', monospace;"
            " min-height: 24px;"
            "}"
            "QComboBox:hover {"
            " border: 1px solid #6A6A6A;"
            "}"
            "QComboBox:disabled {"
            " background-color: #1A1A1A;"
            " color: #7A7A7A;"
            " border: 1px solid #3A3A3A;"
            "}"
            "QComboBox::drop-down {"
            " subcontrol-origin: padding;"
            " subcontrol-position: top right;"
            " width: 22px;"
            " border: none;"
            " background: transparent;"
            "}"
            "QComboBox::down-arrow {"
            " image: none;"
            " width: 0px;"
            " height: 0px;"
            " border-left: 5px solid transparent;"
            " border-right: 5px solid transparent;"
            " border-top: 6px solid #A8A8A8;"
            " margin-right: 8px;"
            "}"
            "QComboBox QAbstractItemView {"
            " background-color: #111111;"
            " color: #E0E0E0;"
            " border: 1px solid #4A4A4A;"
            " outline: none;"
            " selection-background-color: #2E2E2E;"
            " selection-color: #FFFFFF;"
            " font-family: 'Courier New', 'Consolas', 'Menlo', monospace;"
            "}"
            "QPushButton {"
            " border: 1px solid #4A4A4A;"
            " border-radius: 4px;"
            " background-color: #1A1A1A;"
            " color: #E0E0E0;"
            " padding: 4px 8px;"
            " font-family: 'Courier New', 'Consolas', 'Menlo', monospace;"
            " min-height: 24px;"
            "}"
            "QPushButton:hover {"
            " border: 1px solid #6A6A6A;"
            " background-color: #222222;"
            "}"
            "QPushButton:disabled {"
            " background-color: #1A1A1A;"
            " color: #7A7A7A;"
            " border: 1px solid #3A3A3A;"
            "}"
        )

        self.left_column_widget = QWidget()
        self.left_column_widget.setStyleSheet(column_box_style)
        left_column_layout = QVBoxLayout()
        left_column_layout.setContentsMargins(8, 8, 8, 8)
        left_column_layout.setSpacing(6)
        self.left_column_widget.setLayout(left_column_layout)

        self.right_column_widget = QWidget()
        self.right_column_widget.setStyleSheet(column_box_style)
        right_column_layout = QVBoxLayout()
        right_column_layout.setContentsMargins(8, 8, 8, 8)
        right_column_layout.setSpacing(6)
        self.right_column_widget.setLayout(right_column_layout)

        self.action_column_widget = QWidget()
        self.action_column_widget.setStyleSheet(column_box_style)
        action_column_layout = QVBoxLayout()
        action_column_layout.setContentsMargins(8, 8, 8, 8)
        action_column_layout.setSpacing(6)
        self.action_column_widget.setLayout(action_column_layout)

        self.left_player_label = QLabel("Player 1 (White):")
        self.right_player_label = QLabel("Player 2 (Black):")
        self.resign_draw_label = QLabel("Options:")

        self.left_player_type_box = QComboBox()
        self.left_player_type_box.addItems(["Human", "Stockfish"])
        self.left_player_type_box.setCurrentText("Human")
        self.left_player_type_box.setToolTip("Player 1 (White)")

        self.right_player_type_box = QComboBox()
        self.right_player_type_box.addItems(["Human", "Stockfish"])
        self.right_player_type_box.setCurrentText("Human")
        self.right_player_type_box.setToolTip("Player 2 (Black)")

        self.offer_draw_button = QPushButton("Offer Remis")
        self.offer_draw_button.setEnabled(False)

        self.left_ai_difficulty_box = QComboBox()
        for level in range(1, 21):
            self.left_ai_difficulty_box.addItem(self.format_ai_level_text(level), level)
        self.left_ai_difficulty_box.setCurrentIndex(self.selected_left_ai_level - 1)
        self.left_ai_difficulty_box.setToolTip("Stockfish Level for Player 1 (White)")

        self.right_ai_difficulty_box = QComboBox()
        for level in range(1, 21):
            self.right_ai_difficulty_box.addItem(self.format_ai_level_text(level), level)
        self.right_ai_difficulty_box.setCurrentIndex(self.selected_right_ai_level - 1)
        self.right_ai_difficulty_box.setToolTip("Stockfish Level for Player 2 (Black)")

        self.resign_button = QPushButton("Resign")
        self.resign_button.setEnabled(False)

        left_column_layout.addWidget(self.left_player_label)
        left_column_layout.addWidget(self.left_player_type_box)
        left_column_layout.addWidget(self.left_ai_difficulty_box)

        right_column_layout.addWidget(self.right_player_label)
        right_column_layout.addWidget(self.right_player_type_box)
        right_column_layout.addWidget(self.right_ai_difficulty_box)

        action_column_layout.addWidget(self.resign_draw_label)
        action_column_layout.addWidget(self.offer_draw_button)
        action_column_layout.addWidget(self.resign_button)

        matchup_grid.addWidget(self.left_column_widget, 0, 0)
        matchup_grid.addWidget(self.right_column_widget, 0, 1)
        matchup_grid.addWidget(self.action_column_widget, 0, 2)

        self.matchup_controls_widget.setLayout(matchup_grid)

        right_panel.addWidget(self.clock)
        right_panel.addWidget(self.captured)
        right_panel.addWidget(self.matchup_controls_widget)
        right_panel.addWidget(self.command_help_label)
        right_panel.addWidget(self.chat)

        left_panel.addWidget(self.match_label)
        left_panel.addWidget(self.lobby_status_label)
        left_panel.addWidget(self.result_label)
        left_panel.addWidget(self.board)

        main_layout.addLayout(left_panel)
        main_layout.addLayout(right_panel)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def _connect_signals(self):
        self.start_button.clicked.connect(self.start_game)
        self.left_player_type_box.currentTextChanged.connect(self.handle_matchup_changed)
        self.right_player_type_box.currentTextChanged.connect(self.handle_matchup_changed)
        self.resign_button.clicked.connect(self.resign_game)
        self.offer_draw_button.clicked.connect(self.offer_draw)
        self.decline_game_button.clicked.connect(self.decline_game_offer)

        self.left_ai_difficulty_box.currentIndexChanged.connect(self.change_left_ai_difficulty)
        self.right_ai_difficulty_box.currentIndexChanged.connect(self.change_right_ai_difficulty)
        self.time_control_box.currentTextChanged.connect(self.change_time_control)
        self.theme_box.currentTextChanged.connect(self.change_board_theme)
        self.history_back_button.clicked.connect(self.show_previous_snapshot)
        self.history_forward_button.clicked.connect(self.show_next_snapshot)

        self.clock.time_expired.connect(self.handle_time_expired)

        self.client.game_started_received.connect(self.handle_game_started)
        self.client.captured_pieces_updated.connect(self.captured.update_captured_pieces)
        self.client.board_updated.connect(self.handle_board_update)
        self.client.game_status_received.connect(self.handle_game_status)
        self.client.time_control_updated.connect(self.handle_time_control_updated)
        self.client.message_received.connect(self.handle_server_message)
        self.client.host_assigned.connect(self.handle_host_assigned)
        self.client.role_updated.connect(self.handle_role_updated)
        self.client.kicked_from_server.connect(self.handle_kicked_from_server)
        self._hydrate_ui_from_client_state()

    def _hydrate_ui_from_client_state(self):
        if getattr(self.client, "white_player", None) or getattr(self.client, "black_player", None):
            self.update_match_label()

        if isinstance(getattr(self.client, "latest_board", None), list):
            self.handle_board_update(self.client.latest_board)
            self.captured.update_captured_pieces(self.client.latest_board)

        if isinstance(getattr(self.client, "latest_game_status", None), dict):
            self.handle_game_status(self.client.latest_game_status)

    def _initialize_ui_state(self):
        self._last_known_role = getattr(self.client, "role", "spectator")
        self.handle_host_assigned(self.is_host)
        self.update_start_button_base_text()
        self.update_ai_level_visibility()
        self.apply_window_theme()
        self.refresh_lobby_controls()
        self.update_history_buttons()
        self.update_lobby_status_label()

    def clear_history_snapshots(self):
        self.history_snapshots = []
        self.history_index = -1
        self.board.set_review_mode(False)
        self.update_history_buttons()

    def append_history_snapshot(self, status_content: dict) -> bool:
        if not isinstance(status_content, dict):
            return False

        board = status_content.get("board")
        if not isinstance(board, list) or len(board) != 8:
            return False

        snapshot = {
            "board": [row[:] for row in board],
            "status": dict(status_content),
        }

        if self.history_snapshots:
            last_snapshot = self.history_snapshots[-1]
            if last_snapshot.get("board") == snapshot["board"]:
                self.history_snapshots[-1]["status"] = dict(status_content)
                self.update_history_buttons()
                return False

        self.history_snapshots.append(snapshot)
        self.history_index = len(self.history_snapshots) - 1
        self.board.set_review_mode(False)
        self.update_history_buttons()
        return True

    def update_history_buttons(self):
        has_history = len(self.history_snapshots) > 0 and self.history_index >= 0
        self.history_back_button.setEnabled(has_history and self.history_index > 0)
        self.history_forward_button.setEnabled(
            has_history and self.history_index < len(self.history_snapshots) - 1
        )

    def is_reviewing_old_snapshot(self) -> bool:
        return self.history_index >= 0 and self.history_index < len(self.history_snapshots) - 1

    def show_snapshot_at_index(self, index: int):
        if not (0 <= index < len(self.history_snapshots)):
            return

        self.history_index = index
        snapshot = self.history_snapshots[index]
        snapshot_board = snapshot["board"]
        snapshot_status = dict(snapshot["status"])

        self.board.update_board(snapshot_board)
        self.captured.update_captured_pieces(snapshot_board)

        review_mode = index != len(self.history_snapshots) - 1
        self.board.set_review_mode(review_mode)

        if not review_mode:
            self.client.latest_game_status = snapshot_status
            white_time_seconds = snapshot_status.get("white_time_seconds")
            black_time_seconds = snapshot_status.get("black_time_seconds")
            if isinstance(white_time_seconds, int) and isinstance(black_time_seconds, int):
                self.clock.set_seconds(white_time_seconds, black_time_seconds)

        self.update_history_buttons()
        self.refresh_lobby_controls()

    def show_previous_snapshot(self):
        if self.history_index > 0:
            self.show_snapshot_at_index(self.history_index - 1)

    def show_next_snapshot(self):
        if self.history_index < len(self.history_snapshots) - 1:
            self.show_snapshot_at_index(self.history_index + 1)

    def jump_to_latest_snapshot(self):
        if not self.history_snapshots:
            self.clear_history_snapshots()
            return
        self.show_snapshot_at_index(len(self.history_snapshots) - 1)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def start_game(self):
        if self.start_button.text() == "Accept Game":
            self.client.send_command("start")
            return

        if self.start_button.text() in ("Offer Pending", "Cancel Offer"):
            self.client.send_command("cancelstart")
            return

        if not self.client.can_start:
            return

        if self.is_ai_vs_ai_selected():
            self.client.send_command(
                f"startaivai {self.selected_left_ai_level} {self.selected_right_ai_level}"
            )
            return

        if self.is_human_vs_ai_selected():
            left, right = self.get_selected_matchup()
            if left == "Human" and right == "Stockfish":
                self.client.send_command(f"starthvai white {self.selected_right_ai_level}")
            else:
                self.client.send_command(f"starthvai black {self.selected_left_ai_level}")
            return

        self.client.send_command("start")

    def get_selected_matchup(self) -> tuple[str, str]:
        return self.left_player_type_box.currentText(), self.right_player_type_box.currentText()

    def is_human_vs_human_selected(self) -> bool:
        left, right = self.get_selected_matchup()
        return left == "Human" and right == "Human"

    def is_human_vs_ai_selected(self) -> bool:
        left, right = self.get_selected_matchup()
        return (left == "Human" and right == "Stockfish") or (left == "Stockfish" and right == "Human")

    def is_ai_vs_ai_selected(self) -> bool:
        left, right = self.get_selected_matchup()
        return left == "Stockfish" and right == "Stockfish"

    def has_ai_in_matchup(self) -> bool:
        left, right = self.get_selected_matchup()
        return left == "Stockfish" or right == "Stockfish"

    def update_start_button_base_text(self):
        self.decline_game_button.setEnabled(False)
        self.start_button.setText("Play")

        if self.is_ai_vs_ai_selected():
            self.start_button.setText("Stockfish vs Stockfish")
        elif self.is_human_vs_ai_selected():
            self.start_button.setText("Player vs Stockfish")
        else:
            self.start_button.setText("Play")

    def handle_matchup_changed(self, _value: str):
        self.update_start_button_base_text()
        self.update_ai_level_visibility()
        self.refresh_lobby_controls()

    def resign_game(self):
        if (
            self.game_in_progress
            and self.client.can_play
            and getattr(self.client, "my_color", None) in ("white", "black")
        ):
            self.client.send_command("resign")

    def offer_draw(self):
        if (
            self.game_in_progress
            and self.client.can_play
            and getattr(self.client, "my_color", None) in ("white", "black")
        ):
            self.client.send_command("offerdraw")

    def decline_game_offer(self):
        if self.start_button.text() != "Accept Game":
            return
        self.client.send_command("declinestart")

    # ------------------------------------------------------------------
    # UI State
    # ------------------------------------------------------------------

    def refresh_lobby_controls(self):
        can_start = bool(self.client.can_start)
        can_play = bool(self.client.can_play)
        is_connected = bool(getattr(self.client, "isConnected", False))
        not_in_game = not self.game_in_progress
        pending_game_offer = self.start_button.text() in ("Offer Pending", "Cancel Offer", "Accept Game")

        matchup_boxes_enabled = can_start and not_in_game and not pending_game_offer
        left_ai = self.left_player_type_box.currentText() == "Stockfish"
        right_ai = self.right_player_type_box.currentText() == "Stockfish"
        reviewing_old_snapshot = self.is_reviewing_old_snapshot()
        is_actual_player = getattr(self.client, "my_color", None) in ("white", "black")

        if not is_connected:
            self._set_controls_enabled(
                start=False,
                matchup_left=False,
                matchup_right=False,
                left_ai_level=False,
                right_ai_level=False,
                time=False,
                resign=False,
                draw=False,
            )
            return

        if pending_game_offer:
            if self.start_button.text() == "Accept Game":
                start_enabled = True
            else:
                start_enabled = getattr(self.client, "role", "spectator") == "host"
        else:
            start_enabled = can_start and not_in_game

        self.start_button.setEnabled(start_enabled)
        decline_visible = (
                self.start_button.text() == "Accept Game"
                and getattr(self.client, "role", "spectator") == "opponent"
                and not self.game_in_progress
        )
        self.decline_game_action.setVisible(decline_visible)
        self.decline_game_button.setVisible(decline_visible)
        self.decline_game_button.setEnabled(decline_visible)
        self.left_player_type_box.setEnabled(matchup_boxes_enabled)
        self.right_player_type_box.setEnabled(matchup_boxes_enabled)
        self.left_ai_difficulty_box.setEnabled(matchup_boxes_enabled and left_ai)
        self.right_ai_difficulty_box.setEnabled(matchup_boxes_enabled and right_ai)
        host_can_change_time_during_offer = pending_game_offer and getattr(self.client, "role", "spectator") == "host"
        self.time_control_box.setEnabled(
            (can_start or host_can_change_time_during_offer) and not_in_game
        )
        self.resign_button.setEnabled(can_play and self.game_in_progress and is_actual_player)

        if self.offer_draw_button.text() not in ("Offer Pending", "Accept Draw"):
            self.offer_draw_button.setEnabled(can_play and self.game_in_progress and is_actual_player)
        elif self.offer_draw_button.text() == "Accept Draw":
            self.offer_draw_button.setEnabled(can_play and self.game_in_progress and is_actual_player)

    def _set_controls_enabled(self, start, matchup_left, matchup_right, left_ai_level, right_ai_level, time, resign,
                              draw):
        self.start_button.setEnabled(start)
        self.left_player_type_box.setEnabled(matchup_left)
        self.right_player_type_box.setEnabled(matchup_right)
        self.left_ai_difficulty_box.setEnabled(left_ai_level)
        self.right_ai_difficulty_box.setEnabled(right_ai_level)
        self.time_control_box.setEnabled(time)
        self.resign_button.setEnabled(resign)
        self.offer_draw_button.setEnabled(draw)
        self.decline_game_button.hide()
        self.decline_game_button.setEnabled(False)
        self.decline_game_action.setVisible(False)

    def update_lobby_status_label(self):
        if not bool(getattr(self.client, "isConnected", False)):
            self.lobby_status_label.setText("Disconnected")
            return

        role = getattr(self.client, "role", "spectator")
        queue_position = getattr(self.client, "queue_position", None)

        if role == "host":
            text = "Role: Host"
        elif role == "opponent":
            text = "Role: Active Opponent"
        elif queue_position is not None:
            text = f"Role: Spectator | Queue position: {queue_position}"
        else:
            text = "Role: Spectator"

        self.lobby_status_label.setText(text)

    def update_match_label(self):
        white_name = self.client.white_player
        black_name = self.client.black_player

        if white_name and black_name:
            if getattr(self.client, "role", "spectator") == "spectator":
                self.match_label.setText(f"Spectating: {white_name} (White) vs. {black_name} (Black)")
            else:
                self.match_label.setText(f"{white_name} (White) vs. {black_name} (Black)")
        else:
            self.match_label.setText("Waiting for game start...")

    # ------------------------------------------------------------------
    # Settings / Theme
    # ------------------------------------------------------------------

    def change_time_control(self, value: str):
        self.selected_time_control = value
        if self.game_in_progress:
            return

        is_pending_game_offer = self.start_button.text() in ("Offer Pending", "Cancel Offer", "Accept Game")
        can_change_time = bool(self.client.can_start) or (
            is_pending_game_offer and getattr(self.client, "role", "spectator") == "host"
        )
        if not can_change_time:
            return

        self.apply_time_control(value)
        minutes = int(value.split()[0])
        self.client.send_command(f"settime {minutes}")

    def change_left_ai_difficulty(self, index: int):
        if index >= 0:
            self.selected_left_ai_level = index + 1

    def change_right_ai_difficulty(self, index: int):
        if index >= 0:
            self.selected_right_ai_level = index + 1

    def update_ai_level_visibility(self):
        left_ai = self.left_player_type_box.currentText() == "Stockfish"
        right_ai = self.right_player_type_box.currentText() == "Stockfish"
        self.left_ai_difficulty_box.setVisible(True)
        self.right_ai_difficulty_box.setVisible(True)
        self.left_ai_difficulty_box.setEnabled(left_ai and bool(getattr(self.client, "can_start", False)) and not self.game_in_progress)
        self.right_ai_difficulty_box.setEnabled(right_ai and bool(getattr(self.client, "can_start", False)) and not self.game_in_progress)

    def change_board_theme(self, value: str):
        self.selected_board_theme = value
        self.board.set_theme(value)
        self.apply_window_theme()

    def apply_time_control(self, value: str):
        minutes = int(value.split()[0])
        self.clock.set_time_minutes(minutes)

    def apply_window_theme(self):
        self.setStyleSheet(self.WINDOW_THEME_STYLES.get(self.selected_board_theme, ""))

    def estimate_stockfish_elo(self, level: int) -> int:
        min_elo = 1320
        max_elo = 3190
        return round(min_elo + (level - 1) * (max_elo - min_elo) / 19)

    def format_ai_level_text(self, level: int) -> str:
        return f"~{self.estimate_stockfish_elo(level)} Elo"

    # ------------------------------------------------------------------
    # Labels / Results
    # ------------------------------------------------------------------

    def show_result_label(self, text: str, color: str):
        self.result_label.setText(text)
        self.result_label.setStyleSheet(f"font-weight: bold; color: {color};")
        self.result_label.show()

    def clear_result_label(self):
        self.result_label.clear()
        self.result_label.setStyleSheet("")
        self.result_label.hide()

    def get_result_color_for_winner(self, winner_color: str) -> str:
        if self.client.my_color not in ("white", "black"):
            return "gray"
        return "green" if self.client.my_color == winner_color else "red"

    def _show_game_over_result(self, status: str):
        result = self.GAME_RESULT_TEXTS.get(status)
        if result is None:
            self.clear_result_label()
            return

        text, winner_color = result
        if winner_color is None:
            self.show_result_label(text, "gray")
        else:
            self.show_result_label(text, self.get_result_color_for_winner(winner_color))

    # ------------------------------------------------------------------
    # Network Event Handlers
    # ------------------------------------------------------------------

    def handle_role_updated(self, content: dict):
        if not isinstance(content, dict):
            return

        previous_role = getattr(self, "_last_known_role", getattr(self.client, "role", "spectator"))
        new_role = content.get("role", "spectator")

        self.is_host = bool(content.get("is_host", False))
        self.client.role = new_role
        self.client.queue_position = content.get("queue_position")
        self.client.can_start = bool(content.get("can_start", False))
        self.client.can_play = bool(content.get("can_play", False))

        self.update_lobby_status_label()
        self.refresh_lobby_controls()

        if new_role == "opponent" and previous_role != "opponent":
            self.play_sound("notify")

        self._last_known_role = new_role

    def handle_host_assigned(self, is_host: bool):
        was_host = bool(getattr(self, "is_host", False))
        self.is_host = is_host
        self.client.is_host = is_host
        self.update_lobby_status_label()
        self.refresh_lobby_controls()

        if is_host and not was_host:
            self.play_sound("notify")

    def handle_game_started(self, content: dict):
        if not isinstance(content, dict):
            return

        self.client.my_color = content.get("color")
        self.client.white_player = content.get("white")
        self.client.black_player = content.get("black")
        self.clear_history_snapshots()
        self.play_sound("game_start")

        self.clear_result_label()
        self.last_move = None
        self.board.set_last_move(None, None)
        self.update_start_button_base_text()
        self.refresh_lobby_controls()
        self.update_match_label()

    def handle_game_status(self, content: dict):
        if not isinstance(content, dict):
            return

        was_reviewing_old_snapshot = self.is_reviewing_old_snapshot()
        self.client.latest_game_status = content
        added_new_position = self.append_history_snapshot(content)

        if was_reviewing_old_snapshot and added_new_position:
            self.jump_to_latest_snapshot()
        elif not was_reviewing_old_snapshot:
            self.board.apply_square_styles()

        turn = content.get("turn")
        game_over = bool(content.get("game_over"))
        status = content.get("status")
        white_time_seconds = content.get("white_time_seconds")
        black_time_seconds = content.get("black_time_seconds")
        time_minutes = content.get("time_minutes")

        self._update_time_control_from_status(time_minutes)
        self._update_clock_from_status(white_time_seconds, black_time_seconds)

        if game_over:
            self._handle_game_over(status)
            return

        if status in ("ongoing", "check_white", "check_black") and turn in ("white", "black"):
            self.game_in_progress = True
            self.clear_result_label()
            self.refresh_lobby_controls()
            if self.clock.is_running:
                self.clock.switch_player(turn)
            else:
                self.clock.start(turn)

    def _update_time_control_from_status(self, time_minutes):
        if isinstance(time_minutes, int) and time_minutes > 0:
            self.selected_time_control = f"{time_minutes} min"
            self.time_control_box.blockSignals(True)
            self.time_control_box.setCurrentText(self.selected_time_control)
            self.time_control_box.blockSignals(False)
            if not self.game_in_progress:
                self.clock.set_time_minutes(time_minutes)

    def handle_time_control_updated(self, time_minutes: int):
        if not isinstance(time_minutes, int) or time_minutes <= 0:
            return

        self.selected_time_control = f"{time_minutes} min"
        self.time_control_box.blockSignals(True)
        self.time_control_box.setCurrentText(self.selected_time_control)
        self.time_control_box.blockSignals(False)

        if not self.game_in_progress:
            self.clock.set_time_minutes(time_minutes)

    def _update_clock_from_status(self, white_time_seconds, black_time_seconds):
        if isinstance(white_time_seconds, int) and isinstance(black_time_seconds, int):
            self.clock.set_seconds(white_time_seconds, black_time_seconds)

    def _handle_game_over(self, status: str):
        self.game_in_progress = False
        self.board.set_review_mode(False)
        self.history_index = len(self.history_snapshots) - 1 if self.history_snapshots else -1
        self.update_history_buttons()

        if self.client.my_color in ("white", "black"):
            won_statuses = {
                "checkmate_white_wins": "white",
                "timeout_white_wins": "white",
                "resignation_white_wins": "white",
                "disconnect_white_wins": "white",
                "checkmate_black_wins": "black",
                "timeout_black_wins": "black",
                "resignation_black_wins": "black",
                "disconnect_black_wins": "black",
            }
            winner_color = won_statuses.get(status)
            if winner_color is not None:
                if self.client.my_color == winner_color:
                    self.play_sound("you_won")
                else:
                    self.play_sound("you_lost")

        # After a finished game, the lobby becomes startable again for the host.
        self.client.can_play = False
        self.client.can_start = bool(getattr(self.client, "role", "spectator") == "host")

        self.update_start_button_base_text()
        self.clock.stop()
        self.resign_button.setEnabled(False)
        self.offer_draw_button.setEnabled(False)
        self.refresh_lobby_controls()
        self._show_game_over_result(status)

    def handle_server_message(self, message: str):
        if message.startswith(">> "):
            return
        if not isinstance(message, str):
            return

        if message.strip() == "SERVER: You were kicked by the host.":
            self.handle_kicked_from_server("You were kicked by the host.")
            return

        if "Game offer sent to" in message:
            self.start_button.setText("Cancel Offer")
            self.start_button.setEnabled(getattr(self.client, "role", "spectator") == "host")
            self.decline_game_action.setVisible(False)
            self.decline_game_button.hide()
            self.decline_game_button.setEnabled(False)

        elif (
            "offered a game. Accept Game or Decline." in message
            or "offered a game. Click Play to accept." in message
            or "offered a game. Click Player vs Player to accept." in message
        ):
            self.start_button.setText("Accept Game")
            self.start_button.setEnabled(True)
            should_show_decline = (
                    getattr(self.client, "role", "spectator") == "opponent"
                    and not self.game_in_progress
            )
            self.decline_game_action.setVisible(should_show_decline)
            self.decline_game_button.setVisible(should_show_decline)
            self.decline_game_button.setEnabled(should_show_decline)
            self.play_sound("notify")


        elif (
                "Game offer accepted." in message
                or "Game offer cancelled." in message
                or "Game offer declined." in message
        ):
            self.decline_game_action.setVisible(False)
            self.decline_game_button.hide()
            self.decline_game_button.setEnabled(False)
            self.start_button.setText("Play")
            self.update_start_button_base_text()
            self.refresh_lobby_controls()

        self._handle_control_related_server_message(message)
        self._handle_connection_count_server_message(message)
        self._handle_rename_server_message(message)

        if not self.game_in_progress:
            self.offer_draw_button.setText("Offer Remis")
            self.offer_draw_button.setEnabled(False)
            self.resign_button.setEnabled(False)
            self.refresh_lobby_controls()

    def _handle_control_related_server_message(self, message: str):
        if "Only the host can start the game." in message:
            self.start_button.setEnabled(False)
            self.left_player_type_box.setEnabled(False)
            self.right_player_type_box.setEnabled(False)
            self.left_ai_difficulty_box.setEnabled(False)
            self.right_ai_difficulty_box.setEnabled(False)

        elif "Only the host can set the time control." in message:
            self.time_control_box.setEnabled(False)

        elif "Need two active players to start." in message and self.client.can_start:
            self.refresh_lobby_controls()

        elif "Game already started." in message:
            self.start_button.setEnabled(False)
            self.left_player_type_box.setEnabled(False)
            self.right_player_type_box.setEnabled(False)
            self.left_ai_difficulty_box.setEnabled(False)
            self.right_ai_difficulty_box.setEnabled(False)
            self.time_control_box.setEnabled(False)

        elif "No active game to resign." in message:
            self.resign_button.setEnabled(False)
            self.offer_draw_button.setEnabled(False)

        elif "No active game to offer a draw." in message:
            self.resign_button.setEnabled(False)
            self.offer_draw_button.setEnabled(False)

        elif "Draw offer sent to" in message:
            self.offer_draw_button.setText("Offer Pending")
            self.offer_draw_button.setEnabled(False)

        elif "offered a draw. Click Offer Draw to accept." in message:
            self.offer_draw_button.setText("Accept Draw")
            self.offer_draw_button.setEnabled(True)
            self.play_sound("notify")

        elif (
            "Draw offer accepted." in message
            or "Draw offer declined" in message
            or "Draw offer cancelled" in message
        ):
            self.offer_draw_button.setText("Offer Draw")
            self.offer_draw_button.setEnabled(self.game_in_progress)

    def _handle_connection_count_server_message(self, message: str):
        if message.startswith("SERVER: ") and " joined" in message:
            self.other_clients_count += 1
            self.human_opponent_connected = self.other_clients_count > 0
            self.refresh_lobby_controls()

        elif message.startswith("SERVER: ") and (
            " disconnected." in message
            or " left." in message
            or " was kicked." in message
        ):
            self.other_clients_count = max(0, self.other_clients_count - 1)
            self.human_opponent_connected = self.other_clients_count > 0
            self.refresh_lobby_controls()

    def _handle_rename_server_message(self, message: str):
        if not (message.startswith("SERVER: ") and " renamed to " in message):
            return

        rename_text = message[len("SERVER: "):]
        old_name, new_name = rename_text.split(" renamed to ", 1)
        old_name = old_name.strip()
        new_name = new_name.strip()

        if self.client.white_player == old_name:
            self.client.white_player = new_name
        if self.client.black_player == old_name:
            self.client.black_player = new_name

        self.update_match_label()

    def handle_kicked_from_server(self, reason: str):
        self.game_in_progress = False
        self.last_move = None
        self.other_clients_count = 0
        self.human_opponent_connected = False
        self.update_start_button_base_text()

        self.client.my_color = None
        self.client.white_player = None
        self.client.black_player = None

        self._reset_board_state()
        self._reset_window_state_after_disconnect()

        self.hide()
        reconnected = self.client.connect(parent=None, show_dialog=True)
        if not reconnected:
            self.close()
            return

        self.show()
        self.update_lobby_status_label()
        self.refresh_lobby_controls()

    def _reset_board_state(self):
        self.board.set_last_move(None, None)
        self.board.clear_drag_state()
        self.board.current_board = None
        self.board.clear_board()
        self.board.apply_square_styles()

    def _reset_window_state_after_disconnect(self):
        self.clock.stop()
        self.clear_result_label()
        self.match_label.setText("Waiting for game start...")
        self.lobby_status_label.setText("Disconnected")
        self.refresh_lobby_controls()

    def handle_time_expired(self, color: str):
        return

    # ------------------------------------------------------------------
    # Board Updates / Highlighting
    # ------------------------------------------------------------------

    def handle_board_update(self, content):
        if not isinstance(content, list) or len(content) != 8:
            return

        old_board = self.board.current_board if hasattr(self.board, "current_board") else None
        had_previous_board = old_board is not None

        if self.is_reviewing_old_snapshot():
            current_status = None
            if isinstance(getattr(self.client, "latest_game_status", None), dict):
                current_status = self.client.latest_game_status.get("status")

            is_capture = self._is_capture_move(old_board, content) if old_board is not None else False
            is_normal_move = self._is_normal_move(old_board, content) if old_board is not None else False
            self.jump_to_latest_snapshot()

            if had_previous_board:
                if current_status in ("check_white", "check_black"):
                    self.play_sound("check")
                elif is_capture:
                    self.play_sound("capture")
                elif is_normal_move:
                    self.play_sound("move_piece")
            return

        self.update_last_move_highlight(old_board, content)
        self.board.update_board(content)

        if had_previous_board:
            current_status = None
            if isinstance(getattr(self.client, "latest_game_status", None), dict):
                current_status = self.client.latest_game_status.get("status")

            is_capture = self._is_capture_move(old_board, content)
            is_normal_move = self._is_normal_move(old_board, content)

            if current_status in ("check_white", "check_black"):
                self.play_sound("check")
            elif is_capture:
                self.play_sound("capture")
            elif is_normal_move:
                self.play_sound("move_piece")

    def update_last_move_highlight(self, old_board, new_board):
        if not self._is_valid_board_pair(old_board, new_board):
            return

        changed = self._get_changed_squares(old_board, new_board)

        if len(changed) == 2:
            self._highlight_normal_move(old_board, new_board, changed)
        elif len(changed) == 4:
            self._highlight_castling_move(old_board, new_board, changed)
        else:
            self._clear_last_move_highlight()

    def _is_valid_board_pair(self, old_board, new_board):
        return old_board is not None and new_board is not None and len(old_board) == 8 and len(new_board) == 8

    def _get_changed_squares(self, old_board, new_board):
        changed = []
        for row in range(8):
            for col in range(8):
                if old_board[row][col] != new_board[row][col]:
                    changed.append((row, col))
        return changed

    def _highlight_normal_move(self, old_board, new_board, changed):
        from_square = None
        to_square = None

        for row, col in changed:
            old_piece = old_board[row][col]
            new_piece = new_board[row][col]
            if old_piece is not None and new_piece is None:
                from_square = (row, col)
            elif old_piece != new_piece and new_piece is not None:
                to_square = (row, col)

        if from_square is not None and to_square is not None:
            self._set_last_move(from_square, to_square)
        else:
            self._set_last_move(changed[0], changed[1])

    def _highlight_castling_move(self, old_board, new_board, changed):
        king_squares = []
        for row, col in changed:
            old_piece = old_board[row][col]
            new_piece = new_board[row][col]
            if old_piece in ("wK", "bK") or new_piece in ("wK", "bK"):
                king_squares.append((row, col))

        if len(king_squares) != 2:
            self._clear_last_move_highlight()
            return

        from_square = None
        to_square = None

        for row, col in king_squares:
            old_piece = old_board[row][col]
            new_piece = new_board[row][col]
            if old_piece in ("wK", "bK") and new_piece is None:
                from_square = (row, col)
            elif new_piece in ("wK", "bK"):
                to_square = (row, col)

        if from_square is not None and to_square is not None:
            self._set_last_move(from_square, to_square)
        else:
            self._set_last_move(king_squares[0], king_squares[1])

    def _set_last_move(self, from_square, to_square):
        self.last_move = (from_square, to_square)
        self.board.set_last_move(from_square, to_square)

    def _clear_last_move_highlight(self):
        self.last_move = None
        self.board.set_last_move(None, None)