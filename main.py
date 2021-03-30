import serial
import socket


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

if __name__ == '__main__':
    main()