import json
import logging
import random
import shutil
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from model.Game import Game

# ---------------------- Global State ----------------------

# Network
clients: dict[socket.socket, str] = {}
game_started = False
white_player_socket: socket.socket | None = None
black_player_socket: socket.socket | None = None
game: Game | None = None
host_socket: socket.socket | None = None
opponent_socket: socket.socket | None = None
spectator_queue: list[socket.socket] = []
muted_sockets_by_client: dict[socket.socket, set[socket.socket]] = {}
mute_all_clients: set[socket.socket] = set()
kicked_clients: set[socket.socket] = set()

# Game
game_time_minutes = 10
white_time_seconds = game_time_minutes * 60
black_time_seconds = game_time_minutes * 60
active_clock_color: str | None = None
active_turn_started_at: float | None = None
game_result_status: str | None = None
pending_draw_offer_from: socket.socket | None = None
pending_game_offer_from: socket.socket | None = None

# AI
ai_enabled = False
ai_color: str | None = None
ai_level = 10
ai_players: dict[str, int] = {}
engine_board: chess.Board | None = None
stockfish_engine: chess.engine.SimpleEngine | None = None

# PGN
pgn_game = None
pgn_node = None
pgn_moves = []
PGN_DIR = Path(__file__).resolve().parent / "pgn_games"
PGN_DIR.mkdir(exist_ok=True)

# Logs
LOG_DIR = Path(__file__).resolve().parent / "server_logs"
LOG_DIR.mkdir(exist_ok=True)
session_log_entries: list[str] = []
session_log_lock = threading.Lock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

ALLOWED_TIME_CONTROLS = (1, 3, 5, 10, 15, 20, 30, 60)
ALLOWED_AI_LEVELS = tuple(range(1, 21))
AI_MOVE_DELAY_SECONDS = 0.25

# ---------------------- Generic Helpers ----------------------

def send(client: socket.socket, message: str):
    try:
        client.sendall(message.encode("utf-8"))
    except Exception:
        pass


def send_json_to_client(client: socket.socket, json_data: dict | None = None):
    try:
        payload = json.dumps(json_data) + "\n"
        client.sendall(payload.encode("utf-8"))
        log_json_event("SEND", json_data, client_socket=client)
    except Exception:
        pass
def append_session_log(line: str):
    with session_log_lock:
        session_log_entries.append(line)


def log_json_event(direction: str, payload, client_socket: socket.socket | None = None, addr=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    endpoint = "unknown"

    if addr is not None:
        endpoint = f"{addr[0]}:{addr[1]}"
    elif client_socket is not None:
        try:
            peer = client_socket.getpeername()
            endpoint = f"{peer[0]}:{peer[1]}"
        except Exception:
            endpoint = "disconnected"

    try:
        payload_text = json.dumps(payload, ensure_ascii=False)
    except TypeError:
        payload_text = repr(payload)

    line = f"{timestamp} [{direction}] [{endpoint}] {payload_text}"
    logging.info(line)
    append_session_log(line)


def flush_session_logs_to_file():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"server_session_{timestamp}.log"

    with session_log_lock:
        lines = list(session_log_entries)

    if not lines:
        lines = [f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [INFO] No JSON traffic recorded."]

    with open(log_path, "w", encoding="utf-8") as log_file:
        log_file.write("\n".join(lines) + "\n")

    logging.info(f"Session logs written to {log_path}")


def send_server_msg(client_socket: socket.socket, message: str):
    send_json_to_client(client_socket, {
        "type": "msg",
        "content": message,
    })


def broadcast_json(data: dict, sender_socket=None):
    for client in list(clients.keys()):
        if client != sender_socket:
            send_json_to_client(client, data)


def broadcast_server_msg(message: str, sender_socket=None):
    broadcast_json({
        "type": "msg",
        "content": message,
    }, sender_socket)


def close_socket_safely(client_socket: socket.socket):
    try:
        client_socket.close()
    except Exception:
        pass


def shutdown_and_close_socket(client_socket: socket.socket):
    try:
        client_socket.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass
    close_socket_safely(client_socket)


def clear_mute_state_for_client(client_socket: socket.socket):
    muted_sockets_by_client.pop(client_socket, None)
    mute_all_clients.discard(client_socket)
    for muted_set in muted_sockets_by_client.values():
        muted_set.discard(client_socket)


def current_game_times_dict() -> dict:
    current_white, current_black = get_current_clock_values()
    return {
        "white_time_seconds": current_white,
        "black_time_seconds": current_black,
        "time_minutes": game_time_minutes,
    }


def broadcast_board_state():
    if game is None:
        return
    broadcast_json({
        "type": "board",
        "content": game.get_board(),
    })


def clamp_ai_level(level: int) -> int:
    if level < 1:
        return 1
    if level > 20:
        return 20
    return level


def parse_ai_level(level_arg: str, default: int = 10) -> int:
    try:
        return clamp_ai_level(int(level_arg))
    except (TypeError, ValueError):
        return default


# ---------------------- Username Helpers ----------------------

def is_username_taken(username: str, exclude_socket: socket.socket | None = None) -> bool:
    for client_socket, existing_username in clients.items():
        if client_socket == exclude_socket:
            continue
        if existing_username == username:
            return True
    return False


def is_valid_username_length(username: str) -> bool:
    return 1 <= len(username) <= 12


def generate_default_username(seed_number: int) -> str:
    base = f"Guest{seed_number}"
    if len(base) > 12:
        base = base[:12]

    if not is_username_taken(base):
        return base

    counter = 1
    while True:
        suffix = str(counter)
        prefix = "Guest"
        max_prefix_len = 12 - len(suffix)
        candidate = f"{prefix[:max_prefix_len]}{suffix}"
        if not is_username_taken(candidate):
            return candidate
        counter += 1


# ---------------------- Lobby / Roles ----------------------

def get_role_for_socket(client_socket: socket.socket) -> str:
    if client_socket == host_socket:
        return "host"
    if client_socket == opponent_socket:
        return "opponent"
    if client_socket in spectator_queue:
        return "spectator"
    return "spectator"


def get_queue_position(client_socket: socket.socket):
    if client_socket in spectator_queue:
        return spectator_queue.index(client_socket) + 1
    return None


def send_role_update(client_socket: socket.socket):
    role = get_role_for_socket(client_socket)

    if game_started:
        can_play = client_socket in (white_player_socket, black_player_socket)
        can_start = False
    else:
        can_play = client_socket in (host_socket, opponent_socket)
        can_start = client_socket == host_socket

    send_json_to_client(client_socket, {
        "type": "role_update",
        "content": {
            "role": role,
            "queue_position": get_queue_position(client_socket),
            "is_host": client_socket == host_socket,
            "can_start": can_start,
            "can_play": can_play,
        }
    })


def broadcast_role_updates():
    for client_socket in list(clients.keys()):
        send_role_update(client_socket)
        send_json_to_client(client_socket, {
            "type": "host_assigned",
            "content": {
                "is_host": client_socket == host_socket
            }
        })


# --- Role transition helpers ---
def get_role_transition(previous_role: str | None, new_role: str | None) -> tuple[bool, bool]:
    became_host = previous_role != "host" and new_role == "host"
    became_opponent = previous_role != "opponent" and new_role == "opponent"
    return became_host, became_opponent


def snapshot_roles() -> dict[socket.socket, str]:
    return {client_socket: get_role_for_socket(client_socket) for client_socket in list(clients.keys())}


def promote_waiting_players():
    global host_socket, opponent_socket

    if host_socket is None:
        if opponent_socket is not None:
            host_socket = opponent_socket
            opponent_socket = None
        elif spectator_queue:
            host_socket = spectator_queue.pop(0)

    if opponent_socket is None and spectator_queue:
        opponent_socket = spectator_queue.pop(0)


def assign_lobby_role_on_join(client_socket: socket.socket):
    global host_socket, opponent_socket

    if host_socket is None:
        host_socket = client_socket
    elif game_started:
        spectator_queue.append(client_socket)
    elif opponent_socket is None:
        opponent_socket = client_socket
    else:
        spectator_queue.append(client_socket)


def remove_client_from_lobby(client_socket: socket.socket):
    global host_socket, opponent_socket

    if client_socket == host_socket:
        host_socket = None
    elif client_socket == opponent_socket:
        opponent_socket = None
    elif client_socket in spectator_queue:
        spectator_queue.remove(client_socket)

    promote_waiting_players()


def notify_lobby_after_role_change(previous_roles: dict[socket.socket, str] | None = None, left_username: str | None = None):
    broadcast_role_updates()

    previous_roles = previous_roles or {}

    for client_socket in list(clients.keys()):
        new_role = get_role_for_socket(client_socket)
        old_role = previous_roles.get(client_socket)
        became_host, became_opponent = get_role_transition(old_role, new_role)

        if became_host:
            send_server_msg(client_socket, "SERVER: You are now the host.")
        elif became_opponent:
            send_server_msg(client_socket, "SERVER: You are now the opponent.")

        if new_role == "spectator":
            position = get_queue_position(client_socket)
            if position is not None:
                send_server_msg(
                    client_socket,
                    f"SERVER: You are spectating. Queue position: {position}."
                )


def get_socket_by_username(username: str) -> socket.socket | None:
    for client_socket, client_username in clients.items():
        if client_username == username:
            return client_socket
    return None


def is_muted_for_receiver(receiver_socket: socket.socket, sender_socket: socket.socket) -> bool:
    if receiver_socket in mute_all_clients:
        return True
    muted_set = muted_sockets_by_client.get(receiver_socket, set())
    return sender_socket in muted_set


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
    global game_started, active_clock_color, active_turn_started_at, game_result_status, pending_draw_offer_from, pending_game_offer_from

    if not game_started or game is None or game_result_status is not None:
        return False

    current_white, current_black = get_current_clock_values()

    if current_white <= 0:
        commit_current_clock_values()
        game_result_status = "timeout_black_wins"
        save_pgn_file(game_result_status)
        reset_pgn_state()
        broadcast_finished_game_state()
        finalize_finished_game_state()
        broadcast_server_msg("SERVER: White ran out of time. Black wins.")
        return True

    if current_black <= 0:
        commit_current_clock_values()
        game_result_status = "timeout_black_wins"
        save_pgn_file(game_result_status)
        reset_pgn_state()
        broadcast_finished_game_state()
        finalize_finished_game_state()
        broadcast_server_msg("SERVER: White ran out of time. Black wins.")
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


def broadcast_game_status():
    if game is None:
        return

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
            **current_game_times_dict(),
        }
    })

def broadcast_finished_game_state():
    if game is None:
        return

    broadcast_board_state()
    broadcast_json({
        "type": "game_status",
        "content": {
            "status": game_result_status if game_result_status is not None else game.get_game_status(),
            "turn": game.get_turn(),
            "board": game.get_board(),
            "game_over": True,
            "en_passant_target": game.en_passant_target,
            "castling_rights": game.castling_rights,
            **current_game_times_dict(),
        }
    })

def finalize_finished_game_state():
    global game_started, white_player_socket, black_player_socket, game
    global active_clock_color, active_turn_started_at, game_result_status
    global pending_draw_offer_from, pending_game_offer_from

    game_started = False
    white_player_socket = None
    black_player_socket = None
    game = None
    active_clock_color = None
    active_turn_started_at = None
    pending_draw_offer_from = None
    pending_game_offer_from = None
    clear_ai_state()
    broadcast_role_updates()

# ---------------------- AI Helpers ----------------------

def clear_ai_state():
    global ai_enabled, ai_color, ai_level, ai_players, engine_board
    ai_enabled = False
    ai_color = None
    ai_level = 10
    ai_players = {}
    engine_board = None


def get_all_legal_moves_for_current_turn():
    if game is None:
        return []

    turn = game.get_turn()
    prefix = "w" if turn == "white" else "b"
    legal_moves = []

    for from_row in range(8):
        for from_col in range(8):
            piece = game.get_piece(from_row, from_col)
            if piece is None or not piece.startswith(prefix):
                continue

            for to_row in range(8):
                for to_col in range(8):
                    if game.is_legal_move((from_row, from_col), (to_row, to_col)):
                        legal_moves.append(((from_row, from_col), (to_row, to_col)))

    return legal_moves


def get_ai_level_for_color(color: str) -> int | None:
    return ai_players.get(color)


def is_ai_turn() -> bool:
    if game is None:
        return False
    return game.get_turn() in ai_players


def schedule_ai_move_if_needed(delay_seconds: float = AI_MOVE_DELAY_SECONDS):
    if not game_started or game is None or game_result_status is not None:
        return
    if not is_ai_turn():
        return

    timer = threading.Timer(delay_seconds, perform_ai_move_if_needed)
    timer.daemon = True
    timer.start()


def perform_ai_move_if_needed():
    global game_started, active_clock_color, active_turn_started_at, game_result_status
    global pending_draw_offer_from, pending_game_offer_from

    if game is None or not game_started or game_result_status is not None:
        return

    current_turn = game.get_turn()
    current_ai_level = get_ai_level_for_color(current_turn)
    if current_ai_level is None:
        return

    legal_moves = get_all_legal_moves_for_current_turn()
    if not legal_moves:
        return

    commit_current_clock_values()
    move = choose_ai_move(current_ai_level)
    if move is None:
        return

    from_pos, to_pos, promotion = move
    game.move(from_pos, to_pos, promotion or "Q")
    if engine_board is not None:
        push_move_to_engine_board(from_pos, to_pos, promotion)

    active_clock_color = game.get_turn()
    active_turn_started_at = time.monotonic()

    if game.is_game_over():
        game_result_status = game.get_game_status()
        save_pgn_file(game_result_status)
        reset_pgn_state()
        broadcast_finished_game_state()
        finalize_finished_game_state()
        return

    broadcast_board_state()
    broadcast_game_status()
    schedule_ai_move_if_needed()


def choose_ai_move(level: int):
    return choose_stockfish_move(level)


def coord_to_square(row: int, col: int) -> chess.Square:
    file = col
    rank = 7 - row
    return chess.square(file, rank)


def square_to_coord(square: chess.Square) -> tuple[int, int]:
    file = chess.square_file(square)
    rank = chess.square_rank(square)
    return 7 - rank, file


def push_move_to_engine_board(from_pos: tuple[int, int], to_pos: tuple[int, int], promotion: str | None = None):
    global engine_board

    if engine_board is None:
        return

    from_square = coord_to_square(from_pos[0], from_pos[1])
    to_square = coord_to_square(to_pos[0], to_pos[1])

    promotion_map = {
        "Q": chess.QUEEN,
        "R": chess.ROOK,
        "B": chess.BISHOP,
        "N": chess.KNIGHT,
    }
    promotion_piece = promotion_map.get((promotion or "").upper())

    if promotion_piece is not None:
        move = chess.Move(from_square, to_square, promotion=promotion_piece)
    else:
        move = chess.Move(from_square, to_square)

    if move not in engine_board.legal_moves:
        piece = engine_board.piece_at(from_square)
        if piece is not None and piece.piece_type == chess.PAWN:
            target_row = to_pos[0]
            if target_row in (0, 7):
                move = chess.Move(from_square, to_square, promotion=promotion_piece or chess.QUEEN)

    if move not in engine_board.legal_moves:
        raise ValueError(f"Move {move.uci()} is not legal on engine board.")

    engine_board.push(move)
    record_pgn_move(move)


def choose_stockfish_move(level: int):
    global engine_board, stockfish_engine

    if engine_board is None:
        return None

    init_stockfish()
    configure_stockfish_for_level(level)
    result = stockfish_engine.play(engine_board, get_stockfish_limit(level))
    move = result.move

    if move is None:
        return None

    from_pos = square_to_coord(move.from_square)
    to_pos = square_to_coord(move.to_square)

    promotion_map = {
        chess.QUEEN: "Q",
        chess.ROOK: "R",
        chess.BISHOP: "B",
        chess.KNIGHT: "N",
    }
    promotion = promotion_map.get(move.promotion)
    return from_pos, to_pos, promotion


def get_stockfish_path() -> str | None:
    return shutil.which("stockfish")


def init_stockfish():
    global stockfish_engine

    if stockfish_engine is not None:
        return

    stockfish_path = get_stockfish_path()
    if stockfish_path is None:
        raise RuntimeError("Stockfish binary not found. Install it or provide a valid path.")

    stockfish_engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)


def get_stockfish_elo_for_level(level: int) -> int:
    min_elo = 1320
    max_elo = 3190
    return round(min_elo + (level - 1) * (max_elo - min_elo) / 19)


def configure_stockfish_for_level(level: int):
    global stockfish_engine

    if stockfish_engine is None:
        return

    stockfish_engine.configure({
        "UCI_LimitStrength": True,
        "UCI_Elo": get_stockfish_elo_for_level(level),
    })


def get_stockfish_limit(level: int):
    level = max(1, min(level, 20))

    min_time = 0.03
    max_time = 0.50

    progress = (level - 1) / 19
    curved_progress = progress ** 1.6

    thinking_time = min_time + (max_time - min_time) * curved_progress
    return chess.engine.Limit(time=round(thinking_time, 3))


# ---------------------- PGN ----------------------

def reset_pgn_state():
    global pgn_game, pgn_node, pgn_moves
    pgn_game = None
    pgn_node = None
    pgn_moves = []


def init_pgn_game(white_name: str, black_name: str):
    global pgn_game, pgn_node, pgn_moves

    pgn_game = chess.pgn.Game()
    pgn_game.headers["Event"] = "PyChess Game"
    pgn_game.headers["Site"] = "Local Server"
    pgn_game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
    pgn_game.headers["Round"] = "-"
    pgn_game.headers["White"] = white_name
    pgn_game.headers["Black"] = black_name
    pgn_game.headers["Result"] = "*"

    pgn_node = pgn_game
    pgn_moves = []


def record_pgn_move(move: chess.Move):
    global pgn_game, pgn_node, pgn_moves

    if pgn_game is None or pgn_node is None:
        return

    pgn_moves.append(move)
    pgn_node = pgn_node.add_variation(move)


def get_pgn_result_from_status(status: str | None) -> str:
    if status in ("checkmate_white_wins", "timeout_white_wins", "resignation_white_wins", "disconnect_white_wins"):
        return "1-0"
    if status in ("checkmate_black_wins", "timeout_black_wins", "resignation_black_wins", "disconnect_black_wins"):
        return "0-1"
    if status in (
            "stalemate",
            "draw_fifty_move_rule",
            "draw_threefold_repetition",
            "draw_insufficient_material",
            "draw_by_agreement"
    ):
        return "1/2-1/2"
    return "*"


def safe_filename_part(text: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in text)


def save_pgn_file(final_status: str | None):
    global pgn_game

    if pgn_game is None:
        return

    result = get_pgn_result_from_status(final_status)
    pgn_game.headers["Result"] = result

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    white_name = safe_filename_part(pgn_game.headers.get("White", "White"))
    black_name = safe_filename_part(pgn_game.headers.get("Black", "Black"))
    filename = PGN_DIR / f"{timestamp}_{white_name}_vs_{black_name}.pgn"

    with open(filename, "w", encoding="utf-8") as f:
        print(pgn_game, file=f, end="\n\n")


# ---------------------- Message Type Handlers ----------------------

def handle_chat(client_socket: socket.socket, addr, username: str, content: str):
    print(f"{addr[0]}:{addr[1]} ({username}), MSG: {content}")

    data = {
        "type": "msg",
        "content": f">> {username}: {content}"
    }

    for receiver_socket in list(clients.keys()):
        if receiver_socket == client_socket:
            continue
        if is_muted_for_receiver(receiver_socket, client_socket):
            continue
        send_json_to_client(receiver_socket, data)


def handle_command(client_socket: socket.socket, addr, username: str, command: str):
    print(f"{addr[0]}:{addr[1]} ({username}), COMMAND: {command}")

    parts = command.strip().split()
    if not parts:
        send_server_msg(client_socket, "SERVER: Unknown command.")
        return

    cmd = parts[0].lower()
    args = parts[1:]

    command_handlers = {
        "rename": lambda: handle_rename(client_socket, command),
        "quit": lambda: handle_quit(client_socket, username),
        "resign": lambda: handle_resign(client_socket, username),
        "draw": lambda: handle_offer_draw(client_socket, username),
        "offerdraw": lambda: handle_offer_draw(client_socket, username),
        "settime": lambda: handle_set_time(client_socket, username, command),
        "start": lambda: handle_start_game(client_socket, username),
        "cancelstart": lambda: handle_cancel_game_offer(client_socket, username),
        "declinestart": lambda: handle_decline_game_offer(client_socket, username),
        "startai": lambda: handle_start_ai_game(client_socket, username, args[0] if args else "10"),
        "startaivai": lambda: handle_start_ai_vs_ai_game(client_socket, username, args[0] if len(args) > 0 else "10", args[1] if len(args) > 1 else "10",),
        "starthvai": lambda: handle_start_human_vs_ai_game(client_socket, username, args[0] if len(args) > 0 else "white", args[1] if len(args) > 1 else "10",),
        "muteall": lambda: handle_muteall(client_socket),
        "mute": lambda: handle_mute(client_socket, username, args),
        "kick": lambda: handle_kick(client_socket, username, args),
        "ao": lambda: handle_set_active_opponent(client_socket, username, args),
        "list": lambda: handle_list_players(client_socket),
        "host": lambda: handle_transfer_host(client_socket, username, args),
    }

    handler = command_handlers.get(cmd)
    if handler is None:
        send_server_msg(client_socket, "SERVER: Unknown command.")
        return

    handler()


# ---------------------- Command Handlers ----------------------

def handle_set_time(client_socket: socket.socket, username: str, command: str):
    global game_time_minutes

    if client_socket != host_socket:
        send_server_msg(client_socket, "SERVER: Only the host can set the time control.")
        return

    parts = command.split(maxsplit=1)
    if len(parts) != 2:
        send_server_msg(client_socket, "SERVER: Usage: settime <minutes>")
        return

    try:
        minutes = int(parts[1])
    except ValueError:
        send_server_msg(client_socket, "SERVER: Time must be an integer number of minutes.")
        return

    if minutes not in ALLOWED_TIME_CONTROLS:
        send_server_msg(
            client_socket,
            f"SERVER: Allowed time controls are {', '.join(map(str, ALLOWED_TIME_CONTROLS))} minutes."
        )
        return

    if game_started:
        send_server_msg(client_socket, "SERVER: You cannot change the time control after the game has started.")
        return

    game_time_minutes = minutes
    reset_clock_state(game_time_minutes)

    broadcast_server_msg(f"SERVER: {username} set the time control to {minutes} minutes.")

    broadcast_json({
        "type": "time_control_updated",
        "content": {
            "time_minutes": minutes
        }
    })

    if game is not None:
        broadcast_game_status()


def handle_move(client_socket: socket.socket, addr, username: str, content: dict):
    global game_started, white_player_socket, black_player_socket, game
    global active_clock_color, active_turn_started_at, game_result_status, pending_draw_offer_from, pending_game_offer_from

    if not game_started or game is None or game_result_status is not None:
        send_server_msg(client_socket, "SERVER: Game has not started yet.")
        return

    if client_socket == white_player_socket:
        player_color = "white"
    elif client_socket == black_player_socket:
        player_color = "black"
    else:
        send_server_msg(client_socket, "SERVER: You are not part of the current game.")
        return

    if check_timeout_state():
        return

    if not isinstance(content, dict):
        send_server_msg(client_socket, "SERVER: Invalid move payload.")
        return

    from_pos = content.get("from")
    to_pos = content.get("to")
    promotion = content.get("promotion")

    if (
        not isinstance(from_pos, list) or len(from_pos) != 2 or
        not isinstance(to_pos, list) or len(to_pos) != 2
    ):
        send_server_msg(client_socket, "SERVER: Move must contain 'from' and 'to'.")
        return

    if promotion is not None:
        if not isinstance(promotion, str):
            send_json_to_client(client_socket, {
                "type": "msg",
                "content": "SERVER: Promotion must be a string."
            })
            return
        promotion = promotion.upper()
        if promotion not in ("Q", "R", "B", "N"):
            send_json_to_client(client_socket, {
                "type": "msg",
                "content": "SERVER: Invalid promotion piece."
            })
            return

    from_row, from_col = from_pos
    to_row, to_col = to_pos

    if not all(isinstance(x, int) for x in [from_row, from_col, to_row, to_col]):
        send_server_msg(client_socket, "SERVER: Move coordinates must be integers.")
        return

    if not all(0 <= x < 8 for x in [from_row, from_col, to_row, to_col]):
        send_server_msg(client_socket, "SERVER: Move coordinates out of bounds.")
        return

    if game.get_turn() != player_color:
        send_server_msg(client_socket, f"SERVER: It is {game.get_turn()}'s turn.")
        return

    if pending_draw_offer_from is not None and pending_draw_offer_from != client_socket:
        pending_draw_offer_from = None
        broadcast_server_msg("SERVER: Draw offer declined by move.")

    piece = game.get_piece(from_row, from_col)
    if piece is None:
        send_server_msg(client_socket, "SERVER: No piece on source square.")
        return

    if player_color == "white" and not piece.startswith("w"):
        send_server_msg(client_socket, "SERVER: That is not your piece.")
        return

    if player_color == "black" and not piece.startswith("b"):
        send_server_msg(client_socket, "SERVER: That is not your piece.")
        return

    if not game.is_legal_move((from_row, from_col), (to_row, to_col), promotion or "Q"):
        send_server_msg(client_socket, "SERVER: Illegal move.")
        return

    commit_current_clock_values()

    if not game.move((from_row, from_col), (to_row, to_col), promotion or "Q"):
        send_server_msg(client_socket, "SERVER: Move could not be executed.")
        return

    if engine_board is not None:
        push_move_to_engine_board((from_row, from_col), (to_row, to_col), promotion)

    active_clock_color = game.get_turn()
    active_turn_started_at = time.monotonic()

    if game.is_game_over():
        game_result_status = game.get_game_status()
        save_pgn_file(game_result_status)
        reset_pgn_state()
        broadcast_finished_game_state()
        finalize_finished_game_state()
        return

    broadcast_board_state()
    broadcast_game_status()
    perform_ai_move_if_needed()


def handle_rename(client_socket: socket.socket, command: str):
    parts = command.split(maxsplit=1)
    if len(parts) < 2:
        send_server_msg(client_socket, "SERVER: Usage: \\rename <name>")
        return

    new_name = parts[1].strip()
    if not new_name:
        send_server_msg(client_socket, "SERVER: Usage: \\rename <name>")
        return

    if not is_valid_username_length(new_name):
        send_server_msg(client_socket, "SERVER: Usernames must be between 1 and 12 characters long.")
        return

    if is_username_taken(new_name, exclude_socket=client_socket):
        send_server_msg(client_socket, f"SERVER: The username {new_name} is already taken.")
        return

    old_name = clients[client_socket]
    clients[client_socket] = new_name

    broadcast_json({
        "type": "msg",
        "content": f"SERVER: {old_name} renamed to {new_name}",
    })


def handle_quit(client_socket: socket.socket, username: str):
    global pending_draw_offer_from, pending_game_offer_from

    if pending_draw_offer_from == client_socket:
        pending_draw_offer_from = None
    if pending_game_offer_from == client_socket:
        pending_game_offer_from = None

    clear_mute_state_for_client(client_socket)
    reset_game_state_if_needed(client_socket, username)
    clients.pop(client_socket, None)
    broadcast_server_msg(f"SERVER: {username} left.", client_socket)
    close_socket_safely(client_socket)


def handle_resign(client_socket: socket.socket, username: str):
    global game_started, white_player_socket, black_player_socket, game
    global active_clock_color, active_turn_started_at, game_result_status, pending_draw_offer_from, pending_game_offer_from

    if not game_started or game is None:
        send_server_msg(client_socket, "SERVER: No active game to resign.")
        return

    if client_socket == white_player_socket:
        winner = "Computer" if black_player_socket is None and get_ai_level_for_color("black") is not None else clients.get(black_player_socket, "Black")
        result_status = "resignation_black_wins"
    elif client_socket == black_player_socket:
        winner = clients.get(white_player_socket, "White")
        result_status = "resignation_white_wins"
    else:
        send_server_msg(client_socket, "SERVER: Only active players can resign.")
        return

    game_result_status = result_status
    save_pgn_file(game_result_status)
    reset_pgn_state()
    pending_draw_offer_from = None
    pending_game_offer_from = None

    broadcast_server_msg(f"SERVER: {username} resigned. {winner} wins.")

    broadcast_finished_game_state()
    finalize_finished_game_state()


def handle_offer_draw(client_socket: socket.socket, username: str):
    global game_started, white_player_socket, black_player_socket, game
    global active_clock_color, active_turn_started_at, game_result_status, pending_draw_offer_from, pending_game_offer_from

    if not game_started or game is None:
        send_server_msg(client_socket, "SERVER: No active game to offer a draw.")
        return

    if ai_players:
        send_server_msg(client_socket, "SERVER: Draw offers are not available against the computer.")
        return

    if client_socket == white_player_socket:
        opposing_player_socket = black_player_socket
    elif client_socket == black_player_socket:
        opposing_player_socket = white_player_socket
    else:
        send_server_msg(client_socket, "SERVER: Only active players can offer a draw.")
        return

    opponent_name = clients.get(opposing_player_socket, "Opponent")
    sender_name = username or clients.get(client_socket, "Player")

    if pending_draw_offer_from is None:
        pending_draw_offer_from = client_socket
        send_server_msg(client_socket, f"SERVER: Draw offer sent to {opponent_name}.")
        if opposing_player_socket is not None:
            send_server_msg(
                opposing_player_socket,
                f"SERVER: {sender_name} offered a draw. Click Offer Draw to accept."
            )
        return

    if pending_draw_offer_from == client_socket:
        send_server_msg(client_socket, "SERVER: Draw offer already pending.")
        return

    if pending_draw_offer_from == opposing_player_socket:
        pending_draw_offer_from = None
        pending_game_offer_from = None
        game_result_status = "draw_by_agreement"
        save_pgn_file(game_result_status)
        reset_pgn_state()

        broadcast_server_msg("SERVER: Draw offer accepted.")

        broadcast_finished_game_state()
        finalize_finished_game_state()

def handle_mute(client_socket: socket.socket, username: str, args: list[str]):
    if not args:
        send_server_msg(client_socket, "SERVER: Usage: mute <username>")
        return

    target_username = " ".join(args).strip()
    target_socket = get_socket_by_username(target_username)

    if target_socket is None:
        send_server_msg(client_socket, f"SERVER: No player named {target_username} is connected.")
        return

    if target_socket == client_socket:
        send_server_msg(client_socket, "SERVER: You cannot mute yourself.")
        return

    muted_set = muted_sockets_by_client.setdefault(client_socket, set())
    if target_socket in muted_set:
        muted_set.remove(target_socket)
        send_server_msg(client_socket, f"SERVER: You unmuted {target_username}.")
        return

    muted_set.add(target_socket)
    send_server_msg(client_socket, f"SERVER: You muted {target_username}.")


def handle_muteall(client_socket: socket.socket):
    if client_socket in mute_all_clients:
        mute_all_clients.remove(client_socket)
        send_server_msg(client_socket, "SERVER: You unmuted all players.")
        return

    mute_all_clients.add(client_socket)
    send_server_msg(client_socket, "SERVER: You muted all players.")


def handle_kick(client_socket: socket.socket, username: str, args: list[str]):
    global kicked_clients

    if client_socket != host_socket:
        send_server_msg(client_socket, "SERVER: Only the host can kick a player.")
        return

    if not args:
        send_server_msg(client_socket, "SERVER: Usage: kick <username>")
        return

    target_username = " ".join(args).strip()
    target_socket = get_socket_by_username(target_username)

    if target_socket is None:
        send_server_msg(client_socket, f"SERVER: No player named {target_username} is connected.")
        return

    if target_socket == client_socket:
        send_server_msg(client_socket, "SERVER: You cannot kick yourself.")
        return

    if target_socket in spectator_queue:
        pass
    elif target_socket == opponent_socket and not game_started:
        pass
    elif target_socket == opponent_socket and game_started:
        send_server_msg(client_socket, "SERVER: You cannot kick the opponent after the game has started.")
        return
    else:
        send_server_msg(client_socket, "SERVER: You can only kick spectators, or the opponent before the game starts.")
        return

    target_name = clients.get(target_socket, "Player")
    kicked_clients.add(target_socket)

    send_json_to_client(target_socket, {
        "type": "kicked",
        "content": {
            "reason": "You were kicked by the host."
        }
    })
    send_server_msg(client_socket, f"SERVER: {target_name} was kicked.")

    shutdown_and_close_socket(target_socket)

def handle_set_active_opponent(client_socket: socket.socket, username: str, args: list[str]):
    global opponent_socket, spectator_queue

    if client_socket not in (host_socket, opponent_socket):
        send_server_msg(client_socket, "SERVER: Only the host or the current opponent can assign the opponent.")
        return

    if game_started:
        send_server_msg(client_socket, "SERVER: You cannot change the opponent after the game has started.")
        return

    if pending_game_offer_from is not None:
        send_server_msg(client_socket, "SERVER: You cannot set the opponent while a game offer is pending.")
        return

    if not args:
        send_server_msg(client_socket, "SERVER: Usage: \\ao <username>")
        return

    target_username = " ".join(args).strip()
    target_socket = get_socket_by_username(target_username)

    if target_socket is None:
        send_server_msg(client_socket, f"SERVER: No player named {target_username} is connected.")
        return

    if target_socket == host_socket:
        send_server_msg(client_socket, "SERVER: The host cannot become the opponent.")
        return

    if target_socket == opponent_socket and client_socket == host_socket:
        send_server_msg(client_socket, f"SERVER: {target_username} is already the opponent.")
        return

    if target_socket == opponent_socket and client_socket == opponent_socket:
        send_server_msg(client_socket, f"SERVER: {target_username} is already the opponent.")
        return

    previous_roles = snapshot_roles()
    old_opponent_socket = opponent_socket

    if target_socket in spectator_queue:
        spectator_queue.remove(target_socket)

    opponent_socket = target_socket

    if old_opponent_socket is not None and old_opponent_socket != target_socket:
        spectator_queue.insert(0, old_opponent_socket)

    broadcast_server_msg(f"SERVER: {target_username} is now the opponent.")
    notify_lobby_after_role_change(previous_roles)

def handle_transfer_host(client_socket: socket.socket, username: str, args: list[str]):
    global host_socket, opponent_socket, spectator_queue

    if client_socket != host_socket:
        send_server_msg(client_socket, "SERVER: Only the host can transfer host rights.")
        return

    if game_started:
        send_server_msg(client_socket, "SERVER: You cannot transfer host rights after the game has started.")
        return

    if pending_game_offer_from is not None:
        send_server_msg(client_socket, "SERVER: You cannot transfer host rights while a game offer is pending.")
        return

    if not args:
        send_server_msg(client_socket, "SERVER: Usage: \\host <username>")
        return

    target_username = " ".join(args).strip()
    target_socket = get_socket_by_username(target_username)

    if target_socket is None:
        send_server_msg(client_socket, f"SERVER: No player named {target_username} is connected.")
        return

    if target_socket == host_socket:
        send_server_msg(client_socket, f"SERVER: {target_username} is already the host.")
        return

    previous_roles = snapshot_roles()
    old_host_socket = host_socket
    old_opponent_socket = opponent_socket
    total_players = len(clients)

    if target_socket in spectator_queue:
        spectator_queue.remove(target_socket)

    if target_socket == old_opponent_socket:
        host_socket = target_socket
        if total_players <= 2 and old_host_socket is not None and old_host_socket != host_socket:
            opponent_socket = old_host_socket
        else:
            opponent_socket = spectator_queue.pop(0) if spectator_queue else None
    else:
        host_socket = target_socket
        opponent_socket = old_opponent_socket

    if old_host_socket is not None and old_host_socket != host_socket:
        if old_host_socket in spectator_queue:
            spectator_queue.remove(old_host_socket)
        if not (total_players <= 2 and target_socket == old_opponent_socket):
            spectator_queue.append(old_host_socket)

    broadcast_server_msg(f"SERVER: {target_username} is now the host.")
    notify_lobby_after_role_change(previous_roles)

def handle_list_players(client_socket: socket.socket):
    player_lines = []

    for listed_socket, listed_username in clients.items():
        suffixes = []

        if listed_socket == client_socket:
            suffixes.append("You")
        if listed_socket == host_socket:
            suffixes.append("Host")
        elif listed_socket == opponent_socket:
            suffixes.append("Opponent")
        else:
            suffixes.append("Spectator")

        player_lines.append(f"- {listed_username} ({', '.join(suffixes)})")

    if not player_lines:
        send_server_msg(client_socket, "SERVER: No players are currently connected.")
        return

    player_list_text = "SERVER: \n################## CONNECTED PLAYERS ####################\n\n" + "\n".join(player_lines) + "\n\n#########################################################\n"
    send_server_msg(client_socket, player_list_text)

def handle_start_ai_game(client_socket: socket.socket, username: str, level_arg: str):
    global game_started, white_player_socket, black_player_socket, game
    global active_clock_color, active_turn_started_at, game_result_status
    global pending_draw_offer_from, pending_game_offer_from, host_socket
    global ai_enabled, ai_color, ai_level, ai_players, engine_board

    if client_socket != host_socket:
        send_server_msg(client_socket, "SERVER: Only the host can start the game.")
        return

    if len(clients) != 1 or opponent_socket is not None or spectator_queue:
        send_server_msg(client_socket, "SERVER: AI mode is only available when no other player is connected.")
        return

    if game_started:
        send_server_msg(client_socket, "SERVER: Game already started.")
        return

    level = parse_ai_level(level_arg)

    clear_ai_state()
    reset_pgn_state()
    ai_level = level
    human_color = random.choice(["white", "black"])
    computer_name = f"Stockfish (Level {level}, ~{get_stockfish_elo_for_level(level)} Elo)"

    if human_color == "white":
        white_player_socket = client_socket
        black_player_socket = None
        ai_color = "black"
        ai_players = {"black": level}
        white_name = username
        black_name = computer_name
    else:
        white_player_socket = None
        black_player_socket = client_socket
        ai_color = "white"
        ai_players = {"white": level}
        white_name = computer_name
        black_name = username

    init_pgn_game(white_name, black_name)

    game = Game()
    engine_board = chess.Board()
    reset_clock_state(game_time_minutes)
    active_clock_color = "white"
    active_turn_started_at = time.monotonic()
    game_result_status = None
    pending_draw_offer_from = None
    pending_game_offer_from = None
    game_started = True
    ai_enabled = True

    send_json_to_client(client_socket, {
        "type": "game_started",
        "content": {
            "color": human_color,
            "white": white_name,
            "black": black_name,
        }
    })

    broadcast_board_state()
    broadcast_game_status()
    schedule_ai_move_if_needed()


def handle_start_ai_vs_ai_game(client_socket: socket.socket, username: str, white_level_arg: str, black_level_arg: str):
    global game_started, white_player_socket, black_player_socket, game
    global active_clock_color, active_turn_started_at, game_result_status
    global pending_draw_offer_from, pending_game_offer_from, host_socket
    global ai_enabled, ai_color, ai_level, ai_players, engine_board

    if client_socket != host_socket:
        send_server_msg(client_socket, "SERVER: Only the host can start the game.")
        return

    if game_started:
        send_server_msg(client_socket, "SERVER: Game already started.")
        return

    white_level = parse_ai_level(white_level_arg)
    black_level = parse_ai_level(black_level_arg)

    clear_ai_state()
    reset_pgn_state()

    white_player_socket = None
    black_player_socket = None
    ai_color = None
    ai_level = white_level
    ai_players = {
        "white": white_level,
        "black": black_level,
    }

    white_name = f"Computer (Level {white_level}, ~{get_stockfish_elo_for_level(white_level)} Elo)"
    black_name = f"Computer (Level {black_level}, ~{get_stockfish_elo_for_level(black_level)} Elo)"

    init_pgn_game(white_name, black_name)

    game = Game()
    engine_board = chess.Board()
    reset_clock_state(game_time_minutes)
    active_clock_color = "white"
    active_turn_started_at = time.monotonic()
    game_result_status = None
    pending_draw_offer_from = None
    pending_game_offer_from = None
    game_started = True
    ai_enabled = True

    for client in list(clients.keys()):
        send_json_to_client(client, {
            "type": "game_started",
            "content": {
                "color": None,
                "white": white_name,
                "black": black_name,
            }
        })

    broadcast_board_state()
    broadcast_game_status()
    broadcast_role_updates()
    schedule_ai_move_if_needed()


def handle_start_human_vs_ai_game(client_socket: socket.socket, username: str, human_color_arg: str, level_arg: str):
    global game_started, white_player_socket, black_player_socket, game
    global active_clock_color, active_turn_started_at, game_result_status
    global pending_draw_offer_from, pending_game_offer_from, host_socket
    global ai_enabled, ai_color, ai_level, ai_players, engine_board

    if client_socket != host_socket:
        send_server_msg(client_socket, "SERVER: Only the host can start the game.")
        return

    if len(clients) != 1 or opponent_socket is not None or spectator_queue:
        send_server_msg(client_socket, "SERVER: AI mode is only available when no other player is connected.")
        return

    if game_started:
        send_server_msg(client_socket, "SERVER: Game already started.")
        return

    human_color = (human_color_arg or "white").lower()
    if human_color not in ("white", "black"):
        human_color = "white"

    level = parse_ai_level(level_arg)

    clear_ai_state()
    reset_pgn_state()
    ai_level = level
    computer_name = f"Computer (Level {level}, ~{get_stockfish_elo_for_level(level)} Elo)"

    if human_color == "white":
        white_player_socket = client_socket
        black_player_socket = None
        ai_color = "black"
        ai_players = {"black": level}
        white_name = username
        black_name = computer_name
    else:
        white_player_socket = None
        black_player_socket = client_socket
        ai_color = "white"
        ai_players = {"white": level}
        white_name = computer_name
        black_name = username

    init_pgn_game(white_name, black_name)

    game = Game()
    engine_board = chess.Board()
    reset_clock_state(game_time_minutes)
    active_clock_color = "white"
    active_turn_started_at = time.monotonic()
    game_result_status = None
    pending_draw_offer_from = None
    pending_game_offer_from = None
    game_started = True
    ai_enabled = True

    send_json_to_client(client_socket, {
        "type": "game_started",
        "content": {
            "color": human_color,
            "white": white_name,
            "black": black_name,
        }
    })

    broadcast_board_state()
    broadcast_game_status()
    schedule_ai_move_if_needed()


def handle_start_game(client_socket: socket.socket, username: str):
    global game_started, white_player_socket, black_player_socket, game
    global active_clock_color, active_turn_started_at, game_result_status
    global pending_draw_offer_from, pending_game_offer_from, host_socket, engine_board

    if host_socket is None or opponent_socket is None:
        send_server_msg(client_socket, "SERVER: Need two active players to start.")
        return

    if game_started:
        send_server_msg(client_socket, "SERVER: Game already started.")
        return

    if pending_game_offer_from is None:
        if client_socket != host_socket:
            send_server_msg(client_socket, "SERVER: Only the host can start the game.")
            return

        pending_game_offer_from = client_socket
        send_server_msg(client_socket, f"SERVER: Game offer sent to {clients.get(opponent_socket, 'Opponent')}.")
        if opponent_socket is not None:
            send_server_msg(opponent_socket, f"SERVER: {username} offered a game. Click Play to accept.")
        return

    if pending_game_offer_from == client_socket:
        send_server_msg(client_socket, "SERVER: Game offer already pending.")
        return

    if pending_game_offer_from != host_socket or client_socket != opponent_socket:
        send_server_msg(client_socket, "SERVER: Only the opponent can accept the pending game offer.")
        return

    pending_game_offer_from = None

    clear_ai_state()
    reset_pgn_state()
    sockets = [host_socket, opponent_socket]
    random.shuffle(sockets)
    white_player_socket = sockets[0]
    black_player_socket = sockets[1]
    white_name = clients[white_player_socket]
    black_name = clients[black_player_socket]

    init_pgn_game(clients.get(white_player_socket, "White"), clients.get(black_player_socket, "Black"))

    game = Game()
    engine_board = chess.Board()
    reset_clock_state(game_time_minutes)
    active_clock_color = "white"
    active_turn_started_at = time.monotonic()
    game_result_status = None
    pending_draw_offer_from = None
    game_started = True

    broadcast_server_msg("SERVER: Game offer accepted.")

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

    broadcast_board_state()
    broadcast_game_status()


# ---------------------- Game Offer Cancel/Decline Handlers ----------------------

def handle_cancel_game_offer(client_socket: socket.socket, username: str):
    global pending_game_offer_from

    if pending_game_offer_from is None:
        send_server_msg(client_socket, "SERVER: No pending game offer to cancel.")
        return

    if client_socket != pending_game_offer_from:
        send_server_msg(client_socket, "SERVER: Only the player who sent the game offer can cancel it.")
        return

    pending_game_offer_from = None
    broadcast_server_msg("SERVER: Game offer cancelled.")
    broadcast_role_updates()


def handle_decline_game_offer(client_socket: socket.socket, username: str):
    global pending_game_offer_from

    if pending_game_offer_from is None:
        send_server_msg(client_socket, "SERVER: No pending game offer to decline.")
        return

    if client_socket == pending_game_offer_from:
        send_server_msg(client_socket, "SERVER: You cannot decline your own game offer.")
        return

    if client_socket != opponent_socket:
        send_server_msg(client_socket, "SERVER: Only the opponent can decline the pending game offer.")
        return

    pending_game_offer_from = None
    broadcast_server_msg("SERVER: Game offer declined.")
    broadcast_role_updates()

# ---------------------- Disconnect / Cleanup ----------------------

def reset_game_state_if_needed(disconnected_socket: socket.socket, username: str | None):
    global game_started, white_player_socket, black_player_socket, game
    global active_clock_color, active_turn_started_at, game_result_status, pending_draw_offer_from, pending_game_offer_from
    global host_socket, opponent_socket, kicked_clients

    was_kicked = disconnected_socket in kicked_clients
    was_active_lobby_player = disconnected_socket in (host_socket, opponent_socket)
    was_active_game_player = disconnected_socket in (white_player_socket, black_player_socket)

    pending_offer_cancelled = False
    if pending_game_offer_from is not None and disconnected_socket in (host_socket, opponent_socket):
        pending_game_offer_from = None
        pending_offer_cancelled = True

    if was_active_game_player and game is not None:
        disconnect_status = None
        if disconnected_socket == white_player_socket:
            disconnect_status = "disconnect_black_wins"
        elif disconnected_socket == black_player_socket:
            disconnect_status = "disconnect_white_wins"

        save_pgn_file(disconnect_status)
        reset_pgn_state()

        broadcast_json({
            "type": "game_status",
            "content": {
                "status": disconnect_status,
                "turn": game.get_turn(),
                "board": game.get_board(),
                "game_over": True,
                **current_game_times_dict(),
            }
        }, disconnected_socket)

        finalize_finished_game_state()
        reset_clock_state(game_time_minutes)

        if username:
            if was_kicked:
                broadcast_server_msg(f"SERVER: {username} was kicked. Game Over!", disconnected_socket)
            else:
                broadcast_server_msg(f"SERVER: {username} disconnected. Game Over!", disconnected_socket)
    else:
        if username:
            if was_kicked:
                broadcast_server_msg(f"SERVER: {username} was kicked by the host.", disconnected_socket)
            else:
                broadcast_server_msg(f"SERVER: {username} disconnected.", disconnected_socket)

    if pending_offer_cancelled:
        broadcast_json({
            "type": "msg",
            "content": "SERVER: Game offer cancelled."
        }, disconnected_socket)

    clear_mute_state_for_client(disconnected_socket)
    previous_roles = snapshot_roles()
    remove_client_from_lobby(disconnected_socket)

    if was_active_lobby_player:
        notify_lobby_after_role_change(previous_roles, username)
    else:
        broadcast_role_updates()

    if was_kicked:
        kicked_clients.discard(disconnected_socket)

# ---------------------- Client Thread ----------------------

def handle_client(client_socket: socket.socket, addr):
    receive_buffer = ""

    try:
        while True:
            username = clients.get(client_socket)
            request = client_socket.recv(4096)
            if not request:
                break

            receive_buffer += request.decode("utf-8")

            while "\n" in receive_buffer:
                raw_message, receive_buffer = receive_buffer.split("\n", 1)
                raw_message = raw_message.strip()

                if not raw_message:
                    continue

                try:
                    request_json = json.loads(raw_message)
                    log_json_event("RECV", request_json, client_socket=client_socket, addr=addr)
                    msg_type = request_json.get("type")
                    content = request_json.get("content")

                    if msg_type == "msg":
                        handle_chat(client_socket, addr, username, content)
                    elif msg_type == "command":
                        handle_command(client_socket, addr, username, content)
                    elif msg_type == "move":
                        handle_move(client_socket, addr, username, content)

                except json.JSONDecodeError:
                    send_server_msg(client_socket, "SERVER: invalid json")
                    continue

    except Exception as e:
        print(f"Error handling client: {e}")

    finally:
        username = clients.get(client_socket)
        if client_socket in clients:
            reset_game_state_if_needed(client_socket, username)
            clients.pop(client_socket, None)
        close_socket_safely(client_socket)
        print(f"Connection to client ({addr[0]}:{addr[1]}) closed")

# ---------------------- Server ----------------------

def get_current_match_names() -> tuple[str | None, str | None]:
    white_name = None
    black_name = None

    if pgn_game is not None:
        white_name = pgn_game.headers.get("White")
        black_name = pgn_game.headers.get("Black")

    if white_name is None:
        if white_player_socket is not None:
            white_name = clients.get(white_player_socket)
        elif get_ai_level_for_color("white") is not None:
            level = get_ai_level_for_color("white")
            white_name = f"Computer (Level {level}, ~{get_stockfish_elo_for_level(level)} Elo)"

    if black_name is None:
        if black_player_socket is not None:
            black_name = clients.get(black_player_socket)
        elif get_ai_level_for_color("black") is not None:
            level = get_ai_level_for_color("black")
            black_name = f"Computer (Level {level}, ~{get_stockfish_elo_for_level(level)} Elo)"

    return white_name, black_name

def run_server():
    server_ip = "127.0.0.1"
    port = 8000
    server = None

    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((server_ip, port))
        server.listen()

        print(f"Listening on {server_ip}:{port}")
        clock_thread = threading.Thread(target=clock_broadcast_loop, daemon=True)
        clock_thread.start()

        while True:
            client_socket, addr = server.accept()
            send_json_to_client(client_socket, {
                "type": "connection_accepted",
                "content": "",
            })
            print(f"Accepted connection from {addr[0]}:{addr[1]}")

            anonymous_name = generate_default_username(addr[1])
            clients[client_socket] = anonymous_name
            assign_lobby_role_on_join(client_socket)
            broadcast_role_updates()

            role = get_role_for_socket(client_socket)
            if role == "host":
                send_server_msg(client_socket, "SERVER: You joined as the host.")
            elif role == "opponent":
                send_server_msg(client_socket, "SERVER: You joined as the opponent.")
            else:
                send_server_msg(
                    client_socket,
                    f"SERVER: You are spectating. Queue position: {get_queue_position(client_socket)}."
                )

            broadcast_server_msg(f"SERVER: {anonymous_name} joined", client_socket)

            if game is not None:
                white_name, black_name = get_current_match_names()
                send_json_to_client(client_socket, {
                    "type": "game_started",
                    "content": {
                        "color": None,
                        "white": white_name,
                        "black": black_name,
                    }
                })
                send_json_to_client(client_socket, {
                    "type": "board",
                    "content": game.get_board()
                })
                send_json_to_client(client_socket, {
                    "type": "game_status",
                    "content": {
                        "status": game_result_status if game_result_status is not None else game.get_game_status(),
                        "turn": game.get_turn(),
                        "board": game.get_board(),
                        "game_over": bool(game_result_status is not None or game.is_game_over()),
                        "en_passant_target": game.en_passant_target,
                        "castling_rights": game.castling_rights,
                        **current_game_times_dict(),
                    }
                })

            thread = threading.Thread(
                target=handle_client,
                args=(client_socket, addr),
                daemon=True,
            )
            thread.start()

    except Exception as e:
        print(f"Server error: {e}")

    finally:
        flush_session_logs_to_file()
        if stockfish_engine is not None:
            try:
                stockfish_engine.quit()
            except Exception:
                pass
        if server is not None:
            server.close()


run_server()