from html import escape

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QSizePolicy
)

from network.NetworkClient import NetworkClient


class ChatWidget(QWidget):
    CHAT_STYLESHEET = """
        .chat-user { color: #B0B0B0; font-family: 'Courier New', 'Consolas', 'Menlo', monospace; }
        .chat-self { color: #C8C8C8; font-weight: 600; font-family: 'Courier New', 'Consolas', 'Menlo', monospace; }
        .chat-server-info { color: #8E8E8E; font-style: italic; font-family: 'Courier New', 'Consolas', 'Menlo', monospace; }
        .chat-server-event { color: #BDB76B; font-weight: 600; font-family: 'Courier New', 'Consolas', 'Menlo', monospace; }
        .chat-server-error { color: #C97B63; font-weight: 600; font-family: 'Courier New', 'Consolas', 'Menlo', monospace; }
        .chat-server-success { color: #8FB38F; font-weight: 600; font-family: 'Courier New', 'Consolas', 'Menlo', monospace; }
    """

    SERVER_ERROR_KEYWORDS = (
        "illegal",
        "invalid",
        "only the host",
        "cannot change the active opponent",
        "host cannot become the active opponent",
        "only the host can transfer host rights",
        "cannot transfer host rights",
        "is already the host",
        "already taken",
        "between 1 and 12 characters",
        "usage:",
        "cannot",
        "no active game",
        "need two players",
        "need two active players",
        "already pending",
        "not part of the current game",
        "out of bounds",
    )

    SERVER_SUCCESS_KEYWORDS = (
        "wins",
        "checkmate",
        "timeout",
        "draw offer accepted",
        "game started",
        "you are now the host",
        "is now the active opponent",
        "is now the host",
    )

    SERVER_INFO_KEYWORDS = (
        "joined",
        "left",
        "renamed",
        "set the time control",
        "draw offer sent",
        "offered a draw",
        "declined",
        "disconnected",
        "muted",
        "spectating",
        "queue position",
        "active opponent",
        "usage: \\ao <username>",
        "usage: \\host <username>",
        "connected players:",
        "(host)",
        "(active opponent)",
        "(spectator)",
    )

    def __init__(self, network_client: NetworkClient):
        super().__init__()

        self.client = network_client

        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout()

        self.chat_view = QTextEdit()
        self.chat_view.setStyleSheet(
            "color: #B0B0B0; font-family: 'Courier New', 'Consolas', 'Menlo', monospace;"
        )
        self.chat_view.setReadOnly(True)
        self.chat_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.chat_view.document().setDefaultStyleSheet(self.CHAT_STYLESHEET)

        self.input = QLineEdit()
        self.input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input.setPlaceholderText("Type message...")

        self.send_button = QPushButton("Send")

        input_row = QHBoxLayout()
        input_row.addWidget(self.input)
        input_row.addWidget(self.send_button)

        layout.addWidget(self.chat_view)
        layout.addLayout(input_row)

        self.setLayout(layout)

    def _connect_signals(self):
        self.input.returnPressed.connect(self.send_message)
        self.send_button.clicked.connect(self.send_message)
        self.client.message_received.connect(self.receive_message)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send_message(self):
        msg = self.input.text().strip()

        if msg == "":
            return

        if msg.startswith("\\"):
            self._handle_command_input(msg)
        else:
            self._handle_chat_input(msg)

        self.input.clear()

    def _handle_chat_input(self, msg: str):
        self.client.send_chat(msg)
        self.append_message(f">> You: {msg}", "chat-self")

    def _handle_command_input(self, msg: str):
        if msg in ("\\quit", "\\q"):
            self.client.send_command("quit")
            QApplication.quit()
            return

        if msg == "\\debug":
            self._toggle_mutestatus()
            return

        if msg == "\\muteall":
            self.client.send_command("muteall")
            return

        if msg in ("\\rename", "\\r"):
            self._show_usage("\\rename <name> or \\r <name> (rename yourself)")
            return

        if msg.startswith("\\rename ") or msg.startswith("\\r "):
            self._handle_rename_command(msg)
            return

        if msg == "\\mute":
            self._show_usage("\\mute <username> or \\m <username> (mutes messages from a user)")
            return

        if msg.startswith("\\mute ") or msg.startswith("\\m "):
            self._handle_target_command(msg, command_name="mute", usage="\\mute <username>")
            return

        if msg == "\\kick":
            self._show_usage("\\kick <username> or \\k <username> (kicks a user, host only)")
            return

        if msg.startswith("\\kick ") or msg.startswith("\\k "):
            self._handle_target_command(msg, command_name="kick", usage="\\kick <username>")
            return

        if msg == "\\ao":
            self._show_usage("\\ao <username> (assign other opponent, host only)")
            return

        if msg.startswith("\\ao "):
            self._handle_target_command(msg, command_name="ao", usage="\\ao <username>")
            return

        if msg == "\\host":
            self._show_usage("\\host <username> (transfer host rights, host only)")
            return

        if msg.startswith("\\host "):
            self._handle_target_command(msg, command_name="host", usage="\\host <username>")
            return

        if msg in ("\\list", "\\l"):
            self.client.send_command("list")
            return

        self.append_message("Unknown command", "chat-server-error")

    def _handle_rename_command(self, msg: str):
        name = msg.split(maxsplit=1)[1]
        self.client.send_command(f"rename {name}")

        if not self.client.mute_status:
            self.append_message(f"Successfully renamed to {name}", "chat-server-success")

    def _handle_target_command(self, msg: str, command_name: str, usage: str):
        target = msg.split(maxsplit=1)[1].strip()

        if not target:
            self._show_usage(usage)
            return

        self.client.send_command(f"{command_name} {target}")

    def _toggle_mutestatus(self):
        if self.client.mute_status is False:
            self.client.mute_status = True
            self.client.message_received.emit("Server status muted")
        else:
            self.client.mute_status = False
            self.client.message_received.emit("Server status unmuted")

    def _show_usage(self, usage: str):
        self.append_message(f"Usage: {usage}", "chat-server-info")
        self.input.clear()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def append_message(self, msg: str, css_class: str):
        display_msg = msg
        if isinstance(display_msg, str) and display_msg.startswith("SERVER: "):
            display_msg = display_msg[len("SERVER: "):]

        safe_msg = escape(display_msg).replace("\n", "<br>")
        self.chat_view.append(f'<span class="{css_class}">{safe_msg}</span>')

    def receive_message(self, msg: str):
        css_class = self.classify_message(msg)
        self.append_message(msg, css_class)

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify_message(self, msg: str) -> str:
        if msg.startswith(">> "):
            return "chat-user"

        if msg.startswith("SERVER:"):
            return self._classify_server_message(msg)

        if msg.isupper():
            return "chat-server-event"

        return "chat-user"

    def _classify_server_message(self, msg: str) -> str:
        lowered = msg.lower()

        if self._contains_any(lowered, self.SERVER_ERROR_KEYWORDS):
            return "chat-server-error"

        if self._contains_any(lowered, self.SERVER_SUCCESS_KEYWORDS):
            return "chat-server-success"

        if self._contains_any(lowered, self.SERVER_INFO_KEYWORDS):
            return "chat-server-info"

        return "chat-server-event"

    @staticmethod
    def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)