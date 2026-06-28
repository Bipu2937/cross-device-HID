"""
Tkinter-based Dashboard UI for Cross-Device HID.
Provides setup instructions, network details, connection status,
and a list of discovered peers with click-to-connect buttons.
"""
import sys
import tkinter as tk
from tkinter import messagebox
import os

class DashboardApp:
    def __init__(
        self,
        local_ip: str,
        hostname: str,
        on_connect,      # Callable[[dict], None]
        on_disconnect,   # Callable[[], None]
        on_quit,         # Callable[[], None]
    ):
        self.local_ip = local_ip
        self.hostname = hostname
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._on_quit = on_quit

        self._peers: list[dict] = []
        self._status = "Idle — Ready to connect or accept connections"
        self._active_ip: str | None = None
        self._is_controlled = False

        # Create root window
        self.root = tk.Tk()
        self.root.title("Cross-Device HID Dashboard")
        self.root.geometry("780x480")
        self.root.resizable(False, False)

        # Style configuration
        self.bg_color = "#1e1e2e"          # Dark slate/indigo background
        self.card_bg = "#252538"           # Card frame background
        self.text_primary = "#f8f9fa"      # Off-white primary text
        self.text_secondary = "#adb5bd"    # Light gray secondary text
        self.accent_blue = "#3a86ff"       # Vibrant action blue
        self.accent_green = "#2ec4b6"      # Connected green
        self.accent_red = "#e63946"        # Error/disconnect red

        self.root.configure(bg=self.bg_color)

        # Handle window closing (redirect to hide to system tray)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        # Set taskbar icon if available (can use custom generation or fall back)
        try:
            # A default icon can be set if needed
            pass
        except Exception:
            pass

        self._build_ui()

    def _build_ui(self):
        # Header banner
        header_frame = tk.Frame(self.root, bg=self.bg_color, pady=15)
        header_frame.pack(fill=tk.X, padx=20)

        title_label = tk.Label(
            header_frame,
            text="Cross-Device HID Control Panel",
            font=("Segoe UI", 18, "bold"),
            fg=self.text_primary,
            bg=self.bg_color,
        )
        title_label.pack(anchor="w")

        subtitle_label = tk.Label(
            header_frame,
            text="Control another computer's mouse and keyboard seamlessly over the local network.",
            font=("Segoe UI", 10),
            fg=self.text_secondary,
            bg=self.bg_color,
        )
        subtitle_label.pack(anchor="w", pady=(2, 0))

        # Main Content Layout (Two Columns)
        main_content = tk.Frame(self.root, bg=self.bg_color)
        main_content.pack(fill=tk.BOTH, expand=True, padx=20, pady=(5, 15))

        # Left Column: Setup Info & Guide
        left_col = tk.Frame(main_content, bg=self.bg_color, width=340)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        left_col.pack_propagate(False)

        # Local Machine Info Card
        local_card = tk.LabelFrame(
            left_col,
            text=" Local PC Details ",
            font=("Segoe UI", 10, "bold"),
            fg=self.accent_blue,
            bg=self.card_bg,
            padx=15,
            pady=12,
            bd=1,
            relief="flat",
        )
        local_card.pack(fill=tk.X, pady=(0, 10))

        self._add_info_row(local_card, "Computer Name:", self.hostname, 0)
        self._add_info_row(local_card, "Local IP Address:", self.local_ip, 1)

        # Quick Setup Guide Card
        guide_card = tk.LabelFrame(
            left_col,
            text=" Quick Setup Instructions ",
            font=("Segoe UI", 10, "bold"),
            fg=self.accent_blue,
            bg=self.card_bg,
            padx=15,
            pady=12,
            bd=1,
            relief="flat",
        )
        guide_card.pack(fill=tk.BOTH, expand=True)

        guide_steps = [
            "1. Run this app on BOTH computers.",
            "2. Make sure they are connected to the same network.",
            "3. The other PC will automatically appear in the list.",
            "4. Click 'Control' to start controlling it.",
            "5. Move mouse back to your PC to regain normal use.",
        ]
        for i, step in enumerate(guide_steps):
            lbl = tk.Label(
                guide_card,
                text=step,
                font=("Segoe UI", 9),
                fg=self.text_primary,
                bg=self.card_bg,
                justify="left",
                anchor="w",
                wraplength=300,
            )
            lbl.pack(fill=tk.X, anchor="w", pady=3)

        # Right Column: Discovered Devices
        right_col = tk.Frame(main_content, bg=self.bg_color, width=380)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        right_col.pack_propagate(False)

        peers_card = tk.LabelFrame(
            right_col,
            text=" Discovered Computers on Network ",
            font=("Segoe UI", 10, "bold"),
            fg=self.accent_blue,
            bg=self.card_bg,
            padx=15,
            pady=12,
            bd=1,
            relief="flat",
        )
        peers_card.pack(fill=tk.BOTH, expand=True)

        # Canvas for scrollable list of peers (if needed)
        self.peers_container = tk.Frame(peers_card, bg=self.card_bg)
        self.peers_container.pack(fill=tk.BOTH, expand=True)

        self._refresh_peers_ui()

        # Status Bar & Actions Footer
        footer = tk.Frame(self.root, bg=self.card_bg, height=45)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        # Status Label
        self.status_icon = tk.Label(
            footer,
            text="●",
            font=("Segoe UI", 12),
            fg=self.text_secondary,
            bg=self.card_bg,
            padx=10,
        )
        self.status_icon.pack(side=tk.LEFT)

        self.status_lbl = tk.Label(
            footer,
            text=self._status,
            font=("Segoe UI", 9, "bold"),
            fg=self.text_primary,
            bg=self.card_bg,
        )
        self.status_lbl.pack(side=tk.LEFT, padx=(0, 10))

        # Quit Button
        quit_btn = tk.Button(
            footer,
            text="Quit Application",
            font=("Segoe UI", 9, "bold"),
            bg=self.accent_red,
            fg="white",
            activebackground="#b22222",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=15,
            pady=3,
            cursor="hand2",
            command=self._on_quit,
        )
        quit_btn.pack(side=tk.RIGHT, padx=15, pady=8)

    def _add_info_row(self, parent, label_text, val_text, row):
        lbl = tk.Label(
            parent,
            text=label_text,
            font=("Segoe UI", 9),
            fg=self.text_secondary,
            bg=self.card_bg,
            anchor="w",
        )
        lbl.grid(row=row, column=0, sticky="w", pady=4)

        val = tk.Label(
            parent,
            text=val_text,
            font=("Segoe UI", 9, "bold"),
            fg=self.text_primary,
            bg=self.card_bg,
            anchor="w",
        )
        val.grid(row=row, column=1, sticky="w", padx=(10, 0), pady=4)

    def _refresh_peers_ui(self):
        # Clear container
        for widget in self.peers_container.winfo_children():
            widget.destroy()

        if not self._peers:
            empty_lbl = tk.Label(
                self.peers_container,
                text="Scanning local network for devices...\n\nMake sure the app is open on other devices.",
                font=("Segoe UI", 10, "italic"),
                fg=self.text_secondary,
                bg=self.card_bg,
                justify="center",
            )
            empty_lbl.pack(fill=tk.BOTH, expand=True, pady=40)
            return

        # Populated container
        for i, peer in enumerate(self._peers):
            peer_ip = peer["ip"]
            peer_name = peer["name"]
            is_active = (peer_ip == self._active_ip)

            peer_frame = tk.Frame(self.peers_container, bg=self.card_bg, pady=6)
            peer_frame.pack(fill=tk.X, anchor="w", pady=4)

            # Details
            details_frame = tk.Frame(peer_frame, bg=self.card_bg)
            details_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

            name_lbl = tk.Label(
                details_frame,
                text=peer_name,
                font=("Segoe UI", 10, "bold"),
                fg=self.text_primary,
                bg=self.card_bg,
                anchor="w",
            )
            name_lbl.pack(fill=tk.X, anchor="w")

            ip_lbl = tk.Label(
                details_frame,
                text=f"IP: {peer_ip}",
                font=("Segoe UI", 8),
                fg=self.text_secondary,
                bg=self.card_bg,
                anchor="w",
            )
            ip_lbl.pack(fill=tk.X, anchor="w")

            # Button
            btn_text = "Disconnect" if is_active else "Control"
            btn_bg = self.accent_red if is_active else self.accent_blue
            btn_active_bg = "#b22222" if is_active else "#2b6cb0"
            btn_cmd = self._on_disconnect if is_active else lambda p=peer: self._on_connect(p)

            action_btn = tk.Button(
                peer_frame,
                text=btn_text,
                font=("Segoe UI", 9, "bold"),
                bg=btn_bg,
                fg="white",
                activebackground=btn_active_bg,
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=15,
                pady=4,
                cursor="hand2",
                command=btn_cmd,
            )
            action_btn.pack(side=tk.RIGHT, padx=(10, 0))

    # ------------------------------------------------------------------
    # Public Thread-Safe API
    # ------------------------------------------------------------------

    def update_peers(self, peers: list[dict]):
        """Update peer list (thread-safe)."""
        def update():
            self._peers = list(peers)
            self._refresh_peers_ui()
        self.root.after(0, update)

    def update_status(self, status: str):
        """Update status label & background colors (thread-safe)."""
        def update():
            self._status = status
            status_lower = status.lower()

            if "connected" in status_lower:
                # Controlling remote PC
                if ":" in status:
                    ip = status.split(":", 1)[1]
                    self._active_ip = ip
                    self._is_controlled = False
                    self._status = f"Controlling device @ {ip}"
                self.status_icon.configure(fg=self.accent_green)
                self.status_lbl.configure(text=self._status, fg=self.accent_green)
            elif "controlled_by" in status_lower:
                # Being controlled by a remote PC
                ip = status.split(":", 1)[1] if ":" in status else "Remote Controller"
                self._active_ip = None
                self._is_controlled = True
                self._status = f"Warning: Machine is controlled by {ip}"
                self.status_icon.configure(fg=self.accent_red)
                self.status_lbl.configure(text=self._status, fg=self.accent_red)
            elif "disconnected" in status_lower or "idle" in status_lower:
                self._active_ip = None
                self._is_controlled = False
                self._status = "Idle — Ready to connect or accept connections"
                self.status_icon.configure(fg=self.text_secondary)
                self.status_lbl.configure(text=self._status, fg=self.text_primary)
            elif "error" in status_lower:
                self._active_ip = None
                self._is_controlled = False
                self._status = "Connection lost — retrying…"
                self.status_icon.configure(fg=self.accent_red)
                self.status_lbl.configure(text=self._status, fg=self.accent_red)
            else:
                self.status_lbl.configure(text=status, fg=self.text_primary)

            self._refresh_peers_ui()

        self.root.after(0, update)

    def show(self):
        """Bring window to foreground."""
        def action():
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        self.root.after(0, action)

    def hide(self):
        """Hide window to system tray (does not close app)."""
        self.root.withdraw()

    def run(self):
        """Start the Tkinter event loop."""
        self.root.mainloop()

    def stop(self):
        """Close/destroy the UI."""
        try:
            self.root.destroy()
        except Exception:
            pass
