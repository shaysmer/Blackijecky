import random
import socket
import time
import threading

from shared.protocol import *




BROADCAST_IP = "<broadcast>"
OFFER_INTERVAL_SEC = 1.0


def start_offer_broadcast(server_name, tcp_port, stop_event):
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


def recv_exact(conn, n):
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("client disconnected")
        data += chunk
    return data


def new_deck():
    deck = [(rank, suit) for suit in range(4) for rank in range(1, 14)]
    random.shuffle(deck)
    return deck


def hand_sum(hand):
    return sum(card_value(rank) for rank, _ in hand)


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

            # Read request (some teams send '\n' after request per example :contentReference[oaicite:18]{index=18})
            req = recv_exact(conn, REQUEST_SIZE)
            parsed = unpack_request(req)
            if parsed is None:
                print("[TCP] Invalid request, closing")
                conn.close()
                continue

            # Optional newline: אם מגיע ב-recv הבא, זה בסדר להתעלם
            conn.settimeout(0.05)
            try:
                extra = conn.recv(1)
            except Exception:
                pass
            conn.settimeout(None)

            rounds, client_name = parsed
            print(f"[TCP] Client '{client_name}' requested {rounds} rounds")

            for i in range(rounds):
                print(f"[GAME] Round {i + 1}/{rounds}")
                play_round(conn)

            conn.close()


    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        stop_event.set()
        tcp_sock.close()

def play_round(conn: socket.socket):
    deck = new_deck()

    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]  # dealer[1] hidden until dealer turn :contentReference[oaicite:13]{index=13}

    # Initial deal: send player 2 + dealer 1 visible :contentReference[oaicite:14]{index=14}
    for r, s in player:
        conn.sendall(pack_server_payload(RESULT_NOT_OVER, r, s))
    conn.sendall(pack_server_payload(RESULT_NOT_OVER, dealer[0][0], dealer[0][1]))

    # Player turn
    while True:
        if hand_sum(player) > 21:
            # player bust => dealer wins :contentReference[oaicite:15]{index=15}
            conn.sendall(pack_server_payload(RESULT_LOSS, 0, 0))
            return

        decision_bytes = recv_exact(conn, CLIENT_PAYLOAD_SIZE)
        decision = unpack_client_payload(decision_bytes)
        if decision is None:
            raise ValueError("invalid client payload")

        if decision == "Stand":
            break

        # Hittt
        card = deck.pop()
        player.append(card)
        conn.sendall(pack_server_payload(RESULT_NOT_OVER, card[0], card[1]))

    # Dealer turn: reveal hidden, then hit until total >=17 or bust :contentReference[oaicite:16]{index=16}
    conn.sendall(pack_server_payload(RESULT_NOT_OVER, dealer[1][0], dealer[1][1]))

    while hand_sum(dealer) < 17:
        card = deck.pop()
        dealer.append(card)
        conn.sendall(pack_server_payload(RESULT_NOT_OVER, card[0], card[1]))
        if hand_sum(dealer) > 21:
            conn.sendall(pack_server_payload(RESULT_WIN, 0, 0))
            return

    # Decide winner :contentReference[oaicite:17]{index=17}
    p_total = hand_sum(player)
    d_total = hand_sum(dealer)

    if p_total > d_total:
        conn.sendall(pack_server_payload(RESULT_WIN, 0, 0))
    elif d_total > p_total:
        conn.sendall(pack_server_payload(RESULT_LOSS, 0, 0))
    else:
        conn.sendall(pack_server_payload(RESULT_TIE, 0, 0))




if __name__ == "__main__":
    TEAM_NAME = "GOAT"
    run_tcp_server(TEAM_NAME)
