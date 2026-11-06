"""
Peer-to-Peer File Transfer Protocol Manager.
Handles decentralized file announcements, direct chunked streaming over TCP,
and end-to-end cryptographic checksum verification (SHA-256).
"""
import os
import hashlib
import time
import uuid
import logging
from typing import Dict, Optional, Callable
from config import FILE_CHUNK_SIZE, SHARED_FOLDER
from core.protocol import build_file_chunk_frame

logger = logging.getLogger(__name__)


def compute_sha256(filepath: str) -> str:
    """Calculate SHA-256 hash of a local file."""
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(262144):
            hasher.update(chunk)
    return hasher.hexdigest()


class DownloadSession:
    """Tracks state and progress of an ongoing incoming direct file transfer."""
    def __init__(self, transfer_id: str, file_id: str, filename: str, filesize: int,
                 expected_sha256: str, dest_path: str,
                 on_progress: Optional[Callable] = None,
                 on_complete: Optional[Callable] = None,
                 on_error: Optional[Callable] = None):
        self.transfer_id = transfer_id
        self.file_id = file_id
        self.filename = filename
        self.filesize = filesize
        self.expected_sha256 = expected_sha256
        self.dest_path = dest_path
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error

        self.received_bytes = 0
        self.file_handle = open(dest_path, 'wb')
        self.hasher = hashlib.sha256()
        self.start_time = time.time()

    def write_chunk(self, chunk_data: bytes, is_last: bool):
        """Write chunk to file and update checksum hasher."""
        self.file_handle.write(chunk_data)
        self.hasher.update(chunk_data)
        self.received_bytes += len(chunk_data)

        if self.on_progress and self.filesize > 0:
            pct = min(100.0, (self.received_bytes / self.filesize) * 100.0)
            self.on_progress(self.transfer_id, self.filename, self.received_bytes, self.filesize, pct)

        if is_last or (self.filesize > 0 and self.received_bytes >= self.filesize):
            self.finish()

    def finish(self):
        """Close file and verify integrity."""
        try:
            self.file_handle.flush()
            self.file_handle.close()
        except Exception:
            pass

        actual_hash = self.hasher.hexdigest()
        if self.expected_sha256 and actual_hash.lower() != self.expected_sha256.lower():
            err_msg = f"Checksum mismatch! Expected {self.expected_sha256[:8]}, got {actual_hash[:8]}"
            logger.error(f"[FILE_TRANSFER] {err_msg}")
            if self.on_error:
                self.on_error(self.transfer_id, err_msg)
        else:
            logger.info(f"[FILE_TRANSFER] Successfully downloaded {self.filename} ({self.received_bytes} bytes).")
            if self.on_complete:
                self.on_complete(self.transfer_id, self.filename, self.dest_path)

    def cancel(self, error_message: str = "Transfer aborted"):
        """Abort transfer and delete incomplete file."""
        try:
            self.file_handle.close()
            if os.path.exists(self.dest_path):
                os.remove(self.dest_path)
        except Exception:
            pass
        if self.on_error:
            self.on_error(self.transfer_id, error_message)


class FileTransferManager:
    """
    Decentralized P2P File Sharing Engine.
    No centralized file storage is used; files reside directly on offering peers.
    """
    def __init__(self, shared_dir=SHARED_FOLDER):
        self.shared_dir = shared_dir
        os.makedirs(self.shared_dir, exist_ok=True)

        self.local_files: Dict[str, dict] = {}        # file_id -> metadata
        self.network_files: Dict[str, dict] = {}      # file_id -> metadata (all mesh files)
        self.active_downloads: Dict[str, DownloadSession] = {}

    def share_file(self, filepath: str, owner_peer_id: str, owner_username: str) -> dict:
        """Register a local file for P2P sharing and return announcement metadata."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        filesize = os.path.getsize(filepath)
        filename = os.path.basename(filepath)
        file_hash = compute_sha256(filepath)
        file_id = f"{file_hash[:12]}_{int(time.time())}"

        metadata = {
            "file_id": file_id,
            "filename": filename,
            "filesize": filesize,
            "sha256": file_hash,
            "owner_peer_id": owner_peer_id,
            "owner_username": owner_username,
            "local_path": os.path.abspath(filepath),
            "shared_at": time.time()
        }

        self.local_files[file_id] = metadata
        self.network_files[file_id] = metadata
        logger.info(f"[FILE_TRANSFER] Shared '{filename}' ({filesize} bytes, SHA256: {file_hash[:8]}...)")
        return metadata

    def register_network_file(self, metadata: dict):
        """Record a file offered by a remote peer."""
        file_id = metadata.get("file_id")
        if file_id:
            self.network_files[file_id] = metadata

    def remove_peer_files(self, peer_id: str):
        """Purge catalog entries for files hosted by a disconnected peer."""
        to_del = [fid for fid, m in self.network_files.items() if m.get("owner_peer_id") == peer_id]
        for fid in to_del:
            del self.network_files[fid]

    def create_download_session(self, file_id: str, dest_dir: str, on_progress=None, on_complete=None, on_error=None):
        """Initialize incoming download session."""
        meta = self.network_files.get(file_id)
        if not meta:
            raise ValueError(f"File ID '{file_id}' not found in network catalog")

        transfer_id = str(uuid.uuid4())[:8]
        filename = meta['filename']
        dest_path = os.path.join(dest_dir, filename)

        # Avoid overwriting existing file with same name
        base, ext = os.path.splitext(dest_path)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = f"{base}_{counter}{ext}"
            counter += 1

        session = DownloadSession(
            transfer_id=transfer_id,
            file_id=file_id,
            filename=filename,
            filesize=meta['filesize'],
            expected_sha256=meta.get('sha256', ''),
            dest_path=dest_path,
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error
        )
        self.active_downloads[transfer_id] = session

        request_payload = {
            "type": "FILE_REQUEST",
            "transfer_id": transfer_id,
            "file_id": file_id,
            "owner_peer_id": meta['owner_peer_id']
        }
        return transfer_id, meta['owner_peer_id'], request_payload

    def process_incoming_chunk(self, meta: dict, chunk_bytes: bytes):
        """Route incoming chunk to appropriate download session."""
        transfer_id = meta.get("transfer_id")
        session = self.active_downloads.get(transfer_id)
        if not session:
            logger.warning(f"[FILE_TRANSFER] Received chunk for unknown transfer_id: {transfer_id}")
            return

        is_last = meta.get("is_last", False)
        session.write_chunk(chunk_data=chunk_bytes, is_last=is_last)

        if is_last or session.received_bytes >= session.filesize:
            self.active_downloads.pop(transfer_id, None)

    def stream_file_to_peer(self, file_id: str, transfer_id: str, send_func: Callable, stop_check: Optional[Callable] = None):
        """
        Stream local file chunks directly to the requesting peer.
        send_func accepts bytes (the built file chunk frame).
        """
        meta = self.local_files.get(file_id)
        if not meta:
            logger.error(f"[FILE_TRANSFER] Cannot stream: file_id '{file_id}' not found locally")
            return

        filepath = meta['local_path']
        filesize = meta['filesize']
        sent_bytes = 0
        chunk_idx = 0
        total_chunks = max(1, (filesize + FILE_CHUNK_SIZE - 1) // FILE_CHUNK_SIZE)

        logger.info(f"[FILE_TRANSFER] Starting chunked stream of '{meta['filename']}' ({total_chunks} chunks)")

        with open(filepath, 'rb') as f:
            while sent_bytes < filesize:
                if stop_check and stop_check():
                    logger.warning("[FILE_TRANSFER] Transfer aborted by peer disconnect")
                    break

                chunk = f.read(FILE_CHUNK_SIZE)
                if not chunk:
                    break

                sent_bytes += len(chunk)
                is_last = (sent_bytes >= filesize)

                chunk_meta = {
                    "transfer_id": transfer_id,
                    "file_id": file_id,
                    "chunk_idx": chunk_idx,
                    "total_chunks": total_chunks,
                    "offset": sent_bytes,
                    "is_last": is_last
                }

                frame = build_file_chunk_frame(chunk_meta, chunk)
                send_func(frame)
                chunk_idx += 1
                time.sleep(0.001)  # Minimal pacing to prevent socket buffer exhaustion

        logger.info(f"[FILE_TRANSFER] Finished streaming '{meta['filename']}' ({sent_bytes}/{filesize} bytes)")
