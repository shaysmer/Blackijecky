import struct

# ===== Constants =====
MAGIC_COOKIE = 0xabcddcba

OFFER_TYPE = 0x2
REQUEST_TYPE = 0x3
PAYLOAD_TYPE = 0x4

UDP_PORT = 13122
NAME_LEN = 32


# ===== Offer Message =====
# | magic (4) | msg_type (1) | tcp_port (2) | server_name (32) |
OFFER_FORMAT = "!IBH32s"
OFFER_SIZE = struct.calcsize(OFFER_FORMAT)


def pack_offer(tcp_port, server_name):
    name_bytes = server_name.encode("utf-8")[:NAME_LEN]
    name_bytes = name_bytes.ljust(NAME_LEN, b"\x00")

    return struct.pack(
        OFFER_FORMAT,
        MAGIC_COOKIE,
        OFFER_TYPE,
        tcp_port,
        name_bytes
    )


def unpack_offer(data):
    if len(data) < OFFER_SIZE:
        return None

    magic, msg_type, tcp_port, name_bytes = struct.unpack(
        OFFER_FORMAT, data[:OFFER_SIZE]
    )

    if magic != MAGIC_COOKIE or msg_type != OFFER_TYPE:
        return None

    server_name = name_bytes.rstrip(b"\x00").decode("utf-8")
    return tcp_port, server_name


# ===== Request Message =====
# | magic (4) | msg_type (1) | rounds (1) | client_name (32) |
REQUEST_FORMAT = "!IBB32s"
REQUEST_SIZE = struct.calcsize(REQUEST_FORMAT)


def pack_request(rounds, client_name):
    name_bytes = client_name.encode("utf-8")[:NAME_LEN]
    name_bytes = name_bytes.ljust(NAME_LEN, b"\x00")

    return struct.pack(
        REQUEST_FORMAT,
        MAGIC_COOKIE,
        REQUEST_TYPE,
        rounds,
        name_bytes
    )


def unpack_request(data):
    if len(data) < REQUEST_SIZE:
        return None

    magic, msg_type, rounds, name_bytes = struct.unpack(
        REQUEST_FORMAT, data[:REQUEST_SIZE]
    )

    if magic != MAGIC_COOKIE or msg_type != REQUEST_TYPE:
        return None

    client_name = name_bytes.rstrip(b"\x00").decode("utf-8")
    return rounds, client_name

# ===== Payload Messages (TCP) =====
# Spec:
# Client payload:  magic(4) | type(1=0x4) | decision(5 bytes: "Hittt"/"Stand")
# Server payload:  magic(4) | type(1=0x4) | result(1) | rank(2 bytes 01-13) | suit(1 byte 0-3)
# result: 0x3 win / 0x2 loss / 0x1 tie / 0x0 round not over
# rank: uint16, suit: 0..3 (H D C S)

CLIENT_PAYLOAD_FORMAT = "!IB5s"
CLIENT_PAYLOAD_SIZE = struct.calcsize(CLIENT_PAYLOAD_FORMAT)

SERVER_PAYLOAD_FORMAT = "!IBBHB"
SERVER_PAYLOAD_SIZE = struct.calcsize(SERVER_PAYLOAD_FORMAT)

RESULT_NOT_OVER = 0x0
RESULT_TIE = 0x1
RESULT_LOSS = 0x2
RESULT_WIN = 0x3

SUIT_CHARS = ["H", "D", "C", "S"]


def pack_client_payload(decision):
    if decision not in ("Hittt", "Stand"):
        raise ValueError("decision must be 'Hit' or 'Stand'")
    return struct.pack(CLIENT_PAYLOAD_FORMAT, MAGIC_COOKIE, PAYLOAD_TYPE, decision.encode("ascii"))


def unpack_client_payload(data):
    if len(data) < CLIENT_PAYLOAD_SIZE:
        return None
    magic, msg_type, decision_bytes = struct.unpack(CLIENT_PAYLOAD_FORMAT, data[:CLIENT_PAYLOAD_SIZE])
    if magic != MAGIC_COOKIE or msg_type != PAYLOAD_TYPE:
        return None
    decision = decision_bytes.decode("ascii", errors="ignore")
    if decision not in ("Hittt", "Stand"):
        return None
    return decision


def pack_server_payload(result, rank, suit):
    if result not in (RESULT_NOT_OVER, RESULT_TIE, RESULT_LOSS, RESULT_WIN):
        raise ValueError("invalid result")
    if not (0 <= rank <= 13):
        raise ValueError("rank must be 0..13")
    if not (0 <= suit <= 3):
        raise ValueError("suit must be 0..3")
    return struct.pack(SERVER_PAYLOAD_FORMAT, MAGIC_COOKIE, PAYLOAD_TYPE, result, rank, suit)


def unpack_server_payload(data):
    if len(data) < SERVER_PAYLOAD_SIZE:
        return None
    magic, msg_type, result, rank, suit = struct.unpack(SERVER_PAYLOAD_FORMAT, data[:SERVER_PAYLOAD_SIZE])
    if magic != MAGIC_COOKIE or msg_type != PAYLOAD_TYPE:
        return None
    return result, rank, suit


def card_value(rank):
    # Spec: A=11, J/Q/K=10, 2-10 as-is :contentReference[officiate:10]{index=10}
    if rank == 1:
        return 11
    if 2 <= rank <= 10:
        return rank
    if 11 <= rank <= 13:
        return 10
    return 0


def card_to_str(rank, suit):
    if rank == 1:
        r = "🅰️"
    elif rank == 2:
        r = "2️⃣"
    elif rank == 3:
        r = "3️⃣"
    elif rank == 4:
        r = "4️⃣"
    elif rank == 5:
        r = "5️⃣"
    elif rank == 6:
        r = "6️⃣"
    elif rank == 7:
        r = "7️⃣"
    elif rank == 8:
        r = "8️⃣"
    elif rank == 9:
        r = "9️⃣"
    elif rank == 10:
        r = "🔟"
    elif rank == 11:
        r = "🤴🏼"
    elif rank == 12:
        r = "👸🏽"
    elif rank == 13:
        r = "🤴🏻"
    else:
        r = "?"
    s = SUIT_CHARS[suit]
    if suit == 0:
        s = "♥️"
    elif suit == 1:
        s = "♦️"
    elif suit == 2:
        s = "♣️"
    elif suit == 3:
        s = "♠️"
    else:
        s ="?"
    return f"{r} {s}"


