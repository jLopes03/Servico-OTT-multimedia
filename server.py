import socket
import threading
import pickle
import json
import queue
import os
import re
import ffmpeg
import shutil
import time
import networkx

from collections import deque

from videoProtocol import videoProtocol
from requestProtocol import requestProtocol
from controlProtocol import controlProtocol
from TCPHandler import TCPHandler

TCP_PORT = 9595
UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

CHUNK_SIZE = 940 # 188 * 5, MTU UDP -> 1500

clientsQueue = queue.Queue()
nodeQueueUdp = queue.Queue()

tcpHandlers = {}

metrics = {} # (origem, dest) -> N segundos
networkxGraph = networkx.Graph()
bestPathsPP = {} # ip -> (path,rtt)
clientPings = {} # client ip -> [(ppIp,rtt)]

clientAddrs = {} # clientIP -> (clientIP,Port)

videoDelays = {} # videoName -> delay

streamsSending = {} # videoName -> set(vizinhos para onde enviar)
streamsSendingLocks = {} # videoName -> Lock

statusUpdates = 0
statusLock = threading.Lock()

readyNodes = deque()

def countEdges(graph_dict):
    """
    Counts the number of edges in an undirected graph represented as a dictionary.
    
    Parameters:
        graph_dict (dict): The graph representation where the key is the 'ip',
                           and the value is a tuple (id, [neighbours], is_pp, wayBack).
    
    Returns:
        int: The count of edges in the graph.
    """
    edge_count = 0
    
    for ip, (_, neighbours, _, _) in graph_dict.items():
        # Add the number of neighbours of the current ip
        edge_count += len(neighbours)
    
    # Since each edge is counted twice, divide the sum by 2
    return edge_count // 2

def loadOverlay():
    nodeTree = {}
    with open("overlay.json", "r") as jsonFile:
        data = json.load(jsonFile)

    for node in data["nodes"]:
        nodeTree[node["ip"]] = (node["id"], node["neighbours"], node["pp"],node["wayBack"])

    return nodeTree

def convertToMpegts(videoName):
    ffmpeg.input(f"Videos/{videoName}").output(f"mpegtsVideos/{videoName}.ts",f="mpegts",vcodec="libx264",acodec="aac",preset="superfast",loglevel="quiet").run()
    # ffmpeg -i VideoA.mp4 -f mpegts -c:v libx264 -preset superfast -c:a aac output.ts

    #tambem vamos calcular o delay:
    delay = calculateDelay(videoName)
    videoDelays[videoName] = delay

def discoverSplitVideos():
    os.makedirs("mpegtsVideos")

    for videoName in os.listdir("Videos"):
        threading.Thread(target=convertToMpegts,args=(videoName,)).start()

    return os.listdir("Videos")
   
def receivePacketsUdp(udpSocket):
    udpSocket.settimeout(None) # colocar em blocking mode
    while True:
        data, addr = udpSocket.recvfrom(1500) # MTU UPD
        loadedData = pickle.loads(data)
        
        if loadedData.getOrigin() == "Client":
            clientsQueue.put((loadedData, addr))
        elif loadedData.getOrigin() == "Node":
            nodeQueueUdp.put((loadedData,addr))

def calculateDelay(videoName):
    
    probe = ffmpeg.probe(f"mpegtsVideos/{videoName}.ts", v='error', show_entries='format=bit_rate')

    totalBitrate = int(probe['format'].get('bit_rate'))

    totalByteRate = totalBitrate/8

    return CHUNK_SIZE/totalByteRate

# servidor vê caminho, avisa o vizinho para quem vai enviar por tcp e guarda num dicionário para onde está a enviar o video: Video -> set(vizinhos a quem enviar)
# o servidor ao avisar o vizinho tambem avisa para quem ele tem que enviar, sendo assim o caminho da transmissão é enviado por tcp
# nodes têm de filtrar pelo nome do video de modo a saber para onde enviar cada pacotes, talvez dicionário de queues para permitir multithreading, ou apenas uma queue com um if
# clientes avisam que querem sair ao pop, o pop remove o ip do cliente da lista e informa quem está a enviar para ele que já não precisa caso não tenha mais clientes
# para isto é necessário os nodes guardarem tambem de quem estão a receber o quê, portanto o dicionário lá em cima será na verdade: Video -> (set(vizinhos a quem enviar), quem está a enviar para ele)
# mudamos de lista para set, assim não tem repetidos e garantimos o menor número de fluxos

def sendVideo(udpSocket, videoName, delay):

    # streamsSending : videoName -> set(Vizinhos)

    with open(f"mpegtsVideos/{videoName}.ts","rb") as tsFile:
        seqNumber = 0
        while True:
            startTime = time.time()

            if not (videoChunk := tsFile.read(CHUNK_SIZE)) or videoName not in streamsSending:
                break 

            neighboursToSend = streamsSending[videoName]

            videoPacket = videoProtocol((SERVER_IP,UDP_PORT),videoName,seqNumber,videoChunk)
            pickledVideoPacket = pickle.dumps(videoPacket)
            #print(len(pickledVideoPacket))

            for neighbour in neighboursToSend:
                udpSocket.sendto(pickledVideoPacket,neighbour)

            seqNumber += 1

            elapsedTime = time.time() - startTime
            time.sleep(max(0,delay - elapsedTime))


def handleClients(udpSocket,videoList, numPPs):

    while True:
    
        clientPacket, clientAddr = clientsQueue.get(True) # bloqueia até ter um pacote
        clientAddrs[clientAddr[0]] = clientAddr
    
        if clientPacket.getPayload() == "VL": #Video List
    
            listResponse = requestProtocol("Server",videoList)
            udpSocket.sendto(pickle.dumps(listResponse),clientAddr)
    
        elif (match := re.match(r"W : (.*)",clientPacket.getPayload())):
    
            videoName = match.group(1)
    
            if videoName in videoList: # fazer a verificação de não ser pacote repetido (se o cliente já vê o vídeo ou não)

                if clientAddr[0] not in clientPings: # se já foram pedidas métricas para este cliente
                    
                    clientPings[clientAddr[0]] = []
                    for ip, handler in tcpHandlers.items():
                        pingReq = controlProtocol("PING Request",((SERVER_IP,TCP_PORT)),((ip,TCP_PORT)),clientAddr)
                        handler.sendPacket(pingReq)
                
                while len(clientPings[clientAddr[0]]) < numPPs:
                    time.sleep(0.5) # poupar CPU

                ppIp = calcBestPP(clientAddr[0])

                nodeLocationPacket = requestProtocol("Server",f"{ppIp}")
                udpSocket.sendto(pickle.dumps(nodeLocationPacket),clientAddr)

                streamPath = [(ip, UDP_PORT) for ip in bestPathsPP[ppIp][0]]
                streamPath += [clientAddr]

                print(f"melhor pp para {clientAddr[0]} é {ppIp} com caminho {streamPath}")

                #informar vizinho por TCP
                neighbourToSend = streamPath[1] # (ip,porta) # streamPath[0] é o servidor
                tcpHandlers[neighbourToSend[0]].sendPacket(controlProtocol("NEW Client",((SERVER_IP,TCP_PORT)),neighbourToSend,(streamPath,videoName)))

                if videoName not in streamsSending: # isto é sequencial, não precisa de lock
                    streamsSending[videoName] = {neighbourToSend}
                    
                    if videoName not in streamsSendingLocks:
                        streamsSendingLocks[videoName] = threading.Lock()

                    threading.Thread(target=sendVideo, args=(udpSocket,videoName,videoDelays[videoName])).start()
                else:
                    with streamsSendingLocks[videoName]:
                        streamsSending[videoName].add(neighbourToSend)
            else:
    
                errorMessage = requestProtocol("Server","Stream não existe.")
                udpSocket.sendto(pickle.dumps(errorMessage),clientAddr)


def sendNeighbours(udpSocket, nodeTree, ip):

    neighbours = nodeTree[ip][1] # nodeTree[nodeIp][1] -> neightbours de nodeIp 
    wayBackN = nodeTree[ip][3] # quantas conexões tcp aceitar (as que aceita são o caminho até ao servidor)
    isPP = nodeTree[ip][2]

    while True:

        neighbourList = requestProtocol("Server",(neighbours,wayBackN,isPP)) 
        udpSocket.sendto(pickle.dumps(neighbourList),(ip,UDP_PORT))

        try:
            respPacket, addr = nodeQueueUdp.get(True,1)
            if respPacket.getPayload() == "ACK" and addr[0] == ip:
                finalAck = requestProtocol("Server","ACK")
                udpSocket.sendto(pickle.dumps(finalAck),(ip,UDP_PORT))
                break

        except queue.Empty:
            pass
        
def registerNodes(udpSocket,nodeTree):
    
    nodesIps = list(nodeTree.keys())
    nodesIps.remove(SERVER_IP)

    for ip in nodesIps:
        sendNeighbours(udpSocket,nodeTree,ip)
        

def handleNeighbours(tcpHandler,neighbourAddr):
    global statusUpdates

    try:
        while True:
            packet = tcpHandler.receivePacket() 
            packetType = packet.getType()

            if packetType == "CONNECTED":

                connectedList = packet.getPayload()

                #print(f"\n{connectedList}\n")
                
                for elem in connectedList:
                    readyNodes.append(elem)

            elif packetType == "RTT Finish":
                
                prevTime =  metrics[(SERVER_IP,neighbourAddr)]
                metrics[(SERVER_IP,neighbourAddr)] = time.time() - prevTime
            
            elif packetType == "RTT Update":

                rttDict = packet.getPayload()
                metrics.update(rttDict)
                
                with statusLock:
                    statusUpdates += 1

                # limite de updates deve ser o número de links na rede que não estão ligados ao servidor, os que estão ligados nem fazem update, sendo o servidor a calcular

            elif packetType == "PING Response":

                (ppIp, rtt, clientIp) = packet.getPayload()
                print(packet.getPayload())
                clientPings[clientIp].append((ppIp,rtt))

            elif packetType == "STOP Client":
                
                videoName = packet.getPayload()

                with streamsSendingLocks[videoName]:
                    
                    sendingTo = streamsSending[videoName]
                    sendingTo.remove((neighbourAddr,UDP_PORT)) # se este recebe um STOP é porque está a enviar vídeo para quem enviou o pedido de STOP

                    if not sendingTo:
                        del streamsSending[videoName]

            else:
                print(f"Na thread responsável por {neighbourAddr} ----> {packet.getPayload()}") # se algum nodo overlay morrer de momento, os conectados também morrem
    
    finally:
        tcpHandler.close()


def networkTest(nodeTree): # pra já apenas RTT

    for addr, handler in tcpHandlers.items():
        startRTT = controlProtocol("RTT Start",(SERVER_IP,TCP_PORT),(addr,TCP_PORT))
        metrics[(SERVER_IP,addr)] = time.time()
        handler.sendPacket(startRTT)        

    while countEdges(nodeTree) - len(nodeTree[SERVER_IP][1]) != statusUpdates:
        time.sleep(0.5) # poupar CPU
     
    print("Métricas Obtidas!")
    for (src,dest), rtt in metrics.items():
        print(f"RTT de {rtt} segundos no link de {src} a {dest}.")

    weightedEdges = [(u, v, w) for (u, v), w in metrics.items()]
    networkxGraph.add_weighted_edges_from(weightedEdges,"quality")
    

def bestPathToPPs(nodeTree):
    for ip, (_,_,isPP,_) in nodeTree.items():
        if isPP:
            shortestPath = (networkx.shortest_path(networkxGraph,SERVER_IP,ip,"quality"), networkx.shortest_path_length(networkxGraph,SERVER_IP,ip,"quality"))
            bestPathsPP[ip] = shortestPath

    for addr, (path, weight) in bestPathsPP.items():
        print(f"Caminho mais curto para {addr} -> {path} com peso {weight}")

def calcBestPP(clientIp):

#    bestPathsPP = {} # ip -> (path,rtt)
#    clientPings = {} # client ip -> [(ppIp.rtt)]

    pathsToClientRtt = {} # ppIp -> total rtt

    for ppIp, (_,ppRtt) in bestPathsPP.items():

        clientPingTime = 10000
        for ip,rtt in clientPings[clientIp]:
            if ip == ppIp:
                clientPingTime = rtt
                break

        pathsToClientRtt[ppIp] = ppRtt + clientPingTime

    sortedDict = sorted(pathsToClientRtt.items(), key=lambda item: item[1])
    return sortedDict[0][0] # primeiro da lista, primeiro do tuplo
    

def main():
    try:
        nodeTree = loadOverlay() # ip -> (id, [neighbours], is_pp, wayBack)
        videoList = discoverSplitVideos()
        udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        udpSocket.bind((SERVER_IP, UDP_PORT))

        numPPs = len([isPP for (_,_,isPP,_) in nodeTree.values() if isPP == True])

        threading.Thread(target=receivePacketsUdp, args=(udpSocket,)).start()

        registerNodes(udpSocket,nodeTree)

        for ip in nodeTree[SERVER_IP][1]:
            s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            s.connect((ip,TCP_PORT))

            handler = TCPHandler(s,threading.Lock())
            handler.sendPacket(f"{SERVER_IP}")
            tcpHandlers[ip] = handler


        for addr, handler in tcpHandlers.items():
            threading.Thread(target=handleNeighbours, args=(handler,addr)).start()

        while True:
            if all(key in readyNodes for key in nodeTree.keys() if key != SERVER_IP):
                networkTest(nodeTree)

                bestPathToPPs(nodeTree)

                handleClients(udpSocket,videoList,numPPs)

                break
            time.sleep(0.5) # poupar CPU

    finally:
        if os.path.exists("mpegtsVideos"):
            shutil.rmtree("mpegtsVideos")

main()
