"""
Tkinter-based Dashboard UI for Cross-Device HID.
Provides setup instructions, network details, connection status,
manual IP connection, port configuration, manual peer scanning,
and remote control disconnect warnings/controls.
"""
import sys
import tkinter as tk
from tkinter import messagebox

class DashboardApp:
    def __init__(
        self,
        local_ip: str,
        hostname: str,
        control_port: int,
        discovery_port: int,
        on_connect,                  # Callable[[dict], None]
        on_disconnect,               # Callable[[], None]
        on_quit,                     # Callable[[], None]
        on_manual_scan,              # Callable[[], None]
        on_save_settings,            # Callable[[int, int], bool]
        on_disconnect_remote,        # Callable[[], None] (disconnect incoming controller)
    ):
        self.local_ip = local_ip
        self.hostname = hostname
        self.active_control_port = control_port
        self.active_discovery_port = discovery_port
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._on_quit = on_quit
        self._on_manual_scan = on_manual_scan
        self._on_save_settings = on_save_settings
        self._on_disconnect_remote_cb = on_disconnect_remote

        self._peers: list[dict] = []
        self._status = "Idle — Ready to connect or accept connections"
        self._active_ip: str | None = None
        self._is_controlled = False

        # Create root window
        self.root = tk.Tk()
        self.root.title("Cross-Device HID Dashboard")
        self.root.geometry("860x590")
        self.root.resizable(False, False)

        # Style configuration
        self.bg_color = "#1e1e2e"          # Dark slate/indigo background
        self.card_bg = "#252538"           # Card frame background
        self.text_primary = "#f8f9fa"      # Off-white primary text
        self.text_secondary = "#adb5bd"    # Light gray secondary text
        self.accent_blue = "#3a86ff"       # Vibrant action blue
        self.accent_green = "#2ec4b6"      # Connected green
        self.accent_red = "#e63946"        # Error/disconnect red
        self.accent_yellow = "#ffb703"     # Settings yellow

        self.root.configure(bg=self.bg_color)

        # Handle window closing (redirect to hide to system tray)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        # Bind local Escape key to disconnect incoming controller
        self.root.bind("<Escape>", self._handle_escape_press)

        self._build_ui()

    def _build_ui(self):
        # 0. Active Control Warning Frame (Hidden by default, packed at top when controlled)
        self.warning_frame = tk.Frame(self.root, bg=self.accent_red, pady=8)
        
        self.warning_lbl = tk.Label(
            self.warning_frame,
            text="WARNING: This PC is currently being controlled!",
            font=("Segoe UI", 11, "bold"),
            fg="white",
            bg=self.accent_red,
            anchor="w",
        )
        self.warning_lbl.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)

        self.warning_btn = tk.Button(
            self.warning_frame,
            text="Disconnect Controller (ESC)",
            font=("Segoe UI", 9, "bold"),
            bg="white",
            fg=self.accent_red,
            activebackground="#f8f9fa",
            activeforeground=self.accent_red,
            relief="flat",
            bd=0,
            padx=15,
            pady=3,
            cursor="hand2",
            command=self._on_disconnect_remote,
        )
        self.warning_btn.pack(side=tk.RIGHT, padx=20)

        # Master Container (holds everything else, so warning_frame can be packed above it)
        self.main_container = tk.Frame(self.root, bg=self.bg_color)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # Header banner
        header_frame = tk.Frame(self.main_container, bg=self.bg_color, pady=12)
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
            text="Control another computer's mouse and keyboard seamlessly over the local network. Escape using Ctrl+Alt+Escape.",
            font=("Segoe UI", 9),
            fg=self.text_secondary,
            bg=self.bg_color,
        )
        subtitle_label.pack(anchor="w", pady=(2, 0))

        # Main Content Layout (Two Columns)
        main_content = tk.Frame(self.main_container, bg=self.bg_color)
        main_content.pack(fill=tk.BOTH, expand=True, padx=20, pady=(5, 10))

        # Left Column: Config cards
        left_col = tk.Frame(main_content, bg=self.bg_color, width=380)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        left_col.pack_propagate(False)

        # 1. Local Machine Info Card
        local_card = tk.LabelFrame(
            left_col,
            text=" Local PC Details ",
            font=("Segoe UI", 10, "bold"),
            fg=self.accent_blue,
            bg=self.card_bg,
            padx=15,
            pady=10,
            bd=1,
            relief="flat",
        )
        local_card.pack(fill=tk.X, pady=(0, 10))

        self._add_info_row(local_card, "Computer Name:", self.hostname, 0)
        self._add_info_row(local_card, "Local IP Address:", self.local_ip, 1)

        # 2. Manual IP Connection Card
        manual_card = tk.LabelFrame(
            left_col,
            text=" Direct Connection (Manual IP) ",
            font=("Segoe UI", 10, "bold"),
            fg=self.accent_green,
            bg=self.card_bg,
            padx=15,
            pady=10,
            bd=1,
            relief="flat",
        )
        manual_card.pack(fill=tk.X, pady=(0, 10))

        # IP Input
        tk.Label(manual_card, text="IP Address:", font=("Segoe UI", 9), fg=self.text_secondary, bg=self.card_bg).grid(row=0, column=0, sticky="w", pady=4)
        self.manual_ip_entry = tk.Entry(manual_card, font=("Segoe UI", 9), bg="#1e1e2d", fg=self.text_primary, insertbackground="white", bd=1, relief="flat", width=18)
        self.manual_ip_entry.grid(row=0, column=1, sticky="w", padx=10, pady=4)

        # Port Input
        tk.Label(manual_card, text="Control Port:", font=("Segoe UI", 9), fg=self.text_secondary, bg=self.card_bg).grid(row=1, column=0, sticky="w", pady=4)
        self.manual_port_entry = tk.Entry(manual_card, font=("Segoe UI", 9), bg="#1e1e2d", fg=self.text_primary, insertbackground="white", bd=1, relief="flat", width=8)
        self.manual_port_entry.insert(0, str(self.active_control_port))
        self.manual_port_entry.grid(row=1, column=1, sticky="w", padx=10, pady=4)

        # Manual Connect Button
        self.manual_connect_btn = tk.Button(
            manual_card,
            text="Connect",
            font=("Segoe UI", 9, "bold"),
            bg=self.accent_green,
            fg="white",
            activebackground="#259a8c",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=15,
            pady=4,
            cursor="hand2",
            command=self._handle_manual_connect,
        )
        self.manual_connect_btn.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        # 3. Port Settings Card
        settings_card = tk.LabelFrame(
            left_col,
            text=" Port Configuration Settings ",
            font=("Segoe UI", 10, "bold"),
            fg=self.accent_yellow,
            bg=self.card_bg,
            padx=15,
            pady=10,
            bd=1,
            relief="flat",
        )
        settings_card.pack(fill=tk.BOTH, expand=True)

        # Control Port Input
        tk.Label(settings_card, text="Control Port:", font=("Segoe UI", 9), fg=self.text_secondary, bg=self.card_bg).grid(row=0, column=0, sticky="w", pady=4)
        self.settings_control_port = tk.Entry(settings_card, font=("Segoe UI", 9), bg="#1e1e2d", fg=self.text_primary, insertbackground="white", bd=1, relief="flat", width=8)
        self.settings_control_port.insert(0, str(self.active_control_port))
        self.settings_control_port.grid(row=0, column=1, sticky="w", padx=10, pady=4)

        # Discovery Port Input
        tk.Label(settings_card, text="Discovery Port:", font=("Segoe UI", 9), fg=self.text_secondary, bg=self.card_bg).grid(row=1, column=0, sticky="w", pady=4)
        self.settings_discovery_port = tk.Entry(settings_card, font=("Segoe UI", 9), bg="#1e1e2d", fg=self.text_primary, insertbackground="white", bd=1, relief="flat", width=8)
        self.settings_discovery_port.insert(0, str(self.active_discovery_port))
        self.settings_discovery_port.grid(row=1, column=1, sticky="w", padx=10, pady=4)

        # Save Settings Button
        save_settings_btn = tk.Button(
            settings_card,
            text="Save Ports Config",
            font=("Segoe UI", 9, "bold"),
            bg=self.accent_yellow,
            fg="black",
            activebackground="#cca300",
            activeforeground="black",
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._handle_save_ports,
        )
        save_settings_btn.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        # Info Label
        restart_lbl = tk.Label(
            settings_card,
            text="* Requires app restart to apply changed ports.",
            font=("Segoe UI", 8, "italic"),
            fg=self.text_secondary,
            bg=self.card_bg,
        )
        restart_lbl.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # Right Column: Discovered Devices
        right_col = tk.Frame(main_content, bg=self.bg_color, width=420)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        right_col.pack_propagate(False)

        # Peers Custom Card layout
        peers_card = tk.Frame(right_col, bg=self.card_bg, bd=0)
        peers_card.pack(fill=tk.BOTH, expand=True)

        # Peers Header Frame
        peers_header = tk.Frame(peers_card, bg=self.card_bg, pady=10, padx=15)
        peers_header.pack(fill=tk.X)

        peers_title = tk.Label(
            peers_header,
            text="Discovered Computers",
            font=("Segoe UI", 10, "bold"),
            fg=self.accent_blue,
            bg=self.card_bg,
        )
        peers_title.pack(side=tk.LEFT)

        # Refresh Scan Button
        self.refresh_btn = tk.Button(
            peers_header,
            text="🔄 Refresh Scan",
            font=("Segoe UI", 9, "bold"),
            bg=self.accent_blue,
            fg="white",
            activebackground="#2b6cb0",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=12,
            pady=3,
            cursor="hand2",
            command=self._on_manual_scan,
        )
        self.refresh_btn.pack(side=tk.RIGHT)

        # Horizontal separator
        sep = tk.Frame(peers_card, bg="#2d2d44", height=1)
        sep.pack(fill=tk.X, padx=15)

        # Content list container
        self.peers_container = tk.Frame(peers_card, bg=self.card_bg, padx=15, pady=10)
        self.peers_container.pack(fill=tk.BOTH, expand=True)

        self._refresh_peers_ui()

        # Status Bar & Actions Footer
        footer = tk.Frame(self.main_container, bg=self.card_bg, height=45)
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

    def _handle_manual_connect(self):
        if self._active_ip is not None:
            # Currently active, disconnect
            self._on_disconnect()
            return

        ip = self.manual_ip_entry.get().strip()
        if not ip:
            messagebox.showwarning("Validation Error", "Please enter a valid IP address.")
            return

        port_str = self.manual_port_entry.get().strip()
        try:
            port = int(port_str)
        except ValueError:
            messagebox.showwarning("Validation Error", "Control Port must be an integer.")
            return

        # Trigger manual connect callback
        peer = {
            "name": f"Manual Connection ({ip})",
            "ip": ip,
            "port": port,
        }
        self._on_connect(peer)

    def _handle_save_ports(self):
        try:
            control = int(self.settings_control_port.get().strip())
            discovery = int(self.settings_discovery_port.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Ports must be integer values.")
            return

        if self._on_save_settings(control, discovery):
            messagebox.showinfo("Settings Saved", "Port configurations saved successfully.\nPlease restart the application to apply the changes.")

    def _handle_escape_press(self, event):
        if self._is_controlled:
            print("[Dashboard] Escape pressed on controlled PC. Terminating session.")
            self._on_disconnect_remote()

    def _on_disconnect_remote(self):
        if self._on_disconnect_remote_cb:
            self._on_disconnect_remote_cb()

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
                    self._status = f"Controlling device @ {ip} (Ctrl+Alt+Esc to stop)"
                self.status_icon.configure(fg=self.accent_green)
                self.status_lbl.configure(text=self._status, fg=self.accent_green)

                # Hide warning frame if active
                self.warning_frame.pack_forget()

                # Update manual card connect button to act as disconnect
                self.manual_connect_btn.configure(
                    text="Disconnect",
                    bg=self.accent_red,
                    activebackground="#b22222"
                )
                self.manual_ip_entry.configure(state="disabled")
                self.manual_port_entry.configure(state="disabled")

            elif "controlled_by" in status_lower:
                # Being controlled by a remote PC
                ip = status.split(":", 1)[1] if ":" in status else "Remote Controller"
                self._active_ip = None
                self._is_controlled = True
                self._status = f"Warning: Machine is controlled by {ip}"
                self.status_icon.configure(fg=self.accent_red)
                self.status_lbl.configure(text=self._status, fg=self.accent_red)

                # Update warning banner text and display banner at very top
                self.warning_lbl.configure(text=f"WARNING: PC is being controlled by {ip}!")
                self.warning_frame.pack(fill=tk.X, side=tk.TOP, before=self.main_container)
                
                # Restore window to visible and bring to front so the user is immediately aware
                self.show()

            elif "disconnected" in status_lower or "idle" in status_lower:
                self._active_ip = None
                self._is_controlled = False
                self._status = "Idle — Ready to connect or accept connections"
                self.status_icon.configure(fg=self.text_secondary)
                self.status_lbl.configure(text=self._status, fg=self.text_primary)

                # Hide warning frame
                self.warning_frame.pack_forget()

                # Reset manual card connect button to connect
                self.manual_connect_btn.configure(
                    text="Connect",
                    bg=self.accent_green,
                    activebackground="#259a8c"
                )
                self.manual_ip_entry.configure(state="normal")
                self.manual_port_entry.configure(state="normal")

            elif "error" in status_lower:
                self._active_ip = None
                self._is_controlled = False
                self._status = "Connection lost — retrying…"
                self.status_icon.configure(fg=self.accent_red)
                self.status_lbl.configure(text=self._status, fg=self.accent_red)
                
                # Hide warning frame
                self.warning_frame.pack_forget()
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
