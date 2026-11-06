"""
Peer-to-Peer LAN Auto-Discovery Module
Uses UDP Broadcast Beaconing (Zero-Configuration Networking) to automatically
discover collaboration peers on the local network without requiring a centralized server.
"""
import socket
import json
import threading
import time
import logging

logger = logging.getLogger(__name__)

DISCOVERY_MAGIC = "P2P_COLLAB_DISCOVERY"


def get_local_lan_ip() -> str:
    """
    Determine the primary local LAN IP address of this machine.
    Avoids 127.0.0.1 by testing outbound routing table.
    """
    for target in [("10.255.255.255", 1), ("192.168.1.1", 80), ("8.8.8.8", 80)]:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(0.2)
            s.connect(target)
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        finally:
            s.close()
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"


class DiscoveryBeacon:
    """
    Periodically broadcasts peer identity onto the LAN and listens for peers.
    """
    def __init__(self, peer_id: str, username: str, tcp_port: int, udp_port: int,
                 discovery_port: int = 5550, interval: float = 3.0, on_peer_found=None):
        self.peer_id = peer_id
        self.username = username
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.discovery_port = discovery_port
        self.interval = interval
        self.on_peer_found = on_peer_found

        self.local_ip = get_local_lan_ip()
        self.running = False
        self.listener_socket = None
        self.sender_socket = None
        self.listen_thread = None
        self.broadcast_thread = None

    def start(self):
        """Start discovery listener and broadcaster threads."""
        self.running = True

        # Setup listener socket (binds to discovery port with REUSEADDR)
        try:
            self.listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # On Windows/Linux, SO_BROADCAST is good practice
            self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.listener_socket.bind(('', self.discovery_port))
            self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.listen_thread.start()
            logger.info(f"[DISCOVERY] Listening for LAN beacons on UDP port {self.discovery_port}")
        except Exception as e:
            logger.warning(f"[DISCOVERY] Could not bind listener on port {self.discovery_port}: {e}")

        # Setup sender socket
        try:
            self.sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sender_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
            self.broadcast_thread.start()
            logger.info(f"[DISCOVERY] Broadcasting LAN beacons every {self.interval}s")
        except Exception as e:
            logger.error(f"[DISCOVERY] Could not setup broadcast sender: {e}")

    def _broadcast_loop(self):
        """Periodically broadcast discovery message to LAN."""
        while self.running:
            try:
                beacon_data = {
                    "magic": DISCOVERY_MAGIC,
                    "peer_id": self.peer_id,
                    "username": self.username,
                    "ip": self.local_ip,
                    "tcp_port": self.tcp_port,
                    "udp_port": self.udp_port,
                    "timestamp": time.time()
                }
                msg_bytes = json.dumps(beacon_data).encode('utf-8')
                
                # Broadcast on standard broadcast addresses
                for target_ip in ['<broadcast>', '255.255.255.255', '127.0.0.1']:
                    try:
                        self.sender_socket.sendto(msg_bytes, (target_ip, self.discovery_port))
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"[DISCOVERY] Broadcast error: {e}")

            time.sleep(self.interval)

    def _listen_loop(self):
        """Listen for beacons from other peers."""
        while self.running and self.listener_socket:
            try:
                data, addr = self.listener_socket.recvfrom(2048)
                msg = json.loads(data.decode('utf-8'))
                
                if msg.get("magic") != DISCOVERY_MAGIC:
                    continue

                remote_peer_id = msg.get("peer_id")
                if not remote_peer_id or remote_peer_id == self.peer_id:
                    # Ignore own beacons
                    continue

                # Sender IP: use the IP reported by socket if running across different hosts
                sender_ip = addr[0]
                # If running on same machine (127.0.0.1 or local IP), keep correct address
                reported_ip = msg.get("ip", sender_ip)
                peer_ip = sender_ip if sender_ip not in ("127.0.0.1", self.local_ip) else reported_ip

                peer_info = {
                    "peer_id": remote_peer_id,
                    "username": msg.get("username", "Unknown"),
                    "ip": peer_ip,
                    "tcp_port": int(msg.get("tcp_port", 5555)),
                    "udp_port": int(msg.get("udp_port", 5556)),
                    "last_seen": time.time()
                }

                if self.on_peer_found:
                    self.on_peer_found(peer_info)

            except Exception:
                if not self.running:
                    break

    def stop(self):
        """Stop threads and close sockets."""
        self.running = False
        if self.listener_socket:
            try:
                self.listener_socket.close()
            except Exception:
                pass
        if self.sender_socket:
            try:
                self.sender_socket.close()
            except Exception:
                pass
