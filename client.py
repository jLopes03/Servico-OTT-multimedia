import socket
import pickle
import queue
import threading
import time
import subprocess
import re

from videoProtocol import videoProtocol
from requestProtocol import requestProtocol

UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

videoQueue = queue.Queue()
serverQueue = queue.Queue()
popQueue = queue.Queue()

vieingStream = False

currPP = ""

def receivePackets(udpSocket):
    while True:
        data, addr = udpSocket.recvfrom(1500) # MTU UDP
        loadedData = pickle.loads(data)
        
        if isinstance(loadedData,videoProtocol) and addr[0] == currPP and viewingStream:
                #print(f"Recebi de {currPP}")
                videoQueue.put(loadedData)
        elif isinstance(loadedData,requestProtocol) and loadedData.getOrigin() == "Server":
            serverQueue.put(loadedData)
        elif  isinstance(loadedData,requestProtocol) and loadedData.getOrigin() == "Node":
            popQueue.put(loadedData)


def answerPings(udpSocket):
    while True:
        pingReq = popQueue.get(True)
        pingResp = requestProtocol("ClientResp","PING")
        udpSocket.sendto(pickle.dumps(pingResp),pingReq.getSrcAddr())

def viewStream(udpSocket):
    global currPP, viewingStream

    # lidar com fechar isto graciosamente
    try:

        ffplayProcess = subprocess.Popen(
            ["ffplay","-f","mpegts","-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        while (videoQueue.qsize() < 200): # 200 pacotes aprox -> 1000 segmentos de video de 188 bytes
            time.sleep(0.1)

        while ffplayProcess.poll() == None:
            videoPacket = videoQueue.get(True) # bloqueia
            videoChunk = videoPacket.getPayload()

            try:

                ffplayProcess.stdin.write(videoChunk)
                ffplayProcess.stdin.flush()

            except BrokenPipeError:
                pass

    except KeyboardInterrupt:

        viewingStream = False
        print("\nA terminar a stream...")
        ffplayProcess.kill()

    finally:

        udpSocket.sendto(pickle.dumps(requestProtocol("ClientReq","STOP")),(currPP,UDP_PORT))
        currPP = ""

        while videoQueue.qsize() > 0:
            videoQueue.get_nowait()
    


def watchStreams(udpSocket):
    global currPP, viewingStream

    while True:
        videoName = input("\nVer o quê?\n")

        viewingStream = True

        watchRequest = requestProtocol("Client",f"W : {videoName}")
        udpSocket.sendto(pickle.dumps(watchRequest),(SERVER_IP,UDP_PORT))

        receivedPP = False
        while not receivedPP:
            try:
                if (node := serverQueue.get(True,10)): # timeout devido a atrasos impostos na rede sem perdas (algo a melhorar)
                
                    currPP = node.getPayload()
                    print(f"Resposta do Servidor: {currPP}")

                    if not re.match(r"\d+.\d.+\d+.\d+",currPP):
                        print("IP inválido")
                        break
                    
                    viewStream(udpSocket)

                    receivedPP = True
            except queue.Empty:
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
            if (videoList := serverQueue.get(True,10)): # timeout devido a atrasos impostos na rede sem perdas (algo a melhorar)
                print(videoList.getPayload())
                receivedVideoList = True
        except queue.Empty:
            listRequest = requestProtocol("Client","VL")
            udpSocket.sendto(pickle.dumps(listRequest),(SERVER_IP,UDP_PORT))

    threading.Thread(target=answerPings, args=(udpSocket,)).start()
    watchStreams(udpSocket)

main()