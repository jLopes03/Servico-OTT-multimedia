import socket
import threading
import pickle
import json
import queue
import os

from RTPPacket import RTPPacket

UDP_PORT = 9090

clientsQueue = queue.Queue()

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
        # eventualmente algo para diferenciar de cliente para morte de node
        clientsQueue.put((loadedData, addr))


def handleClients(udpSocket,videoList):
    clientPacket, clientAddr = clientsQueue.get(True) # bloqueia até ter um pacote

    if clientPacket == "VL": #Video List
        udpSocket.sendto(pickle.dumps(videoList),clientAddr)    


def main():
    serverId, nodeTree = loadOverlay() # id -> (ip, [neighbours], is_pp)
    videoList = discoverVideos()
    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    udpSocket.bind((nodeTree[serverId][0], UDP_PORT))

    threading.Thread(target=receivePackets, args=(udpSocket,)).start()
    threading.Thread(target=handleClients,args=(udpSocket, videoList,)).start()

main()
