"""
Wire protocol for cross-device HID sharing.
All messages are newline-delimited JSON sent over TCP.
Discovery uses UDP broadcast.
"""
import json

DISCOVERY_PORT = 54320
CONTROL_PORT = 54321
DISCOVERY_MAGIC = "CROSS_HID_V1"
BUFFER_SIZE = 4096


def encode(msg: dict) -> bytes:
    return (json.dumps(msg) + "\n").encode("utf-8")


def decode(data: str) -> dict:
    return json.loads(data.strip())
