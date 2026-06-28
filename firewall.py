"""
Firewall rule management for Cross-Device HID.

Checks if the required inbound rules exist; if not, spawns a single
elevated (UAC) process to add them — the main app itself never needs
to run as administrator.
"""
import subprocess
import ctypes
import sys
import os

from protocol import DISCOVERY_PORT, CONTROL_PORT


def _rule_exists(rule_name: str) -> bool:
    """Return True if a firewall rule with this exact name already exists."""
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "No rules match the specified criteria" not in result.stdout
    except Exception:
        return False


def _build_netsh_commands(rules: list[dict]) -> str:
    """Build a semicolon-joined string of netsh commands to add missing rules."""
    cmds = []
    for rule in rules:
        if not _rule_exists(rule["name"]):
            cmds.append(
                f'netsh advfirewall firewall add rule '
                f'name="{rule["name"]}" '
                f'protocol={rule["protocol"]} '
                f'dir=in '
                f'localport={rule["port"]} '
                f'action=allow'
            )
    return " & ".join(cmds)


def ensure_firewall_rules(control_port: int = CONTROL_PORT, discovery_port: int = DISCOVERY_PORT) -> bool:
    """
    Ensure Windows Firewall allows the app's ports.

    - If all rules already exist: returns True immediately (no UAC prompt).
    - If any rule is missing: triggers a single UAC-elevated cmd.exe to add
      them, waits for completion, then returns True/False based on success.
    """
    rules = [
        {
            "name": f"CrossDeviceHID-UDP-Discovery-{discovery_port}",
            "protocol": "UDP",
            "port": discovery_port,
        },
        {
            "name": f"CrossDeviceHID-TCP-Control-{control_port}",
            "protocol": "TCP",
            "port": control_port,
        },
    ]

    # Fast-path: all rules exist already
    if all(_rule_exists(r["name"]) for r in rules):
        print("[Firewall] Rules already present — no action needed.")
        return True

    cmds = _build_netsh_commands(rules)
    if not cmds:
        return True  # nothing to add

    print(f"[Firewall] Missing firewall rules for ports UDP:{discovery_port}/TCP:{control_port} — requesting elevation…")

    try:
        # ShellExecuteW with "runas" triggers a UAC prompt.
        # SW_HIDE (0) keeps the cmd window invisible.
        result = ctypes.windll.shell32.ShellExecuteW(
            None,       # hwnd
            "runas",    # verb  — triggers UAC
            "cmd.exe",  # file
            f'/c {cmds}',  # parameters
            None,       # working directory
            0,          # SW_HIDE — no console window shown
        )
        # ShellExecuteW returns > 32 on success
        if result > 32:
            print("[Firewall] Elevation accepted — rules added successfully.")
            return True
        else:
            print(f"[Firewall] ShellExecuteW failed with code {result}.")
            return False
    except Exception as e:
        print(f"[Firewall] Could not add rules: {e}")
        return False
