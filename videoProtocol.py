class videoProtocol:

    def __init__(self, srcAddr, destAddr, videoPath, seqNumber,payload):
        self.srcAddr = srcAddr
        self.destAddr = destAddr
        self.videoPath = videoPath
        self.seqNumber = seqNumber
        self.payload = payload

    def getSrcAddr(self):
        return self.srcAddr

    def getDestAddr(self):
        return self.destAddr

    def getVideoPath(self):
        return self.videoPath

    def getSeqNumber(self):
        return self.seqNumber

    def getPayload(self):
        return self.payload