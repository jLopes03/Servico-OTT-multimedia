import socket
import threading
import pickle
import json
import queue
import os
import re

from RTPProtocol import RTPProtocol
from requestProtocol import requestProtocol

UDP_PORT = 9090

clientsQueue = queue.Queue()
nodeQueueUdp = queue.Queue()

def loadOverlay():
    nodeTree = {}
    with open("overlay.json", "r") as jsonFile:
        data = json.load(jsonFile)

    for node in data["nodes"]:
        nodeTree[node["ip"]] = (node["id"], node["neighbours"], node["pp"])

    return data["server"], nodeTree

def discoverVideos():
    return os.listdir("Videos")

def receivePacketsUdp(udpSocket):
    while True:
        data, addr = udpSocket.recvfrom(1024) #??
        loadedData = pickle.loads(data)
        
        if loadedData.getOrigin() == "Client":
            clientsQueue.put((loadedData, addr))
        elif loadedData.getOrigin() == "Node":
            nodeQueueUdp.put((loadedData,addr))

def handleClients(udpSocket,videoList):
    while True:
        clientPacket, clientAddr = clientsQueue.get(True) # bloqueia até ter um pacote

        if clientPacket.getPayload() == "VL": #Video List
            listResponse = requestProtocol("Server",videoList)
            udpSocket.sendto(pickle.dumps(listResponse),clientAddr)
        
        elif (videoName := re.match(r"W : (.*)",clientPacket.getPayload())):

            if videoName.group(1) in videoList:
                # calcular rota e transmitir video numa nova thread
                nodeLocation = requestProtocol("Server",f"Recebi o pedido da stream {videoName.group(1)}")
                udpSocket.sendto(pickle.dumps(nodeLocation),clientAddr)
            else:
                errorMessage = requestProtocol("Server","Stream doesn't exist.")
                udpSocket.sendto(pickle.dumps(errorMessage),clientAddr)

def registerNodes(udpSocket,nodeTree):
    while True:
        nodePacket, nodeAddr = nodeQueueUdp.get(True)

        if nodePacket.getPayload() == "Neighbours":
            neighbourList = requestProtocol("Server",nodeTree[nodeAddr[0]][1])
            udpSocket.sendto(pickle.dumps(neighbourList),nodeAddr)

def main():
    serverId, nodeTree = loadOverlay() # ip -> (id, [neighbours], is_pp)
    videoList = discoverVideos()
    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    udpSocket.bind((nodeTree[serverId][0], UDP_PORT))

    #servidor tem conexão tcp com os nodos overlay ligados a ele, manda controlPacket pela rede overlay para obter métricas para os pontos de presença, os pontos de presença comunicam com o cliente e obtêm métricas que enviam para o servidor
    #o servidor junta as duas e escolhe o melhor ponto de presença para transmitir para o cliente

    threading.Thread(target=receivePacketsUdp, args=(udpSocket,)).start()
    threading.Thread(target=registerNodes, args=(udpSocket,nodeTree,)).start()
    handleClients(udpSocket,videoList)

main()
