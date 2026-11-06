"""
Network protocol and atomic framing definitions for P2P Collaboration System.
Implements binary length-prefixed framing over TCP and tag-based UDP datagrams.
"""
import struct
import json
import logging
from config import (
    PROTOCOL_MAGIC,
    MSG_TYPE_CONTROL,
    MSG_TYPE_SCREEN,
    MSG_TYPE_FILE_CHUNK
)

logger = logging.getLogger(__name__)

HEADER_STRUCT = '!2sBI'  # 2 bytes magic, 1 byte type, 4 bytes payload length (Big Endian)
HEADER_SIZE = struct.calcsize(HEADER_STRUCT)  # 7 bytes


def build_control_frame(data: dict) -> bytes:
    """Build a framed TCP control message containing JSON payload."""
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    header = struct.pack(HEADER_STRUCT, PROTOCOL_MAGIC, MSG_TYPE_CONTROL, len(payload))
    return header + payload


def build_screen_frame(jpeg_bytes: bytes) -> bytes:
    """Build a framed TCP screen sharing JPEG frame."""
    header = struct.pack(HEADER_STRUCT, PROTOCOL_MAGIC, MSG_TYPE_SCREEN, len(jpeg_bytes))
    return header + jpeg_bytes


def build_file_chunk_frame(meta: dict, chunk_bytes: bytes) -> bytes:
    """
    Build a framed TCP file chunk containing metadata header and binary chunk.
    Payload layout: [4 bytes meta_len] [meta JSON utf-8] [raw chunk bytes]
    """
    meta_json = json.dumps(meta).encode('utf-8')
    payload = struct.pack('!I', len(meta_json)) + meta_json + chunk_bytes
    header = struct.pack(HEADER_STRUCT, PROTOCOL_MAGIC, MSG_TYPE_FILE_CHUNK, len(payload))
    return header + payload


def parse_control_payload(payload: bytes) -> dict:
    """Decode JSON control payload."""
    return json.loads(payload.decode('utf-8'))


def parse_file_chunk_payload(payload: bytes):
    """Decode file chunk payload into (metadata_dict, chunk_bytes)."""
    meta_len = struct.unpack('!I', payload[:4])[0]
    meta_json = payload[4:4 + meta_len].decode('utf-8')
    chunk_data = payload[4 + meta_len:]
    return json.loads(meta_json), chunk_data


class FrameParser:
    """
    Stateful TCP byte stream frame parser with automatic resynchronization.
    Safe against packet fragmentation and buffer coalescing.
    """
    def __init__(self, max_buffer_size: int = 20 * 1024 * 1024):
        self.buffer = bytearray()
        self.max_buffer_size = max_buffer_size

    def feed(self, data: bytes):
        """Append incoming TCP data to the buffer."""
        self.buffer.extend(data)
        if len(self.buffer) > self.max_buffer_size:
            logger.warning("[PROTOCOL] Buffer exceeded maximum size, trimming stale bytes.")
            del self.buffer[:len(self.buffer) - (self.max_buffer_size // 2)]

    def next_frame(self):
        """
        Extract the next complete frame from the buffer.
        Returns (msg_type, payload_bytes) or None if incomplete.
        """
        while len(self.buffer) >= HEADER_SIZE:
            # Look for magic bytes
            magic_idx = self.buffer.find(PROTOCOL_MAGIC)
            if magic_idx == -1:
                # No magic found in buffer, retain at most 1 byte in case it's the start of magic
                self.buffer = self.buffer[-1:]
                return None
            
            if magic_idx > 0:
                # Discard garbage bytes preceding the magic
                del self.buffer[:magic_idx]

            if len(self.buffer) < HEADER_SIZE:
                return None

            # Unpack header
            magic, msg_type, payload_len = struct.unpack_from(HEADER_STRUCT, self.buffer, 0)
            
            # Sanity check payload size (max 50 MB per frame)
            if payload_len > 50 * 1024 * 1024:
                logger.error(f"[PROTOCOL] Corrupt frame detected with length {payload_len}. Dropping header.")
                del self.buffer[:HEADER_SIZE]
                continue

            total_frame_len = HEADER_SIZE + payload_len
            if len(self.buffer) < total_frame_len:
                # Need more data from socket
                return None

            # Extract payload and advance buffer
            payload = bytes(self.buffer[HEADER_SIZE:total_frame_len])
            del self.buffer[:total_frame_len]
            return msg_type, payload

        return None


# =============================================================================
# UDP MEDIA PROTOCOL HELPERS
# =============================================================================

def build_udp_video_packet(peer_id: str, username: str, jpeg_bytes: bytes) -> bytes:
    """Format: VID:<peer_id>:<username>:<jpeg_bytes>"""
    return b'VID:' + peer_id.encode('utf-8') + b':' + username.encode('utf-8') + b':' + jpeg_bytes


def build_udp_audio_packet(peer_id: str, username: str, pcm_bytes: bytes) -> bytes:
    """Format: AUD:<peer_id>:<username>:<pcm_bytes>"""
    return b'AUD:' + peer_id.encode('utf-8') + b':' + username.encode('utf-8') + b':' + pcm_bytes


def parse_udp_packet(data: bytes):
    """
    Parse a received UDP datagram.
    Returns (packet_type, peer_id, username, payload_bytes) or None if invalid.
    """
    try:
        parts = data.split(b':', 3)
        if len(parts) == 4:
            pkt_type = parts[0].decode('utf-8', errors='ignore')
            peer_id = parts[1].decode('utf-8', errors='ignore')
            username = parts[2].decode('utf-8', errors='ignore')
            payload = parts[3]
            return pkt_type, peer_id, username, payload
    except Exception as e:
        logger.debug(f"[PROTOCOL] Error parsing UDP packet: {e}")
    return None
