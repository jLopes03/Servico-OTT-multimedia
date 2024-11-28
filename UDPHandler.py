import pickle
import queue

from requestProtocol import requestProtocol

class UDPHandler:

    def __init__(self,udpSocket,queue,timeout,maxRetries, lock):
        self.udpSocket = udpSocket
        self.queue = queue
        self.timeout = timeout # segundos
        self.maxRetries = maxRetries
        self.lock = lock

    def sendPacketWaitAck(self,packet,destAddr):
        retries = 0
        ackReceived = False

        pickledPacket = pickle.dumps(packet)

        while retries < self.maxRetries and not ackReceived:
            try:
                self.udpSocket.sendto(pickledPacket,destAddr)
                
                ackPacket, _ = self.queue.get(True,self.timeout)
                
                if ackPacket == b"ACK":
                    
                    ackRetries = 0
                    while ackRetries < self.maxRetries:

                        self.udpSocket.sendto(b"ACK2",destAddr)
                        ackRetries += 1
                
                    ackReceived = True

            except queue.Empty:
                retries += 1

        #if not ackReceived:
        #    raise Exception(f"Não recebi ACK depois de {self.maxRetries} tentativas")

        if not ackReceived:
            print("A prosseguir sem ACK")   

    def receivePacketSendAck(self):
        retries = 0
        packetReceived = False
        ackReceived = False

        
        while retries < self.maxRetries and not packetReceived:

            try:
                packet, addr = self.queue.get(True)
                loadedPacket = pickle.loads(packet)

                if loadedPacket.getPayload() != "ACK" and loadedPacket.getPayload() != "ACK2":
                    packetReceived = True

                ackRetries = 0
                while ackRetries < self.maxRetries and not ackReceived and packetReceived:
                    self.udpSocket.sendto(requestProtocol(),addr)
                    
                    try:
                        ackPacket, _ = self.queue.get(True,self.timeout)

                        if ackPacket.getPayload() == b"ACK2":
                            ackReceived = True

                    except queue.Empty:
                        ackRetries += 1

            except queue.Empty:
                retries += 1

        return loadedPacket