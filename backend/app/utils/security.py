"""
Security utilities for input validation and sanitization.
"""
import re
from typing import Optional

def validate_resource_id(resource_id: str, expected_prefix: str | None = None) -> bool:
    """Validate an opaque public resource identifier."""
    if not resource_id or len(resource_id) > 100:
        return False
    if expected_prefix is not None:
        return bool(re.fullmatch(rf"{re.escape(expected_prefix)}_[0-9a-f]{{32}}", resource_id))
    return bool(re.fullmatch(r"[a-zA-Z0-9_-]+", resource_id))


def sanitize_path(path: str, allowed_base: str) -> Optional[str]:
    """
    Sanitize and validate file paths to prevent directory traversal.
    
    Args:
        path: Path to sanitize
        allowed_base: Base directory that path must be within
        
    Returns:
        Sanitized absolute path if valid, None otherwise
    """
    from pathlib import Path
    
    try:
        resolved_path = Path(path).resolve()
        if str(resolved_path).startswith(allowed_base):
            return str(resolved_path)
    except Exception:
        pass
    
    return None
