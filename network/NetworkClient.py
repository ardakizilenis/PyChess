import socket
import json
import threading

from PySide6.QtCore import QObject, Signal


def send_json_to_server(client_socket: socket.socket, msg_type: str, msg_content: str | dict[str, list[int]]):
    message = json.dumps({
        "type": msg_type,
        "content": msg_content
    })
    client_socket.send(message.encode("utf-8"))

class NetworkClient(QObject):

    message_received = Signal(str)
    board_updated = Signal(object)
    captured_pieces_updated = Signal(object)
    game_status_received = Signal(dict)
    host_assigned = Signal(bool)
    game_started_received = Signal(dict)

    def __init__(self):
        super().__init__()
        self.isConnected = False
        self.connection_response = None
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_ip = "127.0.0.1"
        self.server_port = 8000

        self.my_color = None
        self.white_player = None
        self.black_player = None
        self.latest_game_status = None
        self.is_host = False

        self.mute_status = True
        self.last_announced_turn = None
        self.last_announced_status = None

    def connect(self):
        self.socket.connect((self.server_ip, self.server_port))

        thread = threading.Thread(
            target=self.receive_messages,
            daemon=True
        )
        thread.start()

        # wait for server response
        while self.connection_response is None:
            pass

    def send_chat(self, msg: str):
        send_json_to_server(self.socket, "msg", msg)

    def send_command(self, command: str):
        send_json_to_server(self.socket, "command", command)

    def send_move(self, from_row: int, from_col: int, to_row: int, to_col: int):
        send_json_to_server(self.socket, "move", {
            "from": [from_row, from_col],
            "to": [to_row, to_col]
        })

    def receive_messages(self):
        while True:
            try:
                response = self.socket.recv(1024)

                if not response:
                    break

                response = response.decode("utf-8")
                data = json.loads(response)

                msg_type = data.get("type")
                content = data.get("content")

                if msg_type == "msg":
                    self.message_received.emit(content)

                elif msg_type == "connection_accepted":
                    self.isConnected = True
                    self.connection_response = True

                elif msg_type == "connection_refused":
                    self.isConnected = False
                    self.connection_response = False

                elif msg_type == "board":
                    self.board_updated.emit(content)
                    self.captured_pieces_updated.emit(content)

                elif msg_type == "game_started":
                    self.my_color = content.get("color")
                    self.white_player = content.get("white")
                    self.black_player = content.get("black")
                    self.game_started_received.emit(content)
                    # Inform GUI / chat
                    self.message_received.emit(
                        f"SERVER: Game started! {self.white_player} (White) vs {self.black_player} (Black). You are {self.my_color}."
                    )

                elif msg_type == "host_assigned":
                    is_host = bool(content.get("is_host")) if isinstance(content, dict) else False
                    self.is_host = is_host
                    self.host_assigned.emit(is_host)

                elif msg_type == "game_status":
                    self.latest_game_status = content
                    self.game_status_received.emit(content)

                    status = content.get("status")
                    turn = content.get("turn")

                    # Status announcement logic
                    if self.mute_status:
                        continue

                    if status != self.last_announced_status:
                        if status == "check_white":
                            self.message_received.emit("WHITE IS IN CHECK")
                        elif status == "check_black":
                            self.message_received.emit("BLACK IS IN CHECK")
                        elif status == "checkmate_white_wins":
                            self.message_received.emit("CHECKMATE. WHITE WINS!")
                        elif status == "checkmate_black_wins":
                            self.message_received.emit("CHECKMATE. BLACK WINS!")
                        elif status == "stalemate":
                            self.message_received.emit("STALEMATE. GAME OVER!")
                        elif status == "resignation_white_wins":
                            self.message_received.emit("BLACK RESIGNED. WHITE WINS!")
                        elif status == "resignation_black_wins":
                            self.message_received.emit("WHITE RESIGNED. BLACK WINS!")
                        elif status == "timeout_white_wins":
                            self.message_received.emit("TIMEOUT. WHITE WINS!")
                        elif status == "timeout_black_wins":
                            self.message_received.emit("TIMEOUT. BLACK WINS!")

                    if status in ("ongoing", "check_white", "check_black") and turn is not None and turn != self.last_announced_turn:
                        pass

                    self.last_announced_status = status
                    if turn is not None:
                        self.last_announced_turn = turn

            except Exception:
                break