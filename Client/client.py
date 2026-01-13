import socket

from shared.protocol import *


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


def connect_and_send_request(server_ip, tcp_port, rounds, client_name):
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.settimeout(10.0)

    print(f"Connecting to {server_ip}:{tcp_port} ...")
    tcp_sock.connect((server_ip, tcp_port))

    # Send request (אפשר גם להוסיף '\n' לפי הדוגמה, אבל השרת שלנו תומך בשני המצבים) :contentReference[oaicite:21]{index=21}
    tcp_sock.sendall(pack_request(rounds, client_name) + b"\n")

    wins = losses = ties = 0

    for r in range(1, rounds + 1):
        print(f"\n=== Round {r}/{rounds} ===")
        player_cards = []
        dealer_cards = []

        # Initial deal: player 2, dealer 1 visible :contentReference[oaicite:22]{index=22}
        for i in range(3):
            payload = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
            result, rank, suit = unpack_server_payload(payload)
            if result != RESULT_NOT_OVER:
                raise ValueError("unexpected result during initial deal")

            if i < 2:
                player_cards.append((rank, suit))
                total = sum(card_value(x[0]) for x in player_cards)
                print(f"You got: {card_to_str(rank, suit)} | total={total}")
            else:
                dealer_cards.append((rank, suit))
                print(f"Dealer shows: {card_to_str(rank, suit)}")

        # Player decisions
        while True:
            total = sum(card_value(x[0]) for x in player_cards)
            if total > 21:
                # next message should be final result
                break

            choice = input("Hit or stand? (h/s): ").strip().lower()
            if choice in ("h", "hit"):
                tcp_sock.sendall(pack_client_payload("Hittt"))
            elif choice in ("s", "stand"):
                tcp_sock.sendall(pack_client_payload("Stand"))
                break
            else:
                print("Type h/s")
                continue

            # After Hit: server sends a card OR final result
            payload = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
            result, rank, suit = unpack_server_payload(payload)

            if result == RESULT_NOT_OVER:
                player_cards.append((rank, suit))
                total = sum(card_value(x[0]) for x in player_cards)
                print(f"You got: {card_to_str(rank, suit)} | total={total}")
                continue

            # final result arrived early (e.g., bust flow)
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

        # Dealer phase: server reveals hidden + draws + final result :contentReference[oaicite:23]{index=23}
        while True:
            payload = recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
            result, rank, suit = unpack_server_payload(payload)

            if result == RESULT_NOT_OVER:
                dealer_cards.append((rank, suit))
                d_total = sum(card_value(x[0]) for x in dealer_cards)
                print(f"Dealer: {card_to_str(rank, suit)} | dealer_total={d_total}")
                continue

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

    total = wins + losses + ties
    win_rate = wins / total if total else 0.0
    print(f"\nFinished playing {total} rounds, win rate: {win_rate:.2%} (W={wins}, L={losses}, T={ties})")

    tcp_sock.close()


def recv_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("server disconnected")
        data += chunk
    return data



if __name__ == "__main__":
    CLIENT_TEAM_NAME = "GOAT"

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
