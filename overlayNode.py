import socket
import threading
import pickle

from RTPPacket import RTPPacket

UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

def main():
    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    addr = input("Node IP\n")
    udpSocket.bind((addr,UDP_PORT))



main()
