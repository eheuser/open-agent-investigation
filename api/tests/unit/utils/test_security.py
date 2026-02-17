"""
Unit tests for security utilities.

Tests cover:
- SSRF protection via URL validation
- Path traversal protection via path sanitization
- Log injection protection via log message sanitization
"""

import pytest
from pathlib import Path
from fastapi import HTTPException

from app.utils.security import (
    validate_url_safe,
    sanitize_path_component,
    validate_path_within_base,
    sanitize_log_message,
    sanitize_filename,
)


class TestValidateUrlSafe:
    """Tests for SSRF protection via URL validation."""

    def test_valid_https_url(self):
        """Test that valid HTTPS URLs are accepted."""
        url = "https://api.openai.com/v1/chat/completions"
        result = validate_url_safe(url)
        assert result == url

    def test_valid_http_url(self):
        """Test that valid HTTP URLs are accepted."""
        url = "http://example.com/api"
        result = validate_url_safe(url)
        assert result == url

    def test_localhost_blocked(self):
        """Test that localhost URLs are blocked."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url_safe("http://localhost:8080/api")
        assert exc_info.value.status_code == 400
        assert "localhost" in exc_info.value.detail.lower()

    def test_127_0_0_1_blocked(self):
        """Test that 127.0.0.1 URLs are blocked."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url_safe("http://127.0.0.1:8080/api")
        assert exc_info.value.status_code == 400
        assert "localhost" in exc_info.value.detail.lower()

    def test_private_ip_10_blocked(self):
        """Test that 10.x.x.x private IPs are blocked."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url_safe("http://10.0.0.1/api")
        assert exc_info.value.status_code == 400
        assert "private" in exc_info.value.detail.lower()

    def test_private_ip_192_blocked(self):
        """Test that 192.168.x.x private IPs are blocked."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url_safe("http://192.168.1.1/api")
        assert exc_info.value.status_code == 400
        assert "private" in exc_info.value.detail.lower()

    def test_private_ip_172_blocked(self):
        """Test that 172.16-31.x.x private IPs are blocked."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url_safe("http://172.16.0.1/api")
        assert exc_info.value.status_code == 400
        assert "private" in exc_info.value.detail.lower()

    def test_link_local_169_blocked(self):
        """Test that 169.254.x.x link-local IPs are blocked (AWS metadata)."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url_safe("http://169.254.169.254/metadata")
        assert exc_info.value.status_code == 400
        assert "private" in exc_info.value.detail.lower()

    def test_ipv6_localhost_blocked(self):
        """Test that IPv6 localhost (::1) is blocked."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url_safe("http://[::1]:8080/api")
        assert exc_info.value.status_code == 400

    def test_invalid_scheme(self):
        """Test that non-HTTP(S) schemes are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url_safe("file:///etc/passwd")
        assert exc_info.value.status_code == 400
        assert "scheme" in exc_info.value.detail.lower()

    def test_empty_url(self):
        """Test that empty URLs are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url_safe("")
        assert exc_info.value.status_code == 400

    def test_none_url(self):
        """Test that None URLs are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url_safe(None)
        assert exc_info.value.status_code == 400

    def test_allow_private_flag(self):
        """Test that allow_private flag bypasses private IP checks."""
        url = "http://localhost:8080/api"
        result = validate_url_safe(url, allow_private=True)
        assert result == url


class TestSanitizePathComponent:
    """Tests for path traversal protection."""

    def test_valid_filename(self):
        """Test that valid filenames pass through unchanged."""
        assert sanitize_path_component("file.txt") == "file.txt"
        assert sanitize_path_component("report_2024.pdf") == "report_2024.pdf"

    def test_dot_dot_blocked(self):
        """Test that '..' is blocked."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_path_component("..")
        assert exc_info.value.status_code == 400
        assert "traversal" in exc_info.value.detail.lower()

    def test_dot_blocked(self):
        """Test that '.' is blocked."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_path_component(".")
        assert exc_info.value.status_code == 400
        assert "traversal" in exc_info.value.detail.lower()

    def test_path_traversal_prefix_blocked(self):
        """Test that '../' prefix is blocked."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_path_component("../etc/passwd")
        assert exc_info.value.status_code == 400
        assert "traversal" in exc_info.value.detail.lower()

    def test_path_traversal_infix_blocked(self):
        """Test that '/../' infix is blocked."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_path_component("file/../../../etc/passwd")
        assert exc_info.value.status_code == 400
        assert "traversal" in exc_info.value.detail.lower()

    def test_absolute_path_blocked(self):
        """Test that absolute paths are blocked."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_path_component("/etc/passwd")
        assert exc_info.value.status_code == 400
        assert "absolute" in exc_info.value.detail.lower()

    def test_windows_absolute_path_blocked(self):
        """Test that Windows absolute paths are blocked."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_path_component("C:\\Windows\\System32")
        assert exc_info.value.status_code == 400
        assert "absolute" in exc_info.value.detail.lower()

    def test_null_byte_blocked(self):
        """Test that null bytes are blocked."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_path_component("file\x00.txt")
        assert exc_info.value.status_code == 400
        assert "null" in exc_info.value.detail.lower()

    def test_empty_component(self):
        """Test that empty components are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_path_component("")
        assert exc_info.value.status_code == 400


class TestValidatePathWithinBase:
    """Tests for path containment validation."""

    def test_valid_relative_path(self, tmp_path):
        """Test that valid relative paths are accepted."""
        base = tmp_path / "base"
        base.mkdir()
        
        result = validate_path_within_base(Path("subdir/file.txt"), base)
        assert result == base / "subdir" / "file.txt"

    def test_path_escape_blocked(self, tmp_path):
        """Test that paths escaping base directory are blocked."""
        base = tmp_path / "base"
        base.mkdir()
        
        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_base(Path("../../etc/passwd"), base)
        assert exc_info.value.status_code == 400
        assert "traversal" in exc_info.value.detail.lower()

    def test_symlink_escape_blocked(self, tmp_path):
        """Test that symlinks escaping base are blocked."""
        base = tmp_path / "base"
        base.mkdir()
        
        # Create a symlink pointing outside base
        outside = tmp_path / "outside"
        outside.mkdir()
        
        link = base / "link"
        link.symlink_to(outside)
        
        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_base(Path("link"), base)
        assert exc_info.value.status_code == 400


class TestSanitizeLogMessage:
    """Tests for log injection protection."""

    def test_normal_message(self):
        """Test that normal messages pass through unchanged."""
        msg = "Normal log message"
        assert sanitize_log_message(msg) == msg

    def test_newline_removed(self):
        """Test that newlines are replaced with spaces."""
        msg = "Line 1\nLine 2"
        result = sanitize_log_message(msg)
        assert "\n" not in result
        assert result == "Line 1 Line 2"

    def test_carriage_return_removed(self):
        """Test that carriage returns are replaced with spaces."""
        msg = "Line 1\rLine 2"
        result = sanitize_log_message(msg)
        assert "\r" not in result
        assert result == "Line 1 Line 2"

    def test_crlf_removed(self):
        """Test that CRLF sequences are handled."""
        msg = "Line 1\r\nLine 2"
        result = sanitize_log_message(msg)
        assert "\r" not in result
        assert "\n" not in result
        assert result == "Line 1  Line 2"

    def test_control_characters_removed(self):
        """Test that control characters are removed."""
        msg = "Text\x00with\x01control\x1fchars"
        result = sanitize_log_message(msg)
        # Should remove all control chars except tab
        assert "\x00" not in result
        assert "\x01" not in result
        assert "\x1f" not in result

    def test_tab_preserved(self):
        """Test that tabs are preserved."""
        msg = "Column1\tColumn2"
        result = sanitize_log_message(msg)
        assert "\t" in result

    def test_long_message_truncated(self):
        """Test that very long messages are truncated."""
        msg = "A" * 20000
        result = sanitize_log_message(msg, max_length=1000)
        assert len(result) <= 1020  # 1000 + "[truncated]"
        assert result.endswith("...[truncated]")

    def test_injection_attempt(self):
        """Test that log injection attempts are sanitized."""
        # Attempt to inject fake log entry
        msg = "User input\n2024-01-01 ERROR Fake error message"
        result = sanitize_log_message(msg)
        assert "\n" not in result
        # The newline should be replaced, preventing the injection
        assert result == "User input 2024-01-01 ERROR Fake error message"


class TestSanitizeFilename:
    """Tests for filename sanitization."""

    def test_valid_filename(self):
        """Test that valid filenames pass through unchanged."""
        assert sanitize_filename("report.pdf") == "report.pdf"
        assert sanitize_filename("data_2024-01-01.csv") == "data_2024-01-01.csv"

    def test_path_separators_replaced(self):
        """Test that path separators are replaced."""
        assert sanitize_filename("path/to/file.txt") == "path_to_file.txt"
        assert sanitize_filename("path\\to\\file.txt") == "path_to_file.txt"

    def test_dangerous_chars_replaced(self):
        """Test that dangerous characters are replaced."""
        # <, >, :, |, ?, * are replaced with _ (6 chars total, not 7)
        assert sanitize_filename("file<>:|?*.txt") == "file______.txt"

    def test_null_byte_rejected(self):
        """Test that null bytes cause rejection."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename("file\x00.txt")
        assert exc_info.value.status_code == 400

    def test_dot_dot_rejected(self):
        """Test that '..' is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename("..")
        assert exc_info.value.status_code == 400

    def test_long_filename_truncated(self):
        """Test that long filenames are truncated while preserving extension."""
        long_name = "A" * 300 + ".txt"
        result = sanitize_filename(long_name, max_length=255)
        assert len(result) <= 255
        assert result.endswith(".txt")

    def test_windows_reserved_names(self):
        """Test that Windows reserved names are prefixed."""
        reserved = ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]
        for name in reserved:
            result = sanitize_filename(name)
            assert result.startswith("_")
            assert result == f"_{name}"
        
        # Test with extension
        result = sanitize_filename("CON.txt")
        assert result.startswith("_")

    def test_empty_filename_rejected(self):
        """Test that empty filenames are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename("")
        assert exc_info.value.status_code == 400
