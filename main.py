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

# if __name__ == '__main__':
#     main()