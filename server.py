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

from videoProtocol import videoProtocol
from requestProtocol import requestProtocol

UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

CHUNK_SIZE = 940 # 188 * 5, MTU UDP -> 1500

clientsQueue = queue.Queue()
nodeQueueUdp = queue.Queue()

sendingVideo = {} 

def loadOverlay():
    nodeTree = {}
    with open("overlay.json", "r") as jsonFile:
        data = json.load(jsonFile)

    for node in data["nodes"]:
        nodeTree[node["ip"]] = (node["id"], node["neighbours"], node["pp"])

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
    try:
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
    finally:
        shutil.rmtree("mpegtsVideos")

def registerNodes(udpSocket,nodeTree):
    while True:
        nodePacket, _ = nodeQueueUdp.get(True)

        if nodePacket.getPayload() == "Neighbours":

            neighbourList = requestProtocol("Server",nodeTree[nodePacket.getSrcAddr()[0]][1]) #nodeTree[nodeIp][1] -> neightbours de nodeIp 
            udpSocket.sendto(pickle.dumps(neighbourList),nodePacket.getSrcAddr())

def main():
    nodeTree = loadOverlay() # ip -> (id, [neighbours], is_pp)
    videoList = discoverSplitVideos()
    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    udpSocket.bind((SERVER_IP, UDP_PORT))

    #servidor tem conexão tcp com os nodos overlay ligados a ele, manda controlPacket pela rede overlay para obter métricas para os pontos de presença, os pontos de presença comunicam com o cliente e obtêm métricas que enviam para o servidor
    #o servidor junta as duas e escolhe o melhor ponto de presença para transmitir para o cliente

    threading.Thread(target=receivePacketsUdp, args=(udpSocket,)).start()
    threading.Thread(target=registerNodes, args=(udpSocket,nodeTree,)).start()
    handleClients(udpSocket,videoList)

main()
