# Cross-Device HID

Share your mouse and keyboard across multiple Windows PCs on the same Wi-Fi network.

## How it works

| Role | What happens |
|------|-------------|
| **Controlled PC** | Runs the input server — accepts remote mouse/keyboard events and simulates them locally |
| **Controlling PC** | Captures your local mouse/keyboard and streams them to the chosen device |

Every PC runs the **same app** and plays both roles simultaneously.  
Switch targets any time from the taskbar tray icon.

## Quick start

### Option A — Run from source

```powershell
# 1. Install Python 3.10+  (python.org)
# 2. Clone / download this repo, then:
pip install -r requirements.txt
python main.py
```

### Option B — Build a standalone .exe

```powershell
build.bat
# Creates dist\cross_device_hid.exe  (no Python needed on target machines)
```

## Usage

1. **Run the app on every PC** you want to share input with.
2. A tray icon appears in the Windows taskbar notification area.
3. **Right-click the tray icon** to see all discovered PCs on the network.
4. Click a PC name to **start controlling it** — your mouse and keyboard now control that machine.
5. Click the same entry again (or **Stop controlling**) to release control.
6. To control a different PC, just click its name in the menu.

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  Each PC                                                    │
│                                                             │
│  ┌─────────────┐   UDP broadcast    ┌──────────────────┐  │
│  │  Discovery  │◄──────────────────►│  Discovery       │  │
│  │  Service    │   (port 54320)     │  Service         │  │
│  └─────────────┘                   └──────────────────┘  │
│                                                             │
│  ┌─────────────┐   TCP stream       ┌──────────────────┐  │
│  │ InputClient │──────────────────► │  InputServer     │  │
│  │ (captures)  │   (port 54321)     │  (simulates)     │  │
│  └─────────────┘                    └──────────────────┘  │
│                                                             │
│  ┌─────────────┐                                           │
│  │  Tray Icon  │  right-click → pick device                │
│  └─────────────┘                                           │
└────────────────────────────────────────────────────────────┘
```

## Network ports

| Port  | Protocol | Purpose |
|-------|----------|---------|
| 54320 | UDP      | Device discovery (broadcast) |
| 54321 | TCP      | Input event stream |

Open these in Windows Firewall if devices don't appear.

## Firewall (Windows Defender)

Run once as Administrator on each PC:

```powershell
netsh advfirewall firewall add rule name="CrossDeviceHID-UDP" dir=in action=allow protocol=UDP localport=54320
netsh advfirewall firewall add rule name="CrossDeviceHID-TCP" dir=in action=allow protocol=TCP localport=54321
```

Or simply click **Allow access** when Windows prompts on first run.

## Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point — wires everything together |
| `discovery.py` | UDP broadcast device discovery |
| `input_server.py` | TCP server that simulates received events |
| `input_client.py` | Captures local input and streams to remote |
| `tray_icon.py` | System-tray UI |
| `protocol.py` | Shared constants and message encoding |
| `requirements.txt` | Python dependencies |
| `build.bat` | PyInstaller build script |

## Dependencies

- [pynput](https://pynput.readthedocs.io/) — capture and simulate input
- [pystray](https://pystray.readthedocs.io/) — Windows system tray icon
- [Pillow](https://pillow.readthedocs.io/) — tray icon image rendering
