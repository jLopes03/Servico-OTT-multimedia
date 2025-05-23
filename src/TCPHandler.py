import socket
import pickle
import struct

class TCPHandler:

    def __init__(self,tcpSocket,socketLock):
        self.socket = tcpSocket
        self.lock = socketLock

    def sendPacket(self,packet):
        pickledPacket = pickle.dumps(packet)

        size = len(pickledPacket)
        packedSize = struct.pack("!I",size)
            
        with self.lock:
            self.socket.sendall(packedSize)
            self.socket.sendall(pickledPacket)

    def receivePacket(self):
        lenData = b''
        while len(lenData) < 4:
            lenData += self.socket.recv(4 - len(lenData))
        length = struct.unpack("!I",lenData)[0]
        
        data = b''
        while len(data) < length:
            data += self.socket.recv(length - len(data))
        loadedPacket = pickle.loads(data)
        return loadedPacket
    
    def close(self):
        self.socket.close()