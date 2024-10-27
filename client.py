import socket

UDP_PORT = 9090

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(b"Test", ("127.0.0.1", UDP_PORT))

if __name__ == "__main__":
    main()
