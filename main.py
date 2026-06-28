import sys
import threading
import json
import os

from protocol import CONTROL_PORT, DISCOVERY_PORT
from discovery import DiscoveryService, _get_local_ip, _get_hostname
from input_server import InputServer
from input_client import InputClient
from tray_icon import TrayApp
from firewall import ensure_firewall_rules
from dashboard import DashboardApp
from debuglog import reset as _log_reset, log as _log

CONFIG_FILE = "config.json"


def load_config():
    defaults = {"control_port": CONTROL_PORT, "discovery_port": DISCOVERY_PORT}
    if not os.path.exists(CONFIG_FILE):
        return defaults
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            return {
                "control_port": int(data.get("control_port", CONTROL_PORT)),
                "discovery_port": int(data.get("discovery_port", DISCOVERY_PORT))
            }
    except Exception:
        return defaults


def save_config(control_port: int, discovery_port: int) -> bool:
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump({"control_port": control_port, "discovery_port": discovery_port}, f, indent=4)
        return True
    except Exception as e:
        print(f"[Main] Save config failed: {e}")
        return False


def main():
    # Load ports config
    config = load_config()
    control_port = config["control_port"]
    discovery_port = config["discovery_port"]

    # ------------------------------------------------------------------ #
    # 0. Firewall — auto-add rules on first run (one-time UAC prompt)    #
    # ------------------------------------------------------------------ #
    ensure_firewall_rules(control_port=control_port, discovery_port=discovery_port)

    # Get local details
    local_ip = _get_local_ip()
    hostname = _get_hostname()

    _log_reset(f"app start host={hostname} ip={local_ip} "
               f"ctrl_port={control_port} disc_port={discovery_port}")

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
    server = InputServer(port=control_port, on_status_change=on_status)
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
        control_port=control_port,
        discovery_port=discovery_port,
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
        # Quit may be invoked from the tray's background thread. sys.exit() only
        # unwinds the calling thread, leaving the Tk mainloop (and the process)
        # alive. Best-effort-stop the components to release the input hooks and
        # sockets, then force the whole process to exit regardless of thread.
        for name, stop_fn in (
            ("client", client.stop),
            ("discovery", discovery.stop),
            ("server", server.stop),
            ("tray", tray.stop if tray else None),
        ):
            if stop_fn is None:
                continue
            try:
                stop_fn()
            except Exception as e:
                print(f"[Main] error stopping {name}: {e}")
        os._exit(0)

    # Dashboard-specific callbacks
    def on_manual_scan():
        print("[Main] Triggering manual broadcast scan...")
        discovery.broadcast_now()
        # Immediately refresh peers in case list needs to reflect expirations
        if dashboard:
            dashboard.update_peers(discovery.get_peers())

    def on_save_settings(ctrl: int, disc: int) -> bool:
        return save_config(ctrl, disc)

    def disconnect_remote():
        print("[Main] Terminating incoming controller session...")
        server.disconnect_active_client()

    # ------------------------------------------------------------------ #
    # 4. GUI & System-tray UI Setup                                        #
    # ------------------------------------------------------------------ #
    dashboard = DashboardApp(
        local_ip=local_ip,
        hostname=hostname,
        control_port=control_port,
        discovery_port=discovery_port,
        on_connect=connect_to,
        on_disconnect=disconnect,
        on_quit=quit_app,
        on_manual_scan=on_manual_scan,
        on_save_settings=on_save_settings,
        on_disconnect_remote=disconnect_remote,
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
