import socket
import threading
import pickle
import queue

from videoProtocol import videoProtocol
from controlProtocol import controlProtocol
from requestProtocol import requestProtocol

UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

videoQueue = queue.Queue()
controlQueue = queue.Queue() 
serverQueue = queue.Queue() # deve apenas ser usada uma vez, mas preferi deixar

neighbours = {}

def receivePacketsUdp(udpSocket):
    while True:
        data, addr = udpSocket.recvfrom(1500) # MTU UPD
        loadedData = pickle.loads(data)

        if isinstance(loadedData,videoProtocol):
            videoQueue.put(loadedData)
        elif isinstance(loadedData,controlProtocol):
            controlQueue.put(loadedData) 
        elif isinstance(loadedData,requestProtocol):
            serverQueue.put(loadedData)

def main():
    global neighbours

    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    addr = input("Node IP\n")
    udpSocket.bind((addr,UDP_PORT))

    threading.Thread(target=receivePacketsUdp,args=(udpSocket,)).start()

    receivedNeighbours = False

    neighboursRequest = requestProtocol("Node","Neighbours",(addr,UDP_PORT))
    udpSocket.sendto(pickle.dumps(neighboursRequest),(SERVER_IP,UDP_PORT))
    while not receivedNeighbours:
        try:
            if (neighbours := serverQueue.get(True,0.10).getPayload()):
                receivedNeighbours = True
        
        except queue.Empty:
            neighboursRequest = requestProtocol("Node","Neighbours",(addr,UDP_PORT))
            udpSocket.sendto(pickle.dumps(neighboursRequest),(SERVER_IP,UDP_PORT))

    print(neighbours)


main()
