import socket

UDP_PORT = 9090

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('', UDP_PORT))

    while True:
        data, addr = s.recvfrom(1024)
        print(f"Received {data} from {addr}")
        

if __name__ == "__main__":
    main()
