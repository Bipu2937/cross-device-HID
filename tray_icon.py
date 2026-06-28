"""
System-tray icon (Windows taskbar notification area).
Provides a menu to:
  - See discovered devices
  - Click a device to start/stop controlling it
  - See current connection status
  - Quit
"""
from __future__ import annotations

import threading
from typing import Callable

from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as Item, Menu


def _make_icon_image(color: str = "#4A9EFF", size: int = 64) -> Image.Image:
    """Draw a simple rounded-square icon with the given colour."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Background circle
    draw.ellipse([4, 4, size - 4, size - 4], fill=color)
    # Arrow / cursor hint
    mid = size // 2
    draw.polygon(
        [(mid - 10, mid - 14), (mid - 10, mid + 8), (mid + 2, mid), (mid + 8, mid + 14), (mid + 12, mid + 10), (mid + 6, mid - 2), (mid + 16, mid - 2)],
        fill="white",
    )
    return img


_ICON_IDLE = _make_icon_image("#607D8B")      # grey-blue  = idle
_ICON_ACTIVE = _make_icon_image("#4CAF50")    # green      = controlling
_ICON_ERROR = _make_icon_image("#F44336")     # red        = error


class TrayApp:
    """
    Wraps pystray and exposes:
      update_devices(devices)   — refresh the device list in the menu
      set_status(status_str)    — update tooltip / icon colour
    """

    def __init__(
        self,
        on_connect: Callable[[dict], None],
        on_disconnect: Callable[[], None],
        on_quit: Callable[[], None],
        on_show_dashboard: Callable[[], None],
    ):
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._on_quit = on_quit
        self._on_show_dashboard = on_show_dashboard

        self._devices: list[dict] = []
        self._active_ip: str | None = None
        self._status = "Idle — no device selected"

        self._icon = pystray.Icon(
            "CrossDeviceHID",
            icon=_ICON_IDLE,
            title="Cross-Device HID",
            menu=self._build_menu(),
        )

    # ------------------------------------------------------------------
    # Public API (thread-safe, can be called from any thread)
    # ------------------------------------------------------------------

    def run(self):
        """Blocking call — runs the tray event loop (call from main thread)."""
        self._icon.run()

    def stop(self):
        self._icon.stop()

    def update_devices(self, devices: list[dict]):
        self._devices = list(devices)
        self._refresh_menu()

    def set_status(self, status: str):
        if status.startswith("connected:"):
            ip = status.split(":", 1)[1]
            self._active_ip = ip
            self._status = f"Controlling  {self._name_for(ip)}"
            self._icon.icon = _ICON_ACTIVE
        elif status.startswith("controlled_by:"):
            ip = status.split(":", 1)[1]
            self._active_ip = None
            self._status = f"Controlled by {ip}"
            self._icon.icon = _ICON_ERROR
        elif status == "disconnected" or status == "idle":
            self._active_ip = None
            self._status = "Idle — no device selected"
            self._icon.icon = _ICON_IDLE
        elif status == "error":
            self._status = "Connection error — retrying…"
            self._icon.icon = _ICON_ERROR
        self._icon.title = f"Cross-Device HID  |  {self._status}"
        self._refresh_menu()

    # ------------------------------------------------------------------
    # Menu construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> Menu:
        items = [
            Item("Show Dashboard", self._handle_show_dashboard, default=True),
            Menu.SEPARATOR,
            Item(self._status_label, None, enabled=False),
            Menu.SEPARATOR,
        ]

        if self._devices:
            for dev in self._devices:
                items.append(self._device_item(dev))
        else:
            items.append(Item("No devices found on network…", None, enabled=False))

        items += [
            Menu.SEPARATOR,
            Item("Stop controlling", self._handle_disconnect, enabled=self._active_ip is not None),
            Menu.SEPARATOR,
            Item("Quit", self._handle_quit),
        ]
        return Menu(*items)

    def _device_item(self, dev: dict) -> Item:
        ip = dev["ip"]
        label = f"{'✓  ' if ip == self._active_ip else '     '}{dev['name']}  ({ip})"

        def handler(icon, item, _ip=ip, _dev=dev):
            if self._active_ip == _ip:
                self._handle_disconnect(icon, item)
            else:
                self._active_ip = _ip
                self._on_connect(_dev)

        return Item(label, handler)

    @property
    def _status_label(self) -> str:
        return self._status

    def _refresh_menu(self):
        self._icon.menu = self._build_menu()
        # pystray needs update() on Windows to repaint
        try:
            self._icon.update_menu()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_show_dashboard(self, icon=None, item=None):
        self._on_show_dashboard()

    def _handle_disconnect(self, icon=None, item=None):
        self._on_disconnect()

    def _handle_quit(self, icon=None, item=None):
        self._on_quit()
        self._icon.stop()

    def _name_for(self, ip: str) -> str:
        for d in self._devices:
            if d["ip"] == ip:
                return d["name"]
        return ip
