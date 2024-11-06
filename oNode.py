import socket
import threading
import pickle

from RTPPacket import RTPPacket

def receive(s):
    while True:
        data, addr = s.recvfrom(1024)
        rtpPacket = pickle.loads(data)

        print(f"{rtpPacket.getPayload()} from {rtpPacket.getSrcAddr()}")

def send(s,addr):
    while True:
        destIp = input("Where to send?\n")
        rtpPacket = RTPPacket(addr,(destIp, 31415),1, "Boas bro!!!")

        s.sendto(pickle.dumps(rtpPacket),rtpPacket.getDestAddr())

def main():
    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    addr = input("Node IP\n")
    s.bind((addr,31415))

    threading.Thread(target=receive, args=(s,)).start()

    send(s,addr)

main()
