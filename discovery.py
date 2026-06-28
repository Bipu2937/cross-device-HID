"""
UDP broadcast-based device discovery.
Each device announces itself periodically; listeners collect peers.
"""
import json
import socket
import threading
import time
import platform

from protocol import DISCOVERY_PORT, DISCOVERY_MAGIC, encode, decode


def _get_hostname() -> str:
    return platform.node() or socket.gethostname()


def _get_local_ip() -> str:
    """Return the LAN IP by connecting a UDP socket (no packet sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class DiscoveryService:
    """
    Runs two threads:
    - Broadcaster: sends UDP announce packets every 2 s
    - Listener:   receives announce packets from peers and fires on_device_found/lost
    """

    ANNOUNCE_INTERVAL = 2.0
    PEER_TTL = 7.0  # drop peer if not seen for this many seconds

    def __init__(self, control_port: int, on_device_found=None, on_device_lost=None):
        self.control_port = control_port
        self.on_device_found = on_device_found or (lambda d: None)
        self.on_device_lost = on_device_lost or (lambda d: None)

        self.local_ip = _get_local_ip()
        self.hostname = _get_hostname()

        self._peers: dict[str, dict] = {}  # ip -> {name, ip, port, last_seen}
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        threading.Thread(target=self._broadcast_loop, daemon=True, name="HID-Broadcast").start()
        threading.Thread(target=self._listen_loop, daemon=True, name="HID-Listen").start()
        threading.Thread(target=self._expire_loop, daemon=True, name="HID-Expire").start()

    def stop(self):
        self._stop.set()

    def get_peers(self) -> list[dict]:
        with self._lock:
            return list(self._peers.values())

    # ------------------------------------------------------------------
    # Internal loops
    # ------------------------------------------------------------------

    def _make_announce(self) -> bytes:
        msg = {
            "magic": DISCOVERY_MAGIC,
            "type": "announce",
            "name": self.hostname,
            "ip": self.local_ip,
            "port": self.control_port,
        }
        return encode(msg)

    def _broadcast_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            while not self._stop.is_set():
                try:
                    sock.sendto(self._make_announce(), ("<broadcast>", DISCOVERY_PORT))
                except Exception:
                    pass
                self._stop.wait(self.ANNOUNCE_INTERVAL)
        finally:
            sock.close()

    def _listen_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        try:
            sock.bind(("", DISCOVERY_PORT))
        except OSError as e:
            print(f"[Discovery] bind failed: {e}")
            return

        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(1024)
                self._handle_packet(data, addr)
            except socket.timeout:
                pass
            except Exception as e:
                if not self._stop.is_set():
                    print(f"[Discovery] listen error: {e}")

        sock.close()

    def _handle_packet(self, data: bytes, addr):
        try:
            msg = decode(data.decode("utf-8"))
        except Exception:
            return

        if msg.get("magic") != DISCOVERY_MAGIC:
            return
        if msg.get("type") != "announce":
            return

        ip = msg.get("ip", addr[0])
        if ip == self.local_ip:
            return  # ignore self

        device = {
            "name": msg.get("name", ip),
            "ip": ip,
            "port": msg.get("port", self.control_port),
            "last_seen": time.time(),
        }

        with self._lock:
            is_new = ip not in self._peers
            self._peers[ip] = device

        if is_new:
            self.on_device_found(device)

    def _expire_loop(self):
        while not self._stop.is_set():
            now = time.time()
            expired = []
            with self._lock:
                for ip, dev in list(self._peers.items()):
                    if now - dev["last_seen"] > self.PEER_TTL:
                        expired.append(ip)
                for ip in expired:
                    dev = self._peers.pop(ip)
                    self.on_device_lost(dev)
            self._stop.wait(2.0)
