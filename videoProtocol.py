class videoProtocol:

    def __init__(self, srcAddr, videoName, seqNumber,payload):
        self.srcAddr = srcAddr
        self.videoName = videoName
        self.seqNumber = seqNumber
        self.payload = payload

    def getSrcAddr(self):
        return self.srcAddr

    def getVideoName(self):
        return self.videoName

    def getSeqNumber(self):
        return self.seqNumber

    def getPayload(self):
        return self.payload