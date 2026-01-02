import socket
import time
import threading

from shared.protocol import pack_offer, UDP_PORT


BROADCAST_IP = "<broadcast>"
OFFER_INTERVAL_SEC = 1.0


def start_offer_broadcast(server_name: str, tcp_port: int, stop_event: threading.Event):
    """
    Sends UDP broadcast offer messages once every second.
    """
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    offer_packet = pack_offer(tcp_port, server_name)

    while not stop_event.is_set():
        try:
            udp_sock.sendto(offer_packet, (BROADCAST_IP, UDP_PORT))
        except OSError as e:
            print(f"[UDP] Broadcast error: {e}")
        time.sleep(OFFER_INTERVAL_SEC)

    udp_sock.close()


def run_tcp_server(server_name: str):
    """
    Opens a TCP server on an OS-chosen port, prints it, and accepts connections.
    For now: reads a request packet and prints it.
    """
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_sock.bind(("", 0))  # port 0 => OS chooses a free port
    tcp_sock.listen()

    ip = socket.gethostbyname(socket.gethostname())
    tcp_port = tcp_sock.getsockname()[1]

    print(f"Server started, listening on IP address {ip}, TCP port {tcp_port}")
    print(f"Broadcasting offers on UDP port {UDP_PORT}...")

    stop_event = threading.Event()
    offer_thread = threading.Thread(
        target=start_offer_broadcast,
        args=(server_name, tcp_port, stop_event),
        daemon=True
    )
    offer_thread.start()

    try:
        while True:
            conn, addr = tcp_sock.accept()
            print(f"[TCP] Connection from {addr}")

            # For now: just read and print raw bytes length
            data = conn.recv(1024)
            print(f"[TCP] Received {len(data)} bytes")

            conn.sendall(b"ACK\n")
            conn.close()

    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        stop_event.set()
        tcp_sock.close()


if __name__ == "__main__":
    # TODO: put your real team name here (max 32 chars)
    TEAM_NAME = "TeamShay"
    run_tcp_server(TEAM_NAME)
