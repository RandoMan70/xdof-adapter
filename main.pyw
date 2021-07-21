import serial
import configparser
import sys
from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtMultimedia import QSound
from PyQt5.QtNetwork import QUdpSocket, QHostAddress
from PyQt5.QtWidgets import QInputDialog, QLineEdit, QErrorMessage
import win32api
import keycodes
import os

PROGRAM_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = PROGRAM_DIR + "/settings.ini"

class Settings:
    def __init__(self, path):
        self.path = path
        self.config = configparser.ConfigParser()

        self.serial_port_name = "COM6"
        self.serial_port_baudrate = 115200
        self.udp_ip = "127.0.0.33"
        self.udp_port = 10333
        self.time_step = 6
        self.override_wind_speed = 64

        self.load()

    def export(self):
        self.config["serial"] = {
            "port_name": self.serial_port_name,
            "port_baudrate": str(self.serial_port_baudrate)
        }
        self.config["network"] = {
            "listen_addr": self.udp_ip,
            "listen_port": str(self.udp_port)
        }
        self.config["platform"] = {
            "time_step_minutes": str(self.time_step),
        }
        if self.override_wind_speed is not None:
            self.config["platform"]["override_wind_speed"] = str(self.override_wind_speed)


    def extract(self):
        self.serial_port_name = self.config["serial"]["port_name"]
        self.serial_port_baudrate = int(self.config["serial"]["port_baudrate"])

        self.udp_ip = self.config["network"]["listen_addr"]
        self.udp_port = int(self.config["network"]["listen_port"])

        self.time_step = int(self.config["platform"]["time_step_minutes"])

        self.override_wind_speed = None
        if 'override_wind_speed' in self.config["platform"]:
            self.override_wind_speed = int(self.config["platform"]['override_wind_speed'])

    def load(self):
        ret = self.config.read(self.path)
        if len(ret) == 0:
            self.export()
            self.save()
            return

        self.extract()

    def save(self):
        with open(self.path, 'w') as settings_file:
            self.config.write(settings_file)

def time_minutes_text(m):
    trailing = m % 10
    if trailing == 1:
        return "+ " + str(m) + " минута"

    if trailing < 5:
        return "+ " + str(m) + " минуты"

    return "+ " + str(m) + " минут"

class NetworkReceiver(QObject):
    update = pyqtSignal()

    def __init__(self, ip, port):
        super(QObject, self).__init__()
        self.left_front = None
        self.right_front = None
        self.rear = None
        self.angle = None
        self.wind = None

        self.socket = QUdpSocket(self)
        self.socket.bind(QHostAddress(ip), port)
        self.socket.readyRead.connect(self.data_ready)

    def has_data(self):
        return \
            self.left_front is not None and \
            self.right_front is not None and \
            self.rear is not None and \
            self.angle is not None and \
            self.wind is not None

    def data_ready(self):
        while self.socket.hasPendingDatagrams():
            datagram, unused_host, unused_port = self.socket.readDatagram(self.socket.pendingDatagramSize())
            print(datagram.decode().strip())

            numbers = datagram.decode().split()
            self.left_front = int(numbers[0])
            self.right_front = int(numbers[1])
            self.rear = int(numbers[2])
            self.angle = int(numbers[3])
            self.wind = int(numbers[4])

            self.update.emit()


class Platform(QObject):
    status = pyqtSignal(int, int, int, int, int)

    def __init__(self, port_name, baudrate=115200):
        super(QObject, self).__init__()
        self.port = serial.Serial(port=port_name, baudrate=baudrate)
        self.left_front = 0
        self.right_front = 0
        self.rear = 0
        self.angle = 100
        self.wind = 0

    def set_wind(self, wind: int, no_push=False):
        assert (wind >= 0) and (wind <= 255)
        self.wind = wind
        self.push()

    def set_position(self, left_front: int, right_front: int, rear: int, angle: int, no_push=False):
        assert (left_front >= 0) and (left_front <= 255)
        assert (right_front >= 0) and (right_front <= 255)
        assert (rear >= 0) and (rear <= 255)
        assert (angle >= 0) and (angle <= 255)

        self.left_front = left_front
        self.right_front = right_front
        self.rear = rear
        self.angle = angle

        self.push()

    def set(self, left_front: int, right_front: int, rear: int, angle: int, wind: int):
        self.set_position(left_front, right_front, rear, angle, no_push=True)
        self.set_wind(wind, no_push=True)
        self.push()

    def push(self):
        self.status.emit(self.left_front, self.right_front, self.rear, self.angle, self.wind)
        message = [0x41, 0x42, 0xFF, self.left_front, self.right_front, self.rear, self.angle, self.wind]
        self.port.write(bytes(message))


class Path:
    def __init__(self, ndof: int, done_cb):
        self.ndof = ndof
        self.waypoints = []
        self.position = []
        self.next_waypoint = None
        self.done_cb = done_cb

    def set_done(self):
        self.next_waypoint = None
        if self.done_cb is not None:
            self.done_cb()

    def done(self):
        return self.next_waypoint is None

    def step(self):
        if self.done():
            return

        desired = self.waypoints[self.next_waypoint]
        dirty = False

        for i in range(0, self.ndof):
            if self.position[i] < desired[i]:
                self.position[i] += 1
                dirty = True

            if self.position[i] > desired[i]:
                self.position[i] -= 1
                dirty = True

        if not dirty:
            self.next_waypoint += 1
            if self.next_waypoint >= len(self.waypoints):
                self.set_done()

    def reset(self, point: [int]):
        assert self.ndof == len(point)

        self.position = point

        if len(self.waypoints) > 0:
            self.next_waypoint = 0

    def waypoint_add(self, point: [int]):
        assert self.ndof == len(point)

        self.waypoints.append(point)

        if self.next_waypoint is None:
            self.next_waypoint = 0


class KeyChecker(QObject):
    pressed = pyqtSignal(str)
    released = pyqtSignal(str)

    def __init__(self, monitored: [str]):
        super().__init__()
        self.status = {}
        self.monitored = monitored
        for m in self.monitored:
            self.status[m] = False

    def check(self):
        for m in self.monitored:
            pressed = win32api.GetAsyncKeyState(keycodes.vk_key_names[m]) < 0

            if pressed:
                if self.status[m]:
                    continue

                self.status[m] = True
                self.pressed.emit(m)
            else:
                if not self.status[m]:
                    continue

                self.status[m] = False
                self.released.emit(m)

class Ui(QtWidgets.QMainWindow):

    def __init__(self):
        self.stopped = True
        self.app_shutdown = False
        self.timeleft = 0

        self.sound_up = QSound(PROGRAM_DIR + "/sounds/up.wav")
        self.sound_down = QSound(PROGRAM_DIR + "/sounds/down.wav")

        super(Ui, self).__init__()
        uic.loadUi(PROGRAM_DIR + '/basic.ui', self)

        self.platform = Platform(settings.serial_port_name, settings.serial_port_baudrate)
        self.listener = NetworkReceiver(settings.udp_ip, settings.udp_port)
        self.listener.update.connect(self.udp_data_received)

        self.upButton = self.findChild(QtWidgets.QPushButton, 'upButton')
        self.upButton.clicked.connect(self.upButtonPressed)

        self.downButton = self.findChild(QtWidgets.QPushButton, 'downButton')
        self.downButton.clicked.connect(self.downButtonPressed)

        self.defaultTimeButton = self.findChild(QtWidgets.QPushButton, 'defaultTimeButton')
        self.defaultTimeButton.clicked.connect(self.defaultTimeButtonPressed)
        self.defaultTimeButton.setText(time_minutes_text(settings.time_step))

        self.customTimeButton = self.findChild(QtWidgets.QPushButton, 'customTimeButton')
        self.customTimeButton.clicked.connect(self.customTimeButtonPressed)

        self.timeLeftLabel = self.findChild(QtWidgets.QLabel, 'timeLeftLabel')

        self.platformLeftFront = self.findChild(QtWidgets.QProgressBar, 'platformLeftFront')
        self.platformRightFront = self.findChild(QtWidgets.QProgressBar, 'platformRightFront')
        self.platformRear = self.findChild(QtWidgets.QProgressBar, 'platformRear')
        self.platformAngle = self.findChild(QtWidgets.QProgressBar, 'platformAngle')
        self.platformWind = self.findChild(QtWidgets.QProgressBar, 'platformWind')

        self.statusLabel = self.findChild(QtWidgets.QLabel, 'statusLabel')
        self.update_status_label()

        self.path = None

        self.timer = QTimer()
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.timer_timeout)

        self.time_ticker = QTimer()
        self.time_ticker.setInterval(1000)
        self.time_ticker.timeout.connect(self.tick_timeleft)

        self.keychecker = KeyChecker(["f10", "f11", "f12"])
        self.keychecker.pressed.connect(self.pressed)
        self.keycheck_timer = QTimer()
        self.keycheck_timer.setInterval((20))
        self.keycheck_timer.timeout.connect(self.keychecker.check)
        self.keycheck_timer.start()

        self.buttons = []

        for k, v in self.__dict__.items():
            if isinstance(v, QtWidgets.QPushButton):
                self.buttons.append(v)

        self.platform.status.connect(self.update_position_bars)
        self.show()

    def closeEvent(self, event):
        print("CLOSING!")
        self.set_control_disabled(True)
        self.app_shutdown = True
        self.downButton.clicked.emit()
        event.ignore()

    def pressed(self, key):
        if key == "f10":
            self.defaultTimeButtonPressed()

        if key == "f11":
            self.upButton.clicked.emit()

        if key == "f12":
            self.downButton.clicked.emit()

    def udp_data_received(self):
        if self.stopped:
            return

        self.platform.set(
            self.listener.left_front,
            self.listener.right_front,
            self.listener.rear,
            self.listener.angle,
            self.listener.wind
        )

    def set_control_disabled(self, disabled: True):
        for b in self.buttons:
            b.setDisabled(disabled)

    def update_position_bars(self, left_front: int, right_front: int, rear: int, turn: int, wind: int):
        self.platformLeftFront.setValue(left_front)
        self.platformRightFront.setValue(right_front)
        self.platformRear.setValue(rear)
        self.platformAngle.setValue(turn)
        self.platformWind.setValue(wind)
        self.platformLeftFront.update()

    def update_status_label(self):
        if self.stopped:
            self.statusLabel.setStyleSheet("QLabel { color : red; }")
            self.statusLabel.setText("ОСТАНОВЛЕНО")
        else:
            self.statusLabel.setStyleSheet("QLabel { color : blue; }")
            self.statusLabel.setText("РАБОТАЕТ")

    @staticmethod
    def to_value(self, value, v: [int]):
        if v[0] < value:
            v[0] += 1
        if v[0] > value:
            v[0] -= 1

    def timer_timeout(self):
        if self.path.done():
            self.path = None
            self.timer.stop()
            return

        self.path.step()
        p = self.path.position
        self.platform.set_position(p[0], p[1], p[2], p[3])

    def up_process_done(self):
        self.stopped = False
        self.update_status_label()
        if settings.override_wind_speed is not None:
            self.platform.set_wind(settings.override_wind_speed)
        self.time_ticker.start()

    def upButtonPressed(self):
        if self.app_shutdown:
            print("Stopping")
            return

        if self.timeleft <= 0:
            print("No time left")
            return

        print("Up the platform")
        self.sound_up.play()
        self.path = Path(4, self.up_process_done)
        self.path.reset([self.platform.left_front, self.platform.right_front, self.platform.rear, self.platform.angle])
        if self.listener.has_data():
            self.path.waypoint_add(
                [self.listener.left_front,
                 self.listener.right_front,
                 self.listener.rear,
                 self.listener.angle]
            )
        else:
            self.path.waypoint_add([127, 127, 127, 100])
        self.timer.start()

    def down_process_done(self):
        if self.app_shutdown:
            sys.exit()

    def downButtonPressed(self):
        print('Down the platform')
        self.sound_down.play()
        self.stopped = True
        self.time_ticker.stop()
        self.update_status_label()
        self.platform.set_wind(0)
        self.path = Path(4, self.down_process_done)
        self.path.reset([self.platform.left_front, self.platform.right_front, self.platform.rear, self.platform.angle])

        p1 = min([self.platform.left_front, self.platform.right_front, self.platform.rear])

        self.path.waypoint_add([p1, p1, p1, self.platform.angle])
        self.path.waypoint_add([0, 0, 0, 100])

        self.timer.start()

    def sync_timeleft(self):
        minutes = self.timeleft / 60
        seconds = self.timeleft % 60
        self.timeLeftLabel.setText("%d:%02d" % (minutes, seconds))

    def add_timeleft(self, seconds):
        self.timeleft += seconds
        self.sync_timeleft()

    def set_timeleft(self, seconds):
        self.timeleft = seconds
        self.sync_timeleft()

    def tick_timeleft(self):
        self.timeleft -= 1
        if self.timeleft <= 0:
            self.timeleft = 0
            self.time_ticker.stop()
            self.downButtonPressed()

        self.sync_timeleft()

    def defaultTimeButtonPressed(self):
        print("+", settings.time_step, "min.")
        self.add_timeleft(settings.time_step * 60)

    def customTimeButtonPressed(self):
        print("Custom time")

        if self.timeleft == 0:
            timeleft = int(settings.time_step * 60)
        else:
            timeleft = self.timeleft

        minutes = timeleft / 60
        seconds = timeleft % 60

        text = "%d:%02d" % (minutes, seconds)

        while True:
            text, ok = QInputDialog.getText(self, 'Input Dialog',
                                            'Enter your name:', QLineEdit.Normal, text)

            if not ok:
                return
            try:
                parts = text.split(":")
                if len(parts) == 1:
                    minutes = int(parts[0])
                    seconds = 0
                else:
                    (minutes, seconds) = text.split(":", 2)
                    minutes = int(minutes)
                    seconds = int(seconds)
                    if seconds < 0 or seconds > 59:
                        continue

                    if minutes < 0:
                        continue

                self.set_timeleft(minutes * 60 + seconds)
                return
            except Exception as e:
                print("Invalid time (%s):" % (e), text)

if __name__ == "__main__":
    settings = Settings(SETTINGS_FILE)
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QIcon(PROGRAM_DIR + '/wheel.svg'))
    window = Ui()
    app.exec_()
