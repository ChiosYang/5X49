"""
Security utilities for input validation and sanitization.
"""
import re
from typing import Optional

def validate_movie_id(movie_id: str) -> bool:
    """
    Validate movie ID format to prevent injection attacks.
    
    Args:
        movie_id: Movie ID string to validate
        
    Returns:
        True if valid, False otherwise
        
    Valid format:
        - Alphanumeric characters
        - Underscores and hyphens
        - Length between 1 and 100 characters
    """
    if not movie_id or len(movie_id) > 100:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', movie_id))


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
