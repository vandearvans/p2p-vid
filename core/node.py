"""
Core Peer-to-Peer Node Implementation.
Manages full-mesh TCP/UDP overlay networking, peer discovery, peer exchange (PEX),
distributed media routing, screen sharing floor control, and file transfers.
"""
import socket
import threading
import time
import uuid
import logging
from typing import Dict, Optional, Callable, List

from config import (
    DEFAULT_TCP_PORT,
    DEFAULT_UDP_PORT,
    DEFAULT_DISCOVERY_PORT,
    HEARTBEAT_INTERVAL,
    PEER_TIMEOUT,
    MSG_TYPE_CONTROL,
    MSG_TYPE_SCREEN,
    MSG_TYPE_FILE_CHUNK
)
from core.protocol import (
    FrameParser,
    build_control_frame,
    build_screen_frame,
    parse_control_payload,
    parse_file_chunk_payload,
    build_udp_video_packet,
    build_udp_audio_packet,
    parse_udp_packet
)
from core.discovery import DiscoveryBeacon, get_local_lan_ip
from core.file_transfer import FileTransferManager
from core.media import AudioEngine, VideoEngine
from core.screen_share import ScreenShareEngine

logger = logging.getLogger(__name__)


class PeerConnection:
    """Represents an active, direct point-to-point TCP link with a remote peer."""
    def __init__(self, sock: socket.socket, addr: tuple):
        self.sock = sock
        self.addr = addr
        self.peer_id: Optional[str] = None
        self.username: str = "Unknown"
        self.ip: str = addr[0]
        self.tcp_port: int = addr[1]
        self.udp_port: int = DEFAULT_UDP_PORT
        
        self.send_lock = threading.Lock()
        self.parser = FrameParser()
        self.last_seen = time.time()
        self.latency_ms: float = 0.0
        self.is_connected = True

    def send(self, data: bytes):
        """Thread-safe frame transmission."""
        if not self.is_connected:
            return
        with self.send_lock:
            try:
                self.sock.sendall(data)
            except Exception as e:
                logger.debug(f"[PEER_CONN] Error sending to {self.username}: {e}")
                self.is_connected = False

    def close(self):
        """Close socket connection."""
        self.is_connected = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class P2PNode:
    """
    Main Peer-to-Peer Node (Servent) Engine.
    Combines client and server capabilities into an autonomous LAN collaboration agent.
    """
    def __init__(self, username: str, requested_tcp_port: int = DEFAULT_TCP_PORT,
                 requested_udp_port: int = DEFAULT_UDP_PORT, enable_discovery: bool = True):
        self.peer_id = f"{username.lower()}_{uuid.uuid4().hex[:6]}"
        self.username = username
        self.local_ip = get_local_lan_ip()
        self.enable_discovery = enable_discovery

        # Callback registry for UI event notification
        self.callbacks = {
            "on_peer_joined": None,       # (peer_id, username, info)
            "on_peer_left": None,         # (peer_id, username)
            "on_chat_message": None,      # (sender_username, text, timestamp, is_private)
            "on_video_frame": None,       # (peer_id, username, frame_data)
            "on_screen_frame": None,      # (presenter_username, frame_data)
            "on_presenter_changed": None, # (presenter_username_or_None)
            "on_file_available": None,    # (file_meta)
            "on_file_progress": None,     # (transfer_id, filename, received, total, pct)
            "on_file_complete": None,     # (transfer_id, filename, local_path)
            "on_file_error": None,        # (transfer_id, err_msg)
            "on_status_msg": None         # (text)
        }

        # Network state
        self.peers: Dict[str, PeerConnection] = {}
        self.peers_lock = threading.RLock()
        self.current_presenter: Optional[str] = None  # username of active screen presenter
        self.running = False

        # Bind TCP & UDP sockets (auto-incrementing port if busy)
        self.tcp_sock, self.tcp_port = self._bind_tcp(requested_tcp_port)
        self.udp_sock, self.udp_port = self._bind_udp(requested_udp_port)

        # Subsystems
        self.file_manager = FileTransferManager()
        self.audio_engine = AudioEngine(on_audio_chunk=self._on_local_audio)
        self.video_engine = VideoEngine(username=self.username,
                                        on_local_frame=self._on_local_video_frame,
                                        on_video_packet=self._on_local_video_packet)
        self.screen_engine = ScreenShareEngine(on_frame=self._on_local_screen_frame)
        self.discovery = DiscoveryBeacon(
            peer_id=self.peer_id,
            username=self.username,
            tcp_port=self.tcp_port,
            udp_port=self.udp_port,
            discovery_port=DEFAULT_DISCOVERY_PORT,
            on_peer_found=self._on_discovered_peer
        ) if enable_discovery else None

        # Network statistics
        self.stats = {
            "bytes_sent": 0,
            "bytes_recv": 0,
            "packets_sent": 0,
            "packets_recv": 0,
            "start_time": time.time()
        }

    def _bind_tcp(self, start_port: int):
        """Bind TCP listener socket, trying subsequent ports if already occupied."""
        port = start_port
        while port < start_port + 100:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.bind(('', port))
                s.listen(25)
                logger.info(f"[P2P_NODE] TCP listening on port {port}")
                return s, port
            except OSError:
                port += 1
        raise RuntimeError("No available TCP port found in range!")

    def _bind_udp(self, start_port: int):
        """Bind UDP media socket, trying subsequent ports if occupied."""
        port = start_port
        while port < start_port + 100:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2097152)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2097152)
                s.bind(('', port))
                logger.info(f"[P2P_NODE] UDP listening on port {port}")
                return s, port
            except OSError:
                port += 1
        raise RuntimeError("No available UDP port found in range!")

    def set_callback(self, event_name: str, func: Callable):
        """Register an event listener for UI binding."""
        if event_name in self.callbacks:
            self.callbacks[event_name] = func

    def _trigger(self, event_name: str, *args):
        """Safely fire a callback if registered."""
        func = self.callbacks.get(event_name)
        if func:
            try:
                func(*args)
            except Exception as e:
                logger.debug(f"[P2P_NODE] Callback error for '{event_name}': {e}")

    # =========================================================================
    # LIFECYCLE & THREADS
    # =========================================================================

    def start(self):
        """Start P2P network threads."""
        self.running = True

        # Accept incoming TCP connections
        threading.Thread(target=self._tcp_accept_loop, daemon=True).start()

        # Receive incoming UDP media packets (video/audio)
        threading.Thread(target=self._udp_media_loop, daemon=True).start()

        # Heartbeat & peer monitor
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

        # Start audio playback engine
        self.audio_engine.start()

        # Start LAN discovery beacon
        if self.discovery:
            self.discovery.start()

        self._trigger("on_status_msg", f"P2P node started on {self.local_ip}:{self.tcp_port}")

    def stop(self):
        """Gracefully disconnect from mesh and shutdown all threads."""
        if not self.running:
            return
        self.running = False

        # Broadcast leave event
        self.broadcast_control({
            "type": "PEER_LEAVE",
            "peer_id": self.peer_id,
            "username": self.username
        })

        if self.discovery:
            self.discovery.stop()

        self.screen_engine.stop()
        self.video_engine.stop()
        self.audio_engine.stop()

        with self.peers_lock:
            for p in list(self.peers.values()):
                p.close()
            self.peers.clear()

        try:
            self.tcp_sock.close()
        except Exception:
            pass
        try:
            self.udp_sock.close()
        except Exception:
            pass

    # =========================================================================
    # PEER CONNECTION & MESH MANAGEMENT
    # =========================================================================

    def connect_to_peer(self, host: str, port: int) -> bool:
        """
        Manually or programmatically initiate an outgoing TCP connection to a peer.
        Enables cross-subnet connection and localhost multi-instance testing.
        """
        # Resolve localhost
        if host in ("localhost", "127.0.0.1") and host != self.local_ip:
            target_ip = "127.0.0.1"
        else:
            target_ip = host

        # Prevent connecting to self
        if (target_ip in ("127.0.0.1", self.local_ip)) and port == self.tcp_port:
            return False

        # Check if already connected to this endpoint
        with self.peers_lock:
            for p in self.peers.values():
                if p.ip == target_ip and p.tcp_port == port:
                    return False

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(5.0)
            sock.connect((target_ip, port))
            sock.settimeout(None)

            conn = PeerConnection(sock, (target_ip, port))
            
            # Send initial Handshake
            handshake = {
                "type": "HANDSHAKE",
                "peer_id": self.peer_id,
                "username": self.username,
                "ip": self.local_ip,
                "tcp_port": self.tcp_port,
                "udp_port": self.udp_port,
                "timestamp": time.time()
            }
            conn.send(build_control_frame(handshake))

            threading.Thread(target=self._peer_receiver_loop, args=(conn,), daemon=True).start()
            return True
        except Exception as e:
            logger.debug(f"[P2P_NODE] Failed to connect to peer {host}:{port}: {e}")
            return False

    def _tcp_accept_loop(self):
        """Accept incoming TCP connections from other peers."""
        while self.running:
            try:
                client_sock, addr = self.tcp_sock.accept()
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                conn = PeerConnection(client_sock, addr)
                threading.Thread(target=self._peer_receiver_loop, args=(conn,), daemon=True).start()
            except Exception:
                if not self.running:
                    break

    def _peer_receiver_loop(self, conn: PeerConnection):
        """Dedicated TCP receive thread for an individual peer."""
        while self.running and conn.is_connected:
            try:
                data = conn.sock.recv(65536)
                if not data:
                    break

                self.stats["bytes_recv"] += len(data)
                self.stats["packets_recv"] += 1
                conn.last_seen = time.time()
                conn.parser.feed(data)

                # Process all fully framed messages in buffer
                while frame := conn.parser.next_frame():
                    msg_type, payload = frame
                    if msg_type == MSG_TYPE_CONTROL:
                        msg = parse_control_payload(payload)
                        self._handle_control_message(conn, msg)
                    elif msg_type == MSG_TYPE_SCREEN:
                        if self.current_presenter and self.current_presenter != self.username:
                            self._trigger("on_screen_frame", self.current_presenter, payload)
                    elif msg_type == MSG_TYPE_FILE_CHUNK:
                        meta, chunk_data = parse_file_chunk_payload(payload)
                        self.file_manager.process_incoming_chunk(meta, chunk_data)

            except Exception as e:
                logger.debug(f"[P2P_NODE] Connection exception with {conn.username}: {e}")
                break

        # Cleanup on disconnection
        self._disconnect_peer(conn)

    def _disconnect_peer(self, conn: PeerConnection):
        """Remove disconnected peer and notify mesh."""
        peer_id = conn.peer_id
        username = conn.username
        conn.close()

        with self.peers_lock:
            if peer_id and peer_id in self.peers:
                del self.peers[peer_id]

        if peer_id:
            logger.info(f"[P2P_NODE] Peer '{username}' disconnected.")
            self.file_manager.remove_peer_files(peer_id)
            if self.current_presenter == username:
                self.current_presenter = None
                self._trigger("on_presenter_changed", None)
            self._trigger("on_peer_left", peer_id, username)

    def _handle_control_message(self, conn: PeerConnection, msg: dict):
        """Process incoming JSON control/signaling frames."""
        m_type = msg.get("type")

        # ----------------- 1. HANDSHAKE -----------------
        if m_type == "HANDSHAKE":
            remote_id = msg.get("peer_id")
            remote_user = msg.get("username", "Unknown")
            remote_tcp = int(msg.get("tcp_port", DEFAULT_TCP_PORT))
            remote_udp = int(msg.get("udp_port", DEFAULT_UDP_PORT))
            remote_ip = conn.addr[0] if conn.addr[0] not in ("127.0.0.1", self.local_ip) else msg.get("ip", conn.addr[0])

            # Simultaneous Connection Tie-Breaker
            with self.peers_lock:
                if remote_id in self.peers:
                    # Duplicate connection detected; keep connection initiated by higher peer_id
                    if self.peer_id > remote_id:
                        conn.close()
                        return
                    else:
                        existing = self.peers[remote_id]
                        existing.close()

                conn.peer_id = remote_id
                conn.username = remote_user
                conn.ip = remote_ip
                conn.tcp_port = remote_tcp
                conn.udp_port = remote_udp
                self.peers[remote_id] = conn

            # Reply with HANDSHAKE_ACK and known peers for Peer Exchange (PEX)
            with self.peers_lock:
                known_peers = [
                    {
                        "peer_id": p.peer_id,
                        "username": p.username,
                        "ip": p.ip,
                        "tcp_port": p.tcp_port,
                        "udp_port": p.udp_port
                    }
                    for p in self.peers.values()
                    if p.peer_id and p.peer_id != remote_id
                ]

            ack = {
                "type": "HANDSHAKE_ACK",
                "peer_id": self.peer_id,
                "username": self.username,
                "ip": self.local_ip,
                "tcp_port": self.tcp_port,
                "udp_port": self.udp_port,
                "known_peers": known_peers,
                "presenter": self.current_presenter,
                "files": list(self.file_manager.network_files.values())
            }
            conn.send(build_control_frame(ack))
            self._trigger("on_peer_joined", remote_id, remote_user, {"ip": remote_ip, "port": remote_tcp})

        # ----------------- 2. HANDSHAKE_ACK -----------------
        elif m_type == "HANDSHAKE_ACK":
            remote_id = msg.get("peer_id")
            remote_user = msg.get("username", "Unknown")
            remote_tcp = int(msg.get("tcp_port", DEFAULT_TCP_PORT))
            remote_udp = int(msg.get("udp_port", DEFAULT_UDP_PORT))
            remote_ip = conn.addr[0] if conn.addr[0] not in ("127.0.0.1", self.local_ip) else msg.get("ip", conn.addr[0])

            conn.peer_id = remote_id
            conn.username = remote_user
            conn.ip = remote_ip
            conn.tcp_port = remote_tcp
            conn.udp_port = remote_udp

            with self.peers_lock:
                self.peers[remote_id] = conn

            self._trigger("on_peer_joined", remote_id, remote_user, {"ip": remote_ip, "port": remote_tcp})

            if msg.get("presenter"):
                self.current_presenter = msg.get("presenter")
                self._trigger("on_presenter_changed", self.current_presenter)

            # Sync file catalog
            for fmeta in msg.get("files", []):
                self.file_manager.register_network_file(fmeta)
                self._trigger("on_file_available", fmeta)

            # Execute Peer Exchange (PEX): connect to all other known mesh peers
            for peer_info in msg.get("known_peers", []):
                p_id = peer_info.get("peer_id")
                if p_id and p_id != self.peer_id and p_id not in self.peers:
                    self.connect_to_peer(peer_info["ip"], peer_info["tcp_port"])

        # ----------------- 3. CHAT -----------------
        elif m_type == "CHAT":
            sender = msg.get("username", conn.username)
            text = msg.get("text", "")
            ts = msg.get("timestamp", time.strftime("%H:%M:%S"))
            is_private = msg.get("is_private", False)
            self._trigger("on_chat_message", sender, text, ts, is_private)

        # ----------------- 4. SCREEN SHARING FLOOR CONTROL -----------------
        elif m_type == "SCREEN_SHARE_START":
            presenter = msg.get("username", conn.username)
            self.current_presenter = presenter
            self._trigger("on_presenter_changed", presenter)

        elif m_type == "SCREEN_SHARE_STOP":
            if self.current_presenter == msg.get("username", conn.username):
                self.current_presenter = None
                self._trigger("on_presenter_changed", None)

        # ----------------- 5. FILE ANNOUNCEMENT & REQUEST -----------------
        elif m_type == "FILE_ANNOUNCE":
            file_meta = msg.get("file")
            if file_meta:
                self.file_manager.register_network_file(file_meta)
                self._trigger("on_file_available", file_meta)

        elif m_type == "FILE_REQUEST":
            file_id = msg.get("file_id")
            transfer_id = msg.get("transfer_id")
            # Stream the requested file chunks directly over conn
            threading.Thread(
                target=self.file_manager.stream_file_to_peer,
                args=(file_id, transfer_id, conn.send, lambda: not conn.is_connected),
                daemon=True
            ).start()

        # ----------------- 6. HEARTBEATS (PING / PONG) -----------------
        elif m_type == "PING":
            conn.send(build_control_frame({
                "type": "PONG",
                "echo_ts": msg.get("ts", time.time())
            }))

        elif m_type == "PONG":
            sent_ts = msg.get("echo_ts", time.time())
            conn.latency_ms = max(0.0, (time.time() - sent_ts) * 1000.0)

        # ----------------- 7. PEER LEAVE -----------------
        elif m_type == "PEER_LEAVE":
            self._disconnect_peer(conn)

    def _heartbeat_loop(self):
        """Periodic keep-alive ping and dead peer prune."""
        while self.running:
            time.sleep(HEARTBEAT_INTERVAL)
            now = time.time()
            with self.peers_lock:
                peers_list = list(self.peers.values())

            for p in peers_list:
                if not p.is_connected or (now - p.last_seen > PEER_TIMEOUT):
                    logger.warning(f"[P2P_NODE] Peer {p.username} timed out; dropping connection.")
                    self._disconnect_peer(p)
                else:
                    p.send(build_control_frame({"type": "PING", "ts": now}))

    def _on_discovered_peer(self, peer_info: dict):
        """Invoked when UDP broadcast beacon detects a LAN peer."""
        p_id = peer_info.get("peer_id")
        if p_id and p_id != self.peer_id:
            with self.peers_lock:
                already_connected = p_id in self.peers
            if not already_connected:
                logger.info(f"[P2P_NODE] Auto-discovered LAN peer: {peer_info['username']} ({peer_info['ip']}:{peer_info['tcp_port']})")
                self.connect_to_peer(peer_info["ip"], peer_info["tcp_port"])

    # =========================================================================
    # UDP MEDIA STREAMING (VIDEO / AUDIO)
    # =========================================================================

    def _udp_media_loop(self):
        """Receive incoming UDP datagrams containing real-time video or audio."""
        while self.running:
            try:
                data, addr = self.udp_sock.recvfrom(65535)
                if not data:
                    continue

                self.stats["bytes_recv"] += len(data)
                self.stats["packets_recv"] += 1

                parsed = parse_udp_packet(data)
                if not parsed:
                    continue

                pkt_type, peer_id, sender_username, payload = parsed
                if peer_id == self.peer_id:
                    continue  # Ignore self packets

                if pkt_type == "VID":
                    self._trigger("on_video_frame", peer_id, sender_username, payload)
                elif pkt_type == "AUD":
                    self.audio_engine.feed_audio(payload)

            except Exception:
                if not self.running:
                    break

    def _on_local_audio(self, pcm_bytes: bytes):
        """Microphone callback: transmit audio datagram to all mesh peers over UDP."""
        if not self.peers:
            return
        packet = build_udp_audio_packet(self.peer_id, self.username, pcm_bytes)
        with self.peers_lock:
            endpoints = [(p.ip, p.udp_port) for p in self.peers.values() if p.is_connected]

        for ip, port in endpoints:
            try:
                self.udp_sock.sendto(packet, (ip, port))
                self.stats["bytes_sent"] += len(packet)
                self.stats["packets_sent"] += 1
            except Exception:
                pass

    def _on_local_video_frame(self, frame_np):
        """Webcam callback for local preview."""
        pass

    def _on_local_video_packet(self, jpeg_bytes: bytes):
        """Webcam callback: transmit JPEG video datagram to all mesh peers over UDP."""
        if not self.peers:
            return
        packet = build_udp_video_packet(self.peer_id, self.username, jpeg_bytes)
        with self.peers_lock:
            endpoints = [(p.ip, p.udp_port) for p in self.peers.values() if p.is_connected]

        for ip, port in endpoints:
            try:
                self.udp_sock.sendto(packet, (ip, port))
                self.stats["bytes_sent"] += len(packet)
                self.stats["packets_sent"] += 1
            except Exception:
                pass

    def _on_local_screen_frame(self, jpeg_bytes: bytes):
        """Desktop capture callback: broadcast screen frame over TCP."""
        frame = build_screen_frame(jpeg_bytes)
        self.broadcast_raw(frame)

    # =========================================================================
    # PUBLIC HIGH-LEVEL CONTROLS
    # =========================================================================

    def send_chat(self, text: str, recipient_peer_id: Optional[str] = None):
        """Send a public broadcast or private direct message."""
        ts = time.strftime("%H:%M:%S")
        msg = {
            "type": "CHAT",
            "username": self.username,
            "text": text,
            "timestamp": ts,
            "is_private": bool(recipient_peer_id)
        }

        if recipient_peer_id:
            with self.peers_lock:
                peer = self.peers.get(recipient_peer_id)
            if peer:
                peer.send(build_control_frame(msg))
        else:
            self.broadcast_control(msg)

        # Echo to own local UI
        self._trigger("on_chat_message", self.username, text, ts, bool(recipient_peer_id))

    def broadcast_control(self, msg: dict):
        """Send framed control message to all active peers."""
        frame = build_control_frame(msg)
        self.broadcast_raw(frame)

    def broadcast_raw(self, raw_bytes: bytes):
        """Send raw framed bytes to all connected peers."""
        with self.peers_lock:
            peers_list = list(self.peers.values())
        for p in peers_list:
            if p.is_connected:
                p.send(raw_bytes)
                self.stats["bytes_sent"] += len(raw_bytes)
                self.stats["packets_sent"] += 1

    def share_file(self, filepath: str) -> dict:
        """Share a local file with the entire mesh."""
        meta = self.file_manager.share_file(filepath, self.peer_id, self.username)
        self.broadcast_control({"type": "FILE_ANNOUNCE", "file": meta})
        self._trigger("on_file_available", meta)
        return meta

    def download_file(self, file_id: str, dest_dir: str):
        """Request and download a file directly from offering peer."""
        def on_prog(tid, name, rec, tot, pct):
            self._trigger("on_file_progress", tid, name, rec, tot, pct)

        def on_comp(tid, name, path):
            self._trigger("on_file_complete", tid, name, path)

        def on_err(tid, err):
            self._trigger("on_file_error", tid, err)

        transfer_id, owner_id, req = self.file_manager.create_download_session(
            file_id=file_id,
            dest_dir=dest_dir,
            on_progress=on_prog,
            on_complete=on_comp,
            on_error=on_err
        )

        with self.peers_lock:
            owner = self.peers.get(owner_id)

        if not owner or not owner.is_connected:
            raise ConnectionError("File owner is no longer online!")

        owner.send(build_control_frame(req))
        return transfer_id

    def start_screen_sharing(self) -> bool:
        """Acquire floor control and begin streaming screen frames."""
        if self.current_presenter and self.current_presenter != self.username:
            return False  # Screen share floor already taken

        self.current_presenter = self.username
        self.broadcast_control({
            "type": "SCREEN_SHARE_START",
            "username": self.username
        })
        self._trigger("on_presenter_changed", self.username)
        self.screen_engine.start()
        return True

    def stop_screen_sharing(self):
        """Release floor control and stop screen capture."""
        if self.current_presenter == self.username:
            self.screen_engine.stop()
            self.current_presenter = None
            self.broadcast_control({
                "type": "SCREEN_SHARE_STOP",
                "username": self.username
            })
            self._trigger("on_presenter_changed", None)

    def toggle_video(self) -> bool:
        """Toggle webcam video transmission."""
        if self.video_engine.running:
            self.video_engine.stop()
            return False
        else:
            self.video_engine.start()
            return True

    def toggle_audio(self) -> bool:
        """Toggle microphone capture."""
        if self.audio_engine.recording:
            self.audio_engine.stop_recording()
            return False
        else:
            return self.audio_engine.start_recording()
