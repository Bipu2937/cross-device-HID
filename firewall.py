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

_RULES = [
    {
        "name": "CrossDeviceHID-UDP-Discovery",
        "protocol": "UDP",
        "port": DISCOVERY_PORT,
    },
    {
        "name": "CrossDeviceHID-TCP-Control",
        "protocol": "TCP",
        "port": CONTROL_PORT,
    },
]


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


def _build_netsh_commands() -> str:
    """Build a semicolon-joined string of netsh commands to add missing rules."""
    cmds = []
    for rule in _RULES:
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


def ensure_firewall_rules() -> bool:
    """
    Ensure Windows Firewall allows the app's ports.

    - If all rules already exist: returns True immediately (no UAC prompt).
    - If any rule is missing: triggers a single UAC-elevated cmd.exe to add
      them, waits for completion, then returns True/False based on success.

    The main process is never elevated; only a short-lived cmd.exe subprocess
    runs with admin rights.
    """
    # Fast-path: all rules exist already
    if all(_rule_exists(r["name"]) for r in _RULES):
        print("[Firewall] Rules already present — no action needed.")
        return True

    cmds = _build_netsh_commands()
    if not cmds:
        return True  # nothing to add

    print("[Firewall] Missing firewall rules — requesting elevation to add them…")

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
