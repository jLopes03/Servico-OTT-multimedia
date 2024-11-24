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
import struct
from collections import deque

from videoProtocol import videoProtocol
from requestProtocol import requestProtocol

TCP_PORT = 9595
UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

CHUNK_SIZE = 940 # 188 * 5, MTU UDP -> 1500

clientsQueue = queue.Queue()
nodeQueueUdp = queue.Queue()

tcpSockets = {}

tcpSocketLock = threading.Lock()

readyNodes = deque()

sendingVideo = {} 

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
        

def handleNeighbours(tcpSocket,neighbourAddr):

    try:
        while True:
            lenData = b''
            while len(lenData) < 4:
                lenData += tcpSocket.recv(4 - len(lenData))
            length = struct.unpack("!I",lenData)[0]

            #print(f"Reading {length}")
            
            data = b''
            while len(data) < length:
                data += tcpSocket.recv(length - len(data))
            loadedPacket = pickle.loads(data)
            
            if loadedPacket.getType() == "CONNECTED":

                connectedList = loadedPacket.getPayload()

                #print(f"\n{connectedList}\n")
                
                for elem in connectedList:
                    readyNodes.append(elem)

            else:
                print(f"Na thread responsável por {neighbourAddr} ----> {loadedPacket.getPayload()}") # se algum nodo overlay morrer de momento, os conectados também morrem
    
    finally:
        tcpSocket.close()

def main():
    try:
        nodeTree = loadOverlay() # ip -> (id, [neighbours], is_pp, wayBack)
        videoList = discoverSplitVideos()
        udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        udpSocket.bind((SERVER_IP, UDP_PORT))

        threading.Thread(target=receivePacketsUdp, args=(udpSocket,)).start()

        registerNodes(udpSocket,nodeTree)

        for ip in nodeTree[SERVER_IP][1]:
            tcpSockets[ip] = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            tcpSockets[ip].connect((ip,TCP_PORT))

            tcpSockets[ip].send(pickle.dumps(f"{SERVER_IP}"))

        for addr, sock in tcpSockets.items():
            threading.Thread(target=handleNeighbours, args=(sock,addr)).start()

        while True:
            if all(key in readyNodes for key in nodeTree.keys() if key != SERVER_IP):
                print(f"Rede pronta! ---> {readyNodes}")
                handleClients(udpSocket,videoList)
                break
            time.sleep(0.5) # poupar CPU

    finally:
        if os.path.exists("mpegtsVideos"):
            shutil.rmtree("mpegtsVideos")

main()
