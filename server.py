import socket
import threading
import pickle
import json
import queue
import os

from RTPPacket import RTPPacket

UDP_PORT = 9090

clientsQueue = queue.Queue()
#nodeQueue?

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
        # eventualmente algo para diferenciar de cliente para morte de node
        clientsQueue.put((loadedData, addr))


def handleClients(udpSocket,videoList):
    clientPacket, clientAddr = clientsQueue.get(True) # bloqueia até ter um pacote

    if clientPacket == "VL": #Video List
        udpSocket.sendto(pickle.dumps(videoList),clientAddr)    


def main():
    nodeDict = discoverOverlay()
    videoList = discoverVideos()
    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    udpSocket.bind((nodeDict["O1"][0],UDP_PORT))

    threading.Thread(target=receivePackets, args=(udpSocket,)).start()
    threading.Thread(target=handleClients,args=(udpSocket,videoList,)).start()


main()
