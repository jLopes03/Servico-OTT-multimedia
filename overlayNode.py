import socket
import threading
import pickle
import queue
import sys
import struct

from videoProtocol import videoProtocol
from controlProtocol import controlProtocol
from requestProtocol import requestProtocol

TCP_PORT = 9595
UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

myAddr = ""

tcpSockets = {}
tcpSocketsLocks = {}

IpsLeadingToServer = []

videoQueue = queue.Queue()
controlQueue = queue.Queue() 
serverQueue = queue.Queue() # deve apenas ser usada uma vez, mas preferi deixar

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


def handleNeighbour(tcpSocket,neighbourAddr):

    try:
        while True:
            lenData = b''
            while len(lenData) < 4:
                lenData += tcpSocket.recv(4 - len(lenData))
            length = struct.unpack("!I",lenData)[0]

            data = b''
            while len(data) < length:
                data += tcpSocket.recv(length - len(data))
            loadedPacket = pickle.loads(data)

            if loadedPacket.getType() == "CONNECTED":

                connectedList = loadedPacket.getPayload()
                
                #print(f"Received {connectedList} from {neighbourAddr}")
                
                connectedList.append(myAddr)

                for ip in IpsLeadingToServer:
                    connectedPacket = controlProtocol("CONNECTED",(myAddr,TCP_PORT),(ip,TCP_PORT),connectedList)
                    pickledPacket = pickle.dumps(connectedPacket)
                        
                    size = len(pickledPacket)
                    packedSize = struct.pack("!I",size)

                    with tcpSocketsLocks[ip]:

                        #print(f"Sending {connectedList} to {ip}")
                        tcpSockets[ip].sendall(packedSize)
                        tcpSockets[ip].sendall(pickledPacket)

            else:
                print(f"Na thread responsável por {neighbourAddr} ----> {loadedPacket.getPayload()}") # se algum nodo overlay morrer de momento, os conectados também morrem
    finally:
        tcpSocket.close()

def main():
    global myAddr

    myAddr = input("Node IP\n")

    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    udpSocket.bind((myAddr,UDP_PORT))

    threading.Thread(target=receivePacketsUdp,args=(udpSocket,)).start()

    receivedNeighbours = False
    while not receivedNeighbours:
        try:
            if (neighboursPacket := serverQueue.get(True,0.10)):
                
                neighbours, wayBackN, isPP = neighboursPacket.getPayload()
                receivedNeighbours = True

                for _ in range(10): # melhorar isto
                    ackPacket = requestProtocol("Node","ACK",(myAddr,UDP_PORT))
                    udpSocket.sendto(pickle.dumps(ackPacket),(SERVER_IP,UDP_PORT))

        except queue.Empty:
            pass
    
    print(neighbours)

    tcpServerSocket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    tcpServerSocket.bind((myAddr,TCP_PORT))
    tcpServerSocket.listen(wayBackN)
    
    for _ in range(wayBackN):
        conn, _ = tcpServerSocket.accept()
        registeredIp = pickle.loads(conn.recv(1024)) # a interface que a client socket tcp escolhe pode não ser a mesma que o servidor conhece
        tcpSockets[registeredIp] = conn
        tcpSocketsLocks[registeredIp] = threading.Lock()
        
        IpsLeadingToServer.append(registeredIp)

    tcpServerSocket.close()

    for neighbour in neighbours:
        if neighbour not in tcpSockets.keys():
            tcpSockets[neighbour] = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            tcpSocketsLocks[neighbour] = threading.Lock()

            tcpSockets[neighbour].connect((neighbour,TCP_PORT))
            tcpSockets[neighbour].send(pickle.dumps(f"{myAddr}"))
    
    for addr, sock in tcpSockets.items():
        threading.Thread(target=handleNeighbour,args=(sock,addr,)).start()

    if isPP: #na fronteira da rede, os PP iniciam uma cadeia de mensagens até ao servidor para ele saber que a rede está pronta
        for ip in IpsLeadingToServer:
            connectedPacket = controlProtocol("CONNECTED",(myAddr,TCP_PORT),(ip,TCP_PORT),[myAddr])

            pickledPacket = pickle.dumps(connectedPacket)
                        
            size = len(pickledPacket)
            packedSize = struct.pack("!I",size)

            tcpSockets[ip].sendall(packedSize)
            tcpSockets[ip].sendall(pickledPacket)

    if input() == "s":
        for s in tcpSockets.values():
            p = controlProtocol("TEST","","",f"Boas do {myAddr}!")
            pickledP = pickle.dumps(p)

            size = len(pickledP)
            packedSize = struct.pack("!I",size)
            
            s.sendall(packedSize)
            s.sendall(pickledP)

main()
