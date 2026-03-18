import sys

from PySide6.QtWidgets import QApplication

from network.NetworkClient import NetworkClient
from view.MainWindow import ChessClient


def main():
    app = QApplication(sys.argv)
    client = NetworkClient()

    if not client.connect(show_dialog=True):
        return

    window = ChessClient(client)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()