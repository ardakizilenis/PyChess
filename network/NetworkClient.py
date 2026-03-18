import socket
import json
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


def send_json_to_server(client_socket: socket.socket, msg_type: str, msg_content: str | dict[str, list[int]]):
    message = json.dumps({
        "type": msg_type,
        "content": msg_content
    }) + "\n"
    client_socket.sendall(message.encode("utf-8"))


class LocalhostShortcutLineEdit(QLineEdit):
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Space:
            self.setText("127.0.0.1")
            self.end(False)
            event.accept()
            return
        super().keyPressEvent(event)


class ConnectionDialog(QDialog):
    def __init__(self, current_ip: str, current_port: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Server")
        self.setModal(True)

        self._build_ui(current_ip, current_port)

    def _build_ui(self, current_ip: str, current_port: int):
        layout = QVBoxLayout()

        ip_row = QHBoxLayout()
        ip_row.addWidget(QLabel("IP:"))
        self.ip_input = LocalhostShortcutLineEdit()
        self.ip_input.setPlaceholderText("Enter server IP (Space = 127.0.0.1)")
        self.ip_input.setText(current_ip)
        ip_row.addWidget(self.ip_input)
        layout.addLayout(ip_row)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Port:"))
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("Enter server port")
        self.port_input.setText(str(current_port))
        port_row.addWidget(self.port_input)
        layout.addLayout(port_row)

        button_row = QHBoxLayout()
        self.connect_button = QPushButton("Connect")
        self.cancel_button = QPushButton("Cancel")
        self.connect_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.connect_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.setLayout(layout)

    def get_connection_data(self) -> tuple[str, int] | None:
        ip = self.ip_input.text().strip()
        port_text = self.port_input.text().strip()

        if not ip:
            QMessageBox.warning(self, "Invalid IP", "Please enter an IP address.")
            return None

        try:
            port = int(port_text)
        except ValueError:
            QMessageBox.warning(self, "Invalid Port", "Port must be a valid number.")
            return None

        if not (1 <= port <= 65535):
            QMessageBox.warning(self, "Invalid Port", "Port must be between 1 and 65535.")
            return None

        return ip, port

    def accept(self):
        data = self.get_connection_data()
        if data is None:
            return
        super().accept()


class NetworkClient(QObject):
    message_received = Signal(str)
    board_updated = Signal(object)
    captured_pieces_updated = Signal(object)
    game_status_received = Signal(dict)
    time_control_updated = Signal(int)
    host_assigned = Signal(bool)
    game_started_received = Signal(dict)
    role_updated = Signal(dict)
    kicked_from_server = Signal(str)

    STATUS_ANNOUNCEMENTS = {
        "check_white": "WHITE IS IN CHECK",
        "check_black": "BLACK IS IN CHECK",
        "checkmate_white_wins": "CHECKMATE. WHITE WINS!",
        "checkmate_black_wins": "CHECKMATE. BLACK WINS!",
        "draw_fifty_move_rule": "DRAW BY 50-MOVE RULE. GAME OVER!",
        "draw_threefold_repetition": "DRAW BY THREEFOLD REPETITION. GAME OVER!",
        "draw_insufficient_material": "DRAW BY INSUFFICIENT MATERIAL. GAME OVER!",
        "draw_by_agreement": "DRAW BY AGREEMENT. GAME OVER!",
        "resignation_white_wins": "BLACK RESIGNED. WHITE WINS!",
        "resignation_black_wins": "WHITE RESIGNED. BLACK WINS!",
        "timeout_white_wins": "TIMEOUT. WHITE WINS!",
        "timeout_black_wins": "TIMEOUT. BLACK WINS!",
        "disconnect_white_wins": "DISCONNECT. WHITE WINS!",
        "disconnect_black_wins": "DISCONNECT. BLACK WINS!"
    }

    def __init__(self):
        super().__init__()

        self.isConnected = False
        self.connection_response = None
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_ip = "127.0.0.1"
        self.server_port = 8080
        self.connection_dialog = None

        self.my_color = None
        self.white_player = None
        self.black_player = None
        self.latest_game_status = None
        self.latest_board = None
        self.is_host = False
        self.host_assignment_received = False
        self.role = "spectator"
        self.queue_position = None
        self.can_play = False
        self.can_start = False

        self.mute_status = True
        self.last_announced_turn = None
        self.last_announced_status = None
        self.receive_buffer = ""
        self.last_kick_reason = None

    # ------------------------------------------------------------------
    # Session state
    # ------------------------------------------------------------------

    def reset_session_state(self):
        self.isConnected = False
        self.connection_response = None
        self.my_color = None
        self.white_player = None
        self.black_player = None
        self.latest_game_status = None
        self.latest_board = None
        self.is_host = False
        self.host_assignment_received = False
        self.role = "spectator"
        self.queue_position = None
        self.can_play = False
        self.can_start = False
        self.last_announced_turn = None
        self.last_announced_status = None
        self.receive_buffer = ""

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    def prompt_connection_data(self, parent=None) -> bool:
        self.connection_dialog = ConnectionDialog(self.server_ip, self.server_port, parent)
        if self.connection_dialog.exec() != QDialog.Accepted:
            return False

        data = self.connection_dialog.get_connection_data()
        if data is None:
            return False

        self.server_ip, self.server_port = data
        return True

    def connect(self, parent=None, show_dialog: bool = True) -> bool:
        if show_dialog and not self.prompt_connection_data(parent):
            return False

        self.reset_session_state()
        self.last_kick_reason = None
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        if not self._connect_socket(parent):
            return False

        self._start_receive_thread()

        while self.connection_response is None:
            pass

        if self.connection_response:
            while not self.host_assignment_received:
                pass
            return True

        QMessageBox.warning(
            parent,
            "Connection Refused",
            "The server refused the connection.",
        )
        return False

    def _connect_socket(self, parent=None) -> bool:
        try:
            self.socket.connect((self.server_ip, self.server_port))
            return True
        except Exception as exc:
            QMessageBox.critical(
                parent,
                "Connection Failed",
                f"Could not connect to {self.server_ip}:{self.server_port}.\n\n{exc}",
            )
            return False

    def _start_receive_thread(self):
        thread = threading.Thread(
            target=self.receive_messages,
            daemon=True
        )
        thread.start()

    # ------------------------------------------------------------------
    # Outgoing messages
    # ------------------------------------------------------------------

    def send_chat(self, msg: str):
        send_json_to_server(self.socket, "msg", msg)

    def send_command(self, command: str):
        send_json_to_server(self.socket, "command", command)

    def send_move(self, from_row: int, from_col: int, to_row: int, to_col: int, promotion: str | None = None):
        payload = {
            "from": [from_row, from_col],
            "to": [to_row, to_col]
        }
        if promotion is not None:
            payload["promotion"] = promotion
        send_json_to_server(self.socket, "move", payload)

    # ------------------------------------------------------------------
    # Incoming message dispatch
    # ------------------------------------------------------------------

    def handle_message_data(self, data: dict):
        msg_type = data.get("type")
        content = data.get("content")

        if msg_type == "msg":
            self._handle_msg(content)
        elif msg_type == "connection_accepted":
            self._handle_connection_accepted()
        elif msg_type == "connection_refused":
            self._handle_connection_refused()
        elif msg_type == "kicked":
            self._handle_kicked(content)
        elif msg_type == "board":
            self._handle_board(content)
        elif msg_type == "game_started":
            self._handle_game_started(content)
        elif msg_type == "host_assigned":
            self._handle_host_assigned(content)
        elif msg_type == "role_update":
            self._handle_role_update(content)
        elif msg_type == "game_status":
            self._handle_game_status(content)
        elif msg_type == "time_control_updated":
            if isinstance(content, dict):
                minutes = content.get("time_minutes")
                if isinstance(minutes, int) and minutes > 0:
                    if isinstance(self.latest_game_status, dict):
                        merged_status = dict(self.latest_game_status)
                        merged_status["time_minutes"] = minutes
                    else:
                        merged_status = {"time_minutes": minutes}
                    self.latest_game_status = merged_status
                    self.time_control_updated.emit(minutes)

    def _handle_msg(self, content):
        self.message_received.emit(content)

    def _handle_connection_accepted(self):
        self.isConnected = True
        self.connection_response = True

    def _handle_connection_refused(self):
        self.isConnected = False
        self.connection_response = False

    def _handle_kicked(self, content):
        reason = "You were kicked by the host."
        if isinstance(content, dict):
            reason = content.get("reason", reason)

        self.last_kick_reason = reason

        try:
            self.socket.close()
        except Exception:
            pass

        self.reset_session_state()
        self.kicked_from_server.emit(reason)

    def _handle_board(self, content):
        self.latest_board = content
        self.board_updated.emit(content)
        self.captured_pieces_updated.emit(content)

    def _handle_game_started(self, content):
        if not isinstance(content, dict):
            return

        self.my_color = content.get("color")
        self.white_player = content.get("white")
        self.black_player = content.get("black")
        self.can_play = self.role in ("host", "opponent")

        self.game_started_received.emit(content)
        self.message_received.emit(
            f"SERVER: Game started! {self.white_player} (White) vs {self.black_player} (Black). You are {self.my_color}."
        )

    def _handle_host_assigned(self, content):
        is_host = bool(content.get("is_host")) if isinstance(content, dict) else False
        self.is_host = is_host
        self.host_assignment_received = True
        self.host_assigned.emit(is_host)

    def _handle_role_update(self, content):
        if not isinstance(content, dict):
            return

        self.role = content.get("role", "spectator")
        self.queue_position = content.get("queue_position")
        self.is_host = bool(content.get("is_host", False))
        self.can_start = bool(content.get("can_start", False))
        self.can_play = bool(content.get("can_play", False))
        self.host_assignment_received = True

        self.role_updated.emit(content)

    def _handle_game_status(self, content):
        if not isinstance(content, dict):
            return

        self.latest_game_status = content
        self.can_play = self.role in ("host", "opponent") and not bool(content.get("game_over"))
        self.game_status_received.emit(content)

        status = content.get("status")
        turn = content.get("turn")

        if self.mute_status:
            return

        self._announce_status_if_changed(status)

        self.last_announced_status = status
        if turn is not None:
            self.last_announced_turn = turn

    def _announce_status_if_changed(self, status):
        if status == self.last_announced_status:
            return

        announcement = self.STATUS_ANNOUNCEMENTS.get(status)
        if announcement is not None:
            self.message_received.emit(announcement)

    # ------------------------------------------------------------------
    # Receive loop
    # ------------------------------------------------------------------

    def receive_messages(self):
        while True:
            try:
                response = self.socket.recv(4096)

                if not response:
                    break

                self.receive_buffer += response.decode("utf-8")

                while "\n" in self.receive_buffer:
                    raw_message, self.receive_buffer = self.receive_buffer.split("\n", 1)
                    raw_message = raw_message.strip()

                    if not raw_message:
                        continue

                    data = self._parse_json_message(raw_message)
                    if data is None:
                        continue

                    self.handle_message_data(data)

            except Exception:
                self.isConnected = False
                break

    def _parse_json_message(self, raw_message: str) -> dict | None:
        try:
            return json.loads(raw_message)
        except json.JSONDecodeError:
            return None