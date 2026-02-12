import logging
import json
import requests
from datetime import datetime
from typing import Optional


class HTTPLogHandler(logging.Handler):
    """
    Logging handler that sends log records to a remote HTTP endpoint.
    Used by worker processes to stream logs to the main API server.
    """

    def __init__(self, api_host: str, api_port: int, timeout: float = 2.0):
        """
        Initialize the HTTP log handler.

        Args:
            api_host: Hostname or IP of the API server
            api_port: Port number of the API server
            timeout: HTTP request timeout in seconds (default: 2.0)
        """
        super().__init__()
        self.api_host = api_host
        self.api_port = api_port
        self.timeout = timeout
        self.url = f"http://{api_host}:{api_port}/api/v1/logs/ingest"
        self.session = requests.Session()

    def emit(self, record: logging.LogRecord):
        """
        Send a log record to the API server via HTTP POST.

        Args:
            record: The log record to send
        """
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
                "module": record.module,
                "funcName": record.funcName,
                "lineno": record.lineno,
                "process": record.process,
                "processName": record.processName,
            }

            # Send to API server (non-blocking, fire-and-forget)
            self.session.post(
                self.url,
                json=log_entry,
                timeout=self.timeout,
            )

        except Exception:
            # Don't let logging errors crash the worker
            # Silently ignore HTTP errors to avoid cascading failures
            pass

    def close(self):
        """Close the HTTP session."""
        self.session.close()
        super().close()


def setup_worker_logging(api_host: str, api_port: int, process_name: Optional[str] = None):
    """
    Configure logging for worker processes to send logs to the API server.

    Args:
        api_host: Hostname or IP of the API server
        api_port: Port number of the API server
        process_name: Optional name to identify this worker process
    """
    # Get root logger
    root_logger = logging.getLogger()

    # Create HTTP handler
    http_handler = HTTPLogHandler(api_host, api_port)

    # Format: include process name if provided
    if process_name:
        formatter = logging.Formatter(
            f"[{process_name}] %(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

    http_handler.setFormatter(formatter)

    # Add to root logger
    root_logger.addHandler(http_handler)

    logging.info(f"Worker HTTP logging configured: {api_host}:{api_port}")
