# PyChess

PyChess is a desktop-based multiplayer chess application built with Python and PySide6.  
It combines a graphical chess client, a custom TCP/JSON server, AI support via Stockfish, spectator mode, chat commands, role-based lobby management, PGN export, and server-side session logging.

The project is designed as a self-hostable chess platform with a focus on:
- custom lobby control
- local or remote multiplayer
- human vs human / human vs AI / AI vs AI
- spectator support
- lightweight custom protocol over TCP sockets

---

## Features

### Core gameplay
- Human vs Human
- Human vs AI
- AI vs AI
- Legal move validation
- Check, checkmate, stalemate handling
- En passant
- Castling
- Pawn promotion with piece selection
- Chess clocks with selectable time controls
- PGN export of finished games

### Lobby system
- Host / Active Opponent / Spectator roles
- Queue-based spectator system
- Manual reassignment of Active Opponent
- Host transfer support
- Public spectator joining during ongoing games
- Immediate board/game-state sync for newly joined spectators

### Chat & moderation
- Global chat
- Mute individual users
- Mute all users
- Kick users
- Rename users
- List connected players
- Server-side role and lobby management commands

### AI
- Stockfish integration
- Adjustable AI levels
- Human vs AI color selection
- AI vs AI matches
- AI strength limited by configured Stockfish Elo and move time

### Logging
- Every JSON message sent and received by the server is logged live in the terminal
- Session logs are written to file when the server terminates

---

## Tech Stack

- **Python 3.12**
- **PySide6** for the desktop GUI
- **python-chess** for Stockfish integration and PGN handling
- **socket / threading** for networking
- **custom JSON-over-TCP protocol**

---

## Project Structure

```text
PyChess/
├── model/
│   └── Game.py
├── network/
│   └── NetworkClient.py
├── view/
│   ├── BoardView.py
│   ├── CapturedListView.py
│   ├── ChatView.py
│   ├── ClockView.py
│   └── MainWindow.py
├── pieces/
├── pgn_games/
├── server_logs/
├── main_client.py
└── server.py
```
---

## Important files
	•	server.py: 
                Central TCP server, lobby handling, commands, AI handling, JSON protocol, logging

	•	main_client.py: 
                Client entry point

	•	network/NetworkClient.py: 
                Handles client-server communication and state synchronization

	•	view/MainWindow.py:
                Main GUI window, controls, lobby state, game UI

	•	view/BoardView.py: 
                Chessboard UI, piece rendering, move interactions, drag/drop, highlights

	•	model/Game.py
                Chess game logic and rules

---

## Install and Run

#### 1. Clone Repository

```bash
git clone https://github.com/ardakizilenis/PyChess.git
```
#### 2. In the Root, install requirements

```bash
cd PyChess
chmod +x setup_pychess.sh
./setup_pychess.sh
```

#### 3. Start the Server
```bash
python server.py
```

#### 4. Run the Client
```bash
python main_client.py
```

---

## Default Connection

The client can connect to a custom server IP and port through the connection dialog.

Typical local setup:

- IP: 127.0.0.1
- Port: depending on your current server.py configuration

---

## Game Modes

- Human vs Human
  - Host sends a game offer
  - Opponent accepts
  - Colors are assigned randomly

- Human vs AI
  - Host starts a game against Stockfish
  - Human can be White or Black
  - A level is configurable

- AI vs AI
  - Host starts a match between two AI players
  - All connected clients observe as spectators

---

## Time Controls

Supported time controls:
- 1 min
- 3 min
- 5 min
- 10 min
- 15 min
- 20 min
- 30 min
- 60 min

The host can change the time control before the game starts.
