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

#ex: O1 : ipO1, neighboursO1, isPP
def discoverOverlay():
    # Load the JSON file
    with open("overlay.json", "r") as jsonFile:
        parsedJson = json.load(jsonFile)

    # Extract data from JSON
    nodes = parsedJson["nodes"]
    neighbours = parsedJson["neighbours"]
    pPresence = parsedJson["pPresence"]

    # Create a dictionary of node names to IP addresses
    node_ips = {node_name: ip for node in nodes for node_name, ip in node.items()}

    # Dictionary to hold the structured information for each node
    nodeDict = {}

    # Populate nodeDict with a tuple (ip, [neighbours], isPP) for each node
    for node_name, ip in node_ips.items():
        # Get the neighbors and pPresence status for the node
        node_neighbours = neighbours.get(node_name, [])
        is_pp = node_name in pPresence

        # Store in nodeDict as a tuple (ip, [neighbours], is_pp)
        nodeDict[node_name] = (ip, node_neighbours, is_pp)

    return nodeDict

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
    nodeDict = discoverOverlay()
    videoList = discoverVideos()
    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    udpSocket.bind((nodeDict["O1"][0],UDP_PORT))

    #servidor tem conexão tcp com os nodos overlay ligados a ele, manda controlPacket pela rede overlay para obter métricas para os pontos de presença, os pontos de presença comunicam com o cliente e obtêm métricas que enviam para o servidor
    #o servidor junta as duas e escolhe o melhor ponto de presença para transmitir para o cliente

    threading.Thread(target=receivePackets, args=(udpSocket,)).start()
    handleClients(udpSocket,videoList)


main()
