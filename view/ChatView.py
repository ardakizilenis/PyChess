from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTextEdit, QLineEdit, QSizePolicy
)

from network.NetworkClient import NetworkClient


class ChatWidget(QWidget):

    def __init__(self, network_client: NetworkClient):
        super().__init__()

        self.client = network_client

        layout = QVBoxLayout()

        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.input = QLineEdit()
        self.input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input.setPlaceholderText("Type message...")
        self.input.returnPressed.connect(self.send_message)

        layout.addWidget(self.chat_view)
        layout.addWidget(self.input)

        self.setLayout(layout)

        self.client.message_received.connect(self.receive_message)

    def send_message(self):
        msg = self.input.text().strip()

        if msg == "":
            return

        if msg.startswith("\\"):
            if msg == "\\quit":
                self.client.send_command("quit")
                QApplication.quit()
                return

            elif msg == "\\rename" or msg == "\\rename ":
                self.chat_view.append("Usage: \\rename <name>")
                self.input.clear()
                return

            elif msg.startswith("\\rename "):
                name = msg.split(maxsplit=1)[1]
                self.client.send_command(f"rename {name}")
                if not self.client.mute_status:
                    self.chat_view.append(f"Successfully renamed to {name}")

            elif msg == "\\start":
                self.client.send_command("start")

            elif msg == "\\mute" and self.client.mute_status == False:
                self.client.mute_status = True
                self.client.message_received.emit("Server status muted")
            elif msg == "\\mute" and self.client.mute_status == True:
                self.client.mute_status = False
                self.client.message_received.emit("Server status unmuted")

            else:
                self.chat_view.append("Unknown command")
                self.input.clear()
                return

        else:
            self.client.send_chat(msg)
            self.chat_view.append(f">> You: {msg}")

        self.input.clear()

    def receive_message(self, msg: str):
        self.chat_view.append(msg)