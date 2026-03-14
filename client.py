import socket
import json
import threading

class Client:
    def __init__(self):
        self.name = ""

def receive_messages(client):
    while True:
        try:
            response = client.recv(1024)

            if not response:
                break

            response = response.decode("utf-8")

            if response.lower() == "closed":
                break

            print(f"{response}")
            print(">> ", end="", flush=True)

        except Exception:
            break

def run_client():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server_ip = "127.0.0.1"
    server_port = 8001

    client.connect((server_ip, server_port))

    receive_thread = threading.Thread(target=receive_messages, args=(client,), daemon=True)
    receive_thread.start()


    try:
        while True:
            msg = input(">> ")

            if not msg.startswith("\\"):
                json_msg = json.dumps({
                    "type": "msg",
                    "items": msg
                })
                client.send(json_msg.encode("utf-8"))
            else:
                if msg == "\\quit":
                    json_msg = json.dumps({
                        "type": "command",
                        "items": "quit"
                    })
                    client.send(json_msg.encode("utf-8"))
                    break
                elif msg == "\\rename" or msg == "\\rename ":
                    print("Usage: \\rename <name>")

                elif msg.startswith("\\rename "):
                    name = msg.split(maxsplit=1)[1]
                    json_msg = json.dumps({
                        "type": "command",
                        "items": f"rename {name}"
                    })
                    client.send(json_msg.encode("utf-8"))

                else:
                    print("Unknown command")
                    continue

    except Exception as e:
        print(f"Client Error: {e}")

    finally:
        try:
            client.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        client.close()
        print("Connection to server closed")


run_client()