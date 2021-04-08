import serial
import socket
import sys
from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import QObject, QThread, pyqtSignal

# Step 1: Create a worker class
class Worker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int)

    def run(self):
        port = serial.Serial(port='COM3', baudrate=9600, timeout=1)
        while True:
            try:
                # data = port.readline()
                data = port.read(size=8)
            except TimeoutError:
                continue
            # print(data.decode().strip())
            print(" ".join(["{:02d}".format(x) for x in data]))


class Ui(QtWidgets.QMainWindow):
    def __init__(self):
        super(Ui, self).__init__()
        uic.loadUi('basic.ui', self)

        self.upButton = self.findChild(QtWidgets.QPushButton, 'upButton')
        self.upButton.clicked.connect(self.upButtonPressed)

        self.downButton = self.findChild(QtWidgets.QPushButton, 'downButton')
        self.downButton.clicked.connect(self.downButtonPressed)

        self.show()

    def upButtonPressed(self):
        print('UP!')

    def downButtonPressed(self):
        print('DOWN!')

def push_state(left_front: int, right_front: int, rear: int, turn: int, wind: int):
    print(left_front, right_front, rear, turn, wind)

print("starting\n")

def main():
    port = serial.Serial(port='COM3', baudrate=9600, timeout=1)
    while True:
        try:
            # data = port.readline()
            data = port.read(size=8)
        except TimeoutError:
            continue
        # print(data.decode().strip())
        print( " ".join(["{:02d}".format(x) for x in data]))

app = QtWidgets.QApplication(sys.argv)
window = Ui()
app.exec_()

port = serial.Serial(port="COM6", baudrate=9600)
localIP = "127.0.0.33"
localPort = 10333

def push_state(left_front: int, right_front: int, rear: int, turn:int  = 100, wind: int = 0):
    assert (left_front >= 0) and (left_front <= 255)
    assert (right_front >= 0) and (right_front <= 255)
    assert (rear >= 0) and (rear <= 255)
    assert (turn >= 0) and (turn <= 255)
    assert (wind >= 0) and (wind <= 255)

    message = [0x41, 0x42, 0xFF, left_front, right_front, rear, turn, wind]
    port.write(bytes(message))

def main():
    sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    sock.bind((localIP, localPort))

    while True:
        dgram = sock.recv(128)
        print(dgram.decode().strip())

        numbers=dgram.decode().split()
        push_state(int(numbers[0]), int(numbers[1]), int(numbers[2]))

# if __name__ == '__main__':
#     main()