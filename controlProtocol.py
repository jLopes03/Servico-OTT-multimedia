class controlProtocol:
    
    def __init__(self, type,srcAddr, destAddr, payload):
        self.type = type
        self.srcAddr = srcAddr
        self.destAddr = destAddr
        self.payload = payload

    def getType(self):
        return self.type
    
    def getSrcAddr(self):
        return self.srcAddr

    def getDestAddr(self):
        return self.destAddr
    
    def getPayload(self):
        return self.payload