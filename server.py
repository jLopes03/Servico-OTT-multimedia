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
bestPathsPP = {}

statusUpdates = 0
statusLock = threading.Lock()

readyNodes = deque()

sendingVideo = {} 

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

def discoverSplitVideos():
    os.makedirs("mpegtsVideos")

    for videoName in os.listdir("Videos"):
        threading.Thread(target=convertToMpegts,args=(videoName,)).start()

    return os.listdir("Videos")
   
def receivePacketsUdp(udpSocket):
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


def sendVideo(udpSocket, videoName, clientAddr, delay):

    with open(f"mpegtsVideos/{videoName}.ts","rb") as tsFile:
        
        while True:
            startTime = time.time()

            if not (videoChunk := tsFile.read(CHUNK_SIZE)):
                break

            videoPacket = videoProtocol((SERVER_IP,UDP_PORT),clientAddr,[],0,videoChunk)
            udpSocket.sendto(pickle.dumps(videoPacket),clientAddr)

            elapsedTime = time.time() - startTime
            time.sleep(max(0,delay - elapsedTime))


def handleClients(udpSocket,videoList):
    while True:
    
        clientPacket, clientAddr = clientsQueue.get(True) # bloqueia até ter um pacote
    
        if clientPacket.getPayload() == "VL": #Video List
    
            listResponse = requestProtocol("Server",videoList)
            udpSocket.sendto(pickle.dumps(listResponse),clientAddr)
    
        elif (match := re.match(r"W : (.*)",clientPacket.getPayload())):
    
            videoName = match.group(1)
    
            if videoName in videoList:
  
                # calcular rota e transmitir video numa nova thread
                # clientAddr -> [videoName] (uma thread por node a quem está a enviar)
                # provavelmente será necessário uma lista de rotas para alem do nome do video caso o nodo à frente tenha de fazer multicast, fica pesado na rede
                # pensar tambem em mandar o caminho ao ponto de presença e ter o ponto de presença a fazer backtrack por esse caminho
    
                delay = calculateDelay(videoName)
                nodeLocation = requestProtocol("Server",f"{delay}")
                udpSocket.sendto(pickle.dumps(nodeLocation),clientAddr)
                threading.Thread(target=sendVideo, args=(udpSocket,videoName,clientAddr,delay,)).start()
    
            else:
    
                errorMessage = requestProtocol("Server","Stream doesn't exist.")
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
            shortestPath = networkx.shortest_path(networkxGraph,SERVER_IP,ip,"quality")
            bestPathsPP[ip] = shortestPath

    for addr, path in bestPathsPP.items():
        print(f"Caminho mais curto para {addr} -> {path}")

def main():
    try:
        nodeTree = loadOverlay() # ip -> (id, [neighbours], is_pp, wayBack)
        videoList = discoverSplitVideos()
        udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        udpSocket.bind((SERVER_IP, UDP_PORT))

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

                handleClients(udpSocket,videoList)

                break
            time.sleep(0.5) # poupar CPU

    finally:
        if os.path.exists("mpegtsVideos"):
            shutil.rmtree("mpegtsVideos")

main()
