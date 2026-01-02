import socket

from shared.protocol import UDP_PORT, unpack_offer, pack_request, REQUEST_SIZE


def listen_for_offer():
    """
    Listen on UDP port 13122 for offer messages.
    Returns (server_ip, tcp_port, server_name) for the first valid offer.
    """
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_sock.bind(("", UDP_PORT))

    print(f"Client started, listening for offer requests on UDP port {UDP_PORT}...")

    while True:
        data, addr = udp_sock.recvfrom(1024)
        server_ip = addr[0]

        parsed = unpack_offer(data)
        if parsed is None:
            continue

        tcp_port, server_name = parsed
        print(f"Received offer from {server_ip} (server='{server_name}', tcp_port={tcp_port})")
        udp_sock.close()
        return server_ip, tcp_port, server_name


def connect_and_send_request(server_ip: str, tcp_port: int, rounds: int, client_name: str):
    """
    Connect over TCP, send request packet, then read ACK.
    """
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.settimeout(5.0)

    print(f"Connecting to {server_ip}:{tcp_port} ...")
    tcp_sock.connect((server_ip, tcp_port))

    req = pack_request(rounds, client_name)
    tcp_sock.sendall(req)

    # Server currently replies with b"ACK\n"
    ack = tcp_sock.recv(1024)
    print(f"Server replied: {ack!r}")

    tcp_sock.close()


if __name__ == "__main__":
    # TODO: set your real team name here (max 32 chars)
    CLIENT_TEAM_NAME = "ClientTeamShay"

    # Ask user for rounds
    while True:
        try:
            rounds = int(input("How many rounds do you want to play? "))
            if 1 <= rounds <= 255:
                break
            print("Please enter a number between 1 and 255.")
        except ValueError:
            print("Please enter a valid integer.")

    server_ip, tcp_port, server_name = listen_for_offer()
    connect_and_send_request(server_ip, tcp_port, rounds, CLIENT_TEAM_NAME)
