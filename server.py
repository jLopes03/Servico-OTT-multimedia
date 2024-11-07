import socket
import threading
import pickle
import json
import queue
import os
import re

from RTPPacket import RTPPacket

UDP_PORT = 9090

clientsQueue = queue.Queue()
nodeQueue = queue.Queue()


def loadOverlay():
    nodeTree = {}
    with open("overlay.json", "r") as jsonFile:
        data = json.load(jsonFile)

    for node in data["nodes"]:
        nodeTree[node["id"]] = (node["ip"], node["neighbours"], node["pp"])

    return data["server"], nodeTree

def discoverVideos():
    return os.listdir("Videos")

def receivePackets(udpSocket):
    while True:
        data, addr = udpSocket.recvfrom(1024) #??
        loadedData = pickle.loads(data)
        
        clientsQueue.put((loadedData, addr))


def handleClients(udpSocket,videoList):
    while True:
        clientPacket, clientAddr = clientsQueue.get(True) # bloqueia até ter um pacote

        if clientPacket == "VL": #Video List
            udpSocket.sendto(pickle.dumps(videoList),clientAddr)    
        elif (videoName := re.match(r"W : (.*)",clientPacket)):
            print(f"{clientAddr[0]} => {videoName.group(1)}") #grupo de captura, apagar depois
            if videoName.group(1) in videoList:
                udpSocket.sendto(pickle.dumps(f"Recebi o pedido da stream {videoName.group(1)}"),clientAddr) # apagar isto depois
                # transmitir video numa nova thread
            else:
                udpSocket.sendto(pickle.dumps(f"Stream doesn't exist."),clientAddr)

def main():
    serverId, nodeTree = loadOverlay() # id -> (ip, [neighbours], is_pp)
    videoList = discoverVideos()
    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    udpSocket.bind((nodeTree[serverId][0], UDP_PORT))

    #servidor tem conexão tcp com os nodos overlay ligados a ele, manda controlPacket pela rede overlay para obter métricas para os pontos de presença, os pontos de presença comunicam com o cliente e obtêm métricas que enviam para o servidor
    #o servidor junta as duas e escolhe o melhor ponto de presença para transmitir para o cliente

    threading.Thread(target=receivePackets, args=(udpSocket,)).start()
    handleClients(udpSocket,videoList)

main()
