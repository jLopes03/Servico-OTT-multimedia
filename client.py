import socket
import pickle
import queue
import threading

from RTPPacket import RTPPacket

UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

rtpQueue = queue.Queue()
controlQueue = queue.Queue()

def receivePackets(udpSocket):
    while True:
        data, addr = udpSocket.recvfrom(1024) #??
        loadedData = pickle.loads(data)
        if loadedData.isinstance(RTPPacket):
            rtpQueue.put(loadedData)
        else:
            controlQueue.put(loadedData)


def main():
    #clientIp = input("My IP?\n")
    udpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    threading.Thread(target=receivePackets, args=(udpSocket,)).start()

    # VL -> Video List || W : title -> Watch
    receivedVideoList = False
    udpSocket.sendto(pickle.dumps("VL"),(SERVER_IP,UDP_PORT))
    while not receivedVideoList:
        try:
            if (videoList := controlQueue.get(True,0.10)): #aranjar um timeout
                receivedVideoList = True
        except queue.Empty:
            udpSocket.sendto(pickle.dumps("VL"),(SERVER_IP,UDP_PORT))
    
    #pode acontecer de receber ter a list novamente na queue porque o servidor recebeu pacotes mesmo depois de enviar a resposta que o cliente recebeu mais tarde, provavelmente será para ignorar com base em headers

    print(videoList)

main()