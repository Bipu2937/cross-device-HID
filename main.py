import sys
import threading

from protocol import CONTROL_PORT
from discovery import DiscoveryService, _get_local_ip, _get_hostname
from input_server import InputServer
from input_client import InputClient
from tray_icon import TrayApp
from firewall import ensure_firewall_rules
from dashboard import DashboardApp


def main():
    # ------------------------------------------------------------------ #
    # 0. Firewall — auto-add rules on first run (one-time UAC prompt)    #
    # ------------------------------------------------------------------ #
    ensure_firewall_rules()

    # Get local details
    local_ip = _get_local_ip()
    hostname = _get_hostname()

    # Forward references
    tray: TrayApp | None = None
    dashboard: DashboardApp | None = None

    # Status propagation
    def on_status(status: str):
        if tray:
            tray.set_status(status)
        if dashboard:
            dashboard.update_status(status)

    # ------------------------------------------------------------------ #
    # 1. Input server — accept remote control of THIS machine             #
    # ------------------------------------------------------------------ #
    server = InputServer(port=CONTROL_PORT, on_status_change=on_status)
    server.start()

    # ------------------------------------------------------------------ #
    # 2. Input client — control ANOTHER machine                           #
    # ------------------------------------------------------------------ #
    client = InputClient(on_status_change=on_status)

    # ------------------------------------------------------------------ #
    # 3. Device discovery                                                  #
    # ------------------------------------------------------------------ #
    def on_found(dev: dict):
        print(f"[Discovery] Found: {dev['name']} @ {dev['ip']}")
        peers = discovery.get_peers()
        if tray:
            tray.update_devices(peers)
        if dashboard:
            dashboard.update_peers(peers)

    def on_lost(dev: dict):
        print(f"[Discovery] Lost:  {dev['name']} @ {dev['ip']}")
        if client.is_connected():
            client.disconnect()
        peers = discovery.get_peers()
        if tray:
            tray.update_devices(peers)
        if dashboard:
            dashboard.update_peers(peers)

    discovery = DiscoveryService(
        control_port=CONTROL_PORT,
        on_device_found=on_found,
        on_device_lost=on_lost,
    )
    discovery.start()

    # Connect handlers
    def connect_to(dev: dict):
        print(f"[Main] Connecting to {dev['name']} ({dev['ip']})")
        client.connect(dev["ip"], dev["port"])

    def disconnect():
        print("[Main] Disconnecting")
        client.disconnect()

    def quit_app():
        print("[Main] Quitting")
        # Stop client/discovery/server
        client.stop()
        discovery.stop()
        server.stop()
        # Close UIs
        if tray:
            tray.stop()
        if dashboard:
            dashboard.stop()
        sys.exit(0)

    # ------------------------------------------------------------------ #
    # 4. GUI & System-tray UI Setup                                        #
    # ------------------------------------------------------------------ #
    dashboard = DashboardApp(
        local_ip=local_ip,
        hostname=hostname,
        on_connect=connect_to,
        on_disconnect=disconnect,
        on_quit=quit_app,
    )

    tray = TrayApp(
        on_connect=connect_to,
        on_disconnect=disconnect,
        on_quit=quit_app,
        on_show_dashboard=dashboard.show,
    )

    # Run tray in a background thread on Windows
    threading.Thread(target=tray.run, daemon=True, name="HID-Tray").start()

    # Run dashboard mainloop on main thread (required for Tkinter)
    dashboard.run()


if __name__ == "__main__":
    main()
