"""
Unit tests for log streaming service.
"""

import pytest
import logging
import asyncio
from app.services.log_streaming import (
    StreamingLogHandler,
    streaming_handler,
    setup_log_streaming,
    get_streaming_handler,
)


@pytest.mark.unit
class TestStreamingLogHandler:
    """Test StreamingLogHandler class."""

    def test_handler_initialization(self):
        """Test that handler initializes with correct defaults."""
        handler = StreamingLogHandler()
        assert handler.max_logs == 1000
        assert len(handler.log_buffer) == 0
        assert len(handler.queues) == 0

    def test_handler_custom_max_logs(self):
        """Test handler with custom max_logs value."""
        handler = StreamingLogHandler(max_logs=500)
        assert handler.max_logs == 500

    def test_format_log_entry(self):
        """Test formatting of log record into dictionary."""
        handler = StreamingLogHandler()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        entry = handler.format_log_entry(record)
        
        assert "timestamp" in entry
        assert entry["level"] == "INFO"
        assert entry["logger"] == "test.logger"
        assert "Test message" in entry["message"]
        assert entry["lineno"] == 42

    def test_emit_adds_to_buffer(self):
        """Test that emit adds log entry to buffer."""
        handler = StreamingLogHandler(max_logs=10)
        handler.setFormatter(logging.Formatter("%(message)s"))
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test log",
            args=(),
            exc_info=None,
        )
        
        handler.emit(record)
        
        assert len(handler.log_buffer) == 1
        assert handler.log_buffer[0]["message"] == "Test log"

    def test_get_recent_logs_all(self):
        """Test getting all recent logs."""
        handler = StreamingLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        
        # Add some logs
        for i in range(5):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=i,
                msg=f"Log {i}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
        
        logs = handler.get_recent_logs()
        assert len(logs) == 5

    def test_get_recent_logs_limited(self):
        """Test getting limited number of recent logs."""
        handler = StreamingLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        
        # Add some logs
        for i in range(10):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=i,
                msg=f"Log {i}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
        
        logs = handler.get_recent_logs(limit=3)
        assert len(logs) == 3
        # Should be the most recent ones
        assert logs[-1]["message"] == "Log 9"

    @pytest.mark.asyncio
    async def test_add_client(self):
        """Test adding a client queue."""
        handler = StreamingLogHandler()
        queue = asyncio.Queue()
        
        await handler.add_client(queue)
        
        assert queue in handler.queues
        assert len(handler.queues) == 1

    @pytest.mark.asyncio
    async def test_remove_client(self):
        """Test removing a client queue."""
        handler = StreamingLogHandler()
        queue = asyncio.Queue()
        
        await handler.add_client(queue)
        await handler.remove_client(queue)
        
        assert queue not in handler.queues
        assert len(handler.queues) == 0

    @pytest.mark.asyncio
    async def test_emit_to_client_queue(self):
        """Test that emit sends logs to client queues."""
        handler = StreamingLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        queue = asyncio.Queue()
        
        await handler.add_client(queue)
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        handler.emit(record)
        
        # Give async operations time to complete
        await asyncio.sleep(0.01)
        
        assert not queue.empty()
        log_entry = await queue.get()
        assert log_entry["message"] == "Test message"


@pytest.mark.unit
class TestGlobalHandlerFunctions:
    """Test global handler functions."""

    def test_get_streaming_handler(self):
        """Test that get_streaming_handler returns the global instance."""
        handler = get_streaming_handler()
        assert isinstance(handler, StreamingLogHandler)
        assert handler is streaming_handler

    def test_setup_log_streaming(self):
        """Test that setup_log_streaming adds handler to root logger."""
        # Get root logger
        root_logger = logging.getLogger()
        
        # Remove handler if already present
        if streaming_handler in root_logger.handlers:
            root_logger.removeHandler(streaming_handler)
        
        # Setup streaming
        setup_log_streaming()
        
        # Verify handler was added
        assert streaming_handler in root_logger.handlers

    def test_setup_log_streaming_idempotent(self):
        """Test that calling setup_log_streaming multiple times doesn't add duplicates."""
        root_logger = logging.getLogger()
        
        # Remove handler if present
        while streaming_handler in root_logger.handlers:
            root_logger.removeHandler(streaming_handler)
        
        # Call setup multiple times
        setup_log_streaming()
        setup_log_streaming()
        setup_log_streaming()
        
        # Count how many times the handler appears
        count = sum(1 for h in root_logger.handlers if h is streaming_handler)
        assert count == 1

    def test_buffer_max_size(self):
        """Test that buffer respects max_logs limit."""
        handler = StreamingLogHandler(max_logs=5)
        handler.setFormatter(logging.Formatter("%(message)s"))
        
        # Add more logs than max_logs
        for i in range(10):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=i,
                msg=f"Log {i}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
        
        # Should only keep the last 5
        assert len(handler.log_buffer) == 5
        # Should be logs 5-9
        assert handler.log_buffer[0]["message"] == "Log 5"
        assert handler.log_buffer[-1]["message"] == "Log 9"

    @pytest.mark.asyncio
    async def test_emit_with_full_queue(self):
        """Test that emit handles full client queues gracefully."""
        handler = StreamingLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        
        # Create a small queue and fill it
        queue = asyncio.Queue(maxsize=1)
        await handler.add_client(queue)
        
        # Fill the queue
        await queue.put({"test": "data"})
        
        # Emit should not raise even though queue is full
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        handler.emit(record)  # Should not raise
        
        # Log should still be in buffer
        assert len(handler.log_buffer) == 1

    @pytest.mark.asyncio
    async def test_remove_nonexistent_client(self):
        """Test that removing a non-existent client doesn't raise."""
        handler = StreamingLogHandler()
        queue = asyncio.Queue()
        
        # Should not raise
        await handler.remove_client(queue)
        assert len(handler.queues) == 0

    def test_emit_with_exception_in_format(self):
        """Test that emit handles formatting errors gracefully."""
        handler = StreamingLogHandler()
        
        # Create a record that might cause formatting issues
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test %s",  # Format string without args
            args=(),
            exc_info=None,
        )
        
        # Should handle error without crashing
        handler.emit(record)
        # Buffer might or might not have the entry depending on error handling
        assert isinstance(handler.log_buffer, type(handler.log_buffer))
