import socket
import threading
import json

clients = {}

def broadcast(message, client_socket):
    for client in clients:
        if client != client_socket:
            try:
                client.send(message.encode("utf-8"))
            except:
                pass

# ---------- Client Handler ----------
def handle_client(client_socket, addr):
    try:
        while True:
            username = clients.get(client_socket, f"Anonymous{addr[1]}")
            request = client_socket.recv(1024).decode("utf-8")
            try:
                request_json = json.loads(request)

                # ---------- Message Types ----------
                match request_json['type']:
                    # ----- CHAT -----
                    case "msg":
                        print(f"{addr[0]}:{addr[1]} ({username}), MSG: {request_json['items']}")

                        response = f"{username}: {request_json['items']}"
                        broadcast(response, client_socket)
                    # Type: commands
                    case "command":
                        print(f"{addr[0]}:{addr[1]} ({username}), COMMAND: {request_json['items']}")

                        # ----- QUIT -----
                        if request_json['items'] == "quit":
                            print()
                            clients.pop(client_socket, None)
                            response = f"SERVER: {username} left."
                            broadcast(response, client_socket)

                        # ----- RENAME -----
                        if request_json['items'].startswith("rename"):
                            parts = request_json['items'].split(maxsplit=1)
                            if len(parts) < 2:
                                client_socket.send("SERVER: Usage: \\rename <name>".encode("utf-8"))
                                continue
                            new_name = parts[1]
                            old_name = clients[client_socket]
                            clients[client_socket] = new_name
                            response = f"SERVER: {old_name} is now known as {new_name}"
                            broadcast(response, client_socket)

            except json.JSONDecodeError:
                client_socket.send("invalid json".encode("utf-8"))
                continue

    except Exception as e:
        print(f"Error handling client: {e}")
    finally:
        clients.pop(client_socket, None)
        client_socket.close()
        print(f"Connection to client ({addr[0]}:{addr[1]}) closed")

# ---------- Main ----------
def run_server():
    server_ip = "127.0.0.1"  # server hostname or IP address
    port = 8001  # server port number
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((server_ip, port))
        server.listen()
        print(f"Listening on {server_ip}:{port}")

        while True:
            # accept a client connection, add to list
            client_socket, addr = server.accept()
            print(f"Accepted connection from {addr[0]}:{addr[1]}")
            clients[client_socket] = "Anonymous"
            broadcast(f"SERVER: Anonymous{addr[1]} joined", client_socket)

            # start a new thread to handle the client
            thread = threading.Thread(target=handle_client, args=(client_socket, addr,))
            thread.start()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        server.close()

run_server()
