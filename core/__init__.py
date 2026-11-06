"""
Core package for P2P Collaboration System
"""
from core.protocol import FrameParser, build_control_frame, build_screen_frame, build_file_chunk_frame
from core.node import P2PNode
from core.discovery import DiscoveryBeacon
from core.media import AudioEngine, VideoEngine
from core.screen_share import ScreenShareEngine
from core.file_transfer import FileTransferManager

__all__ = [
    'P2PNode',
    'FrameParser',
    'build_control_frame',
    'build_screen_frame',
    'build_file_chunk_frame',
    'DiscoveryBeacon',
    'AudioEngine',
    'VideoEngine',
    'ScreenShareEngine',
    'FileTransferManager'
]
