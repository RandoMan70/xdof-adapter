import serial
import socket
import sys
from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtNetwork import QUdpSocket, QHostAddress
import win32api
import keycodes
import os

serial_port_name = "COM6"
serlal_port_baudrate = 115200

udp_ip = "127.0.0.33"
udp_port = 10333
PROGRAM_DIR = os.path.dirname(os.path.abspath(__file__))


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

        super(Ui, self).__init__()
        uic.loadUi(PROGRAM_DIR + '/basic.ui', self)

        self.platform = Platform(serial_port_name, serlal_port_baudrate)
        self.listener = NetworkReceiver(udp_ip, udp_port)
        self.listener.update.connect(self.udp_data_received)

        self.upButton = self.findChild(QtWidgets.QPushButton, 'upButton')
        self.upButton.clicked.connect(self.upButtonPressed)

        self.downButton = self.findChild(QtWidgets.QPushButton, 'downButton')
        self.downButton.clicked.connect(self.downButtonPressed)

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

        self.keychecker = KeyChecker(["f11", "f12"])
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
        self.platform.set_wind(255)

    def upButtonPressed(self):
        if self.app_shutdown:
            return

        print("UP!")
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
        print('DOWN!')
        self.stopped = True
        self.update_status_label()
        self.platform.set_wind(0)
        self.path = Path(4, self.down_process_done)
        self.path.reset([self.platform.left_front, self.platform.right_front, self.platform.rear, self.platform.angle])

        p1 = min([self.platform.left_front, self.platform.right_front, self.platform.rear])

        self.path.waypoint_add([p1, p1, p1, self.platform.angle])
        self.path.waypoint_add([0, 0, 0, 100])

        self.timer.start()


app = QtWidgets.QApplication(sys.argv)
app.setWindowIcon(QIcon(PROGRAM_DIR + '/wheel.svg'))
window = Ui()
app.exec_()