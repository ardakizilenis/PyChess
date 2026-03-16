import socket
import threading
import json
import random
from model.Game import Game

# ---------------------- Global State ----------------------


clients: dict[socket.socket, str] = {}
game_started = False
white_player_socket: socket.socket | None = None
black_player_socket: socket.socket | None = None
game: Game | None = None

# ---------------------- Send and Broadcast ----------------------

def send(client: socket.socket, message: str):
    try:
        client.send(message.encode("utf-8"))
    except Exception:
        pass

def broadcast_json(data: dict, sender_socket=None):
    for client in list(clients.keys()):
        if client != sender_socket:
            send_json_to_client(client, data)

def send_json_to_client(client: socket.socket, json_data: dict | None = None):
    try:
        json_data = json.dumps(json_data)
        client.send(json_data.encode("utf-8"))
    except Exception:
        pass

# ---------------------- Game Status Broadcast Helper ----------------------

def broadcast_game_status():
    if game is None:
        return

    status = game.get_game_status()
    broadcast_json({
        "type": "game_status",
        "content": {
            "status": status,
            "turn": game.get_turn(),
            "board": game.get_board(),
            "game_over": game.is_game_over()
        }
    })

# ---------------------- Message Type Handlers ----------------------

def handle_chat(client_socket: socket.socket, addr, username: str, content: str):
    print(f"{addr[0]}:{addr[1]} ({username}), MSG: {content}")

    data = {
        "type": "msg",
        "content": f">> {username}: {content}"
    }
    broadcast_json(data, client_socket)

def handle_command(client_socket: socket.socket, addr, username: str, command: str):
    print(f"{addr[0]}:{addr[1]} ({username}), COMMAND: {command}")

    if command.startswith("rename"):
        handle_rename(client_socket, command)

    elif command == "quit":
        handle_quit(client_socket, username)

    elif command == "resign":
        handle_resign(client_socket, username)

    elif command == "draw":
        handle_offer_draw(client_socket, username)

    elif command == "start":
        handle_start_game(client_socket, username)

def handle_move(client_socket: socket.socket, addr, username: str, content: dict):
    global game_started, white_player_socket, black_player_socket, game

    if not game_started or game is None:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Game has not started yet."
        })
        return

    if client_socket == white_player_socket:
        player_color = "white"
    elif client_socket == black_player_socket:
        player_color = "black"
    else:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: You are not part of the current game."
        })
        return

    if not isinstance(content, dict):
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Invalid move payload."
        })
        return

    from_pos = content.get("from")
    to_pos = content.get("to")

    if (
        not isinstance(from_pos, list) or len(from_pos) != 2 or
        not isinstance(to_pos, list) or len(to_pos) != 2
    ):
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Move must contain 'from' and 'to'."
        })
        return

    from_row, from_col = from_pos
    to_row, to_col = to_pos

    if not all(isinstance(x, int) for x in [from_row, from_col, to_row, to_col]):
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Move coordinates must be integers."
        })
        return

    if not all(0 <= x < 8 for x in [from_row, from_col, to_row, to_col]):
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Move coordinates out of bounds."
        })
        return

    if game.get_turn() != player_color:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": f"SERVER: It is {game.get_turn()}'s turn."
        })
        return

    piece = game.get_piece(from_row, from_col)

    if piece is None:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: No piece on source square."
        })
        return

    if player_color == "white" and not piece.startswith("w"):
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: That is not your piece."
        })
        return

    if player_color == "black" and not piece.startswith("b"):
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: That is not your piece."
        })
        return

    if not game.is_legal_move((from_row, from_col), (to_row, to_col)):
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Illegal move."
        })
        return

    if not game.move((from_row, from_col), (to_row, to_col)):
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Move could not be executed."
        })
        return

    broadcast_json({
        "type": "board",
        "content": game.get_board()
    })
    broadcast_game_status()

# ---------------------- Command Handlers ----------------------

def handle_rename(client_socket: socket.socket, command: str):
    parts = command.split(maxsplit=1)
    if len(parts) < 2:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Usage: \\rename <name>"
        })
        return
    new_name = parts[1]
    old_name = clients[client_socket]
    clients[client_socket] = new_name
    data = {
        "type": "msg",
        "content": f"SERVER: {old_name} renamed to {new_name}"
    }
    broadcast_json(data, client_socket)

def handle_quit(client_socket: socket.socket, username: str):
    clients.pop(client_socket, None)
    data = {
        "type": "msg",
        "content": f"SERVER: {username} left."
    }
    broadcast_json(data, client_socket)

def handle_resign(client_socket: socket.socket, username: str):
    global game_started, white_player_socket, black_player_socket, game

    if not game_started or game is None:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: No active game to resign from."
        })
        return

    if client_socket == white_player_socket:
        winner = clients.get(black_player_socket, "Black")
        result = "black"
    elif client_socket == black_player_socket:
        winner = clients.get(white_player_socket, "White")
        result = "white"
    else:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: You are not part of the current game."
        })
        return

    broadcast_json({
        "type": "msg",
        "content": f"SERVER: {username} resigned. {winner} wins."
    })

    broadcast_json({
        "type": "game_status",
        "content": {
            "status": f"resignation_{result}_wins",
            "turn": game.get_turn(),
            "board": game.get_board(),
            "game_over": True
        }
    })

    game_started = False
    white_player_socket = None
    black_player_socket = None
    game = None

def handle_offer_draw(client_socket: socket.socket, username: str):
    global game_started, white_player_socket, black_player_socket, game

    if not game_started or game is None:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: No active game to offer a draw in."
        })
        return

    broadcast_json({
        "type": "msg",
        "content": f"SERVER: {username} offered a draw."
    }, client_socket)

def handle_start_game(client_socket: socket.socket, username: str):
    global game_started, white_player_socket, black_player_socket, game

    if len(clients) != 2:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Need two players to start."
        })
        return

    if game_started:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Game already started."
        })
        return

    sockets = list(clients.keys())
    random.shuffle(sockets)
    white_player_socket = sockets[0]
    black_player_socket = sockets[1]
    white_name = clients[white_player_socket]
    black_name = clients[black_player_socket]

    game = Game()
    game_started = True

    send_json_to_client(white_player_socket, {
        "type": "game_started",
        "content": {
            "color": "white",
            "white": white_name,
            "black": black_name
        }
    })

    send_json_to_client(black_player_socket, {
        "type": "game_started",
        "content": {
            "color": "black",
            "white": white_name,
            "black": black_name
        }
    })

    broadcast_json({
        "type": "board",
        "content": game.get_board()
    })
    broadcast_game_status()

# ---------------------- Client Thread ----------------------

def reset_game_state_if_needed(disconnected_socket: socket.socket, username: str | None):
    global game_started, white_player_socket, black_player_socket, game

    if disconnected_socket not in (white_player_socket, black_player_socket):
        return

    game_started = False
    white_player_socket = None
    black_player_socket = None
    game = None

    if username:
        broadcast_json({
            "type": "msg",
            "content": f"SERVER: {username} disconnected. Game Over!"
        }, disconnected_socket)

# ---------------------- Client Thread ----------------------

def handle_client(client_socket: socket.socket, addr):
    try:
        while True:
            username = clients.get(client_socket)
            request = client_socket.recv(1024).decode("utf-8")
            if not request:
                break

            try:
                request_json = json.loads(request)
                msg_type = request_json.get("type")
                content = request_json.get("content")

                if msg_type == "msg":
                    handle_chat(client_socket, addr, username, content)

                elif msg_type == "command":
                    handle_command(client_socket, addr, username, content)

                elif msg_type == "move":
                    handle_move(client_socket, addr, username, content)

            except json.JSONDecodeError:
                send_json_to_client(client_socket, {
                    "type": "msg",
                    "content": "SERVER: invalid json"
                })
                continue

    except Exception as e:
        print(f"Error handling client: {e}")

    finally:
        username = clients.pop(client_socket, None)
        reset_game_state_if_needed(client_socket, username)
        client_socket.close()
        print(f"Connection to client ({addr[0]}:{addr[1]}) closed")


# ---------------------- Server ----------------------

def run_server():
    server_ip = "127.0.0.1"
    port = 8001

    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((server_ip, port))
        server.listen()

        print(f"Listening on {server_ip}:{port}")

        while True:
            client_socket, addr = server.accept()
            if len(clients) < 2:
                send_json_to_client(client_socket, {
                    "type": "connection_accepted",
                    "content": ""
                })
                print(f"Accepted connection from {addr[0]}:{addr[1]}")
                clients[client_socket] = f"Anonymous{addr[1]}"
                broadcast_json({
                    "type": "msg",
                    "content": f"SERVER: Anonymous{addr[1]} joined"
                }, client_socket)
                thread = threading.Thread(
                    target=handle_client,
                    args=(client_socket, addr),
                    daemon=True,
                )
                thread.start()

            else:
                send_json_to_client(client_socket, {
                    "type": "connection_refused",
                    "content": ""
                })
                print(f"Refused connection from {addr[0]}:{addr[1]}")
                client_socket.close()

    except Exception as e:
        print(f"Server error: {e}")

    finally:
        server.close()


run_server()
