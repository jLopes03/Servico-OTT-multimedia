import socket
import threading
import pickle
import queue
import time
import sys

from videoProtocol import videoProtocol
from controlProtocol import controlProtocol
from requestProtocol import requestProtocol
from TCPHandler import TCPHandler

TCP_PORT = 9595
UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

myIp = ""
isPP = False

tcpHandlers = {}

IpsLeadingToServer = []

metrics = {}
rttRequestsSent = False
rttRequestsLock = threading.Lock()

videoQueue = queue.Queue()
controlQueue = queue.Queue() 
serverQueue = queue.Queue() # deve apenas ser usada uma vez, mas preferi deixar
clientsResponseQueue = {}
clientsRequestQueue = queue.Queue()

clientPings = {} # se estiver aqui, já foi pinged: ip -> rtt
pingLock = threading.Lock()

streamsSending = {} # videoName -> (set(vizinhos a quem enviar),de onde recebe(ip))
streamsSendingLocks = {} # videoName -> Lock
newClientLock = threading.Lock()

sendCondition = threading.Condition()

clientsWatching = {} # clientIp -> VideoName

# pop usam ffmpeg para enviar para clientes?

def receivePacketsUdp(udpSocket):
    while True:
        data, addr = udpSocket.recvfrom(1500) # MTU UPD
        loadedData = pickle.loads(data)

        if isinstance(loadedData,videoProtocol):
            videoQueue.put((loadedData,data))
        elif isinstance(loadedData,requestProtocol) and loadedData.getOrigin() == "Server":
            serverQueue.put(loadedData)
        elif isinstance(loadedData,requestProtocol) and loadedData.getOrigin() == "ClientResp":
            if addr[0] not in clientsResponseQueue:
                clientsResponseQueue[addr[0]] = queue.Queue()
            clientsResponseQueue[addr[0]].put(loadedData)
        elif isinstance(loadedData,requestProtocol) and loadedData.getOrigin() == "ClientReq":
            clientsRequestQueue.put((loadedData,addr))


def redirectStreams(udpSocket): 
    while True:                 
        videoPacket, pickledPacket = videoQueue.get(True)
        videoName = videoPacket.getVideoName()

        while videoName not in streamsSending: # fazer tempo caso o tcp não tenha chegado
            print("Waiting")
            pass
        
        if streamsSending[videoName] == "STOPPED": # saltar o pacote caso seja de uma stream que já não quero
            continue
        
        with streamsSendingLocks[videoName]:
            sendTo, _ = streamsSending[videoName]
            copiedSendTo = sendTo.copy()

        for dest in copiedSendTo:
            #print(f"sending to {dest}")
            udpSocket.sendto(pickledPacket,dest)

def handleClients():
    while True:
        clientPacket, clientAddr = clientsRequestQueue.get(True)

        if clientPacket.getPayload() != "STOP":
            print(f"Erro a receber do cliente, recebi {clientPacket.getPayload()}")

        videoName = clientsWatching[clientAddr[0]]

        with streamsSendingLocks[videoName]:
            sendingTo, receivingFrom = streamsSending[videoName]
            sendingTo.remove(clientAddr)
            
            del clientsWatching[clientAddr[0]]

            if not sendingTo:

                tcpHandlers[receivingFrom].sendPacket(controlProtocol("STOP Client",((myIp,TCP_PORT)),((SERVER_IP,TCP_PORT)),videoName))

                streamsSending[videoName] = "STOPPED"
            
            print(streamsSending)

def handleNeighbour(tcpHandler,neighbourIp,udpSocket):

    try:
        while True:
            
            loadedPacket = tcpHandler.receivePacket()
            packetType = loadedPacket.getType()

            if packetType == "CONNECTED":

                connectedList = loadedPacket.getPayload()
                
                #print(f"Received {connectedList} from {neighbourIp}")
                
                connectedList.append(myIp)

                for ip in IpsLeadingToServer:
                    connectedPacket = controlProtocol("CONNECTED",(myIp,TCP_PORT),(ip,TCP_PORT),connectedList)
                    tcpHandlers[ip].sendPacket(connectedPacket)

            elif packetType == "RTT Start":
                
                rttFinish = controlProtocol("RTT Finish",(myIp,TCP_PORT),(neighbourIp,TCP_PORT))
                tcpHandler.sendPacket(rttFinish)

                with rttRequestsLock: 
                    rttRequestsSent = True

                if rttRequestsSent: # para não medir várias vezes os mesmos links
                    for addr, handler in tcpHandlers.items():
                        if addr not in IpsLeadingToServer:

                            startRTT = controlProtocol("RTT Start",(myIp,TCP_PORT),(addr,TCP_PORT))
                            metrics[(myIp,addr)] = time.time()
                            handler.sendPacket(startRTT)

            elif packetType == "RTT Finish":

                prevTime =  metrics[(myIp,neighbourIp)]
                with rttRequestsLock: # impossibilita duas threads enviarem valores atualizados de um lado e desatualizados de outro, assim uma envia um atualizado e outra desatualizado e a seguinte já envia os dois atualizados
                    metrics[(myIp,neighbourIp)] = time.time() - prevTime
                    #print(f"RTT {myIp} ---> {neighbourIp} : {metrics[(myIp,neighbourIp)]}")
                
                # Enviar RTT Update para os de trás
                for addr in IpsLeadingToServer:

                    updateRTT = controlProtocol("RTT Update",(myIp,TCP_PORT),(neighbourIp,TCP_PORT),metrics)
                     
                    for ip in IpsLeadingToServer:
                        tcpHandlers[ip].sendPacket(updateRTT)


            elif packetType == "RTT Update":
                # Reencaminhar RTT Update para trás
                # Devem haver repetidos mas a medição só é feita uma vez por link

                rttDict = loadedPacket.getPayload()
                metrics.update(rttDict)

                updateRTT = controlProtocol("RTT Update",(myIp,TCP_PORT),(neighbourIp,TCP_PORT),metrics)
                     
                for ip in IpsLeadingToServer:
                    tcpHandlers[ip].sendPacket(updateRTT)

            elif packetType == "PING Request":

                if isPP:

                    clientAddr = loadedPacket.getPayload()

                    with pingLock:
                        if clientAddr[0] in clientPings: # verificar se isto funciona verdadeiramente
                            rtt = clientPings[clientAddr[0]]

                        else:

                            pingReq = requestProtocol("Node","PING",(myIp,UDP_PORT))
                            startTime = time.time()
                            udpSocket.sendto(pickle.dumps(pingReq),clientAddr)

                            while clientAddr[0] not in clientsResponseQueue:
                                pass

                            clientsResponseQueue[clientAddr[0]].get(True)
                            rtt = time.time() - startTime

                            clientPings[clientAddr[0]] = rtt

                        returnRTT = controlProtocol("PING Response",((myIp,TCP_PORT)),((SERVER_IP,TCP_PORT)),(myIp,rtt,clientAddr[0]))
                            
                        for ip in IpsLeadingToServer:
                            tcpHandlers[ip].sendPacket(returnRTT)

                else:
                    for ip, handler in tcpHandlers.items():
                        if ip not in IpsLeadingToServer:
                            handler.sendPacket(loadedPacket)

            elif packetType == "PING Response":

                for ip in IpsLeadingToServer:
                    tcpHandlers[ip].sendPacket(loadedPacket)

            elif packetType == "NEW Client":
                
                streamPath, videoName = loadedPacket.getPayload()
                whereToSend = streamPath[streamPath.index((myIp,UDP_PORT)) + 1] # (ip, porta)

                newClientLock.acquire()
                if videoName not in streamsSending or streamsSending[videoName] == "STOPPED":
                    streamsSending[videoName] = ({whereToSend},neighbourIp)
                    streamsSendingLocks[videoName] = threading.Lock()

                if isPP:
                    clientsWatching[whereToSend[0]] = videoName

                streamsSendingLocks[videoName].acquire()
                newClientLock.release()
                streamsSending[videoName][0].add(whereToSend)

                if not isPP:
                    tcpHandlers[whereToSend[0]].sendPacket(loadedPacket) # enviar o próximo no caminho de qualquer forma, ele pode precisar de bifurcar

                print(streamsSending)
                streamsSendingLocks[videoName].release()

            elif packetType == "STOP Client":

                videoName = loadedPacket.getPayload()

                with streamsSendingLocks[videoName]:
                    sendingTo, receivingFrom = streamsSending[videoName]
                    sendingTo.remove((neighbourIp,UDP_PORT)) # se este recebe um STOP é porque está a enviar vídeo para quem enviou o pedido de STOP

                    if not sendingTo:
                        
                        tcpHandlers[receivingFrom].sendPacket(loadedPacket)

                        streamsSending[videoName] = "STOPPED"

                    print(streamsSending)

            else:
                print(f"Na thread responsável por {neighbourIp} ----> {loadedPacket.getPayload()}")
    finally:
        tcpHandler.close()

def main():
    global myIp, isPP

    myIp = sys.argv[1]

    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    udpSocket.bind((myIp,UDP_PORT))

    tcpServerSocket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    tcpServerSocket.bind((myIp,TCP_PORT))

    threading.Thread(target=receivePacketsUdp,args=(udpSocket,)).start()

    receivedNeighbours = False
    while not receivedNeighbours:
        try:
            if (neighboursPacket := serverQueue.get(True,0.10)):
                
                neighbours, wayBackN, isPP = neighboursPacket.getPayload()
                receivedNeighbours = True

                for _ in range(10): # melhorar isto
                    ackPacket = requestProtocol("Node","ACK",(myIp,UDP_PORT))
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
            handler.sendPacket(f"{myIp}")

            tcpHandlers[neighbour] = handler
    
    for ip, handler in tcpHandlers.items():
        threading.Thread(target=handleNeighbour,args=(handler,ip,udpSocket)).start()

    if isPP: #na fronteira da rede, os PP iniciam uma cadeia de mensagens até ao servidor para ele saber que a rede está pronta
        for ip in IpsLeadingToServer:
            connectedPacket = controlProtocol("CONNECTED",(myIp,TCP_PORT),(ip,TCP_PORT),[myIp])
            tcpHandlers[ip].sendPacket(connectedPacket)

        threading.Thread(target=handleClients).start()

    threading.Thread(target=redirectStreams,args=(udpSocket,)).start()

main()
