"""
Security utilities for input validation and sanitization.

This module provides functions to prevent common security vulnerabilities:
- SSRF (Server-Side Request Forgery) via URL validation
- Path traversal attacks via path sanitization
- Log injection via log message sanitization
"""

import re
import ipaddress
from pathlib import Path
from urllib.parse import urlparse
from fastapi import HTTPException, status


# Private IP ranges that should be blocked for SSRF protection
PRIVATE_IP_RANGES = [
    ipaddress.ip_network("0.0.0.0/8"),  # Current network
    ipaddress.ip_network("10.0.0.0/8"),  # Private network
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local (AWS metadata)
    ipaddress.ip_network("172.16.0.0/12"),  # Private network
    ipaddress.ip_network("192.168.0.0/16"),  # Private network
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


def validate_url_safe(url: str, allow_private: bool = False) -> str:
    """
    Validate that a URL is safe to make requests to (SSRF protection).
    
    This function prevents Server-Side Request Forgery (SSRF) attacks by:
    - Ensuring the URL uses http or https scheme
    - Blocking requests to private IP ranges (localhost, RFC1918, link-local, etc.)
    - Blocking requests to localhost/127.0.0.1
    - Validating the URL format
    
    Args:
        url: The URL to validate
        allow_private: If True, allow private IP ranges (use with caution, only for testing)
    
    Returns:
        The validated URL (unchanged if valid)
    
    Raises:
        HTTPException: 400 if the URL is invalid or unsafe
    
    Examples:
        >>> validate_url_safe("https://api.openai.com/v1/chat/completions")
        'https://api.openai.com/v1/chat/completions'
        
        >>> validate_url_safe("http://localhost:8080/api")  # Raises HTTPException
        >>> validate_url_safe("http://169.254.169.254/metadata")  # Raises HTTPException
    """
    if not url or not isinstance(url, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must be a non-empty string"
        )
    
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL format: {str(e)}"
        )
    
    # Ensure scheme is http or https
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"URL scheme must be http or https, got: {parsed.scheme}"
        )
    
    # Extract hostname
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must contain a valid hostname"
        )
    
    # Skip private IP validation if explicitly allowed (for testing/development)
    if allow_private:
        return url
    
    # Block localhost variations
    localhost_patterns = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "0:0:0:0:0:0:0:1",
    ]
    
    if hostname.lower() in localhost_patterns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requests to localhost are not allowed for security reasons"
        )
    
    # Try to resolve hostname to IP and check if it's private
    try:
        ip = ipaddress.ip_address(hostname)
        
        # Check if IP is in any private range
        for private_range in PRIVATE_IP_RANGES:
            if ip in private_range:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Requests to private IP addresses are not allowed: {hostname}"
                )
    except ValueError:
        # hostname is not an IP address, it's a domain name
        # We can't easily check if it resolves to a private IP without DNS lookup
        # which could be slow and have its own security issues
        # For now, we'll allow domain names and rely on network-level controls
        pass
    
    return url


def sanitize_path_component(component: str, allow_dots: bool = False) -> str:
    """
    Sanitize a path component to prevent directory traversal attacks.
    
    Args:
        component: A single path component (filename or directory name)
        allow_dots: If True, allow "." and ".." (use with extreme caution)
    
    Returns:
        Sanitized path component
    
    Raises:
        HTTPException: 400 if the component contains path traversal attempts
    
    Examples:
        >>> sanitize_path_component("file.txt")
        'file.txt'
        
        >>> sanitize_path_component("../../../etc/passwd")  # Raises HTTPException
        >>> sanitize_path_component("file/../../secret")  # Raises HTTPException
    """
    if not component or not isinstance(component, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path component must be a non-empty string"
        )
    
    # Strip surrounding whitespace
    component = component.strip()
    if not component:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path component must be a non-empty string"
        )
    
    # Remove any null bytes
    if "\x00" in component:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path component contains null bytes"
        )
    
    # Check for absolute paths BEFORE normalization
    if component.startswith("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Absolute paths are not allowed"
        )
    
    # Check for Windows absolute paths (C:, D:, etc.) BEFORE normalization
    if len(component) > 1 and component[1] == ":":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Absolute paths are not allowed"
        )
    
    # Check for path traversal attempts BEFORE normalization
    if not allow_dots:
        # Check for . and .. exactly
        if component in (".", ".."):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path traversal attempts are not allowed"
            )
        
        # Check for ../ or ..\ prefix (path traversal)
        if component.startswith("../") or component.startswith("..\\"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path traversal attempts are not allowed"
            )
        
        # Check for /../ or \..\  or /..\ or \../ anywhere in path
        if "/../" in component or "/..\\" in component or "\\../" in component or "\\..\\" in component:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path traversal attempts are not allowed"
            )
    
    # Normalize to a single path segment: this drops any directory parts and
    # collapses traversal sequences so that only the final name is kept.
    # For example, "../../../etc/passwd" -> "passwd".
    normalized = Path(component).name
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path traversal attempts are not allowed"
        )
    
    component = normalized
    
    # Optionally restrict allowed characters to a conservative set to avoid
    # unexpected filesystem semantics.
    # Allows letters, digits, dot, underscore and hyphen.
    if not re.fullmatch(r"[A-Za-z0-9._-]+", component):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path component contains invalid characters"
        )
    
    return component


def validate_path_within_base(path: Path, base: Path, resolve: bool = True) -> Path:
    """
    Validate that a path is within a base directory (prevents path traversal).
    
    Args:
        path: The path to validate
        base: The base directory that path must be within
        resolve: If True, resolve both paths to absolute paths before checking
    
    Returns:
        The validated path (resolved if resolve=True)
    
    Raises:
        HTTPException: 400 if the path escapes the base directory
    
    Examples:
        >>> base = Path("/data/investigations")
        >>> validate_path_within_base(Path("abc123/file.txt"), base)
        Path("/data/investigations/abc123/file.txt")
        
        >>> validate_path_within_base(Path("../../etc/passwd"), base)  # Raises HTTPException
    """
    if resolve:
        try:
            # Resolve to absolute paths
            resolved_base = base.resolve(strict=False)
            # Construct the full path and resolve it
            full_path = base / path
            resolved_path = full_path.resolve(strict=False)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid path: {sanitize_log_message(str(e))}"
            )
    else:
        resolved_base = base
        # Still need to construct the full path safely
        try:
            resolved_path = base / path
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid path: {sanitize_log_message(str(e))}"
            )
    
    # Check if resolved_path is within resolved_base
    try:
        resolved_path.relative_to(resolved_base)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path traversal attempt detected"
        )
    
    return resolved_path


def sanitize_log_message(message: str, max_length: int = 10000) -> str:
    """
    Sanitize a log message to prevent log injection attacks.
    
    This function removes/escapes characters that could be used to:
    - Inject fake log entries (newlines, carriage returns)
    - Exploit log parsers (control characters)
    - Create excessively long log entries
    
    Args:
        message: The message to sanitize
        max_length: Maximum allowed length (longer messages are truncated)
    
    Returns:
        Sanitized message safe for logging
    
    Examples:
        >>> sanitize_log_message("Normal message")
        'Normal message'
        
        >>> sanitize_log_message("Fake\\nINFO: Injected log entry")
        'Fake INFO: Injected log entry'
        
        >>> sanitize_log_message("Message with \\r\\n CRLF")
        'Message with  CRLF'
    """
    if not isinstance(message, str):
        message = str(message)
    
    # Remove newlines and carriage returns (prevent log injection)
    message = message.replace("\n", " ").replace("\r", " ")
    
    # Remove other control characters (except tab and space)
    message = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", message)
    
    # Truncate if too long
    if len(message) > max_length:
        message = message[:max_length] + "...[truncated]"
    
    return message


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize a filename to prevent path traversal and filesystem issues.
    
    Args:
        filename: The filename to sanitize
        max_length: Maximum allowed length
    
    Returns:
        Sanitized filename safe for filesystem operations
    
    Raises:
        HTTPException: 400 if filename is invalid
    
    Examples:
        >>> sanitize_filename("report.pdf")
        'report.pdf'
        
        >>> sanitize_filename("../../etc/passwd")  # Raises HTTPException
        >>> sanitize_filename("file<>|*.txt")  # Raises HTTPException
    """
    if not filename or not isinstance(filename, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename must be a non-empty string"
        )
    
    # Remove path separators
    filename = filename.replace("/", "_").replace("\\", "_")
    
    # Remove null bytes
    if "\x00" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename contains null bytes"
        )
    
    # Check for path traversal
    if filename in (".", "..") or filename.startswith(".."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename"
        )
    
    # Remove/replace dangerous characters for Windows and Unix
    # Windows reserved: < > : " / \ | ? *
    # Also remove control characters
    dangerous_chars = r'[<>:"|?*\x00-\x1f\x7f]'
    filename = re.sub(dangerous_chars, "_", filename)
    
    # Truncate if too long
    if len(filename) > max_length:
        # Try to preserve extension
        name_parts = filename.rsplit(".", 1)
        if len(name_parts) == 2:
            name, ext = name_parts
            max_name_len = max_length - len(ext) - 1
            filename = name[:max_name_len] + "." + ext
        else:
            filename = filename[:max_length]
    
    # Check for Windows reserved names
    reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    
    name_without_ext = filename.rsplit(".", 1)[0].upper()
    if name_without_ext in reserved_names:
        filename = "_" + filename
    
    return filename


__all__ = [
    "validate_url_safe",
    "sanitize_path_component",
    "validate_path_within_base",
    "sanitize_log_message",
    "sanitize_filename",
]

