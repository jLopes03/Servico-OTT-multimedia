import socket
import pickle
import queue
import threading

from RTPProtocol import RTPProtocol
from requestProtocol import requestProtocol

UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

rtpQueue = queue.Queue()
controlQueue = queue.Queue()

def receivePackets(udpSocket):
    while True:
        data, addr = udpSocket.recvfrom(1024) #??
        loadedData = pickle.loads(data)
        if isinstance(loadedData,RTPProtocol):
            rtpQueue.put(loadedData)
        elif isinstance(loadedData,requestProtocol):
            controlQueue.put(loadedData)


def watchStream(udpSocket):
    while True:
        videoName = input("What to watch?\n")
    
        receivedPP = False
        while not receivedPP:
            try:
                if (node := controlQueue.get(True,0.10)):
                    #ver transmissão
                    print(node)
                    receivedPP = True
            except queue.Empty:
                watchRequest = requestProtocol("Client",f"W : {videoName}")
                udpSocket.sendto(pickle.dumps(watchRequest),(SERVER_IP,UDP_PORT)) 

def main():
    #clientIp = input("My IP?\n")
    udpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    threading.Thread(target=receivePackets, args=(udpSocket,)).start()

    # VL -> Video List || W : title -> Watch
    receivedVideoList = False
    
    listRequest = requestProtocol("Client","VL")
    udpSocket.sendto(pickle.dumps(listRequest),(SERVER_IP,UDP_PORT))
    while not receivedVideoList:
        try:
            if (videoList := controlQueue.get(True,0.10)): #aranjar um timeout
                print(videoList.getPayload())
                receivedVideoList = True
        except queue.Empty:
            listRequest = requestProtocol("Client","VL")
            udpSocket.sendto(pickle.dumps(listRequest),(SERVER_IP,UDP_PORT))
    
    #pode acontecer de receber ter a list novamente na queue porque o servidor recebeu pacotes mesmo depois de enviar a resposta que o cliente recebeu mais tarde, provavelmente será para ignorar com base em headers

    watchStream(udpSocket)

main()