"""
Runs on the CONTROLLED device.
Accepts a TCP connection and replays mouse/keyboard events using pynput.
"""
import json
import socket
import threading

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController

from protocol import CONTROL_PORT, BUFFER_SIZE

# Map string names -> pynput Button
_BUTTON_MAP = {
    "left": Button.left,
    "right": Button.right,
    "middle": Button.middle,
}

# Map string names -> pynput Key (special keys)
_SPECIAL_KEYS = {name: getattr(Key, name) for name in dir(Key) if not name.startswith("_")}


def _resolve_key(key_str: str):
    if key_str in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[key_str]
    if key_str.startswith("\\x") or len(key_str) > 1:
        # Try to decode as unicode char
        try:
            return bytes(key_str, "utf-8").decode("unicode_escape")
        except Exception:
            pass
    return key_str  # single character


class InputServer:
    """Listens for one controller at a time and simulates its input locally."""

    def __init__(self, host: str = "0.0.0.0", port: int = CONTROL_PORT, on_status_change=None):
        self.host = host
        self.port = port
        self._mouse = MouseController()
        self._keyboard = KeyboardController()
        self._stop = threading.Event()
        self._server_sock = None
        self.on_status_change = on_status_change or (lambda status: None)
        self._active_conn = None
        self._server_lock = threading.Lock()

    def start(self):
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(1)
        self._server_sock.settimeout(1.0)
        print(f"[InputServer] Listening on {self.host}:{self.port}")
        threading.Thread(target=self._accept_loop, daemon=True, name="HID-Server").start()

    def stop(self):
        self._stop.set()
        self.disconnect_active_client()
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass

    def disconnect_active_client(self):
        """Forcefully disconnect the currently connected remote controller."""
        with self._server_lock:
            if self._active_conn:
                try:
                    self._active_conn.close()
                    print("[InputServer] Force disconnected active remote controller.")
                except Exception as e:
                    print(f"[InputServer] Error disconnecting client: {e}")
                self._active_conn = None

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, addr = self._server_sock.accept()
                print(f"[InputServer] Controller connected from {addr}")
                threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True,
                    name=f"HID-Client-{addr}",
                ).start()
            except socket.timeout:
                pass
            except OSError:
                break

    def _handle_client(self, conn: socket.socket, addr):
        with self._server_lock:
            self._active_conn = conn
        conn.settimeout(5.0)
        buf = ""
        self.on_status_change(f"controlled_by:{addr[0]}")
        try:
            while not self._stop.is_set():
                try:
                    chunk = conn.recv(BUFFER_SIZE).decode("utf-8")
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._dispatch(json.loads(line))
        except Exception as e:
            print(f"[InputServer] Client {addr} error: {e}")
        finally:
            conn.close()
            with self._server_lock:
                if self._active_conn == conn:
                    self._active_conn = None
            print(f"[InputServer] Controller {addr} disconnected")
            self.on_status_change("idle")

    def _dispatch(self, msg: dict):
        t = msg.get("type")
        try:
            if t == "mouse_move":
                self._mouse.position = (msg["x"], msg["y"])
            elif t == "mouse_move_rel":
                self._mouse.move(msg["dx"], msg["dy"])
            elif t == "mouse_click":
                btn = _BUTTON_MAP.get(msg.get("button", "left"), Button.left)
                if msg.get("pressed"):
                    self._mouse.press(btn)
                else:
                    self._mouse.release(btn)
            elif t == "mouse_scroll":
                self._mouse.scroll(msg.get("dx", 0), msg.get("dy", 0))
            elif t == "key":
                key = _resolve_key(msg["key"])
                if msg.get("pressed"):
                    self._keyboard.press(key)
                else:
                    self._keyboard.release(key)
        except Exception as e:
            print(f"[InputServer] dispatch error ({t}): {e}")
