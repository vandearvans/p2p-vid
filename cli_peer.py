"""
Headless / Terminal-Based P2P Collaboration Peer Node
Ideal for scripted testing, headless environments, or multi-terminal benchmarking.
"""
import sys
import os
import time
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.node import P2PNode

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')


def main():
    parser = argparse.ArgumentParser(description="Headless P2P Collaboration Peer")
    parser.add_argument("--username", "-u", type=str, default="CLI_Peer", help="Username")
    parser.add_argument("--tcp", type=int, default=5555, help="TCP Port")
    parser.add_argument("--udp", type=int, default=5556, help="UDP Port")
    parser.add_argument("--connect", "-c", type=str, default="", help="Peer to join (IP:Port)")
    args = parser.parse_args()

    node = P2PNode(
        username=args.username,
        requested_tcp_port=args.tcp,
        requested_udp_port=args.udp,
        enable_discovery=True
    )

    node.set_callback("on_peer_joined", lambda pid, u, info: print(f"\n[EVENT] 🟢 Peer joined: {u} ({info['ip']}:{info['port']})"))
    node.set_callback("on_peer_left", lambda pid, u: print(f"\n[EVENT] 🔴 Peer left: {u}"))
    node.set_callback("on_chat_message", lambda s, t, ts, priv: print(f"\n[{ts}] {s}: {t}"))
    node.set_callback("on_file_available", lambda m: print(f"\n[FILE] 📄 New file offered: {m['filename']} ({m['filesize']} bytes) from {m['owner_username']}"))

    node.start()

    print("=" * 60)
    print(f"P2P Node '{args.username}' running on {node.local_ip}:{node.tcp_port} (TCP) / {node.udp_port} (UDP)")
    print("Commands: /chat <text>, /connect <ip:port>, /peers, /stats, /exit")
    print("=" * 60)

    if args.connect:
        if ":" in args.connect:
            ip, p = args.connect.split(":", 1)
            node.connect_to_peer(ip.strip(), int(p.strip()))
        else:
            node.connect_to_peer(args.connect.strip(), 5555)

    try:
        while True:
            cmd = input(f"[{args.username}]> ").strip()
            if not cmd:
                continue
            if cmd == "/exit":
                break
            elif cmd == "/peers":
                with node.peers_lock:
                    print(f"Connected Peers ({len(node.peers)}):")
                    for p in node.peers.values():
                        print(f" - {p.username} @ {p.ip}:{p.tcp_port} (Latency: {p.latency_ms:.1f}ms)")
            elif cmd == "/stats":
                print(f"Bytes Sent: {node.stats['bytes_sent']}, Bytes Recv: {node.stats['bytes_recv']}")
            elif cmd.startswith("/connect "):
                target = cmd.split(" ", 1)[1].strip()
                if ":" in target:
                    ip, p = target.split(":", 1)
                    node.connect_to_peer(ip.strip(), int(p.strip()))
                else:
                    node.connect_to_peer(target, 5555)
            elif cmd.startswith("/chat "):
                text = cmd.split(" ", 1)[1]
                node.send_chat(text)
            else:
                # Default to chat message
                node.send_chat(cmd)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        print("\nStopping P2P node...")
        node.stop()
        print("Done.")


if __name__ == '__main__':
    main()
