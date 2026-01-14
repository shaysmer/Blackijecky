import random
import socket
import time
import threading

from shared.protocol import *

# UDP broadcast address used for discovery (clients listen on UDP_PORT)
BROADCAST_IP = "<broadcast>"
# How often the server advertises itself over UDP
OFFER_INTERVAL_SEC = 1.0


def start_offer_broadcast(server_name, tcp_port, stop_event):
    """
    Periodically broadcast a UDP "offer" so clients can discover the server.
    - Uses UDP broadcast to reach clients on the local network without knowing their IPs.
    - Re-sends the same packed offer every OFFER_INTERVAL_SEC until stop_event is set.
    """
    # UDP socket configured for broadcasting (discovery channel)
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    # Build the offer packet once (contains magic cookie/type + tcp_port + server_name)
    offer_packet = pack_offer(tcp_port, server_name)

    while not stop_event.is_set():
        try:
            # Broadcast the offer on the well-known UDP discovery port
            udp_sock.sendto(offer_packet, (BROADCAST_IP, UDP_PORT))
        except OSError as e:
            # Non-fatal: keep server alive even if a broadcast send fails temporarily
            print(f"[UDP] Broadcast error: {e}")
        time.sleep(OFFER_INTERVAL_SEC)

    udp_sock.close()


def recv_exact(conn, n):
    """
    Receive exactly n bytes from a TCP socket.
    TCP is a byte stream (no message boundaries), so recv() may return partial data.
    This helper loops until exactly n bytes are received or the peer disconnects.
    """
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            # Empty read - client closed the connection
            raise ConnectionError("client disconnected")
        data += chunk
    return data


def new_deck():
    """
   Create and shuffle a standard 52-card deck.
   Cards are represented as tuples: (rank, suit)
   - rank: 1..13
   - suit: 0..3
   """
    deck = [(rank, suit) for suit in range(4) for rank in range(1, 14)]
    random.shuffle(deck)
    return deck


def hand_sum(hand):
    """
    Compute the Blackjack score of a hand using protocol's card_value(rank).
    """
    return sum(card_value(rank) for rank, _ in hand)


def play_round(conn):
    """
    Run a single Blackjack round over an existing TCP connection.

    Protocol flow (server -> client):
    1) Initial deal: 2 player cards (RESULT_NOT_OVER) + 1 dealer visible (RESULT_NOT_OVER)
    2) Player loop:
       - Read action payload ("Hittt"/"Stand")
       - If Hit: send a new card (RESULT_NOT_OVER)
       - If player busts: send final result (RESULT_LOSS) and end the round
    3) Dealer loop:
       - Reveal hidden dealer card (RESULT_NOT_OVER)
       - Dealer hits until total >= 17
       - If dealer busts: send final result (RESULT_WIN) and end
    4) Otherwise compare totals and send final result (WIN/LOSS/TIE) with (0,0) card fields
    """
    # Server creates authoritative game state (deck + hands)
    deck = new_deck()

    # Deal initial hands (dealer[1] is hidden until dealer phase)
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]

    # Initial deal: send player 2 cards
    for r, s in player:
        conn.sendall(pack_server_payload(RESULT_NOT_OVER, r, s))

    # Send dealer's visible card only (hidden card is sent later)
    conn.sendall(pack_server_payload(RESULT_NOT_OVER, dealer[0][0], dealer[0][1]))

    # Player turn: wait for client actions and respond with cards / final result
    while True:
        if hand_sum(player) > 21:
            # player bust - dealer wins
            conn.sendall(pack_server_payload(RESULT_LOSS, 0, 0))
            return

        # Read fixed-size client action payload
        decision_bytes = recv_exact(conn, CLIENT_PAYLOAD_SIZE)
        decision = unpack_client_payload(decision_bytes)
        if decision is None:
            # Defensive: protocol violation / corrupted payload
            raise ValueError("invalid client payload")

        if decision == "Stand":
            # Player stops drawing, move to dealer phase
            break

        # Any non-Stand is treated as Hit (client uses "Hittt")
        card = deck.pop()
        player.append(card)

        # Send drawn card (round still in progress)
        conn.sendall(pack_server_payload(RESULT_NOT_OVER, card[0], card[1]))

    # Dealer turn: reveal hidden card first
    conn.sendall(pack_server_payload(RESULT_NOT_OVER, dealer[1][0], dealer[1][1]))

    # Dealer hits until >= 17
    while hand_sum(dealer) < 17:
        card = deck.pop()
        dealer.append(card)
        conn.sendall(pack_server_payload(RESULT_NOT_OVER, card[0], card[1]))
        # If dealer busts, player wins immediately
        if hand_sum(dealer) > 21:
            conn.sendall(pack_server_payload(RESULT_WIN, 0, 0))
            return

    # Compare totals and send final outcome
    p_total = hand_sum(player)
    d_total = hand_sum(dealer)

    if p_total > d_total:
        conn.sendall(pack_server_payload(RESULT_WIN, 0, 0))
    elif d_total > p_total:
        conn.sendall(pack_server_payload(RESULT_LOSS, 0, 0))
    else:
        conn.sendall(pack_server_payload(RESULT_TIE, 0, 0))


def handle_client(conn, addr):
    """
    Handle one TCP client session (possibly multiple rounds) in a dedicated thread.
    Responsibilities:
    - Read and validate the initial request (round count + client name).
    - Run play_round() exactly 'rounds' times on the same TCP connection.
    - Catch errors, log them, and close the connection safely.
    """
    try:
        print(f"[TCP] Connection from {addr}")

        # Read fixed-size request message
        req = recv_exact(conn, REQUEST_SIZE)
        parsed = unpack_request(req)
        if parsed is None:
            print(f"[TCP] Invalid request from {addr}, closing")
            return

        # Client may append newline; try to consume a single extra byte if present
        # (keeps compatibility with clients that send "request + \\n")
        try:
            conn.settimeout(0.05)
            _ = conn.recv(1)
        except Exception:
            pass
        finally:
            # After handshake, remove timeout to let gameplay proceed normally
            conn.settimeout(None)

        rounds, client_name = parsed
        print(f"[TCP] Client '{client_name}' from {addr} requested {rounds} rounds")

        # Play requested number of rounds sequentially on the same connection
        for i in range(rounds):
            print(f"[GAME] {client_name} ({addr}) Round {i + 1}/{rounds}")
            play_round(conn)

        print(f"[TCP] Finished client '{client_name}' from {addr}")

    except Exception as e:
        # Any protocol/network/game error ends the session for this client
        print(f"[TCP] Error with {addr}: {e}")
    finally:
        # Always close connection to release OS resources
        try:
            conn.close()
        except Exception:
            pass


def run_tcp_server(server_name):
    """
    Start the TCP game server and a parallel UDP broadcaster for discovery.
    - Binds TCP to port 0 so the OS picks a free ephemeral port.
    - Prints IP/port for debugging, but clients discover port via UDP offer.
    - Accepts clients in a loop; each client is handled in a separate thread.
    - Stops broadcasting and closes the TCP socket on shutdown.
    """
    # TCP listening socket (gameplay channel)
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Port 0 => let OS select an available port automatically
    tcp_sock.bind(("", 0))
    tcp_sock.listen()

    # Best-effort local IP for display. discovery does not rely on this print
    ip = socket.gethostbyname(socket.gethostname())
    tcp_port = tcp_sock.getsockname()[1]

    print(f"Server started, listening on IP address {ip}, TCP port {tcp_port}")
    print(f"Broadcasting offers on UDP port {UDP_PORT}...")

    # Start UDP broadcaster in background (daemon thread exits with main process)
    stop_event = threading.Event()
    offer_thread = threading.Thread(
        target=start_offer_broadcast,
        args=(server_name, tcp_port, stop_event),
        daemon=True
    )
    offer_thread.start()

    try:
        # Accept clients forever; each client handled concurrently in its own thread
        while True:
            conn, addr = tcp_sock.accept()

            t = threading.Thread(
                target=handle_client,
                args=(conn, addr),
                daemon=True
            )
            t.start()

    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        # Signal broadcaster to stop and close server socket
        stop_event.set()
        tcp_sock.close()


if __name__ == "__main__":
    TEAM_NAME = "GOAT"
    run_tcp_server(TEAM_NAME)