# shared/protocol.py
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


def pack_offer(tcp_port: int, server_name: str) -> bytes:
    name_bytes = server_name.encode("utf-8")[:NAME_LEN]
    name_bytes = name_bytes.ljust(NAME_LEN, b"\x00")

    return struct.pack(
        OFFER_FORMAT,
        MAGIC_COOKIE,
        OFFER_TYPE,
        tcp_port,
        name_bytes
    )


def unpack_offer(data: bytes):
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


def pack_request(rounds: int, client_name: str) -> bytes:
    name_bytes = client_name.encode("utf-8")[:NAME_LEN]
    name_bytes = name_bytes.ljust(NAME_LEN, b"\x00")

    return struct.pack(
        REQUEST_FORMAT,
        MAGIC_COOKIE,
        REQUEST_TYPE,
        rounds,
        name_bytes
    )


def unpack_request(data: bytes):
    if len(data) < REQUEST_SIZE:
        return None

    magic, msg_type, rounds, name_bytes = struct.unpack(
        REQUEST_FORMAT, data[:REQUEST_SIZE]
    )

    if magic != MAGIC_COOKIE or msg_type != REQUEST_TYPE:
        return None

    client_name = name_bytes.rstrip(b"\x00").decode("utf-8")
    return rounds, client_name

