class requestProtocol:

    def __init__(self,origin,payload):
        self.origin = origin # client, server, node
        self.payload = payload

    def getOrigin(self):
        return self.origin

    def getPayload(self):
        return self.payload