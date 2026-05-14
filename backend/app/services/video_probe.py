import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any, Optional


class VideoProbeService:
    """Read compact technical metadata from a video file using ffprobe."""

    def probe(self, video_path: Path) -> dict[str, Any]:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe or not video_path.exists():
            return {}

        try:
            completed = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    str(video_path),
                ],
                capture_output=True,
                check=True,
                text=True,
                timeout=20,
            )
            payload = json.loads(completed.stdout or "{}")
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return {}

        return self._parse_payload(payload)

    def _parse_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        streams = payload.get("streams") or []
        format_info = payload.get("format") or {}
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        if not video_stream:
            return {}

        width = self._to_int(video_stream.get("width"))
        height = self._to_int(video_stream.get("height"))
        bit_rate = self._to_int(video_stream.get("bit_rate")) or self._to_int(format_info.get("bit_rate"))
        duration = self._to_float(video_stream.get("duration")) or self._to_float(format_info.get("duration"))

        result = {
            "video_width": width,
            "video_height": height,
            "video_codec": video_stream.get("codec_name"),
            "video_bitrate": bit_rate,
            "video_duration": duration,
            "video_fps": self._parse_frame_rate(video_stream),
            "video_dynamic_range": self._detect_dynamic_range(video_stream),
            "video_bit_depth": self._detect_bit_depth(video_stream),
        }

        audio_tracks = self._parse_audio_tracks(streams)
        if audio_tracks:
            result["audio_tracks"] = audio_tracks

        return {key: value for key, value in result.items() if value is not None}

    def _parse_audio_tracks(self, streams: list[dict[str, Any]]) -> list[dict[str, str]]:
        tracks = []
        for stream in streams:
            if stream.get("codec_type") != "audio":
                continue
            tags = stream.get("tags") or {}
            codec = stream.get("codec_name") or ""
            language = tags.get("language") or ""
            channels = stream.get("channels")
            track = {
                "codec": codec,
                "language": language,
                "channels": str(channels) if channels else "",
            }
            if track["codec"] or track["language"] or track["channels"]:
                tracks.append(track)
        return tracks

    def _detect_dynamic_range(self, video_stream: dict[str, Any]) -> str:
        side_data = video_stream.get("side_data_list") or []
        side_data_text = " ".join(str(item) for item in side_data).lower()
        if "dovi" in side_data_text or "dolby vision" in side_data_text:
            return "Dolby Vision"

        color_transfer = (video_stream.get("color_transfer") or "").lower()
        if color_transfer == "smpte2084":
            return "HDR10"
        if color_transfer == "arib-std-b67":
            return "HLG"
        if color_transfer in {"bt709", "iec61966-2-1"}:
            return "SDR"
        return "unknown"

    def _detect_bit_depth(self, video_stream: dict[str, Any]) -> Optional[int]:
        bits_per_raw_sample = self._to_int(video_stream.get("bits_per_raw_sample"))
        if bits_per_raw_sample:
            return bits_per_raw_sample

        pix_fmt = video_stream.get("pix_fmt") or ""
        for bit_depth in (16, 14, 12, 10, 8):
            if str(bit_depth) in pix_fmt:
                return bit_depth
        return None

    def _parse_frame_rate(self, video_stream: dict[str, Any]) -> Optional[float]:
        rate = video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")
        if not rate or rate == "0/0":
            return None
        try:
            value = float(Fraction(rate))
        except (ValueError, ZeroDivisionError):
            return None
        return round(value, 3)

    def _to_int(self, value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _to_float(self, value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


video_probe_service = VideoProbeService()
