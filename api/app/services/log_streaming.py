import logging
import asyncio
from typing import Dict, List
from datetime import datetime
from collections import deque


class StreamingLogHandler(logging.Handler):
    """
    Custom logging handler that captures logs and streams them to connected clients.
    Maintains a circular buffer of the last 1,000 log entries.
    """

    def __init__(self, max_logs: int = 1000):
        super().__init__()
        self.max_logs = max_logs
        self.log_buffer: deque = deque(maxlen=max_logs)
        self.queues: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    def emit(self, record: logging.LogRecord):
        """
        Called when a log record is emitted. Formats the record and adds it to the buffer
        and all connected client queues.
        """
        try:
            log_entry = self.format_log_entry(record)
            
            # Add to circular buffer (thread-safe via deque)
            self.log_buffer.append(log_entry)
            
            # Send to all connected clients (non-blocking)
            # We use asyncio.create_task to avoid blocking the logging thread
            for queue in self.queues[:]:  # Create a copy to avoid modification during iteration
                try:
                    # Non-blocking put - if queue is full, skip this client
                    if not queue.full():
                        queue.put_nowait(log_entry)
                except Exception:
                    # Queue might be closed or client disconnected
                    pass
                    
        except Exception:
            # Don't let logging errors crash the application
            self.handleError(record)

    def format_log_entry(self, record: logging.LogRecord) -> Dict:
        """
        Format a log record into a structured dictionary for JSON serialization.
        """
        return {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self.format(record),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }

    async def add_client(self, queue: asyncio.Queue):
        """
        Register a new client queue to receive log entries.
        """
        async with self._lock:
            self.queues.append(queue)

    async def remove_client(self, queue: asyncio.Queue):
        """
        Unregister a client queue.
        """
        async with self._lock:
            if queue in self.queues:
                self.queues.remove(queue)

    def get_recent_logs(self, limit: int = None) -> List[Dict]:
        """
        Get recent logs from the circular buffer.
        
        Args:
            limit: Maximum number of logs to return. If None, returns all buffered logs.
        
        Returns:
            List of log entries, most recent last.
        """
        if limit is None:
            return list(self.log_buffer)
        else:
            # Return the most recent 'limit' entries
            return list(self.log_buffer)[-limit:]


# Global streaming log handler instance
streaming_handler = StreamingLogHandler(max_logs=1000)

# Configure the handler with a formatter
formatter = logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
streaming_handler.setFormatter(formatter)


def setup_log_streaming():
    """
    Add the streaming handler to the root logger.
    This should be called during application startup.
    """
    root_logger = logging.getLogger()
    
    # Check if already added
    if streaming_handler not in root_logger.handlers:
        root_logger.addHandler(streaming_handler)
        logging.info("Log streaming handler initialized")


def get_streaming_handler() -> StreamingLogHandler:
    """
    Get the global streaming log handler instance.
    """
    return streaming_handler
