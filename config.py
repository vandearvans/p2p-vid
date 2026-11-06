"""
Configuration settings for P2P Collaboration System
Computer Networks Course Project
"""
import os

# Default Network Settings
DEFAULT_DISCOVERY_PORT = 5550  # UDP Broadcast discovery
DEFAULT_TCP_PORT = 5555        # TCP Control, Screen sharing & File transfers
DEFAULT_UDP_PORT = 5556        # UDP Real-time Video & Audio streaming

# Broadcast address for LAN discovery
BROADCAST_ADDRESS = '<broadcast>'
DISCOVERY_INTERVAL = 3.0       # Seconds between periodic beacons
HEARTBEAT_INTERVAL = 5.0       # Keep-alive ping interval in seconds
PEER_TIMEOUT = 15.0            # Seconds before marking an unresponsive peer dead

# Media Configurations
VIDEO_WIDTH = 320
VIDEO_HEIGHT = 240
VIDEO_FPS = 12
VIDEO_JPEG_QUALITY = 50

SCREEN_SCALE = 0.5
SCREEN_FPS = 10
SCREEN_JPEG_QUALITY = 65

AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_CHUNK = 1024

# File Transfer Configurations
FILE_CHUNK_SIZE = 65536        # 64 KB per chunk
MAX_FILE_SIZE_MB = 100
SHARED_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shared_files')

# Protocol Magic Header
PROTOCOL_MAGIC = b'P2'
MSG_TYPE_CONTROL = 0x01
MSG_TYPE_SCREEN = 0x02
MSG_TYPE_FILE_CHUNK = 0x03
