"""
Main Graphical User Interface for P2P Multi-User Collaboration System.
Built with Tkinter and PIL, providing dynamic time-of-day theming, multi-tile video grid,
presentation canvas, group/private chat, and peer-to-peer file sharing manager.
"""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import threading
import queue
import time
import os
from datetime import datetime
from PIL import Image, ImageTk
import cv2
import numpy as np

from ui.theme import ThemeManager, THEMES
from core.node import P2PNode
from config import DEFAULT_TCP_PORT, DEFAULT_UDP_PORT, SHARED_FOLDER


class CollaborationApp:
    """
    Main application controller managing UI lifecycle and binding to P2PNode.
    """
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("P2P COLLABORATION SYSTEM - Computer Networks Project")
        self.root.geometry("1400x880")
        self.root.minsize(1050, 700)

        self.node = None
        self.username = None
        self.current_theme = ThemeManager.get_time_adaptive_theme()
        self.ui_queue = queue.Queue()

        # Video frame caching
        self.peer_video_labels = {}   # peer_id -> (container_frame, label_widget)
        self.peer_last_frame_ts = {}  # peer_id -> timestamp
        self.screen_photo_ref = None
        self.my_video_photo_ref = None

        # Sizing
        self.video_width = 240
        self.video_height = 180

        # Run UI event processor loop
        self.process_ui_queue()

        # Show login startup screen
        self.show_login_screen()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def process_ui_queue(self):
        """Dispatch pending UI mutations on the main GUI thread."""
        try:
            for _ in range(25):
                func, args = self.ui_queue.get_nowait()
                func(*args)
        except queue.Empty:
            pass
        finally:
            self.root.after(30, self.process_ui_queue)

    # =========================================================================
    # LOGIN / STARTUP SCREEN
    # =========================================================================

    def show_login_screen(self):
        """Display modernized Olive Minimalist startup screen."""
        theme = ThemeManager.get_login_theme()
        self.root.configure(bg=theme['bg'])

        self.login_frame = tk.Frame(self.root, bg=theme['bg'])
        self.login_frame.place(relx=0.5, rely=0.5, anchor='center')

        card = tk.Frame(
            self.login_frame,
            bg=theme['panel_bg'],
            highlightbackground=theme['border'],
            highlightthickness=2,
            padx=45,
            pady=35
        )
        card.pack()

        # Title & Subtitle
        tk.Label(
            card,
            text="🌐 P2P COLLABORATION",
            font=('Segoe UI', 30, 'bold'),
            bg=theme['panel_bg'],
            fg=theme['primary']
        ).pack(pady=(10, 5))

        tk.Label(
            card,
            text="Autonomous Peer-to-Peer LAN Collaboration System\n(Zero Central Server • Full Mesh Architecture)",
            font=('Segoe UI', 10),
            bg=theme['panel_bg'],
            fg=theme['text'],
            justify='center'
        ).pack(pady=(0, 20))

        form = tk.Frame(card, bg=theme['panel_bg'])
        form.pack(fill='x', pady=5)

        # 1. Username
        tk.Label(form, text="Your Username", font=('Segoe UI', 10, 'bold'),
                 bg=theme['panel_bg'], fg=theme['text']).pack(anchor='w', pady=(8, 2))
        u_box = tk.Frame(form, bg=theme['input_bg'], highlightbackground=theme['border'], highlightthickness=1)
        u_box.pack(fill='x', pady=2)
        self.username_entry = tk.Entry(u_box, font=('Segoe UI', 11), bg=theme['input_bg'],
                                       fg=theme['text'], relief=tk.FLAT, bd=0)
        self.username_entry.pack(fill='x', padx=10, pady=8)
        self.username_entry.insert(0, f"Peer_{int(time.time()) % 1000}")
        self.username_entry.bind('<Return>', lambda e: self.start_p2p_mesh())

        # 2. Port configuration row
        port_row = tk.Frame(form, bg=theme['panel_bg'])
        port_row.pack(fill='x', pady=8)

        # TCP Port
        tcp_col = tk.Frame(port_row, bg=theme['panel_bg'])
        tcp_col.pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 5))
        tk.Label(tcp_col, text="Local TCP Port", font=('Segoe UI', 9, 'bold'),
                 bg=theme['panel_bg'], fg=theme['text']).pack(anchor='w')
        t_box = tk.Frame(tcp_col, bg=theme['input_bg'], highlightbackground=theme['border'], highlightthickness=1)
        t_box.pack(fill='x', pady=2)
        self.tcp_port_entry = tk.Entry(t_box, font=('Segoe UI', 10), bg=theme['input_bg'],
                                       fg=theme['text'], relief=tk.FLAT, bd=0)
        self.tcp_port_entry.pack(fill='x', padx=8, pady=6)
        self.tcp_port_entry.insert(0, str(DEFAULT_TCP_PORT))

        # UDP Port
        udp_col = tk.Frame(port_row, bg=theme['panel_bg'])
        udp_col.pack(side=tk.LEFT, fill='x', expand=True, padx=(5, 0))
        tk.Label(udp_col, text="Local UDP Port", font=('Segoe UI', 9, 'bold'),
                 bg=theme['panel_bg'], fg=theme['text']).pack(anchor='w')
        u_port_box = tk.Frame(udp_col, bg=theme['input_bg'], highlightbackground=theme['border'], highlightthickness=1)
        u_port_box.pack(fill='x', pady=2)
        self.udp_port_entry = tk.Entry(u_port_box, font=('Segoe UI', 10), bg=theme['input_bg'],
                                       fg=theme['text'], relief=tk.FLAT, bd=0)
        self.udp_port_entry.pack(fill='x', padx=8, pady=6)
        self.udp_port_entry.insert(0, str(DEFAULT_UDP_PORT))

        # 3. Optional Bootstrap Peer
        tk.Label(form, text="Bootstrap Peer (Optional - IP:Port to Join)", font=('Segoe UI', 9, 'bold'),
                 bg=theme['panel_bg'], fg=theme['text']).pack(anchor='w', pady=(8, 2))
        b_box = tk.Frame(form, bg=theme['input_bg'], highlightbackground=theme['border'], highlightthickness=1)
        b_box.pack(fill='x', pady=2)
        self.bootstrap_entry = tk.Entry(b_box, font=('Segoe UI', 10), bg=theme['input_bg'],
                                        fg=theme['text'], relief=tk.FLAT, bd=0)
        self.bootstrap_entry.pack(fill='x', padx=10, pady=6)
        self.bootstrap_entry.insert(0, "")

        # Launch Button
        tk.Button(
            card,
            text="🚀 START / JOIN P2P MESH",
            font=('Segoe UI', 12, 'bold'),
            bg=theme['primary'],
            fg='#ffffff',
            activebackground=theme['secondary'],
            activeforeground='#ffffff',
            relief=tk.FLAT,
            padx=25,
            pady=12,
            cursor='hand2',
            command=self.start_p2p_mesh
        ).pack(fill='x', pady=(25, 10))

    def start_p2p_mesh(self):
        """Initialize P2P Node and load main workspace."""
        username = self.username_entry.get().strip()
        if not username:
            messagebox.showerror("Error", "Please enter a valid username")
            return

        try:
            tcp_p = int(self.tcp_port_entry.get().strip())
            udp_p = int(self.udp_port_entry.get().strip())
        except ValueError:
            messagebox.showerror("Error", "TCP and UDP ports must be integers")
            return

        bootstrap_addr = self.bootstrap_entry.get().strip()

        try:
            self.node = P2PNode(
                username=username,
                requested_tcp_port=tcp_p,
                requested_udp_port=udp_p,
                enable_discovery=True
            )
            self._bind_node_callbacks()
            self.node.start()
            self.username = username

            # Connect to bootstrap peer if supplied
            if bootstrap_addr:
                if ":" in bootstrap_addr:
                    b_ip, b_port = bootstrap_addr.split(":", 1)
                    threading.Thread(target=self.node.connect_to_peer, args=(b_ip.strip(), int(b_port.strip())), daemon=True).start()
                else:
                    threading.Thread(target=self.node.connect_to_peer, args=(bootstrap_addr.strip(), DEFAULT_TCP_PORT), daemon=True).start()

            self.login_frame.destroy()
            self.create_main_interface()

        except Exception as e:
            messagebox.showerror("Error Initializing Node", str(e))

    def _bind_node_callbacks(self):
        """Connect P2P node events to UI queue dispatcher."""
        self.node.set_callback("on_peer_joined", lambda pid, u, info: self.ui_queue.put((self._ui_on_peer_joined, (pid, u, info))))
        self.node.set_callback("on_peer_left", lambda pid, u: self.ui_queue.put((self._ui_on_peer_left, (pid, u))))
        self.node.set_callback("on_chat_message", lambda s, t, ts, priv: self.ui_queue.put((self._ui_on_chat, (s, t, ts, priv))))
        self.node.set_callback("on_video_frame", lambda pid, u, data: self.ui_queue.put((self._ui_on_video_frame, (pid, u, data))))
        self.node.set_callback("on_screen_frame", lambda pres, data: self.ui_queue.put((self._ui_on_screen_frame, (pres, data))))
        self.node.set_callback("on_presenter_changed", lambda pres: self.ui_queue.put((self._ui_on_presenter_changed, (pres,))))
        self.node.set_callback("on_file_available", lambda meta: self.ui_queue.put((self._ui_on_file_available, (meta,))))
        self.node.set_callback("on_file_progress", lambda tid, name, rec, tot, pct: self.ui_queue.put((self._ui_on_file_progress, (tid, name, rec, tot, pct))))
        self.node.set_callback("on_file_complete", lambda tid, name, path: self.ui_queue.put((self._ui_on_file_complete, (tid, name, path))))
        self.node.set_callback("on_file_error", lambda tid, err: self.ui_queue.put((self._ui_on_file_error, (tid, err))))
        self.node.set_callback("on_status_msg", lambda text: self.ui_queue.put((self._ui_on_status, (text,))))

        # Hook local video preview
        self.node.video_engine.on_local_frame = lambda frame: self.ui_queue.put((self._ui_on_my_video_frame, (frame,)))

    # =========================================================================
    # MAIN WORKSPACE LAYOUT
    # =========================================================================

    def create_main_interface(self):
        """Construct multi-column collaboration dashboard."""
        self.current_theme = ThemeManager.get_time_adaptive_theme()
        theme = self.current_theme
        self.root.configure(bg=theme['bg'])

        self.main_container = tk.Frame(self.root, bg=theme['bg'])
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # ---------------- TOP NAVIGATION BAR ----------------
        self.top_bar = tk.Frame(
            self.main_container,
            bg=theme['panel_bg'],
            height=68,
            highlightbackground=theme['border'],
            highlightthickness=2
        )
        self.top_bar.pack(fill=tk.X, side=tk.TOP)
        self.top_bar.pack_propagate(False)

        # Left Info
        info_frame = tk.Frame(self.top_bar, bg=theme['panel_bg'])
        info_frame.pack(side=tk.LEFT, padx=18, pady=10)

        self.title_label = tk.Label(
            info_frame,
            text=f"🌐 P2P COLLABORATION  •  👤 {self.username}",
            font=('Segoe UI', 15, 'bold'),
            bg=theme['panel_bg'],
            fg=theme['primary']
        )
        self.title_label.pack(anchor='w')

        self.node_badge = tk.Label(
            info_frame,
            text=f"🟢 Mesh Node Online | IP: {self.node.local_ip} | TCP:{self.node.tcp_port} UDP:{self.node.udp_port}",
            font=('Segoe UI', 9),
            bg=theme['panel_bg'],
            fg=theme['text']
        )
        self.node_badge.pack(anchor='w')

        # Right Media Controls
        btn_frame = tk.Frame(self.top_bar, bg=theme['panel_bg'])
        btn_frame.pack(side=tk.RIGHT, padx=18, pady=12)

        self.video_btn = tk.Button(
            btn_frame,
            text="📹 Video",
            font=('Segoe UI', 10, 'bold'),
            bg=theme['input_bg'],
            fg=theme['text'],
            activebackground=theme['secondary'],
            activeforeground='#ffffff',
            relief=tk.FLAT,
            padx=14,
            pady=6,
            cursor='hand2',
            command=self.toggle_video
        )
        self.video_btn.pack(side=tk.LEFT, padx=4)

        self.audio_btn = tk.Button(
            btn_frame,
            text="🎤 Audio",
            font=('Segoe UI', 10, 'bold'),
            bg=theme['input_bg'],
            fg=theme['text'],
            activebackground=theme['secondary'],
            activeforeground='#ffffff',
            relief=tk.FLAT,
            padx=14,
            pady=6,
            cursor='hand2',
            command=self.toggle_audio
        )
        self.audio_btn.pack(side=tk.LEFT, padx=4)

        self.screen_btn = tk.Button(
            btn_frame,
            text="🖥️ Share",
            font=('Segoe UI', 10, 'bold'),
            bg=theme['primary'],
            fg='#ffffff',
            activebackground=theme['accent'],
            activeforeground='#ffffff',
            relief=tk.FLAT,
            padx=14,
            pady=6,
            cursor='hand2',
            command=self.toggle_screen_share
        )
        self.screen_btn.pack(side=tk.LEFT, padx=4)

        # Theme Selector Dropdown
        self.theme_var = tk.StringVar(value="Theme")
        theme_names = list(THEMES.keys())
        self.theme_menu = ttk.Combobox(btn_frame, textvariable=self.theme_var, values=theme_names, width=9, state="readonly")
        self.theme_menu.pack(side=tk.LEFT, padx=6)
        self.theme_menu.bind("<<ComboboxSelected>>", self.on_theme_selected)

        tk.Button(
            btn_frame,
            text="❌ Exit",
            font=('Segoe UI', 10, 'bold'),
            bg='#ef4444',
            fg='#ffffff',
            activebackground='#dc2626',
            activeforeground='#ffffff',
            relief=tk.FLAT,
            padx=14,
            pady=6,
            cursor='hand2',
            command=self.on_closing
        ).pack(side=tk.LEFT, padx=4)

        # ---------------- DISCOVERY & QUICK CONNECT BAR ----------------
        self.conn_bar = tk.Frame(
            self.main_container,
            bg=theme['input_bg'],
            height=42,
            highlightbackground=theme['border'],
            highlightthickness=1
        )
        self.conn_bar.pack(fill=tk.X, side=tk.TOP)
        self.conn_bar.pack_propagate(False)

        conn_inner = tk.Frame(self.conn_bar, bg=theme['input_bg'])
        conn_inner.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        tk.Label(conn_inner, text="🔗 Connect to Peer:", font=('Segoe UI', 9, 'bold'),
                 bg=theme['input_bg'], fg=theme['text']).pack(side=tk.LEFT, padx=(0, 5))

        tk.Label(conn_inner, text="IP:", font=('Segoe UI', 9), bg=theme['input_bg'], fg=theme['text']).pack(side=tk.LEFT)
        self.quick_ip_entry = tk.Entry(conn_inner, font=('Segoe UI', 9), width=15)
        self.quick_ip_entry.pack(side=tk.LEFT, padx=4)
        self.quick_ip_entry.insert(0, "127.0.0.1")

        tk.Label(conn_inner, text="Port:", font=('Segoe UI', 9), bg=theme['input_bg'], fg=theme['text']).pack(side=tk.LEFT)
        self.quick_port_entry = tk.Entry(conn_inner, font=('Segoe UI', 9), width=7)
        self.quick_port_entry.pack(side=tk.LEFT, padx=4)
        self.quick_port_entry.insert(0, str(DEFAULT_TCP_PORT))

        tk.Button(
            conn_inner,
            text="Connect",
            font=('Segoe UI', 8, 'bold'),
            bg=theme['secondary'],
            fg='#ffffff',
            relief=tk.FLAT,
            padx=10,
            command=self.connect_to_peer_quick
        ).pack(side=tk.LEFT, padx=6)

        # Discovery indicator
        self.discovery_label = tk.Label(
            conn_inner,
            text="📡 LAN Auto-Discovery: ACTIVE (UDP 5550)",
            font=('Segoe UI', 9, 'italic'),
            bg=theme['input_bg'],
            fg='#16a34a'
        )
        self.discovery_label.pack(side=tk.RIGHT, padx=10)

        # ---------------- MAIN CONTENT AREA ----------------
        self.content_frame = tk.Frame(self.main_container, bg=theme['bg'])
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        # 1. LEFT COLUMN: Media (Screen Share & Videos)
        self.left_column = tk.Frame(self.content_frame, bg=theme['bg'])
        self.left_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        # Screen Share Panel
        self.screen_panel = tk.LabelFrame(
            self.left_column,
            text="  📺 Screen Share (Waiting for Presenter)  ",
            font=('Segoe UI', 11, 'bold'),
            bg=theme['panel_bg'],
            fg=theme['primary'],
            relief=tk.FLAT,
            highlightbackground=theme['border'],
            highlightthickness=2,
            bd=0
        )
        self.screen_panel.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.screen_display_label = tk.Label(
            self.screen_panel,
            text="⏳ No active presentation.\nClick '🖥️ Share' in the top bar to stream your desktop to all connected peers.",
            font=('Segoe UI', 12),
            bg=theme['input_bg'],
            fg=theme['text']
        )
        self.screen_display_label.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Participant Videos Panel
        self.videos_panel = tk.LabelFrame(
            self.left_column,
            text="  👥 Participant Webcams (P2P UDP Streams)  ",
            font=('Segoe UI', 11, 'bold'),
            bg=theme['panel_bg'],
            fg=theme['primary'],
            relief=tk.FLAT,
            highlightbackground=theme['border'],
            highlightthickness=2,
            bd=0
        )
        self.videos_panel.pack(fill=tk.BOTH, expand=False, pady=(0, 0))

        # Horizontal Scroll Canvas for Videos
        self.video_canvas = tk.Canvas(self.videos_panel, bg=theme['input_bg'], highlightthickness=0, height=210)
        self.video_scrollbar = tk.Scrollbar(self.videos_panel, orient="horizontal", command=self.video_canvas.xview)
        self.video_strip = tk.Frame(self.video_canvas, bg=theme['input_bg'])

        self.video_strip.bind("<Configure>", lambda e: self.video_canvas.configure(scrollregion=self.video_canvas.bbox("all")))
        self.video_canvas.create_window((0, 0), window=self.video_strip, anchor="nw")
        self.video_canvas.configure(xscrollcommand=self.video_scrollbar.set)

        self.video_canvas.pack(side="top", fill="both", expand=True, padx=6, pady=4)
        self.video_scrollbar.pack(side="bottom", fill="x", padx=6, pady=(0, 4))

        # Self Video Tile
        self.my_video_frame = tk.Frame(
            self.video_strip,
            bg=theme['panel_bg'],
            width=self.video_width,
            height=self.video_height,
            highlightbackground=theme['border'],
            highlightthickness=2
        )
        self.my_video_frame.pack(side=tk.LEFT, padx=5, pady=5)
        self.my_video_frame.pack_propagate(False)

        self.my_video_label = tk.Label(
            self.my_video_frame,
            text=f"📹 You ({self.username})\n\nCamera Off",
            font=('Segoe UI', 9, 'bold'),
            bg=theme['input_bg'],
            fg=theme['text']
        )
        self.my_video_label.pack(fill=tk.BOTH, expand=True)

        # 2. MIDDLE COLUMN: Connected Peers
        self.middle_column = tk.Frame(
            self.content_frame,
            bg=theme['panel_bg'],
            width=210,
            highlightbackground=theme['border'],
            highlightthickness=2
        )
        self.middle_column.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 8))
        self.middle_column.pack_propagate(False)

        self.peers_header = tk.Label(
            self.middle_column,
            text="👥 Mesh Peers (0)",
            font=('Segoe UI', 11, 'bold'),
            bg=theme['panel_bg'],
            fg=theme['primary'],
            padx=10,
            pady=10
        )
        self.peers_header.pack(anchor='w')

        self.peers_listbox = tk.Listbox(
            self.middle_column,
            font=('Segoe UI', 9),
            bg=theme['input_bg'],
            fg=theme['text'],
            relief=tk.FLAT,
            selectbackground=theme['primary'],
            selectforeground='#ffffff',
            bd=0,
            highlightthickness=0
        )
        self.peers_listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        # Quick action on selected peer
        peer_btn_box = tk.Frame(self.middle_column, bg=theme['panel_bg'])
        peer_btn_box.pack(fill=tk.X, padx=8, pady=(0, 8))
        tk.Button(
            peer_btn_box,
            text="Private Chat",
            font=('Segoe UI', 8, 'bold'),
            bg=theme['secondary'],
            fg='#ffffff',
            relief=tk.FLAT,
            command=self.initiate_private_chat
        ).pack(fill='x')

        # 3. RIGHT COLUMN: Workspace Tabs (Chat, Files, Stats)
        self.right_column = tk.Frame(
            self.content_frame,
            bg=theme['panel_bg'],
            width=380,
            highlightbackground=theme['border'],
            highlightthickness=2
        )
        self.right_column.pack(side=tk.RIGHT, fill=tk.BOTH)
        self.right_column.pack_propagate(False)

        # Tab Navigation Buttons
        tab_btn_bar = tk.Frame(self.right_column, bg=theme['panel_bg'])
        tab_btn_bar.pack(fill=tk.X)

        self.chat_tab_btn = tk.Button(
            tab_btn_bar,
            text="💬 Chat",
            font=('Segoe UI', 10, 'bold'),
            bg=theme['primary'],
            fg='#ffffff',
            relief=tk.FLAT,
            pady=8,
            cursor='hand2',
            command=lambda: self.switch_tab('chat')
        )
        self.chat_tab_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.files_tab_btn = tk.Button(
            tab_btn_bar,
            text="📁 Files",
            font=('Segoe UI', 10, 'bold'),
            bg=theme['input_bg'],
            fg=theme['text'],
            relief=tk.FLAT,
            pady=8,
            cursor='hand2',
            command=lambda: self.switch_tab('files')
        )
        self.files_tab_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.stats_tab_btn = tk.Button(
            tab_btn_bar,
            text="📊 Stats",
            font=('Segoe UI', 10, 'bold'),
            bg=theme['input_bg'],
            fg=theme['text'],
            relief=tk.FLAT,
            pady=8,
            cursor='hand2',
            command=lambda: self.switch_tab('stats')
        )
        self.stats_tab_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Tab 1: Chat View
        self.chat_view = tk.Frame(self.right_column, bg=theme['panel_bg'])
        self.chat_view.pack(fill=tk.BOTH, expand=True)

        self.chat_display = scrolledtext.ScrolledText(
            self.chat_view,
            font=('Segoe UI', 9),
            bg=theme['input_bg'],
            fg=theme['text'],
            relief=tk.FLAT,
            wrap=tk.WORD,
            insertbackground=theme['primary'],
            padx=10,
            pady=10
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.chat_display.config(state=tk.DISABLED)

        # Chat Input Row
        chat_input_frame = tk.Frame(self.chat_view, bg=theme['panel_bg'])
        chat_input_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

        c_box = tk.Frame(chat_input_frame, bg=theme['input_bg'], highlightbackground=theme['border'], highlightthickness=1)
        c_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.chat_entry = tk.Entry(c_box, font=('Segoe UI', 10), bg=theme['input_bg'],
                                   fg=theme['text'], relief=tk.FLAT, bd=0)
        self.chat_entry.pack(fill=tk.X, padx=8, pady=7)
        self.chat_entry.bind('<Return>', lambda e: self.send_chat_message())

        tk.Button(
            chat_input_frame,
            text="Send",
            font=('Segoe UI', 9, 'bold'),
            bg=theme['secondary'],
            fg='#ffffff',
            relief=tk.FLAT,
            padx=16,
            pady=6,
            cursor='hand2',
            command=self.send_chat_message
        ).pack(side=tk.RIGHT)

        # Tab 2: Files View
        self.files_view = tk.Frame(self.right_column, bg=theme['panel_bg'])

        tk.Button(
            self.files_view,
            text="📤 Share Local File with Mesh",
            font=('Segoe UI', 10, 'bold'),
            bg=theme['secondary'],
            fg='#ffffff',
            relief=tk.FLAT,
            pady=8,
            cursor='hand2',
            command=self.share_local_file
        ).pack(fill=tk.X, padx=10, pady=8)

        tk.Label(
            self.files_view,
            text="📂 Available Mesh Files (Double-click to Download):",
            font=('Segoe UI', 9, 'bold'),
            bg=theme['panel_bg'],
            fg=theme['text']
        ).pack(anchor='w', padx=10, pady=(4, 2))

        self.files_listbox = tk.Listbox(
            self.files_view,
            font=('Segoe UI', 9),
            bg=theme['input_bg'],
            fg=theme['text'],
            relief=tk.FLAT,
            selectbackground=theme['primary'],
            selectforeground='#ffffff',
            bd=0
        )
        self.files_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        self.files_listbox.bind('<Double-Button-1>', self.download_selected_file)

        # File Progress Bar & Status
        self.file_progress_var = tk.DoubleVar(value=0.0)
        self.file_progress_bar = ttk.Progressbar(self.files_view, variable=self.file_progress_var, maximum=100)
        self.file_progress_bar.pack(fill=tk.X, padx=10, pady=4)

        self.file_status_label = tk.Label(
            self.files_view,
            text="Ready. Files stream directly peer-to-peer.",
            font=('Segoe UI', 8),
            bg=theme['panel_bg'],
            fg=theme['text']
        )
        self.file_status_label.pack(anchor='w', padx=10, pady=(0, 8))

        # Tab 3: Network Stats View
        self.stats_view = tk.Frame(self.right_column, bg=theme['panel_bg'])
        self.stats_text = tk.Label(
            self.stats_view,
            text="",
            font=('Consolas', 9),
            bg=theme['input_bg'],
            fg=theme['text'],
            justify='left',
            anchor='nw',
            padx=12,
            pady=12
        )
        self.stats_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Welcome banner
        self.append_chat("System", f"Welcome {self.username}! P2P Collaboration node online.", is_system=True)

        # Schedule live stats updater
        self.update_stats_display()

    # =========================================================================
    # TAB & THEME SWITCHING
    # =========================================================================

    def switch_tab(self, tab_name: str):
        """Switch active workspace panel."""
        theme = self.current_theme
        for btn in (self.chat_tab_btn, self.files_tab_btn, self.stats_tab_btn):
            btn.config(bg=theme['input_bg'], fg=theme['text'])

        self.chat_view.pack_forget()
        self.files_view.pack_forget()
        self.stats_view.pack_forget()

        if tab_name == 'chat':
            self.chat_view.pack(fill=tk.BOTH, expand=True)
            self.chat_tab_btn.config(bg=theme['primary'], fg='#ffffff')
        elif tab_name == 'files':
            self.files_view.pack(fill=tk.BOTH, expand=True)
            self.files_tab_btn.config(bg=theme['primary'], fg='#ffffff')
        elif tab_name == 'stats':
            self.stats_view.pack(fill=tk.BOTH, expand=True)
            self.stats_tab_btn.config(bg=theme['primary'], fg='#ffffff')

    def on_theme_selected(self, event=None):
        """Handle theme switch from dropdown."""
        theme_key = self.theme_var.get()
        if theme_key in THEMES:
            self.current_theme = THEMES[theme_key]
            # Redraw interface with new palette
            self.apply_theme_to_ui()

    def apply_theme_to_ui(self):
        """Re-apply active colors to interface widgets."""
        theme = self.current_theme
        self.root.configure(bg=theme['bg'])
        self.main_container.configure(bg=theme['bg'])
        self.top_bar.configure(bg=theme['panel_bg'], highlightbackground=theme['border'])
        self.title_label.configure(bg=theme['panel_bg'], fg=theme['primary'])
        self.node_badge.configure(bg=theme['panel_bg'], fg=theme['text'])
        self.screen_panel.configure(bg=theme['panel_bg'], fg=theme['primary'], highlightbackground=theme['border'])
        self.videos_panel.configure(bg=theme['panel_bg'], fg=theme['primary'], highlightbackground=theme['border'])
        self.middle_column.configure(bg=theme['panel_bg'], highlightbackground=theme['border'])
        self.right_column.configure(bg=theme['panel_bg'], highlightbackground=theme['border'])
        self.peers_header.configure(bg=theme['panel_bg'], fg=theme['primary'])

    # =========================================================================
    # MEDIA TOGGLES & ACTIONS
    # =========================================================================

    def toggle_video(self):
        """Toggle local webcam video."""
        is_on = self.node.toggle_video()
        theme = self.current_theme
        if is_on:
            self.video_btn.config(bg=theme['secondary'], fg='#ffffff')
        else:
            self.video_btn.config(bg=theme['input_bg'], fg=theme['text'])
            self.my_video_label.config(text=f"📹 You ({self.username})\n\nCamera Off", image='')

    def toggle_audio(self):
        """Toggle microphone recording."""
        is_on = self.node.toggle_audio()
        theme = self.current_theme
        if is_on:
            self.audio_btn.config(bg=theme['secondary'], fg='#ffffff')
        else:
            self.audio_btn.config(bg=theme['input_bg'], fg=theme['text'])

    def toggle_screen_share(self):
        """Toggle desktop presentation."""
        if self.node.current_presenter == self.username:
            self.node.stop_screen_sharing()
            self.screen_btn.config(bg=self.current_theme['primary'], fg='#ffffff', text="🖥️ Share")
        else:
            success = self.node.start_screen_sharing()
            if success:
                self.screen_btn.config(bg='#ef4444', fg='#ffffff', text="⏹️ Stop")
            else:
                messagebox.showwarning("Screen Share", f"{self.node.current_presenter} is already presenting!")

    def connect_to_peer_quick(self):
        """Connect to peer entered in quick bar."""
        ip = self.quick_ip_entry.get().strip()
        try:
            port = int(self.quick_port_entry.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Port must be an integer")
            return

        threading.Thread(target=self.node.connect_to_peer, args=(ip, port), daemon=True).start()
        self.append_chat("System", f"Initiating connection to {ip}:{port}...", is_system=True)

    def send_chat_message(self):
        """Send message from chat box."""
        text = self.chat_entry.get().strip()
        if not text:
            return
        self.chat_entry.delete(0, tk.END)
        self.node.send_chat(text)

    def initiate_private_chat(self):
        """Pre-populate chat with private target."""
        sel = self.peers_listbox.curselection()
        if not sel:
            messagebox.showinfo("Private Chat", "Select a peer from the list first.")
            return
        idx = sel[0]
        peer_keys = list(self.node.peers.keys())
        if idx < len(peer_keys):
            p = self.node.peers[peer_keys[idx]]
            self.chat_entry.delete(0, tk.END)
            self.chat_entry.insert(0, f"@{p.username} ")
            self.chat_entry.focus()

    def share_local_file(self):
        """Select a local file and broadcast announcement."""
        path = filedialog.askopenfilename(title="Select File to Share with Mesh")
        if path:
            try:
                meta = self.node.share_file(path)
                self.append_chat("System", f"Offered '{meta['filename']}' ({meta['filesize'] // 1024} KB) to mesh.", is_system=True)
            except Exception as e:
                messagebox.showerror("File Error", str(e))

    def download_selected_file(self, event=None):
        """Trigger direct P2P download of selected file."""
        sel = self.files_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        files = list(self.node.file_manager.network_files.values())
        if idx >= len(files):
            return

        fmeta = files[idx]
        file_id = fmeta['file_id']
        filename = fmeta['filename']

        # Choose destination folder
        dest_dir = filedialog.askdirectory(title=f"Choose destination folder for '{filename}'")
        if dest_dir:
            try:
                self.file_status_label.config(text=f"Requesting '{filename}' directly from peer...")
                self.node.download_file(file_id, dest_dir)
            except Exception as e:
                messagebox.showerror("Download Error", str(e))

    # =========================================================================
    # EVENT HANDLERS (DISPATCHED ON UI THREAD VIA ui_queue)
    # =========================================================================

    def _ui_on_peer_joined(self, peer_id: str, username: str, info: dict):
        """A new peer connected directly or via PEX."""
        self.append_chat("System", f"{username} joined the P2P mesh.", is_system=True)
        self._refresh_peers_list()
        self._ensure_peer_video_tile(peer_id, username)

    def _ui_on_peer_left(self, peer_id: str, username: str):
        """A peer disconnected cleanly or timed out."""
        self.append_chat("System", f"{username} left the P2P mesh.", is_system=True)
        self._refresh_peers_list()
        self._remove_peer_video_tile(peer_id)

    def _refresh_peers_list(self):
        """Update participants listbox."""
        self.peers_listbox.delete(0, tk.END)
        with self.node.peers_lock:
            peers = list(self.node.peers.values())
        self.peers_header.config(text=f"👥 Mesh Peers ({len(peers)})")
        for p in peers:
            lat = f"{int(p.latency_ms)}ms" if p.latency_ms > 0 else "<1ms"
            self.peers_listbox.insert(tk.END, f"👤 {p.username} ({p.ip}:{p.tcp_port}) [{lat}]")

    def _ui_on_chat(self, sender: str, text: str, timestamp: str, is_private: bool):
        """Display chat line."""
        self.append_chat(sender, text, timestamp, is_private=is_private)

    def append_chat(self, sender: str, text: str, timestamp: str = None, is_system: bool = False, is_private: bool = False):
        """Append text line to ScrolledText widget."""
        if not timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S")

        self.chat_display.config(state=tk.NORMAL)
        if is_system:
            self.chat_display.insert(tk.END, f"[{timestamp}] ⚙️ {text}\n")
        elif is_private:
            self.chat_display.insert(tk.END, f"[{timestamp}] 🔒 (Private) {sender}: {text}\n")
        else:
            self.chat_display.insert(tk.END, f"[{timestamp}] {sender}: {text}\n")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    # ---------------- Video Display ----------------

    def _ensure_peer_video_tile(self, peer_id: str, username: str):
        """Create video container widget for remote peer if not present."""
        if peer_id in self.peer_video_labels:
            return

        theme = self.current_theme
        frame = tk.Frame(
            self.video_strip,
            bg=theme['panel_bg'],
            width=self.video_width,
            height=self.video_height,
            highlightbackground=theme['border'],
            highlightthickness=2
        )
        frame.pack(side=tk.LEFT, padx=5, pady=5)
        frame.pack_propagate(False)

        lbl = tk.Label(
            frame,
            text=f"📹 {username}\n\nConnecting video...",
            font=('Segoe UI', 9, 'bold'),
            bg=theme['input_bg'],
            fg=theme['text']
        )
        lbl.pack(fill=tk.BOTH, expand=True)

        self.peer_video_labels[peer_id] = (frame, lbl)

    def _remove_peer_video_tile(self, peer_id: str):
        """Remove video container when peer leaves."""
        if peer_id in self.peer_video_labels:
            frame, lbl = self.peer_video_labels.pop(peer_id)
            frame.destroy()

    def _ui_on_my_video_frame(self, frame_np):
        """Render local webcam preview."""
        try:
            rgb = cv2.cvtColor(frame_np, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            img = img.resize((self.video_width, self.video_height))
            photo = ImageTk.PhotoImage(image=img)
            self.my_video_label.config(image=photo, text="")
            self.my_video_photo_ref = photo
        except Exception:
            pass

    def _ui_on_video_frame(self, peer_id: str, username: str, jpeg_data: bytes):
        """Render incoming remote peer video frame."""
        self._ensure_peer_video_tile(peer_id, username)
        if peer_id not in self.peer_video_labels:
            return

        try:
            arr = np.frombuffer(jpeg_data, dtype=np.uint8)
            img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img_bgr is not None:
                rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                img = img.resize((self.video_width, self.video_height))
                photo = ImageTk.PhotoImage(image=img)
                _, lbl = self.peer_video_labels[peer_id]
                lbl.config(image=photo, text="")
                lbl.photo = photo  # Keep reference
        except Exception:
            pass

    # ---------------- Screen Share Display ----------------

    def _ui_on_presenter_changed(self, presenter: str):
        """Update screen share panel header and button state."""
        if presenter:
            self.screen_panel.config(text=f"  📺 Screen Share (Presenter: {presenter})  ")
            if presenter == self.username:
                self.screen_btn.config(bg='#ef4444', fg='#ffffff', text="⏹️ Stop")
            else:
                self.screen_btn.config(bg=self.current_theme['primary'], fg='#ffffff', text="🖥️ Share")
        else:
            self.screen_panel.config(text="  📺 Screen Share (Waiting for Presenter)  ")
            self.screen_display_label.config(
                image='',
                text="⏳ No active presentation.\nClick '🖥️ Share' in the top bar to stream your desktop to all connected peers."
            )
            self.screen_btn.config(bg=self.current_theme['primary'], fg='#ffffff', text="🖥️ Share")

    def _ui_on_screen_frame(self, presenter: str, jpeg_data: bytes):
        """Render received screen frame in presentation canvas."""
        try:
            arr = np.frombuffer(jpeg_data, dtype=np.uint8)
            img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img_bgr is not None:
                # Scale dynamically to panel size
                lbl_w = max(400, self.screen_display_label.winfo_width())
                lbl_h = max(300, self.screen_display_label.winfo_height())

                rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                img.thumbnail((lbl_w, lbl_h), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image=img)

                self.screen_display_label.config(image=photo, text="")
                self.screen_photo_ref = photo
        except Exception:
            pass

    # ---------------- File Transfer Display ----------------

    def _ui_on_file_available(self, meta: dict):
        """Refresh file listbox with newly announced file."""
        self._refresh_file_list()

    def _refresh_file_list(self):
        """Populate Files tab listbox."""
        self.files_listbox.delete(0, tk.END)
        for fid, f in self.node.file_manager.network_files.items():
            kb = f['filesize'] // 1024
            self.files_listbox.insert(tk.END, f"📄 {f['filename']} ({kb} KB) — from {f['owner_username']}")

    def _ui_on_file_progress(self, tid: str, name: str, rec: int, tot: int, pct: float):
        """Update progress bar."""
        self.file_progress_var.set(pct)
        self.file_status_label.config(text=f"Downloading '{name}': {int(pct)}% ({rec // 1024} / {tot // 1024} KB)")

    def _ui_on_file_complete(self, tid: str, name: str, path: str):
        """File download finished and verified."""
        self.file_progress_var.set(100.0)
        self.file_status_label.config(text=f"✅ '{name}' verified & saved to {path}!")
        self.append_chat("System", f"File '{name}' downloaded successfully and SHA-256 verified.", is_system=True)
        messagebox.showinfo("Download Complete", f"File successfully saved:\n{path}")

    def _ui_on_file_error(self, tid: str, err: str):
        """Handle file transfer error."""
        self.file_status_label.config(text=f"❌ Error: {err}")
        messagebox.showerror("Transfer Error", err)

    def _ui_on_status(self, text: str):
        """Display network status line."""
        pass

    # ---------------- Live Stats Display ----------------

    def update_stats_display(self):
        """Update real-time network metrics panel."""
        if self.node and self.node.running:
            uptime = int(time.time() - self.node.stats["start_time"])
            kb_sent = self.node.stats["bytes_sent"] / 1024.0
            kb_recv = self.node.stats["bytes_recv"] / 1024.0
            with self.node.peers_lock:
                peer_count = len(self.node.peers)

            stats_str = (
                f"=== P2P MESH NETWORK METRICS ===\n\n"
                f"Node ID:          {self.node.peer_id}\n"
                f"Username:         {self.username}\n"
                f"Local Endpoint:   {self.node.local_ip}:{self.node.tcp_port} (TCP)\n"
                f"Media Endpoint:   {self.node.local_ip}:{self.node.udp_port} (UDP)\n"
                f"Discovery Port:   UDP 5550 (LAN Broadcast)\n\n"
                f"Connected Peers:  {peer_count} direct full-mesh links\n"
                f"Screen Presenter: {self.node.current_presenter or 'None'}\n"
                f"Mesh Uptime:      {uptime} seconds\n\n"
                f"Bytes Sent:       {kb_sent:.1f} KB ({self.node.stats['packets_sent']} frames)\n"
                f"Bytes Received:   {kb_recv:.1f} KB ({self.node.stats['packets_recv']} frames)\n\n"
                f"Architecture:     Pure Decentralized Servent\n"
                f"Integrity:        SHA-256 Verified\n"
                f"Framing:          7-Byte Atomic Binary TCP Header"
            )
            self.stats_text.config(text=stats_str)

        self.root.after(1000, self.update_stats_display)

    def on_closing(self):
        """Gracefully exit."""
        if self.node:
            self.node.stop()
        self.root.destroy()

    def run(self):
        """Start Tkinter main event loop."""
        self.root.mainloop()
