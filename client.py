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

CHUNK_SIZE = 940

videoQueue = queue.Queue()
serverQueue = queue.Queue()
popQueue = queue.Queue()

currPP = ""

def receivePackets(udpSocket):
    while True:
        data, addr = udpSocket.recvfrom(1500) # MTU UDP
        loadedData = pickle.loads(data)
        
        if isinstance(loadedData,videoProtocol) and addr[0] == currPP:
                #print(f"Recebi de {currPP}")
                videoQueue.put(loadedData)
        elif isinstance(loadedData,requestProtocol) and loadedData.getOrigin() == "Server":
            serverQueue.put(loadedData)
        elif  isinstance(loadedData,requestProtocol) and loadedData.getOrigin() == "Node":
             popQueue.put(loadedData)


def answerPings(udpSocket):
    while True:
        pingReq = popQueue.get(True)
        pingResp = requestProtocol("Client","PING")
        udpSocket.sendto(pickle.dumps(pingResp),pingReq.getSrcAddr())

def viewStream():
    # lidar com fechar isto graciosamente

    try:

        ffplayProcess = subprocess.Popen(
            ["ffplay","-f","mpegts","-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        while (videoQueue.qsize() < 100): # 100 pacotes aprox -> 500 segmentos de video de 188 bytes
            time.sleep(0.1)

        while True:
            videoPacket = videoQueue.get(True) # bloqueia
            videoChunk = videoPacket.getPayload()

            ffplayProcess.stdin.write(videoChunk)
            ffplayProcess.stdin.flush()

    except KeyboardInterrupt:

        print("\nA terminar a stream...")

    finally:
        if ffplayProcess.stdin:
            try:
                ffplayProcess.stdin.close()
            except Exception as closeError:
                print(f"Error closing stdin: {closeError}")

        if ffplayProcess.poll() is None:  # Check if process is still running
            try:
                ffplayProcess.terminate()
            except Exception as terminateError:
                print(f"Error terminating ffplay process: {terminateError}")


def watchStreams(udpSocket):
    global currPP

    while True:
        videoName = input("\nVer o quê?\n")
    
        receivedPP = False
        while not receivedPP:
            try:
                if (node := serverQueue.get(True,10)): # timeout devido a atrasos impostos na rede sem perdas (algo a melhorar)
                
                    currPP = node.getPayload()
                    print(f"Resposta do Servidor: {currPP}")

                    if not re.match(r"\d+.\d.+\d+.\d+",currPP):
                        print("IP inválido")
                        break
                    
                    viewStream()

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
            if (videoList := serverQueue.get(True,10)): # timeout devido a atrasos impostos na rede sem perdas (algo a melhorar)
                print(videoList.getPayload())
                receivedVideoList = True
        except queue.Empty:
            listRequest = requestProtocol("Client","VL")
            udpSocket.sendto(pickle.dumps(listRequest),(SERVER_IP,UDP_PORT))

    addr = udpSocket.getsockname()
    print(f"{addr}")

    threading.Thread(target=answerPings, args=(udpSocket,)).start()
    watchStreams(udpSocket)

main()