import socket
import threading
import pickle
import queue

from RTPProtocol import RTPProtocol
from controlProtocol import controlProtocol
from requestProtocol import requestProtocol

UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

rtpQueue = queue.Queue()
controlQueue = queue.Queue() 
serverQueue = queue.Queue() # deve apenas ser usada uma vez, mas preferi deixar

neighbours = {}

def receivePacketsUdp(udpSocket):
    while True:
        data, addr = udpSocket.recvfrom(1024) #??
        loadedData = pickle.loads(data)

        if isinstance(loadedData,RTPProtocol):
            rtpQueue.put(loadedData)
        elif isinstance(loadedData,controlProtocol):
            controlQueue.put(loadedData) 
        elif isinstance(loadedData,requestProtocol):
            serverQueue.put(loadedData)

def main():
    global neighbours

    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    addr = input("Node IP\n")
    udpSocket.bind((addr,UDP_PORT))

    receivedNeighbours = False

    neighboursRequest = requestProtocol("Node","Neighbours")
    udpSocket.sendto(pickle.dumps(neighboursRequest),(SERVER_IP,UDP_PORT))
    while not receivedNeighbours:
        try:
            if (neighbours := serverQueue.get(True,0.10)):
                receivedNeighbours = False
        
        except queue.Empty:
            neighboursRequest = requestProtocol("Node","Neighbours")
            udpSocket.sendto(pickle.dumps(neighboursRequest),(SERVER_IP,UDP_PORT))

    threading.Thread(target=receivePacketsUdp,args=(udpSocket,)).start()

    print(neighbours)


main()
