"""Read-only container probing and continuous audio/video decoding.

No raw tool diagnostics escape this adapter: their text may contain host paths
or embedded container metadata. Unknown failures are incomplete, never damage.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path

import psutil

FORMATS = "mov,matroska,webm,avi,mpegts,mpeg,mpegvideo,flv,asf,ogg,nut,rm,hevc,h264"
CORRUPT = re.compile(r"invalid data found|moov atom not found|file ended prematurely|packet corrupt|corrupt input packet|"
                     r"corrupt(?:ed)? (?:packet|frame)|error (?:while )?decoding|"
                     r"invalid nal|invalid .*size|truncat|crc mismatch|"
                     r"invalid ebml|invalid sync|header damaged|partial file", re.I)
UNSUPPORTED = re.compile(r"(?:unknown|not found|unsupported|not currently supported).*"
                         r"(?:decoder|codec)|decod(?:er|ing).*not found|"
                         r"not on whitelist|protocol not found|function not implemented|"
                         r"unrecognized option|option .* not found|health process lifecycle unsupported", re.I)
ACCESS = re.compile(r"permission denied|access.*denied|input/output error|no such file|"
                    r"network is unreachable|stale file handle|device not ready", re.I)


def classify(errors: str) -> tuple[str, str]:
    if ACCESS.search(errors):
        return "incomplete", "read_unavailable"
    if UNSUPPORTED.search(errors):
        return "unsupported", "codec_or_tool_unsupported"
    if CORRUPT.search(errors):
        return "abnormal", "media_decode_error"
    return "incomplete", "tool_failed"


class ToolProcess:
    """Drain both pipes with bounded retention, preserving EOF/progress evidence."""
    def __init__(self, arguments: list[str], *, stdout_limit: int = 256_000):
        self.job_handle = None
        options = {"creationflags": subprocess.CREATE_NO_WINDOW | 0x00000004} if os.name == "nt" else {}
        launch = arguments if os.name == "nt" else [sys.executable, "-m", "app.services.video_health_child", str(os.getpid()), *arguments]
        self.process = subprocess.Popen(launch, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
        try:
            if os.name == "nt":
                self.job_handle = self._windows_job()
                psutil.Process(self.process.pid).resume()
        except (OSError, psutil.Error):
            self.process.kill(); self.process.wait(timeout=5)
            self.process.stdout.close(); self.process.stderr.close()
            if self.job_handle:
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel.CloseHandle(self.job_handle)
            raise
        self.stdout = bytearray()
        self.stdout_limit = stdout_limit
        self.overflow = False
        self.errors = deque(maxlen=80)
        self.diagnostic_state: tuple[str, str] | None = None
        self.seconds = 0.0
        self.ended = False
        self.suspended = False
        self.pause_failed = False
        self.readers = [threading.Thread(target=self._read, args=(self.process.stdout, False), daemon=True),
                        threading.Thread(target=self._read, args=(self.process.stderr, True), daemon=True)]
        for reader in self.readers:
            reader.start()
        try:
            owner = psutil.Process(self.process.pid)
            owner.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 10)
        except (psutil.Error, OSError):
            pass

    def _windows_job(self):
        import ctypes
        from ctypes import wintypes
        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                ("flags", wintypes.DWORD), ("min_working", ctypes.c_size_t), ("max_working", ctypes.c_size_t),
                ("active", wintypes.DWORD), ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD)]
        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        job = kernel.CreateJobObjectW(None, None)
        limits = ExtendedLimits(); limits.basic.flags = 0x00002000  # KILL_ON_JOB_CLOSE
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        if (not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
                or not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(int(self.process._handle)))):
            error = ctypes.WinError(ctypes.get_last_error()); kernel.CloseHandle(job); raise error
        return job

    def _read(self, stream, errors: bool):
        try:
            for raw in iter(lambda: stream.readline(4096), b""):
                line = raw[:4000].decode("utf-8", errors="replace").strip()
                if errors:
                    self.errors.append(line)
                    classified = classify(line)
                    if classified[1] != "tool_failed":
                        # Access/unsupported takes precedence over corruption.
                        if self.diagnostic_state is None or classified[0] != "abnormal":
                            self.diagnostic_state = classified
                else:
                    if len(self.stdout) + len(raw) <= self.stdout_limit:
                        self.stdout.extend(raw)
                    else:
                        self.overflow = True
                    if line.startswith("out_time_us="):
                        try:
                            self.seconds = max(self.seconds, int(line.split("=", 1)[1]) / 1_000_000)
                        except ValueError:
                            pass
                    if line == "progress=end":
                        self.ended = True
        finally:
            stream.close()

    def pause(self, suspend: bool):
        if self.suspended == suspend or self.process.poll() is not None:
            return
        owner = psutil.Process(self.process.pid)
        (owner.suspend if suspend else owner.resume)()
        self.suspended = suspend

    def close(self):
        if self.process.poll() is None:
            # Resume before termination so POSIX suspended children can exit.
            try:
                self.pause(False)
            except (psutil.Error, OSError):
                pass
            self.process.kill()
        self.process.wait(timeout=5)
        for reader in self.readers:
            reader.join(timeout=5)
        if self.job_handle:
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(self.job_handle)
            self.job_handle = None

    def result(self) -> tuple[str, str | None]:
        for reader in self.readers:
            reader.join(timeout=5)
        if self.diagnostic_state:
            return self.diagnostic_state
        if self.process.returncode:
            return classify("\n".join(self.errors))
        return "passed", None


def container_arguments(path: Path) -> list[str] | None:
    tool = shutil.which("ffprobe")
    return ([tool, "-v", "warning", "-protocol_whitelist", "file,pipe",
             "-format_whitelist", FORMATS, "-show_format", "-show_streams",
             "-of", "json", "-threads", "1", str(path)] if tool else None)


def decode_arguments(path: Path, streams: list[dict]) -> list[str] | None:
    tool = shutil.which("ffmpeg")
    if not tool:
        return None
    arguments = [tool, "-hide_banner", "-nostdin", "-v", "warning", "-xerror",
                 "-max_error_rate", "0", "-filter_threads", "1", "-filter_complex_threads", "1",
                 "-progress", "pipe:1", "-nostats", "-protocol_whitelist", "file,pipe",
                 "-format_whitelist", FORMATS, "-threads", "1", "-err_detect", "explode",
                 "-i", str(path)]
    for stream in streams:
        arguments.extend(["-map", f"0:{stream['index']}"])
    return [*arguments, "-threads", "1", "-abort_on", "empty_output_stream", "-f", "null", "-"]


def probe_payload(tool: ToolProcess) -> tuple[list[dict], float | None]:
    if tool.overflow:
        raise ValueError("metadata_too_large")
    payload = json.loads(tool.stdout)
    streams = [stream for stream in payload.get("streams", [])
               if stream.get("codec_type") in {"video", "audio"}
               and not (stream.get("disposition") or {}).get("attached_pic")]
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise ValueError("no_video_stream")
    duration = None
    try:
        candidate = float((payload.get("format") or {}).get("duration"))
        if 0 < candidate < 10**8:
            duration = candidate
    except (TypeError, ValueError):
        pass
    return streams, duration
