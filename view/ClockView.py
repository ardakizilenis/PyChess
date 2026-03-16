from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class ClockWidget(QWidget):
    time_expired = Signal(str)

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.title = QLabel("Clock")
        self.title.setAlignment(Qt.AlignCenter)

        self.white_time = QLabel("White: 10:00")
        self.white_time.setAlignment(Qt.AlignCenter)

        self.black_time = QLabel("Black: 10:00")
        self.black_time.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.title)
        layout.addWidget(self.white_time)
        layout.addWidget(self.black_time)

        self.setLayout(layout)

        self.white_seconds = 10 * 60
        self.black_seconds = 10 * 60
        self.active_player = None
        self.is_running = False

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)

        self.refresh_labels()

    def format_seconds(self, total_seconds: int) -> str:
        minutes = max(total_seconds, 0) // 60
        seconds = max(total_seconds, 0) % 60
        return f"{minutes:02d}:{seconds:02d}"

    def refresh_labels(self):
        self.white_time.setText(f"White: {self.format_seconds(self.white_seconds)}")
        self.black_time.setText(f"Black: {self.format_seconds(self.black_seconds)}")

    def set_times(self, white_time: str, black_time: str):
        self.white_seconds = self.parse_time_string(white_time)
        self.black_seconds = self.parse_time_string(black_time)
        self.refresh_labels()

    def parse_time_string(self, time_string: str) -> int:
        parts = time_string.split(":")
        if len(parts) != 2:
            return 10 * 60

        try:
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
        except ValueError:
            return 10 * 60

    def set_time_minutes(self, minutes: int):
        self.white_seconds = minutes * 60
        self.black_seconds = minutes * 60
        self.refresh_labels()

    def set_seconds(self, white_seconds: int, black_seconds: int):
        self.white_seconds = max(0, int(white_seconds))
        self.black_seconds = max(0, int(black_seconds))
        self.refresh_labels()

    def start(self, active_player: str | None = None):
        if active_player is not None:
            self.active_player = active_player
        if self.active_player is None:
            self.active_player = "white"
        self.is_running = True
        self.set_active_player(self.active_player)

    def stop(self):
        self.is_running = False
        self.set_active_player(None)

    def switch_player(self, color: str):
        self.active_player = color
        self.set_active_player(color)

    def tick(self):
        return

    def set_active_player(self, color: str | None):
        active_style = "font-weight: bold; color: #1f6feb;"
        inactive_style = "font-weight: normal; color: black;"

        if color == "white":
            self.white_time.setStyleSheet(active_style)
            self.black_time.setStyleSheet(inactive_style)
        elif color == "black":
            self.white_time.setStyleSheet(inactive_style)
            self.black_time.setStyleSheet(active_style)
        else:
            self.white_time.setStyleSheet(inactive_style)
            self.black_time.setStyleSheet(inactive_style)
