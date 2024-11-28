class videoProtocol:

    def __init__(self, srcAddr, destAddr, videoPaths, seqNumber,payload):
        self.srcAddr = srcAddr
        self.destAddr = destAddr
        self.videoPaths = videoPaths
        self.seqNumber = seqNumber
        self.payload = payload

    def getSrcAddr(self):
        return self.srcAddr

    def getDestAddr(self):
        return self.destAddr

    def getVideoPaths(self):
        return self.videoPaths

    def getSeqNumber(self):
        return self.seqNumber

    def getPayload(self):
        return self.payload

    def setVideoPaths(self,videoPaths):
        self.videoPaths = videoPaths