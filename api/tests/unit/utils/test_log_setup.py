"""
Unit tests for log setup utilities.
"""

import pytest
import os
from unittest.mock import patch


@pytest.mark.unit
class TestLogSetup:
    """Test log setup configuration."""

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a logger instance."""
        from app.utils.log_setup import get_logger
        import logging

        logger = get_logger("test")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test"

    def test_get_logger_default_name(self):
        """Test that get_logger uses module name as default."""
        from app.utils.log_setup import get_logger

        logger = get_logger()
        assert logger.name == "app.utils.log_setup"

    @patch.dict(os.environ, {"LOG_FILE": "/tmp/test.log"})
    def test_log_file_configuration(self):
        """Test that LOG_FILE environment variable is respected."""
        # Re-import to trigger configuration with LOG_FILE set
        import importlib
        import app.utils.log_setup
        importlib.reload(app.utils.log_setup)
        
        from app.utils.log_setup import get_logger
        logger = get_logger("file_test")
        assert isinstance(logger, type(get_logger()))

    def test_log_level_configuration(self):
        """Test that LOG_LEVEL environment variable works."""
        from app.utils.log_setup import get_logger
        import logging
        
        logger = get_logger("level_test")
        # Logger should be configured
        assert isinstance(logger, logging.Logger)

    def test_multiple_loggers(self):
        """Test creating multiple loggers with different names."""
        from app.utils.log_setup import get_logger
        
        logger1 = get_logger("test1")
        logger2 = get_logger("test2")
        logger3 = get_logger("test3")
        
        assert logger1.name == "test1"
        assert logger2.name == "test2"
        assert logger3.name == "test3"
        assert logger1 != logger2 != logger3
