import socket
import threading
import pickle
import json


from RTPPacket import RTPPacket

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


def receivePackets(udpSocket):
    while True:
        data, addr = udpSocket.recvfrom(1024) #??

def main():
    udpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)

print(discoverOverlay())