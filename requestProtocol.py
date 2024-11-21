class requestProtocol:

    def __init__(self,origin,payload,srcAddr = ""):
        self.origin = origin # client, server, node
        self.srcAddr = srcAddr
        self.payload = payload

    def getOrigin(self):
        return self.origin

    def getSrcAddr(self):
        return self.srcAddr

    def getPayload(self):
        return self.payload