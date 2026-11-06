"""
Peer-to-Peer Media Engines: Real-Time Audio (PCM) & Video (JPEG/OpenCV) over UDP.
Supports sounddevice and PyAudio with automatic hardware detection and fallback.
"""
import time
import threading
import queue
import logging
import cv2
import numpy as np

# Try sounddevice first, then pyaudio
HAS_SOUNDDEVICE = False
HAS_PYAUDIO = False

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except Exception:
    pass

if not HAS_SOUNDDEVICE:
    try:
        import pyaudio
        HAS_PYAUDIO = True
    except Exception:
        pass

from config import (
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    VIDEO_FPS,
    VIDEO_JPEG_QUALITY,
    AUDIO_SAMPLE_RATE,
    AUDIO_CHANNELS,
    AUDIO_CHUNK
)

logger = logging.getLogger(__name__)


class AudioEngine:
    """
    Manages low-latency real-time microphone capture and multi-peer audio playback.
    Directly converts audio to 16-bit PCM chunks transmitted via UDP datagrams.
    """
    def __init__(self, sample_rate=AUDIO_SAMPLE_RATE, channels=AUDIO_CHANNELS, chunk=AUDIO_CHUNK, on_audio_chunk=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk = chunk
        self.on_audio_chunk = on_audio_chunk

        self.recording = False
        self.playing = False
        self.is_muted = False
        
        self.playback_queue = queue.Queue(maxsize=100)
        self.record_thread = None
        self.play_thread = None
        self.sd_input_stream = None
        self.sd_output_stream = None

    def start(self):
        """Start audio playback service."""
        self.playing = True
        self.play_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self.play_thread.start()

    def start_recording(self):
        """Start microphone capture stream."""
        if self.recording:
            return True
        self.recording = True
        self.is_muted = False
        self.record_thread = threading.Thread(target=self._record_worker, daemon=True)
        self.record_thread.start()
        return True

    def stop_recording(self):
        """Stop microphone capture."""
        self.recording = False
        if self.record_thread and self.record_thread.is_alive():
            self.record_thread.join(timeout=1.0)
        self.record_thread = None

    def toggle_mute(self) -> bool:
        """Toggle microphone mute status."""
        self.is_muted = not self.is_muted
        return self.is_muted

    def feed_audio(self, pcm_bytes: bytes):
        """Feed received audio bytes from remote peers into playback queue."""
        if not self.playing:
            return
        try:
            self.playback_queue.put_nowait(pcm_bytes)
        except queue.Full:
            # Drop older frames to preserve real-time low latency
            try:
                self.playback_queue.get_nowait()
                self.playback_queue.put_nowait(pcm_bytes)
            except queue.Empty:
                pass

    def _record_worker(self):
        """Microphone capture loop."""
        if HAS_SOUNDDEVICE:
            try:
                with sd.RawInputStream(samplerate=self.sample_rate, channels=self.channels,
                                       dtype='int16', blocksize=self.chunk) as stream:
                    logger.info("[AUDIO] sounddevice microphone input active")
                    while self.recording:
                        data, overflow = stream.read(self.chunk)
                        if self.recording and not self.is_muted and self.on_audio_chunk:
                            self.on_audio_chunk(bytes(data))
            except Exception as e:
                logger.error(f"[AUDIO] sounddevice capture error: {e}")
        elif HAS_PYAUDIO:
            try:
                p = pyaudio.PyAudio()
                stream = p.open(format=pyaudio.paInt16, channels=self.channels,
                                rate=self.sample_rate, input=True, frames_per_buffer=self.chunk)
                logger.info("[AUDIO] PyAudio microphone input active")
                while self.recording:
                    data = stream.read(self.chunk, exception_on_overflow=False)
                    if self.recording and not self.is_muted and self.on_audio_chunk:
                        self.on_audio_chunk(data)
                stream.stop_stream()
                stream.close()
                p.terminate()
            except Exception as e:
                logger.error(f"[AUDIO] PyAudio capture error: {e}")
        else:
            logger.warning("[AUDIO] No supported audio driver found (sounddevice/PyAudio).")

    def _playback_worker(self):
        """Speaker playback loop."""
        if HAS_SOUNDDEVICE:
            try:
                with sd.RawOutputStream(samplerate=self.sample_rate, channels=self.channels,
                                        dtype='int16', blocksize=self.chunk) as stream:
                    logger.info("[AUDIO] sounddevice audio output active")
                    while self.playing:
                        try:
                            data = self.playback_queue.get(timeout=0.2)
                            stream.write(data)
                        except queue.Empty:
                            continue
            except Exception as e:
                logger.error(f"[AUDIO] sounddevice playback error: {e}")
        elif HAS_PYAUDIO:
            try:
                p = pyaudio.PyAudio()
                stream = p.open(format=pyaudio.paInt16, channels=self.channels,
                                rate=self.sample_rate, output=True, frames_per_buffer=self.chunk)
                logger.info("[AUDIO] PyAudio audio output active")
                while self.playing:
                    try:
                        data = self.playback_queue.get(timeout=0.2)
                        stream.write(data)
                    except queue.Empty:
                        continue
                stream.stop_stream()
                stream.close()
                p.terminate()
            except Exception as e:
                logger.error(f"[AUDIO] PyAudio playback error: {e}")

    def stop(self):
        """Stop audio service."""
        self.stop_recording()
        self.playing = False


class VideoEngine:
    """
    Manages webcam capture, dynamic virtual camera fallback, JPEG compression,
    and frame dispatch for UDP transmission.
    """
    def __init__(self, username="You", camera_index=0, width=VIDEO_WIDTH, height=VIDEO_HEIGHT,
                 fps=VIDEO_FPS, quality=VIDEO_JPEG_QUALITY, on_local_frame=None, on_video_packet=None):
        self.username = username
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = fps
        self.quality = quality
        self.on_local_frame = on_local_frame
        self.on_video_packet = on_video_packet

        self.running = False
        self.capture_thread = None
        self.cap = None

    def start(self):
        """Start video capture."""
        if self.running:
            return
        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()

    def _create_virtual_camera_frame(self, t: float) -> np.ndarray:
        """Fallback synthetic video frame if no physical webcam is attached."""
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        # Gradient background
        for y in range(self.height):
            frame[y, :] = [int(40 + 30 * (y / self.height)), int(20 + 20 * (y / self.height)), int(60 + 50 * (y / self.height))]
        
        # Pulsing circle avatar
        radius = int(35 + 8 * np.sin(t * 3))
        center = (self.width // 2, self.height // 2 - 15)
        cv2.circle(frame, center, radius, (0, 200, 255), -1)
        cv2.circle(frame, center, radius + 2, (255, 255, 255), 2)
        
        # User initial in center
        initial = self.username[0].upper() if self.username else "?"
        cv2.putText(frame, initial, (center[0] - 12, center[1] + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (20, 20, 20), 3)

        # Name and badge
        name_str = f"{self.username} (Virtual Cam)"
        cv2.putText(frame, name_str, (10, self.height - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1)
        
        # Animated timestamp bar
        ts = time.strftime("%H:%M:%S")
        cv2.putText(frame, ts, (self.width - 70, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        return frame

    def _capture_loop(self):
        """Webcam capture and encoding loop."""
        use_virtual = False
        try:
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                use_virtual = True
                logger.info("[VIDEO] Physical camera not available; using virtual test camera.")
            else:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap.set(cv2.CAP_PROP_FPS, self.fps)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception as e:
            logger.warning(f"[VIDEO] Error opening camera: {e}; falling back to virtual.")
            use_virtual = True

        interval = 1.0 / self.fps
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.quality]

        start_time = time.time()
        while self.running:
            t0 = time.time()
            frame = None

            if not use_virtual and self.cap:
                ret, raw_frame = self.cap.read()
                if ret and raw_frame is not None:
                    frame = cv2.resize(raw_frame, (self.width, self.height))
                else:
                    time.sleep(0.05)
                    continue
            else:
                frame = self._create_virtual_camera_frame(time.time() - start_time)

            if frame is not None:
                # Local preview
                if self.on_local_frame:
                    self.on_local_frame(frame)

                # JPEG compression
                success, buf = cv2.imencode('.jpg', frame, encode_params)
                if success:
                    jpeg_bytes = buf.tobytes()
                    if self.on_video_packet:
                        self.on_video_packet(jpeg_bytes)

            elapsed = time.time() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def stop(self):
        """Stop video capture."""
        self.running = False
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1.0)
        self.capture_thread = None
