from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QToolBar,
    QPushButton, QLabel, QComboBox
)

from network.NetworkClient import NetworkClient
from view.BoardView import ChessBoard
from view.ChatView import ChatWidget
from view.CapturedListView import CapturedPieces
from view.ClockView import ClockWidget


class ChessClient(QMainWindow):

    def __init__(self, client: NetworkClient):
        super().__init__()

        self.setWindowTitle("PyChess")

        self.client = client
        self.is_host = bool(getattr(self.client, "is_host", False))
        self.game_in_progress = False

        self.selected_time_control = "10 min"

        toolbar = QToolBar("Game Controls")
        self.addToolBar(toolbar)

        self.start_button = QPushButton("Start Game")
        self.start_button.clicked.connect(self.start_game)
        toolbar.addWidget(self.start_button)

        toolbar.addWidget(QLabel("   Time: "))
        self.time_control_box = QComboBox()
        self.time_control_box.addItems(["1 min", "3 min", "5 min", "10 min", "15 min"])
        self.time_control_box.setCurrentText(self.selected_time_control)
        self.time_control_box.currentTextChanged.connect(self.change_time_control)
        self.time_control_box.setEnabled(self.is_host and not self.game_in_progress)
        toolbar.addWidget(self.time_control_box)
        self.start_button.setEnabled(self.is_host and not self.game_in_progress)

        main_widget = QWidget()
        main_layout = QHBoxLayout()

        left_panel = QVBoxLayout()

        self.match_label = QLabel("Waiting for game start...")
        self.match_label.setAlignment(Qt.AlignCenter)
        self.client.game_started_received.connect(self.handle_game_started)

        # Chessboard
        self.board = ChessBoard(client)

        # Right panel
        right_panel = QVBoxLayout()

        self.clock = ClockWidget()
        self.clock.time_expired.connect(self.handle_time_expired)
        self.captured = CapturedPieces()
        self.client.captured_pieces_updated.connect(self.captured.update_captured_pieces)
        self.chat = ChatWidget(self.client)
        self.client.game_status_received.connect(self.handle_game_status)
        self.client.message_received.connect(self.handle_server_message)
        self.client.host_assigned.connect(self.handle_host_assigned)

        # In case host assignment already arrived before the window connected to the signal
        self.handle_host_assigned(self.is_host)

        right_panel.addWidget(self.clock)
        right_panel.addWidget(self.captured)
        right_panel.addWidget(self.chat)

        left_panel.addWidget(self.match_label)
        left_panel.addWidget(self.board)

        main_layout.addLayout(left_panel)
        main_layout.addLayout(right_panel)

        main_widget.setLayout(main_layout)

        self.setCentralWidget(main_widget)

    def start_game(self):
        if not self.is_host:
            return
        self.client.send_command("start")

    def change_time_control(self, value: str):
        self.selected_time_control = value
        if not self.is_host or self.game_in_progress:
            return
        self.apply_time_control(value)
        minutes = int(value.split()[0])
        self.client.send_command(f"settime {minutes}")

    def apply_time_control(self, value: str):
        minutes = int(value.split()[0])
        self.clock.set_time_minutes(minutes)

    def handle_game_status(self, content: dict):
        if not isinstance(content, dict):
            return

        turn = content.get("turn")
        game_over = bool(content.get("game_over"))
        status = content.get("status")
        white_time_seconds = content.get("white_time_seconds")
        black_time_seconds = content.get("black_time_seconds")
        time_minutes = content.get("time_minutes")

        if isinstance(time_minutes, int) and time_minutes > 0:
            self.selected_time_control = f"{time_minutes} min"
            self.time_control_box.blockSignals(True)
            self.time_control_box.setCurrentText(self.selected_time_control)
            self.time_control_box.blockSignals(False)
            if not self.game_in_progress:
                self.clock.set_time_minutes(time_minutes)

        if isinstance(white_time_seconds, int) and isinstance(black_time_seconds, int):
            self.clock.set_seconds(white_time_seconds, black_time_seconds)

        if game_over:
            self.game_in_progress = False
            self.clock.stop()
            self.start_button.setEnabled(self.is_host)
            self.time_control_box.setEnabled(self.is_host)
            return

        if status in ("ongoing", "check_white", "check_black") and turn in ("white", "black"):
            self.game_in_progress = True
            self.start_button.setEnabled(False)
            self.time_control_box.setEnabled(False)
            if self.clock.is_running:
                self.clock.switch_player(turn)
            else:
                self.clock.start(turn)

    def handle_time_expired(self, color: str):
        return

    def update_match_label(self):
        white_name = self.client.white_player
        black_name = self.client.black_player

        if white_name and black_name:
            self.match_label.setText(f"{white_name} (White) vs. {black_name} (Black)")
        else:
            self.match_label.setText("Waiting for game start...")

    def handle_game_started(self, content: dict):
        if not isinstance(content, dict):
            return

        self.client.white_player = content.get("white")
        self.client.black_player = content.get("black")
        self.update_match_label()

    def handle_host_assigned(self, is_host: bool):
        self.is_host = is_host
        self.start_button.setEnabled(is_host and not self.game_in_progress)
        self.time_control_box.setEnabled(is_host and not self.game_in_progress)

    def handle_server_message(self, message: str):
        if not isinstance(message, str):
            return

        if "Only the host can start the game." in message:
            self.start_button.setEnabled(False)
        elif "Only the host can set the time control." in message:
            self.time_control_box.setEnabled(False)
        elif "Need two players to start." in message and self.is_host:
            self.start_button.setEnabled(True)
            self.time_control_box.setEnabled(True)
        elif "Game already started." in message:
            self.start_button.setEnabled(False)
            self.time_control_box.setEnabled(False)
        elif message.startswith("SERVER: ") and " renamed to " in message:
            rename_text = message[len("SERVER: "):]
            old_name, new_name = rename_text.split(" renamed to ", 1)
            old_name = old_name.strip()
            new_name = new_name.strip()

            if self.client.white_player == old_name:
                self.client.white_player = new_name
            if self.client.black_player == old_name:
                self.client.black_player = new_name

            self.update_match_label()