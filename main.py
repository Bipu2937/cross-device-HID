"""
Cross-Device HID  —  entry point
---------------------------------
Each PC runs this app.  It simultaneously:
  1. Acts as a SERVER  (can be controlled by another PC)
  2. Acts as a CLIENT  (can control another PC via the tray menu)

Usage:
  python main.py
  cross_device_hid.exe   (after packaging with PyInstaller)
"""
import sys
import threading

from protocol import CONTROL_PORT
from discovery import DiscoveryService
from input_server import InputServer
from input_client import InputClient
from tray_icon import TrayApp


def main():
    # ------------------------------------------------------------------ #
    # 1. Input server — accept remote control of THIS machine             #
    # ------------------------------------------------------------------ #
    server = InputServer(port=CONTROL_PORT)
    server.start()

    # ------------------------------------------------------------------ #
    # 2. Input client — control ANOTHER machine                           #
    # ------------------------------------------------------------------ #
    tray: TrayApp | None = None   # forward reference filled below

    def on_status(status: str):
        if tray:
            tray.set_status(status)

    client = InputClient(on_status_change=on_status)

    # ------------------------------------------------------------------ #
    # 3. Device discovery                                                  #
    # ------------------------------------------------------------------ #
    def on_found(dev: dict):
        print(f"[Discovery] Found: {dev['name']} @ {dev['ip']}")
        if tray:
            tray.update_devices(discovery.get_peers())

    def on_lost(dev: dict):
        print(f"[Discovery] Lost:  {dev['name']} @ {dev['ip']}")
        if tray:
            # If we were controlling the lost device, disconnect
            if client.is_connected():
                client.disconnect()
            tray.update_devices(discovery.get_peers())

    discovery = DiscoveryService(
        control_port=CONTROL_PORT,
        on_device_found=on_found,
        on_device_lost=on_lost,
    )
    discovery.start()

    # ------------------------------------------------------------------ #
    # 4. System-tray UI                                                    #
    # ------------------------------------------------------------------ #
    def connect_to(dev: dict):
        print(f"[Main] Connecting to {dev['name']} ({dev['ip']})")
        client.connect(dev["ip"], dev["port"])

    def disconnect():
        print("[Main] Disconnecting")
        client.disconnect()

    def quit_app():
        print("[Main] Quitting")
        client.stop()
        discovery.stop()
        server.stop()

    tray = TrayApp(
        on_connect=connect_to,
        on_disconnect=disconnect,
        on_quit=quit_app,
    )

    # Run tray on main thread (required on Windows)
    tray.run()


if __name__ == "__main__":
    main()
