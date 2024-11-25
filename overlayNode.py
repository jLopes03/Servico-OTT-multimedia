import socket
import threading
import pickle
import queue
import time

from videoProtocol import videoProtocol
from controlProtocol import controlProtocol
from requestProtocol import requestProtocol
from TCPHandler import TCPHandler

TCP_PORT = 9595
UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

myAddr = ""

tcpHandlers = {}

IpsLeadingToServer = []

metrics = {}
rttRequestsSent = False
rttRequestsLock = threading.Lock()

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


def handleNeighbour(tcpHandler,neighbourAddr):

    try:
        while True:
            
            loadedPacket = tcpHandler.receivePacket()
            packetType = loadedPacket.getType()

            if packetType == "CONNECTED":

                connectedList = loadedPacket.getPayload()
                
                #print(f"Received {connectedList} from {neighbourAddr}")
                
                connectedList.append(myAddr)

                for ip in IpsLeadingToServer:
                    connectedPacket = controlProtocol("CONNECTED",(myAddr,TCP_PORT),(ip,TCP_PORT),connectedList)
                    tcpHandlers[ip].sendPacket(connectedPacket)

            elif packetType == "RTT Start":
                
                rttFinish = controlProtocol("RTT Finish",(myAddr,TCP_PORT),(neighbourAddr,TCP_PORT))
                tcpHandler.sendPacket(rttFinish)

                with rttRequestsLock: 
                    rttRequestsSent = True

                if rttRequestsSent: # para não medir várias vezes os mesmos links
                    for addr, handler in tcpHandlers.items():
                        if addr not in IpsLeadingToServer:

                            startRTT = controlProtocol("RTT Start",(myAddr,TCP_PORT),(addr,TCP_PORT))
                            metrics[(myAddr,addr)] = time.time()
                            handler.sendPacket(startRTT)

            elif packetType == "RTT Finish":

                prevTime =  metrics[(myAddr,neighbourAddr)]
                with rttRequestsLock: # impossibilita duas threads enviarem valores atualizados de um lado e desatualizados de outro, assim uma envia um atualizado e outra desatualizado e a seguinte já envia os dois atualizados
                    metrics[(myAddr,neighbourAddr)] = time.time() - prevTime
                    #print(f"RTT {myAddr} ---> {neighbourAddr} : {metrics[(myAddr,neighbourAddr)]}")
                
                # Enviar RTT Update para os de trás
                for addr in IpsLeadingToServer:

                    updateRTT = controlProtocol("RTT Update",(myAddr,TCP_PORT),(neighbourAddr,TCP_PORT),metrics)
                     
                    for ip in IpsLeadingToServer:
                        tcpHandlers[ip].sendPacket(updateRTT)


            elif packetType == "RTT Update":
                # Reencaminhar RTT Update para trás
                # Devem haver repetidos mas a medição só é feita uma vez por link

                rttDict = loadedPacket.getPayload()
                metrics.update(rttDict)

                updateRTT = controlProtocol("RTT Update",(myAddr,TCP_PORT),(neighbourAddr,TCP_PORT),metrics)
                     
                for ip in IpsLeadingToServer:
                    tcpHandlers[ip].sendPacket(updateRTT)

            else:
                print(f"Na thread responsável por {neighbourAddr} ----> {loadedPacket.getPayload()}") # se algum nodo overlay morrer de momento, os conectados também morrem
    finally:
        tcpHandler.close()

def main():
    global myAddr

    myAddr = input("Node IP\n")

    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    udpSocket.bind((myAddr,UDP_PORT))

    tcpServerSocket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    tcpServerSocket.bind((myAddr,TCP_PORT))

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
    
    tcpServerSocket.listen(wayBackN)
    for _ in range(wayBackN):
        conn, _ = tcpServerSocket.accept()
        handler = TCPHandler(conn,threading.Lock())
        registeredIp = handler.receivePacket() # a interface que a client socket tcp escolhe pode não ser a mesma que o servidor conhece
        tcpHandlers[registeredIp] = handler
        
        IpsLeadingToServer.append(registeredIp)

    tcpServerSocket.close()

    for neighbour in neighbours:
        if neighbour not in tcpHandlers.keys():
            s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            s.connect((neighbour,TCP_PORT))
            handler = TCPHandler(s,threading.Lock())
            handler.sendPacket(f"{myAddr}")

            tcpHandlers[neighbour] = handler
    
    for addr, handler in tcpHandlers.items():
        threading.Thread(target=handleNeighbour,args=(handler,addr,)).start()

    if isPP: #na fronteira da rede, os PP iniciam uma cadeia de mensagens até ao servidor para ele saber que a rede está pronta
        for ip in IpsLeadingToServer:
            connectedPacket = controlProtocol("CONNECTED",(myAddr,TCP_PORT),(ip,TCP_PORT),[myAddr])
            tcpHandlers[ip].sendPacket(connectedPacket)

    if input() == "s":
        for addr in tcpHandlers.keys():
            p = controlProtocol("TEST","","",f"Boas do {myAddr}!")
            tcpHandlers[addr].sendPacket(p)

main()
