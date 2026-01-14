import socket

from shared.protocol import *


def listen_for_offer():
    """
     Listen for a game offer broadcast over UDP and return connection details.
    The client binds to the well-known UDP discovery port (UDP_PORT) and waits
    for a valid offer packet. Once a valid offer is received, it returns:
    (server_ip, tcp_port, server_name).
    """
    # UDP socket for discovery (server broadcasts offers here)
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Allow quick restart of the client without "Address already in use"
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Bind to all interfaces on the discovery port
    udp_sock.bind(("", UDP_PORT))

    print(f"Client started, listening for offer requests on UDP port {UDP_PORT}...")

    while True:
        # Wait for a UDP datagram (offer)
        data, addr = udp_sock.recvfrom(1024)
        server_ip = addr[0]

        # Validate/parse offer according to our protocol (magic cookie, type, fields, etc.)
        parsed = unpack_offer(data)
        if parsed is None:
            # Ignore malformed/irrelevant broadcasts
            continue

        tcp_port, server_name = parsed
        print(f"Received offer from {server_ip} (server='{server_name}', tcp_port={tcp_port})")

        # Discovery complete. we now switch to TCP for the actual game session
        udp_sock.close()
        return server_ip, tcp_port, server_name


def connect_and_send_request(server_ip, tcp_port, rounds, client_name):
    """
    Connect to the server over TCP, send a play request, and run the game loop.
    Flow:
    1) Connect TCP
    2) Send request (rounds + team name)
    3) For each round:
       - Receive initial deal (2 player cards + 1 dealer visible)
       - Let player Hit/Stand by sending client payloads
       - Receive server stream of dealer draws and final result
    """
    # TCP socket for reliable ordered gameplay messages
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    print(f"Connecting to {server_ip}:{tcp_port} ...")
    tcp_sock.connect((server_ip, tcp_port))

    # Send a single request message (server may accept with/without newline)
    tcp_sock.sendall(pack_request(rounds, client_name) + b"\n")

    # Track overall session stats across rounds
    wins = losses = ties = 0

    for r in range(1, rounds + 1):
        print(f"\n=== Round {r}/{rounds} ===")
        # Local state for this round (we compute totals client-side for UI)
        player_cards = []
        dealer_cards = []

        # Initial deal: server sends 3 payloads: player, player, dealer-visible
        for i in range(3):
            payload = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
            result, rank, suit = unpack_server_payload(payload)
            # During initial deal the round must not be "over" yet
            if result != RESULT_NOT_OVER:
                raise ValueError("unexpected result during initial deal")

            if i < 2:
                player_cards.append((rank, suit))
                total = sum(card_value(x[0]) for x in player_cards)
                print(f"You got: {card_to_str(rank, suit)} | total={total}")
            else:
                dealer_cards.append((rank, suit))
                print(f"Dealer shows: {card_to_str(rank, suit)}")

        # Player action phase: keep asking until Stand, Bust, or server ends round early
        while True:
            total = sum(card_value(x[0]) for x in player_cards)
            if total > 21:
                # Player bust: server will send final result next
                break

            choice = input("Hit or stand? (h/s): ").strip().lower()
            # Client payload indicates requested action
            if choice in ("h", "hit"):
                tcp_sock.sendall(pack_client_payload("Hittt"))
            elif choice in ("s", "stand"):
                tcp_sock.sendall(pack_client_payload("Stand"))
                break
            else:
                print("Type h/s")
                continue

            # After Hit: server replies with either a new card OR an immediate final result
            payload = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
            result, rank, suit = unpack_server_payload(payload)

            if result == RESULT_NOT_OVER:
                # Normal flow: player receives another card
                player_cards.append((rank, suit))
                total = sum(card_value(x[0]) for x in player_cards)
                print(f"You got: {card_to_str(rank, suit)} | total={total}")
                continue

            # Early termination: server decided the round is over (bust/resolution)
            if result == RESULT_WIN:
                wins += 1
                print("Result: YOU WIN 🎉")
            elif result == RESULT_LOSS:
                losses += 1
                print("Result: YOU LOSE 💀")
            else:
                ties += 1
                print("Result: TIE 🤝")
            break

        # Dealer phase: server streams dealer cards (including hidden reveal) until final result
        while True:
            payload = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
            result, rank, suit = unpack_server_payload(payload)

            if result == RESULT_NOT_OVER:
                # Dealer draws/reveals another card
                dealer_cards.append((rank, suit))
                d_total = sum(card_value(x[0]) for x in dealer_cards)
                print(f"Dealer: {card_to_str(rank, suit)} | dealer_total={d_total}")
                continue

            # Final outcome for the round
            if result == RESULT_WIN:
                wins += 1
                print("Result: YOU WIN 🎉")
            elif result == RESULT_LOSS:
                losses += 1
                print("Result: YOU LOSE 💀")
            else:
                ties += 1
                print("Result: TIE 🤝")
            break

    # Session summary
    total = wins + losses + ties
    win_rate = wins / total if total else 0.0
    print(f"\nFinished playing {total} rounds, win rate: {win_rate:.2%} (W={wins}, L={losses}, T={ties})")

    tcp_sock.close()


def recv_exact(sock, n):
    """
    Receive exactly n bytes from a TCP socket.
    TCP is a stream protocol (no message boundaries), so a single recv() may return
    fewer bytes than requested. This helper loops until n bytes are accumulated or
    the server disconnects.
    """
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            # Empty read means the peer closed the connection
            raise ConnectionError("server disconnected")
        data += chunk
    return data



if __name__ == "__main__":
    CLIENT_TEAM_NAME = "GOAT"

    # Validate rounds in protocol range: 1..255 (fits in a single byte if needed)
    while True:
        try:
            rounds = int(input("How many rounds do you want to play? "))
            if 1 <= rounds <= 255:
                break
            print("Please enter a number between 1 and 255.")
        except ValueError:
            print("Please enter a valid integer.")

    # Discovery over UDP, then gameplay over TCP
    server_ip, tcp_port, server_name = listen_for_offer()
    connect_and_send_request(server_ip, tcp_port, rounds, CLIENT_TEAM_NAME)