import fcntl
import logging
import os
import subprocess
import threading
import time

import discord

logger = logging.getLogger(__name__)

F_SETPIPE_SZ = 1031

# 48kHz stereo 16-bit
BYTES_PER_SEC_48K = 48000 * 2 * 2


class GrowingFileSource(discord.AudioSource):
    """追記されるファイルからリアルタイムに読むオーディオソース"""

    FRAME_SIZE = 3840  # 20ms @ 48kHz stereo 16-bit
    SILENCE = b"\x00" * FRAME_SIZE
    PREFILL_BYTES = BYTES_PER_SEC_48K * 5

    def __init__(self, file_path: str, ready_event: threading.Event):
        self._path = file_path
        self._ready = ready_event
        self._file = None
        self._pos = 0
        self._reads = 0
        self._underruns = 0
        self._lock = threading.Lock()

    def read(self) -> bytes:
        self._reads += 1

        with self._lock:
            if self._file is None:
                if not self._ready.wait(timeout=0.02):
                    return self.SILENCE
                self._file = open(self._path, "rb")

            self._file.seek(0, 2)
            file_size = self._file.tell()

            if self._pos + self.FRAME_SIZE <= file_size:
                self._file.seek(self._pos)
                data = self._file.read(self.FRAME_SIZE)
                if len(data) == self.FRAME_SIZE:
                    self._pos += self.FRAME_SIZE
                    if self._reads % 500 == 0:
                        ahead = (file_size - self._pos) / BYTES_PER_SEC_48K
                        logger.debug("pos=%.1fs ahead=%.1fs",
                                     self._pos / BYTES_PER_SEC_48K, ahead)
                    return data

        self._underruns += 1
        if self._underruns % 50 == 1:
            logger.warning("underrun #%d at %.1fs",
                           self._underruns, self._pos / BYTES_PER_SEC_48K)
        return self.SILENCE

    def flush(self):
        """ファイル末尾にジャンプ（曲変更時のバッファスキップ用）"""
        with self._lock:
            if self._file:
                self._file.seek(0, 2)
                old_pos = self._pos
                self._pos = self._file.tell()
                logger.info("flush: skipped %.1fs",
                            (self._pos - old_pos) / BYTES_PER_SEC_48K)

    def _reopen(self):
        """compaction 後にファイル再オープン（lock 保持中に呼ぶ）"""
        if self._file:
            self._file.close()
        self._file = open(self._path, "rb")
        self._pos = 0

    def reset(self):
        with self._lock:
            if self._file:
                self._file.close()
            self._file = None
            self._pos = 0

    def cleanup(self):
        if self._file:
            self._file.close()
        if self._underruns:
            logger.info("source stats: %d underruns / %d reads (%.1f%%)",
                        self._underruns, self._reads,
                        self._underruns / max(self._reads, 1) * 100)

    def is_opus(self) -> bool:
        return False


class LibrespotManager:
    """librespot プロセス管理 + ファイル経由で discord.py に音声供給"""

    AUDIO_FILE = "/tmp/librespot_audio.pcm"
    COMPACT_THRESHOLD = BYTES_PER_SEC_48K * 120  # 2分消費後に compaction
    MAX_RESTART_ATTEMPTS = 5
    RESTART_BACKOFF_BASE = 5  # sec

    def __init__(self):
        self.librespot_proc: subprocess.Popen | None = None
        self._running = False
        self._writer_ffmpeg: subprocess.Popen | None = None
        self._writer_thread: threading.Thread | None = None
        self._file_ready = threading.Event()
        self._source: GrowingFileSource | None = None
        self._restart_count = 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._start_librespot()
        self._start_writer()
        threading.Thread(target=self._monitor_process, daemon=True).start()
        logger.info("librespot ready")

    def _start_librespot(self):
        device_name = os.getenv("LIBRESPOT_DEVICE_NAME", "Discord Bot")
        bitrate = os.getenv("LIBRESPOT_BITRATE", "320")
        cache_dir = os.getenv("LIBRESPOT_CACHE", "/app/cache")

        cmd = [
            "librespot",
            "--name", device_name,
            "--backend", "pipe",
            "--format", "S16",
            "--bitrate", bitrate,
            "--initial-volume", "100",
            "--cache", cache_dir,
            "--system-cache", cache_dir,
            "--disable-discovery",
            "--dither", "none",
            "--volume-ctrl", "linear",
        ]

        logger.info("librespot 起動: %s", device_name)

        self.librespot_proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        try:
            fcntl.fcntl(self.librespot_proc.stdout.fileno(), F_SETPIPE_SZ, 1048576)
        except OSError as e:
            logger.warning("pipe buffer resize failed: %s", e)

        threading.Thread(target=self._log_stderr, daemon=True).start()

    def _start_writer(self):
        """librespot stdout → ffmpeg (44.1k→48k resample) → file"""
        try:
            os.remove(self.AUDIO_FILE)
        except FileNotFoundError:
            pass

        self._file_ready.clear()

        self._writer_ffmpeg = subprocess.Popen(
            [
                "ffmpeg",
                "-f", "s16le", "-ar", "44100", "-ac", "2",
                "-i", "pipe:0",
                "-f", "s16le", "-ar", "48000", "-ac", "2",
                "-loglevel", "error",
                "pipe:1",
            ],
            stdin=self.librespot_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        self._writer_thread = threading.Thread(
            target=self._writer_loop, daemon=True
        )
        self._writer_thread.start()

    def _writer_loop(self):
        bytes_written = 0
        last_compact_check = 0
        with open(self.AUDIO_FILE, "wb") as f:
            while True:
                data = self._writer_ffmpeg.stdout.read(65536)
                if not data:
                    break
                f.write(data)
                f.flush()
                bytes_written += len(data)

                if not self._file_ready.is_set() \
                        and bytes_written >= GrowingFileSource.PREFILL_BYTES:
                    self._file_ready.set()
                    logger.info("audio file ready (%.1fs buffered)",
                                bytes_written / BYTES_PER_SEC_48K)

                # 定期 compaction
                if bytes_written - last_compact_check > BYTES_PER_SEC_48K * 10:
                    last_compact_check = bytes_written
                    source = self._source
                    if source and source._pos > self.COMPACT_THRESHOLD:
                        bytes_written = self._compact(f, source)
                        last_compact_check = bytes_written

        logger.info("writer stopped (total %.1fs)", bytes_written / BYTES_PER_SEC_48K)

    def _compact(self, writer_file, source: GrowingFileSource) -> int:
        with source._lock:
            read_pos = source._pos
            writer_file.flush()
            writer_pos = writer_file.tell()
            remaining_size = writer_pos - read_pos

            if remaining_size <= 0:
                source._reopen()
                writer_file.seek(0)
                writer_file.truncate()
                writer_file.flush()
                return 0

            with open(self.AUDIO_FILE, "rb") as old:
                old.seek(read_pos)
                remaining = old.read(remaining_size)

            writer_file.seek(0)
            writer_file.write(remaining)
            writer_file.truncate()
            writer_file.flush()

            source._reopen()

            logger.info("compact: dropped %.1fs, kept %.1fs",
                        read_pos / BYTES_PER_SEC_48K,
                        len(remaining) / BYTES_PER_SEC_48K)
        return len(remaining)

    def create_audio_source(self) -> discord.AudioSource:
        source = GrowingFileSource(self.AUDIO_FILE, self._file_ready)
        self._source = source
        # 既存データをスキップ
        try:
            source._pos = os.path.getsize(self.AUDIO_FILE)
        except FileNotFoundError:
            pass
        return source

    def flush(self):
        if self._source:
            self._source.flush()

    def _monitor_process(self):
        while self._running:
            time.sleep(5)
            if self.librespot_proc and self.librespot_proc.poll() is not None:
                self._restart_count += 1
                if self._restart_count > self.MAX_RESTART_ATTEMPTS:
                    logger.critical(
                        "librespot が %d 回クラッシュ、自動再起動を停止",
                        self.MAX_RESTART_ATTEMPTS,
                    )
                    return
                backoff = self.RESTART_BACKOFF_BASE * self._restart_count
                logger.error(
                    "librespot crashed (exit %d, attempt %d/%d), retry in %ds",
                    self.librespot_proc.returncode,
                    self._restart_count,
                    self.MAX_RESTART_ATTEMPTS,
                    backoff,
                )
                time.sleep(backoff)
                if not self._running:
                    return
                self._restart()
            else:
                self._restart_count = 0

    def _restart(self):
        if self._writer_ffmpeg:
            try:
                self._writer_ffmpeg.kill()
                self._writer_ffmpeg.wait(timeout=5)
            except Exception:
                pass
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=5)

        self._start_librespot()
        self._start_writer()

        if self._source:
            self._source.reset()

        logger.info("librespot restarted")

    def _log_stderr(self):
        if self.librespot_proc and self.librespot_proc.stderr:
            for line in self.librespot_proc.stderr:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    logger.info("[librespot] %s", text)

    def stop(self):
        self._running = False
        if self._writer_ffmpeg:
            self._writer_ffmpeg.kill()
            self._writer_ffmpeg.wait()
            self._writer_ffmpeg = None
        if self.librespot_proc:
            self.librespot_proc.kill()
            self.librespot_proc.wait()
            self.librespot_proc = None
        try:
            os.remove(self.AUDIO_FILE)
        except FileNotFoundError:
            pass
        logger.info("librespot stopped")
