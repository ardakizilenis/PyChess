import sys

from PySide6.QtWidgets import QApplication

from network.NetworkClient import NetworkClient
from view.MainWindow import ChessClient
from view.ErrorWindow import ErrorWidget

def main():
    app = QApplication(sys.argv)
    client = NetworkClient()
    try:
        client.connect()
    except Exception as e:
        window = ErrorWidget("Connection Error", str(e))
        window.show()
        sys.exit(app.exec())

    if not client.isConnected:
        window = ErrorWidget("Connection Error", "This Game has already started")
    else:
        window = ChessClient(client)

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()