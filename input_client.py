"""
Runs on the CONTROLLING device.
Captures local mouse/keyboard events and streams them to the target device.
"""
import json
import socket
import threading

from pynput import mouse, keyboard
from pynput.mouse import Controller as MouseController

from protocol import CONTROL_PORT, encode
from debuglog import log


import queue

class InputClient:
    """
    Captures all local mouse and keyboard events and forwards them to
    the currently-selected remote device.  Call connect() / disconnect()
    to switch targets.
    """

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
        self._send_queue = queue.Queue()
        self._sender_thread = None
        # Used to convert absolute cursor reports into clean per-step deltas.
        self._mouse_ctrl = MouseController()
        self._anchor: tuple[int, int] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self, ip: str, port: int = CONTROL_PORT):
        """Start capturing and forwarding to (ip, port)."""
        with self._lock:
            self._target = (ip, port)
        self._do_connect(ip, port)
        if self.is_connected():
            if not self._capturing:
                self._start_listeners()
        else:
            # Connection failed — give up and leave control on the local PC.
            with self._lock:
                self._target = None

    def disconnect(self):
        """Stop forwarding and release listeners to return control to local PC."""
        with self._lock:
            self._target = None
        self._close_socket()
        self._stop_listeners()
        self._capturing = False
        self._safe_status("disconnected")

    def stop(self):
        """Fully shut down — stop capturing and close socket."""
        self._capturing = False
        self.disconnect()

    def is_connected(self) -> bool:
        with self._lock:
            return self._sock is not None

    def _safe_status(self, status: str):
        """
        Notify the UI of a status change WITHOUT ever letting a UI error
        propagate into the connection logic. A throwing status callback
        (e.g. a tray-menu rebuild failing) must not abort an otherwise
        successful connect, or input would be captured but never streamed.
        """
        try:
            self.on_status_change(status)
        except Exception as e:
            print(f"[InputClient] status callback error ({status}): {e}")
            log(f"CLIENT status callback raised for {status!r}: {e!r}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_connect(self, ip: str, port: int):
        self._close_socket()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            # Keep the idle connection alive so brief Wi-Fi lulls don't get the
            # link torn down by the OS (the 10053 abort seen in the field).
            s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            s.settimeout(3.0)
            s.connect((ip, port))
            s.settimeout(None)
            with self._lock:
                self._sock = s
            self._start_sender_thread()
            print(f"[InputClient] Connected to {ip}:{port}")
            log(f"CLIENT connected to {ip}:{port} OK")
            self._safe_status(f"connected:{ip}")
        except Exception as e:
            print(f"[InputClient] Connect failed: {e}")
            log(f"CLIENT connect FAILED to {ip}:{port}: {e!r}")
            self._safe_status("error")

    def _close_socket(self):
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None

    def _start_sender_thread(self):
        # Clear queue
        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
            except queue.Empty:
                break
        self._sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self._sender_thread.start()

    def _sender_loop(self):
        while True:
            msg = self._send_queue.get()
            if msg is None:  # Sentinel to stop
                break
            
            with self._lock:
                sock = self._sock
            if sock is None:
                continue
                
            try:
                sock.sendall(encode(msg))
            except Exception as e:
                print(f"[InputClient] send error: {e}")
                log(f"CLIENT send ERROR: {e!r}")
                # Connection dropped — release control back to the local PC and
                # stay released (no auto-reconnect).
                self._close_socket()
                self._stop_listeners()
                self._capturing = False
                with self._lock:
                    self._target = None
                self._safe_status("disconnected")
                break  # exit sender thread

    def _send(self, msg: dict):
        # Non-blocking push to queue, extremely fast, prevents Windows hook timeouts
        self._send_queue.put_nowait(msg)

    # ------------------------------------------------------------------
    # pynput listeners
    # ------------------------------------------------------------------

    def _start_listeners(self):
        if self._capturing:
            return
        self._capturing = True
        self._ctrl_pressed = False
        self._alt_pressed = False
        self._anchor = None
        log("CLIENT listeners starting (suppress=True)")

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
        # While we are controlling a remote device the local cursor is held in
        # place (suppress=True) and we forward *relative* movements.  To produce
        # clean per-step deltas we measure each event against a fixed anchor and
        # then warp the cursor back to that anchor, so there is always headroom
        # to move in any direction and the cursor can never get clamped at a
        # screen edge (which previously froze the deltas at zero -> nothing was
        # forwarded).
        if self._anchor is None:
            self._anchor = (x, y)
            return

        ax, ay = self._anchor
        # Ignore the synthetic move event generated by our own re-centering.
        if x == ax and y == ay:
            return

        dx = x - ax
        dy = y - ay
        if dx != 0 or dy != 0:
            self._send({"type": "mouse_move_rel", "dx": dx, "dy": dy})

        # Re-center so the next physical movement starts from a known point.
        try:
            self._mouse_ctrl.position = (ax, ay)
        except Exception:
            # If we cannot warp the cursor, fall back to tracking the last
            # reported position so deltas stay per-step rather than cumulative.
            self._anchor = (x, y)

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
