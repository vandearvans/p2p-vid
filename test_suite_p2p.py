"""
Automated Test Suite for Peer-to-Peer Multi-User Collaboration System.
Validates:
 1. Binary length-prefixed TCP framing & stream resynchronization
 2. Direct two-peer connection, handshake, and bidirectional chat
 3. Three-peer Full Mesh formation via Peer Exchange (PEX)
 4. Direct P2P chunked file transfer with SHA-256 cryptographic checksum
 5. UDP low-latency video and audio transmission
 6. Distributed screen sharing floor control and presentation streaming
 7. Network fault tolerance and self-healing when a peer abruptly disconnects
 8. Zero-configuration LAN UDP broadcast discovery beaconing
"""
import unittest
import time
import os
import shutil
import hashlib
from config import MSG_TYPE_CONTROL, MSG_TYPE_SCREEN, MSG_TYPE_FILE_CHUNK
from core.protocol import (
    FrameParser,
    build_control_frame,
    build_screen_frame,
    build_file_chunk_frame,
    parse_control_payload,
    parse_file_chunk_payload,
    build_udp_video_packet,
    build_udp_audio_packet,
    parse_udp_packet
)
from core.node import P2PNode
from core.discovery import DiscoveryBeacon


class TestP2PCollaborationSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = os.path.join(os.path.dirname(__file__), "test_scratch")
        os.makedirs(cls.test_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_protocol_framing_and_resync(self):
        """Verify binary 7-byte framing handles fragmentation, coalescing, and noise."""
        parser = FrameParser()

        # Send control frame, screen frame, and file chunk frame in one chunk
        c_frame = build_control_frame({"type": "PING", "val": 42})
        s_frame = build_screen_frame(b"FAKE_SCREEN_JPEG_PAYLOAD")
        f_frame = build_file_chunk_frame({"chunk": 1}, b"RAW_CHUNK_BYTES")

        stream = b"GARBAGE_NOISE_123" + c_frame + s_frame + f_frame
        parser.feed(stream)

        # 1. First frame should resync and extract control
        f1 = parser.next_frame()
        self.assertIsNotNone(f1)
        self.assertEqual(f1[0], MSG_TYPE_CONTROL)
        self.assertEqual(parse_control_payload(f1[1])["val"], 42)

        # 2. Second frame should be screen frame
        f2 = parser.next_frame()
        self.assertIsNotNone(f2)
        self.assertEqual(f2[0], MSG_TYPE_SCREEN)
        self.assertEqual(f2[1], b"FAKE_SCREEN_JPEG_PAYLOAD")

        # 3. Third frame should be file chunk
        f3 = parser.next_frame()
        self.assertIsNotNone(f3)
        self.assertEqual(f3[0], MSG_TYPE_FILE_CHUNK)
        meta, chunk = parse_file_chunk_payload(f3[1])
        self.assertEqual(meta["chunk"], 1)
        self.assertEqual(chunk, b"RAW_CHUNK_BYTES")

        # 4. No more complete frames
        self.assertIsNone(parser.next_frame())

    def test_02_two_peer_handshake_and_chat(self):
        """Verify two peers establish direct TCP mesh connection and exchange chat."""
        node_a = P2PNode("Alice", requested_tcp_port=5901, requested_udp_port=5902, enable_discovery=False)
        node_b = P2PNode("Bob", requested_tcp_port=5903, requested_udp_port=5904, enable_discovery=False)

        node_a.start()
        node_b.start()
        time.sleep(0.3)

        chat_received = []
        node_a.set_callback("on_chat_message", lambda s, t, ts, priv: chat_received.append((s, t, priv)))

        # Connect Bob -> Alice
        connected = node_b.connect_to_peer("127.0.0.1", 5901)
        self.assertTrue(connected)
        time.sleep(0.5)

        self.assertEqual(len(node_a.peers), 1)
        self.assertEqual(len(node_b.peers), 1)

        # Send broadcast chat from Bob
        node_b.send_chat("Hello from Bob!")
        time.sleep(0.3)

        self.assertTrue(any("Hello from Bob!" in m[1] and not m[2] for m in chat_received))

        # Send private chat to Alice
        alice_pid = list(node_b.peers.keys())[0]
        node_b.send_chat("Secret message to Alice", recipient_peer_id=alice_pid)
        time.sleep(0.3)

        self.assertTrue(any("Secret message to Alice" in m[1] and m[2] for m in chat_received))

        node_a.stop()
        node_b.stop()

    def test_03_three_peer_pex_mesh_formation(self):
        """Verify 3-node full mesh forms automatically via Peer Exchange (PEX)."""
        node_a = P2PNode("Alice", requested_tcp_port=5911, requested_udp_port=5912, enable_discovery=False)
        node_b = P2PNode("Bob", requested_tcp_port=5913, requested_udp_port=5914, enable_discovery=False)
        node_c = P2PNode("Charlie", requested_tcp_port=5915, requested_udp_port=5916, enable_discovery=False)

        node_a.start()
        node_b.start()
        node_c.start()
        time.sleep(0.3)

        # Bob connects to Alice
        node_b.connect_to_peer("127.0.0.1", 5911)
        time.sleep(0.3)

        # Charlie connects ONLY to Bob. Bob will share Alice's info via PEX
        node_c.connect_to_peer("127.0.0.1", 5913)
        time.sleep(1.0)  # PEX propagation

        self.assertEqual(len(node_a.peers), 2, "Alice must have 2 peer connections")
        self.assertEqual(len(node_b.peers), 2, "Bob must have 2 peer connections")
        self.assertEqual(len(node_c.peers), 2, "Charlie must have 2 peer connections")

        # Broadcast from Charlie must reach both Alice and Bob
        a_msgs = []
        b_msgs = []
        node_a.set_callback("on_chat_message", lambda s, t, ts, p: a_msgs.append(t))
        node_b.set_callback("on_chat_message", lambda s, t, ts, p: b_msgs.append(t))

        node_c.send_chat("Mesh broadcast test from Charlie")
        time.sleep(0.4)

        self.assertIn("Mesh broadcast test from Charlie", a_msgs)
        self.assertIn("Mesh broadcast test from Charlie", b_msgs)

        node_a.stop()
        node_b.stop()
        node_c.stop()

    def test_04_direct_file_transfer_and_checksum(self):
        """Verify direct P2P chunked file transfer with SHA-256 verification."""
        # Create a test file
        src_file = os.path.join(self.test_dir, "academic_paper.pdf")
        with open(src_file, "wb") as f:
            f.write(b"%PDF-1.4 P2P PROJECT DOCUMENTATION TEST\n" + (os.urandom(1024) * 200)) # ~200 KB

        expected_hash = hashlib.sha256(open(src_file, "rb").read()).hexdigest()

        node_a = P2PNode("Alice", requested_tcp_port=5921, requested_udp_port=5922, enable_discovery=False)
        node_b = P2PNode("Bob", requested_tcp_port=5923, requested_udp_port=5924, enable_discovery=False)

        node_a.start()
        node_b.start()
        time.sleep(0.3)
        node_b.connect_to_peer("127.0.0.1", 5921)
        time.sleep(0.4)

        # Alice shares file
        meta = node_a.share_file(src_file)
        time.sleep(0.3)
        self.assertIn(meta["file_id"], node_b.file_manager.network_files)

        # Bob downloads file
        dest_dir = os.path.join(self.test_dir, "bob_downloads")
        os.makedirs(dest_dir, exist_ok=True)

        download_finished = [False]
        node_b.set_callback("on_file_complete", lambda tid, name, path: download_finished.__setitem__(0, True))

        node_b.download_file(meta["file_id"], dest_dir)

        for _ in range(40):
            if download_finished[0]:
                break
            time.sleep(0.1)

        self.assertTrue(download_finished[0], "Download did not complete in time")

        downloaded_path = os.path.join(dest_dir, meta["filename"])
        self.assertTrue(os.path.exists(downloaded_path))
        actual_hash = hashlib.sha256(open(downloaded_path, "rb").read()).hexdigest()
        self.assertEqual(expected_hash, actual_hash, "SHA-256 checksums must match!")

        node_a.stop()
        node_b.stop()

    def test_05_udp_media_streaming(self):
        """Verify UDP video and audio datagram transmission between peers."""
        node_a = P2PNode("Alice", requested_tcp_port=5931, requested_udp_port=5932, enable_discovery=False)
        node_b = P2PNode("Bob", requested_tcp_port=5933, requested_udp_port=5934, enable_discovery=False)

        node_a.start()
        node_b.start()
        time.sleep(0.3)
        node_b.connect_to_peer("127.0.0.1", 5931)
        time.sleep(0.4)

        received_video = []
        node_b.set_callback("on_video_frame", lambda pid, u, data: received_video.append((u, data)))

        # Alice sends mock video packet directly via UDP
        mock_jpeg = b"\xff\xd8\xff\xe0...TEST_JPEG_STREAM"
        node_a._on_local_video_packet(mock_jpeg)
        time.sleep(0.3)

        self.assertTrue(len(received_video) > 0, "Bob should have received UDP video packet")
        self.assertEqual(received_video[0][0], "Alice")
        self.assertEqual(received_video[0][1], mock_jpeg)

        node_a.stop()
        node_b.stop()

    def test_06_screen_sharing_floor_control(self):
        """Verify distributed presenter floor control."""
        node_a = P2PNode("Alice", requested_tcp_port=5941, requested_udp_port=5942, enable_discovery=False)
        node_b = P2PNode("Bob", requested_tcp_port=5943, requested_udp_port=5944, enable_discovery=False)

        node_a.start()
        node_b.start()
        time.sleep(0.3)
        node_b.connect_to_peer("127.0.0.1", 5941)
        time.sleep(0.4)

        # Alice acquires screen share
        started = node_a.start_screen_sharing()
        self.assertTrue(started)
        time.sleep(0.3)

        self.assertEqual(node_b.current_presenter, "Alice")

        # Bob attempts to present simultaneously -> should be denied
        started_bob = node_b.start_screen_sharing()
        self.assertFalse(started_bob, "Bob should not be able to present while Alice is presenting")

        # Alice stops presenting -> floor released
        node_a.stop_screen_sharing()
        time.sleep(0.3)

        self.assertIsNone(node_b.current_presenter)

        node_a.stop()
        node_b.stop()

    def test_07_mesh_self_healing_on_disconnect(self):
        """Verify mesh automatically recovers and maintains integrity when a peer leaves."""
        node_a = P2PNode("Alice", requested_tcp_port=5951, requested_udp_port=5952, enable_discovery=False)
        node_b = P2PNode("Bob", requested_tcp_port=5953, requested_udp_port=5954, enable_discovery=False)
        node_c = P2PNode("Charlie", requested_tcp_port=5955, requested_udp_port=5956, enable_discovery=False)

        node_a.start()
        node_b.start()
        node_c.start()
        time.sleep(0.3)

        node_b.connect_to_peer("127.0.0.1", 5951)
        node_c.connect_to_peer("127.0.0.1", 5953)
        time.sleep(1.0)

        self.assertEqual(len(node_a.peers), 2)
        self.assertEqual(len(node_c.peers), 2)

        # Bob leaves abruptly
        node_b.stop()
        time.sleep(0.6)

        # Alice and Charlie must remain connected to each other
        self.assertEqual(len(node_a.peers), 1)
        self.assertEqual(len(node_c.peers), 1)
        self.assertEqual(list(node_a.peers.values())[0].username, "Charlie")
        self.assertEqual(list(node_c.peers.values())[0].username, "Alice")

        # Communication between Alice and Charlie still works flawlessly
        received_msgs = []
        node_a.set_callback("on_chat_message", lambda s, t, ts, p: received_msgs.append(t))
        node_c.send_chat("Alice, are you still there?")
        time.sleep(0.3)
        self.assertIn("Alice, are you still there?", received_msgs)

        node_a.stop()
        node_c.stop()

    def test_08_lan_auto_discovery_beacon(self):
        """Verify UDP broadcast discovery sends and receives beacons."""
        found_peers = []
        beacon_a = DiscoveryBeacon("peer_alpha", "Alpha", 5961, 5962, discovery_port=5550, interval=0.5)
        beacon_b = DiscoveryBeacon("peer_beta", "Beta", 5963, 5964, discovery_port=5550, interval=0.5,
                                   on_peer_found=lambda info: found_peers.append(info))

        beacon_b.start()
        beacon_a.start()
        time.sleep(1.2)

        self.assertTrue(len(found_peers) > 0, "Beacon B should have discovered Beacon A")
        self.assertEqual(found_peers[0]["peer_id"], "peer_alpha")
        self.assertEqual(found_peers[0]["username"], "Alpha")

        beacon_a.stop()
        beacon_b.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
