"""Shared text boundary, independent of DB/chat clients and model runtimes."""
import re
import unicodedata

_PRIVATE_INPUT = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{8,}|\bgh[pousr]_[A-Za-z0-9]{10,}|"
    r"\b(?:api[_ -]?key|authorization|password|secret|token)\s*[:=]|"
    r"\bbearer\s+\S+|[A-Za-z]:[\\/]|\\\\[^\s\\]+\\|file://|"
    r"(?:^|[\s\"'(\[{=，。！？；：\u0060])(?:~[^\\/\s]*[\\/]|\.{1,2}[\\/]|[\\/])[^\s\"'<>)}\]]+|"
    # A separator plus a known media/sidecar extension distinguishes an
    # unprefixed relative path from titles such as Face/Off, V/H/S and 9/11.
    # Repeated/mixed separators are still paths, including unnormalized input.
    r"(?:^|[\s\"'(\[{=，。！？；：\u0060])(?:[^\s\\/\"'<>:|?*\u0060]+[\\/]+)+"
    r"[^\\/\r\n]*\.(?:mkv|mp4|m4v|avi|mov|webm|wmv|mpg|mpeg|m2ts|ts|vob|iso|"
    r"nfo|srt|ass|ssa|vtt|sub|idx|jpe?g|png|gif|webp|txt|json|xml|db|sqlite3?|env|pem|key)"
    r"(?=$|[\s\"')\]}>,.;:!?，。！？；：\u0060]))", re.IGNORECASE,
)


def has_private_input(text: str) -> bool:
    return bool(_PRIVATE_INPUT.search(text) or _PRIVATE_INPUT.search(unicodedata.normalize("NFKC", text)))
