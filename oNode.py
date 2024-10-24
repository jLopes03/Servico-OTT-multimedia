import socket
import threading
import pickle

def receive(s):
    while True:
        data, addr = s.recvfrom(1024)
        print(f"{pickle.loads(data)} from {addr}")

def send(s):
    while True:
        addr = input("Where to send?\n")
        s.sendto(pickle.dumps("Boas"),(addr,31415))

def main():
    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    addr = input("Node IP\n")
    s.bind((addr,31415))

    threading.Thread(target=receive, args=(s,)).start()

    send(s)

main()