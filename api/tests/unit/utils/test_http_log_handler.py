import pytest
import logging
from unittest.mock import Mock, patch, MagicMock
from app.utils.http_log_handler import HTTPLogHandler, setup_worker_logging


@pytest.mark.unit
class TestHTTPLogHandler:
    """Test HTTPLogHandler class."""

    def test_handler_initialization(self):
        """Test that handler initializes with correct parameters."""
        handler = HTTPLogHandler(api_host="localhost", api_port=8000)
        
        assert handler.api_host == "localhost"
        assert handler.api_port == 8000
        assert handler.timeout == 2.0
        assert handler.url == "http://localhost:8000/api/v1/logs/ingest"

    def test_handler_custom_timeout(self):
        """Test handler with custom timeout value."""
        handler = HTTPLogHandler(api_host="localhost", api_port=8000, timeout=5.0)
        
        assert handler.timeout == 5.0

    @patch('app.utils.http_log_handler.requests.Session')
    def test_emit_sends_http_post(self, mock_session_class):
        """Test that emit sends HTTP POST with correct data."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        handler = HTTPLogHandler(api_host="localhost", api_port=8000)
        handler.setFormatter(logging.Formatter("%(message)s"))
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        handler.emit(record)
        
        # Verify POST was called
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        
        assert call_args[1]['timeout'] == 2.0
        assert 'json' in call_args[1]
        log_data = call_args[1]['json']
        assert log_data['level'] == 'INFO'
        assert log_data['logger'] == 'test.logger'
        assert 'Test message' in log_data['message']

    @patch('app.utils.http_log_handler.requests.Session')
    def test_emit_handles_exceptions(self, mock_session_class):
        """Test that emit handles HTTP errors gracefully."""
        mock_session = MagicMock()
        mock_session.post.side_effect = Exception("Network error")
        mock_session_class.return_value = mock_session
        
        handler = HTTPLogHandler(api_host="localhost", api_port=8000)
        handler.setFormatter(logging.Formatter("%(message)s"))
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        
        # Should not raise
        handler.emit(record)

    @patch('app.utils.http_log_handler.requests.Session')
    def test_close_closes_session(self, mock_session_class):
        """Test that close method closes the HTTP session."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        handler = HTTPLogHandler(api_host="localhost", api_port=8000)
        handler.close()
        
        mock_session.close.assert_called_once()


@pytest.mark.unit
class TestSetupWorkerLogging:
    """Test setup_worker_logging function."""

    @patch('app.utils.http_log_handler.HTTPLogHandler')
    def test_setup_without_process_name(self, mock_handler_class):
        """Test setup_worker_logging without process name."""
        mock_handler = MagicMock()
        mock_handler.level = logging.INFO  # Set proper level attribute
        mock_handler_class.return_value = mock_handler
        
        root_logger = logging.getLogger()
        initial_handler_count = len(root_logger.handlers)
        
        try:
            setup_worker_logging(api_host="localhost", api_port=8000)
            
            # Verify handler was created with correct params
            mock_handler_class.assert_called_once_with("localhost", 8000)
            
            # Verify formatter was set
            mock_handler.setFormatter.assert_called_once()
        finally:
            # Clean up - remove the mock handler
            if mock_handler in root_logger.handlers:
                root_logger.removeHandler(mock_handler)

    @patch('app.utils.http_log_handler.HTTPLogHandler')
    def test_setup_with_process_name(self, mock_handler_class):
        """Test setup_worker_logging with process name."""
        mock_handler = MagicMock()
        mock_handler.level = logging.INFO  # Set proper level attribute
        mock_handler_class.return_value = mock_handler
        
        root_logger = logging.getLogger()
        
        try:
            setup_worker_logging(
                api_host="localhost",
                api_port=8000,
                process_name="worker-1"
            )
            
            # Verify handler was created
            mock_handler_class.assert_called_once_with("localhost", 8000)
            
            # Verify formatter was set
            mock_handler.setFormatter.assert_called_once()
        finally:
            # Clean up - remove the mock handler
            if mock_handler in root_logger.handlers:
                root_logger.removeHandler(mock_handler)
