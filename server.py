import socket
import threading
import json
import random
import time
from model.Game import Game

# ---------------------- Global State ----------------------


clients: dict[socket.socket, str] = {}
game_started = False
white_player_socket: socket.socket | None = None
black_player_socket: socket.socket | None = None
game: Game | None = None
host_socket: socket.socket | None = None

game_time_minutes = 10
white_time_seconds = game_time_minutes * 60
black_time_seconds = game_time_minutes * 60
active_clock_color: str | None = None
active_turn_started_at: float | None = None
game_result_status: str | None = None

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

# ---------------------- Clock and Game Status Helpers ----------------------

def reset_clock_state(minutes: int):
    global game_time_minutes, white_time_seconds, black_time_seconds
    global active_clock_color, active_turn_started_at, game_result_status

    game_time_minutes = minutes
    white_time_seconds = minutes * 60
    black_time_seconds = minutes * 60
    active_clock_color = None
    active_turn_started_at = None
    game_result_status = None


def get_current_clock_values():
    global white_time_seconds, black_time_seconds

    current_white = white_time_seconds
    current_black = black_time_seconds

    if game_started and active_clock_color is not None and active_turn_started_at is not None:
        elapsed = int(time.monotonic() - active_turn_started_at)
        if active_clock_color == "white":
            current_white = max(0, white_time_seconds - elapsed)
        elif active_clock_color == "black":
            current_black = max(0, black_time_seconds - elapsed)

    return current_white, current_black


def commit_current_clock_values():
    global white_time_seconds, black_time_seconds, active_turn_started_at

    current_white, current_black = get_current_clock_values()
    white_time_seconds = current_white
    black_time_seconds = current_black
    active_turn_started_at = time.monotonic() if active_clock_color is not None else None


def check_timeout_state():
    global game_started, active_clock_color, active_turn_started_at, game_result_status

    if not game_started or game is None or game_result_status is not None:
        return False

    current_white, current_black = get_current_clock_values()

    if current_white <= 0:
        commit_current_clock_values()
        game_result_status = "timeout_black_wins"
        game_started = False
        active_clock_color = None
        active_turn_started_at = None
        broadcast_json({
            "type": "msg",
            "content": "SERVER: White ran out of time. Black wins."
        })
        broadcast_game_status()
        return True

    if current_black <= 0:
        commit_current_clock_values()
        game_result_status = "timeout_white_wins"
        game_started = False
        active_clock_color = None
        active_turn_started_at = None
        broadcast_json({
            "type": "msg",
            "content": "SERVER: Black ran out of time. White wins."
        })
        broadcast_game_status()
        return True

    return False


def clock_broadcast_loop():
    while True:
        try:
            if game is not None and (game_started or active_clock_color is not None):
                if not check_timeout_state():
                    broadcast_game_status()
        except Exception:
            pass
        time.sleep(1)

# ---------------------- Game Status Broadcast Helper ----------------------

def broadcast_game_status():
    if game is None:
        return

    current_white, current_black = get_current_clock_values()
    status = game_result_status if game_result_status is not None else game.get_game_status()
    game_over = bool(game_result_status is not None or game.is_game_over())

    broadcast_json({
        "type": "game_status",
        "content": {
            "status": status,
            "turn": game.get_turn(),
            "board": game.get_board(),
            "game_over": game_over,
            "en_passant_target": game.en_passant_target,
            "castling_rights": game.castling_rights,
            "white_time_seconds": current_white,
            "black_time_seconds": current_black,
            "time_minutes": game_time_minutes,
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

    elif command.startswith("settime"):
        handle_set_time(client_socket, username, command)

    elif command == "start":
        handle_start_game(client_socket, username)
# ---------------------- Set Time Handler ----------------------

def handle_set_time(client_socket: socket.socket, username: str, command: str):
    global game_time_minutes

    if client_socket != host_socket:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Only the host can set the time control."
        })
        return

    parts = command.split(maxsplit=1)
    if len(parts) != 2:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Usage: settime <minutes>"
        })
        return

    try:
        minutes = int(parts[1])
    except ValueError:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Time must be an integer number of minutes."
        })
        return

    if minutes not in (1, 3, 5, 10, 15):
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Allowed time controls are 1, 3, 5, 10, 15 minutes."
        })
        return

    if game_started:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: You cannot change the time control after the game has started."
        })
        return

    game_time_minutes = minutes
    reset_clock_state(game_time_minutes)

    broadcast_json({
        "type": "msg",
        "content": f"SERVER: {username} set the time control to {minutes} minutes."
    })

    if game is not None:
        broadcast_game_status()

def handle_move(client_socket: socket.socket, addr, username: str, content: dict):
    global game_started, white_player_socket, black_player_socket, game
    global active_clock_color, active_turn_started_at, game_result_status

    if not game_started or game is None or game_result_status is not None:
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

    if check_timeout_state():
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

    commit_current_clock_values()

    if not game.move((from_row, from_col), (to_row, to_col)):
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Move could not be executed."
        })
        return


    active_clock_color = game.get_turn()
    active_turn_started_at = time.monotonic()

    if game.is_game_over():
        game_result_status = game.get_game_status()
        game_started = False
        active_clock_color = None
        active_turn_started_at = None

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
    broadcast_json(data)

def handle_quit(client_socket: socket.socket, username: str):
    clients.pop(client_socket, None)
    data = {
        "type": "msg",
        "content": f"SERVER: {username} left."
    }
    broadcast_json(data, client_socket)

def handle_resign(client_socket: socket.socket, username: str):
    global game_started, white_player_socket, black_player_socket, game
    global active_clock_color, active_turn_started_at, game_result_status

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
            "game_over": True,
            "white_time_seconds": get_current_clock_values()[0],
            "black_time_seconds": get_current_clock_values()[1],
            "time_minutes": game_time_minutes,
        }
    })

    active_clock_color = None
    active_turn_started_at = None
    game_result_status = None

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
    global active_clock_color, active_turn_started_at, game_result_status, host_socket

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

    if client_socket != host_socket:
        send_json_to_client(client_socket, {
            "type": "msg",
            "content": "SERVER: Only the host can start the game."
        })
        return

    sockets = list(clients.keys())
    random.shuffle(sockets)
    white_player_socket = sockets[0]
    black_player_socket = sockets[1]
    white_name = clients[white_player_socket]
    black_name = clients[black_player_socket]

    game = Game()
    reset_clock_state(game_time_minutes)
    active_clock_color = "white"
    active_turn_started_at = time.monotonic()
    game_result_status = None
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
    global active_clock_color, active_turn_started_at, game_result_status, host_socket
    if disconnected_socket == host_socket:
        remaining_sockets = [sock for sock in clients.keys() if sock != disconnected_socket]
        host_socket = remaining_sockets[0] if remaining_sockets else None
        if host_socket is not None:
            send_json_to_client(host_socket, {
                "type": "host_assigned",
                "content": {
                    "is_host": True
                }
            })
            send_json_to_client(host_socket, {
                "type": "msg",
                "content": f"SERVER: {username} left. You are now the host."
            })

    if disconnected_socket not in (white_player_socket, black_player_socket):
        return

    game_started = False
    white_player_socket = None
    black_player_socket = None
    game = None

    active_clock_color = None
    active_turn_started_at = None
    game_result_status = None
    reset_clock_state(game_time_minutes)

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
    global host_socket
    server_ip = "127.0.0.1"
    port = 8000

    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((server_ip, port))
        server.listen()

        print(f"Listening on {server_ip}:{port}")
        clock_thread = threading.Thread(target=clock_broadcast_loop, daemon=True)
        clock_thread.start()

        while True:
            client_socket, addr = server.accept()
            if len(clients) < 2:
                send_json_to_client(client_socket, {
                    "type": "connection_accepted",
                    "content": ""
                })
                print(f"Accepted connection from {addr[0]}:{addr[1]}")
                clients[client_socket] = f"Anonymous{addr[1]}"
                if host_socket is None:
                    host_socket = client_socket
                    send_json_to_client(client_socket, {
                        "type": "host_assigned",
                        "content": {
                            "is_host": True
                        }
                    })
                else:
                    send_json_to_client(client_socket, {
                        "type": "host_assigned",
                        "content": {
                            "is_host": False
                        }
                    })
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
