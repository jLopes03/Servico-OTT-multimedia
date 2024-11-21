import socket
import threading
import pickle
import json
import queue
import os
import re
import ffmpeg
import subprocess
import shutil

from videoProtocol import videoProtocol
from requestProtocol import requestProtocol

UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

clientsQueue = queue.Queue()
nodeQueueUdp = queue.Queue()

sendingVideo = {} # (videoName, overlayNode it's being sent to) -> subprocess sending the video
splitVideos = {} # (videoName) -> frames of the video

def loadOverlay():
    nodeTree = {}
    with open("overlay.json", "r") as jsonFile:
        data = json.load(jsonFile)

    for node in data["nodes"]:
        nodeTree[node["ip"]] = (node["id"], node["neighbours"], node["pp"])

    return nodeTree

def discoverVideos():
    os.makedirs("mpgetsVideos")
    return os.listdir("Videos")

def splitVideo(videoName):
    if videoName in splitVideos.keys():
        return

    ffmpeg.input(f"Videos/{videoName}").output(f"mpegtsVideos/{videoName}.ts",f="mpegts",vcodec="libx264",acodec="aac",preset="superfast").run(stderr=open('logfile.txt', 'w'))
    # ffmpeg -i VideoA.mp4 -f mpegts -c:v libx264 -preset superfast -c:a aac output.ts

def receivePacketsUdp(udpSocket):
    while True:
        data, addr = udpSocket.recvfrom(1024) #??
        loadedData = pickle.loads(data)
        
        if loadedData.getOrigin() == "Client":
            clientsQueue.put((loadedData, addr))
        elif loadedData.getOrigin() == "Node":
            nodeQueueUdp.put((loadedData,addr))


def sendVideo(udpSocket, videoName):
    with open(f"mpegtsVideos/{videoName}.ts","rb") as tsVideo:
        
        fileSize = os.fstat(tsVideo).st_size

        while sendingVideo[videoName] and (videoChunk := tsVideo.read(188)): # enquanto a lista tem algum endereço
            
            videoChunk = tsVideo.read(188) # mpeg-ts uses 188 byte packets

            for addr in sendingVideo[videoName]:
                chunkPacket = videoProtocol((SERVER_IP,UDP_PORT),addr,[],0,videoChunk)
                udpSocket.sendto(pickle.dumps(chunkPacket),addr)

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

                    splitVideo(videoName)

                    sendingVideo[(f"{videoName}")] = [clientAddr]

                    ## 

                    nodeLocation = requestProtocol("Server",f"Recebi o pedido da stream {videoName}")
                    udpSocket.sendto(pickle.dumps(nodeLocation),clientAddr)
                else:
                    errorMessage = requestProtocol("Server","Stream doesn't exist.")
                    udpSocket.sendto(pickle.dumps(errorMessage),clientAddr)
    finally:
        shutil.rmtree("fragmentedVideos")

def registerNodes(udpSocket,nodeTree):
    while True:
        nodePacket, _ = nodeQueueUdp.get(True)

        if nodePacket.getPayload() == "Neighbours":   



            neighbourList = requestProtocol("Server",nodeTree[nodePacket.getSrcAddr()[0]][1]) #nodeTree[nodeIp][1] -> neightbours de nodeIp 
            udpSocket.sendto(pickle.dumps(neighbourList),nodePacket.getSrcAddr())

def main():
    nodeTree = loadOverlay() # ip -> (id, [neighbours], is_pp)
    videoList = discoverVideos()
    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    udpSocket.bind((SERVER_IP, UDP_PORT))

    #servidor tem conexão tcp com os nodos overlay ligados a ele, manda controlPacket pela rede overlay para obter métricas para os pontos de presença, os pontos de presença comunicam com o cliente e obtêm métricas que enviam para o servidor
    #o servidor junta as duas e escolhe o melhor ponto de presença para transmitir para o cliente

    threading.Thread(target=receivePacketsUdp, args=(udpSocket,)).start()
    threading.Thread(target=registerNodes, args=(udpSocket,nodeTree,)).start()
    handleClients(udpSocket,videoList)

main()
