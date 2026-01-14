import struct

# Magic cookie helps filter unrelated UDP broadcasts / random bytes
MAGIC_COOKIE = 0xabcddcba

# Message type identifiers (1 byte each)
OFFER_TYPE = 0x2
REQUEST_TYPE = 0x3
PAYLOAD_TYPE = 0x4

# UDP discovery port (clients listen here for offers)
UDP_PORT = 13122
# Fixed string field length (server/client name)
NAME_LEN = 32

# Offer structure:
# | magic (4) | msg_type (1) | tcp_port (2) | server_name (32) |
# Purpose: discovery (server broadcasts its TCP port + name)
OFFER_FORMAT = "!IBH32s"
OFFER_SIZE = struct.calcsize(OFFER_FORMAT)


def pack_offer(tcp_port, server_name):
    """
    Build a UDP Offer message (binary) announcing the server.
    Args:
        tcp_port (int): The TCP port the server is listening on (0..65535).
        server_name (str): Human-readable server/team name (max 32 bytes).

    Returns:
        bytes: Packed offer buffer exactly OFFER_SIZE bytes.
    """
    # Encode to UTF-8, truncate to NAME_LEN, pad with null bytes to fixed size
    name_bytes = server_name.encode("utf-8")[:NAME_LEN]
    name_bytes = name_bytes.ljust(NAME_LEN, b"\x00")

    # Pack using network byte order:
    # I=uint32, B=uint8, H=uint16, 32s=32-byte string
    return struct.pack(
        OFFER_FORMAT,
        MAGIC_COOKIE,
        OFFER_TYPE,
        tcp_port,
        name_bytes
    )


def unpack_offer(data):
    """
    Parse and validate a UDP Offer message.
    Validation:
    - Must be at least OFFER_SIZE bytes
    - magic cookie must match
    - msg_type must be OFFER_TYPE
    Args:
        data (bytes): Raw UDP datagram payload.

    Returns:
        tuple[int, str] | None:
            (tcp_port, server_name) if valid, otherwise None.
    """
    if len(data) < OFFER_SIZE:
        return None

    magic, msg_type, tcp_port, name_bytes = struct.unpack(
        OFFER_FORMAT, data[:OFFER_SIZE]
    )
    # Reject packets that are not ours or not an offer
    if magic != MAGIC_COOKIE or msg_type != OFFER_TYPE:
        return None

    # Remove null padding and decode back to string
    server_name = name_bytes.rstrip(b"\x00").decode("utf-8")
    return tcp_port, server_name

# Request structure:
# | magic (4) | msg_type (1) | rounds (1) | client_name (32) |
# Purpose: client asks the server to play N rounds, and identifies itself.
REQUEST_FORMAT = "!IBB32s"
REQUEST_SIZE = struct.calcsize(REQUEST_FORMAT)


def pack_request(rounds, client_name):
    """
   Build a TCP Request message (binary) from the client to the server.
   Args:
       rounds (int): Number of rounds requested (0..255, fits in 1 byte).
       client_name (str): Client/team name (max 32 bytes).

   Returns:
       bytes: Packed request buffer exactly REQUEST_SIZE bytes.
   """
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
    """
    Parse and validate a TCP Request message.
    Validation:
    - Must be at least REQUEST_SIZE bytes
    - magic cookie must match
    - msg_type must be REQUEST_TYPE

    Args:
       data (bytes): Raw bytes received from TCP.

    Returns:
       tuple[int, str] | None:
           (rounds, client_name) if valid, otherwise None.
    """
    if len(data) < REQUEST_SIZE:
        return None

    magic, msg_type, rounds, name_bytes = struct.unpack(
        REQUEST_FORMAT, data[:REQUEST_SIZE]
    )

    if magic != MAGIC_COOKIE or msg_type != REQUEST_TYPE:
        return None

    client_name = name_bytes.rstrip(b"\x00").decode("utf-8")
    return rounds, client_name

# Payload Messages
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

# Optional lookup for suits
SUIT_CHARS = ["H", "D", "C", "S"]


def pack_client_payload(decision):
    """
    Build a client gameplay payload containing the player's decision.
    Args:
        decision (str): Must be exactly "Hittt" or "Stand" (5 ASCII bytes).

    Returns:
        bytes: Packed client payload exactly CLIENT_PAYLOAD_SIZE bytes.

    Raises:
        ValueError: If decision is not one of the allowed values.
    """
    # Decision is fixed-length 5 bytes (protocol requirement)
    if decision not in ("Hittt", "Stand"):
        raise ValueError("decision must be 'Hittt' or 'Stand'")
    return struct.pack(CLIENT_PAYLOAD_FORMAT, MAGIC_COOKIE, PAYLOAD_TYPE, decision.encode("ascii"))


def unpack_client_payload(data):
    """
    Parse and validate a client gameplay payload.
    Validation:
    - Must be at least CLIENT_PAYLOAD_SIZE bytes
    - magic cookie and type must match
    - decision must be one of the allowed 5-byte commands

    Args:
        data (bytes): Raw bytes from TCP.

    Returns:
        str | None: "Hittt"/"Stand" if valid, otherwise None.
    """
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
    """
    Build a server gameplay payload.

    Two uses:
    1) Card message (result=RESULT_NOT_OVER, rank/suit describe the card)
    2) Final result message (result in WIN/LOSS/TIE, rank=suit=0)

    Args:
        result (int): RESULT_NOT_OVER / RESULT_TIE / RESULT_LOSS / RESULT_WIN
        rank (int): 0..13 (0 used when no card is attached)
        suit (int): 0..3 (ignored if rank=0)

    Returns:
        bytes: Packed server payload exactly SERVER_PAYLOAD_SIZE bytes.
    """
    # Defensive validation keeps protocol consistent
    if result not in (RESULT_NOT_OVER, RESULT_TIE, RESULT_LOSS, RESULT_WIN):
        raise ValueError("invalid result")
    if not (0 <= rank <= 13):
        raise ValueError("rank must be 0..13")
    if not (0 <= suit <= 3):
        raise ValueError("suit must be 0..3")
    return struct.pack(SERVER_PAYLOAD_FORMAT, MAGIC_COOKIE, PAYLOAD_TYPE, result, rank, suit)


def unpack_server_payload(data):
    """
    Parse and validate a server gameplay payload.

    Validation:
    - Must be at least SERVER_PAYLOAD_SIZE bytes
    - magic cookie and type must match

    Args:
        data (bytes): Raw bytes from TCP.

    Returns:
        tuple[int, int, int] | None:
            (result, rank, suit) if valid, otherwise None.
    """
    if len(data) < SERVER_PAYLOAD_SIZE:
        return None
    magic, msg_type, result, rank, suit = struct.unpack(SERVER_PAYLOAD_FORMAT, data[:SERVER_PAYLOAD_SIZE])
    if magic != MAGIC_COOKIE or msg_type != PAYLOAD_TYPE:
        return None
    return result, rank, suit


def card_value(rank):
    """
    Map a card rank (1..13) to a Blackjack point value.
    Rules implemented here:
    - Ace (1) counts as 11
    - 2..10 count as their number
    - J/Q/K (11..13) count as 10
    - rank 0 (used in final-result payloads) returns 0
    """
    if rank == 1:
        return 11
    if 2 <= rank <= 10:
        return rank
    if 11 <= rank <= 13:
        return 10
    return 0


def card_to_str(rank, suit):
    """
    Convert (rank, suit) into a friendly string representation for printing.
    - Uses emojis for ranks and suits for a nicer CLI UI.
    - For invalid ranks/suits returns '?' placeholders.

    Args:
        rank (int): 1..13
        suit (int): 0..3

    Returns:
        str: e.g. "🅰️♥️" or "🔟♠️"
    """
    # Rank emoji mapping
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

    # Suit emoji mapping (0..3)
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