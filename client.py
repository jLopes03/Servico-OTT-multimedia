import socket
import pickle
import queue
import threading
import time
import subprocess

from videoProtocol import videoProtocol
from requestProtocol import requestProtocol

UDP_PORT = 9090
SERVER_IP = "10.0.0.10"

CHUNK_SIZE = 940

videoQueue = queue.Queue()
controlQueue = queue.Queue()

def receivePackets(udpSocket):
    while True:
        data, addr = udpSocket.recvfrom(1500) # MTU UDP
        loadedData = pickle.loads(data)
        if isinstance(loadedData,videoProtocol):
            videoQueue.put(loadedData)
        elif isinstance(loadedData,requestProtocol):
            controlQueue.put(loadedData)


def viewStream():
    
    ffplayProcess = subprocess.Popen(
        ["ffplay","-f","mpegts","-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # lidar com fechar isto graciosamente

    try:

        while (videoQueue.qsize() < 200): # 200 pacotes aprox -> 1000 segmentos de video de 188 bytes
            time.sleep(0.01)

        while True:

            videoPacket = videoQueue.get(True) # bloqueia
            videoChunk = videoPacket.getPayload()

            ffplayProcess.stdin.write(videoChunk)
            ffplayProcess.stdin.flush()

    finally:
        if ffplayProcess.stdin:
            try:
                ffplayProcess.stdin.close()
            except Exception as close_error:
                print(f"Error closing stdin: {close_error}")

        if ffplayProcess.poll() is None:  # Check if process is still running
            try:
                ffplayProcess.terminate()
            except Exception as terminate_error:
                print(f"Error terminating ffplay process: {terminate_error}")

        while not videoQueue.empty():              
            videoQueue.get()



def watchStreams(udpSocket):
    while True:
        videoName = input("\nWhat to watch?\n")
    
        receivedPP = False
        while not receivedPP:
            try:
                if (node := controlQueue.get(True,0.10)):

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
            if (videoList := controlQueue.get(True,0.10)): #aranjar um timeout
                print(videoList.getPayload())
                receivedVideoList = True
        except queue.Empty:
            listRequest = requestProtocol("Client","VL")
            udpSocket.sendto(pickle.dumps(listRequest),(SERVER_IP,UDP_PORT))
    
    #pode acontecer de receber ter a list novamente na queue porque o servidor recebeu pacotes mesmo depois de enviar a resposta que o cliente recebeu mais tarde, provavelmente será para ignorar com base em headers

    watchStreams(udpSocket)

main()