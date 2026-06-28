"""
Runs on the CONTROLLING device.
Captures local mouse/keyboard events and streams them to the target device.
"""
import json
import socket
import threading
import time

from pynput import mouse, keyboard

from protocol import CONTROL_PORT, encode


class InputClient:
    """
    Captures all local mouse and keyboard events and forwards them to
    the currently-selected remote device.  Call connect() / disconnect()
    to switch targets.
    """

    RECONNECT_DELAY = 3.0

    def __init__(self, on_status_change=None):
        self._sock: socket.socket | None = None
        self._target: tuple[str, int] | None = None  # (ip, port)
        self._lock = threading.Lock()
        self._capturing = False
        self._mouse_listener = None
        self._keyboard_listener = None
        self.on_status_change = on_status_change or (lambda status: None)
        self._ctrl_pressed = False
        self._alt_pressed = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self, ip: str, port: int = CONTROL_PORT):
        """Start capturing and forwarding to (ip, port)."""
        with self._lock:
            self._target = (ip, port)
        self._do_connect(ip, port)
        if not self._capturing:
            self._start_listeners()

    def disconnect(self):
        """Stop forwarding; keep listeners running (so we can reconnect)."""
        with self._lock:
            self._target = None
        self._close_socket()
        self.on_status_change("disconnected")

    def stop(self):
        """Fully shut down — stop capturing and close socket."""
        self._capturing = False
        self.disconnect()
        self._stop_listeners()

    def is_connected(self) -> bool:
        with self._lock:
            return self._sock is not None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_connect(self, ip: str, port: int):
        self._close_socket()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect((ip, port))
            s.settimeout(None)
            with self._lock:
                self._sock = s
            self.on_status_change(f"connected:{ip}")
            print(f"[InputClient] Connected to {ip}:{port}")
        except Exception as e:
            print(f"[InputClient] Connect failed: {e}")
            self.on_status_change("error")

    def _close_socket(self):
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None

    def _send(self, msg: dict):
        with self._lock:
            sock = self._sock
        if sock is None:
            return
        try:
            sock.sendall(encode(msg))
        except Exception as e:
            print(f"[InputClient] send error: {e}")
            self._close_socket()
            self.on_status_change("error")
            # Try to reconnect in background
            with self._lock:
                target = self._target
            if target:
                threading.Thread(
                    target=self._reconnect,
                    args=target,
                    daemon=True,
                ).start()

    def _reconnect(self, ip: str, port: int):
        time.sleep(self.RECONNECT_DELAY)
        with self._lock:
            if self._target != (ip, port):
                return  # target changed, abort
        self._do_connect(ip, port)

    # ------------------------------------------------------------------
    # pynput listeners
    # ------------------------------------------------------------------

    def _start_listeners(self):
        self._capturing = True
        self._ctrl_pressed = False
        self._alt_pressed = False

        self._mouse_listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
            suppress=True,
        )
        self._mouse_listener.start()

        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
            suppress=True,
        )
        self._keyboard_listener.start()

    def _stop_listeners(self):
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if self._keyboard_listener:
            self._keyboard_listener.stop()
            self._keyboard_listener = None

    def _on_move(self, x, y):
        self._send({"type": "mouse_move", "x": x, "y": y})

    def _on_click(self, x, y, button, pressed):
        self._send({
            "type": "mouse_click",
            "x": x,
            "y": y,
            "button": button.name,
            "pressed": pressed,
        })

    def _on_scroll(self, x, y, dx, dy):
        self._send({"type": "mouse_scroll", "x": x, "y": y, "dx": dx, "dy": dy})

    def _on_key_press(self, key):
        key_str = self._key_str(key)
        
        # Track modifier keys
        if "ctrl" in key_str:
            self._ctrl_pressed = True
        elif "alt" in key_str:
            self._alt_pressed = True
            
        # Escape sequence: Ctrl + Alt + Escape to regain control
        if key == keyboard.Key.esc and self._ctrl_pressed and self._alt_pressed:
            print("[InputClient] Escape combo pressed. Restoring local control...")
            self._ctrl_pressed = False
            self._alt_pressed = False
            # Call disconnect asynchronously to avoid blocking listener thread
            threading.Thread(target=self.disconnect, daemon=True).start()
            return False  # Stops the keyboard listener
            
        self._send({"type": "key", "key": key_str, "pressed": True})

    def _on_key_release(self, key):
        key_str = self._key_str(key)
        if "ctrl" in key_str:
            self._ctrl_pressed = False
        elif "alt" in key_str:
            self._alt_pressed = False
            
        self._send({"type": "key", "key": key_str, "pressed": False})

    @staticmethod
    def _key_str(key) -> str:
        if hasattr(key, "char") and key.char:
            return key.char
        if hasattr(key, "name"):
            return key.name
        return str(key)
