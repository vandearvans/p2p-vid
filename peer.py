"""
P2P Collaboration System - Main Application Entrypoint
Run this script on any computer on the LAN to launch a collaboration node.
No centralized server is required.
"""
import sys
import os
import argparse
import logging

# Ensure root directory is in Python module search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows console encoding safeguard
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("P2P")


def main():
    parser = argparse.ArgumentParser(description="P2P Multi-User Collaboration System")
    parser.add_argument("--username", "-u", type=str, default="", help="Username for this peer")
    parser.add_argument("--tcp", type=int, default=5555, help="Listening TCP port (default: 5555)")
    parser.add_argument("--udp", type=int, default=5556, help="Listening UDP port (default: 5556)")
    parser.add_argument("--connect", "-c", type=str, default="", help="Bootstrap peer address (IP:Port)")
    parser.add_argument("--auto", action="store_true", help="Auto-start and connect directly to mesh")
    args = parser.parse_args()

    from ui.main_window import CollaborationApp

    app = CollaborationApp()

    # Pre-populate fields if arguments were provided
    if args.username:
        app.username_entry.delete(0, 'end')
        app.username_entry.insert(0, args.username)
    if args.tcp != 5555:
        app.tcp_port_entry.delete(0, 'end')
        app.tcp_port_entry.insert(0, str(args.tcp))
    if args.udp != 5556:
        app.udp_port_entry.delete(0, 'end')
        app.udp_port_entry.insert(0, str(args.udp))
    if args.connect:
        app.bootstrap_entry.delete(0, 'end')
        app.bootstrap_entry.insert(0, args.connect)
    if args.auto:
        app.root.after(100, app.start_p2p_mesh)

    print("=" * 70)
    print("🌐 P2P MULTI-USER COLLABORATION SYSTEM (COMPUTER NETWORKS)")
    print("=" * 70)
    print("Zero Server Architecture • Full Mesh Overlay • LAN Auto-Discovery")
    print("Video & Audio (UDP) • Screen Sharing & Files & Chat (TCP)")
    print("=" * 70)

    app.run()


if __name__ == '__main__':
    main()
