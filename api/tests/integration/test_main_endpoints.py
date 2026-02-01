"""Simple tests to increase coverage slightly."""
import pytest


class TestSimpleCoverage:
    """Simple tests that don't require complex setup."""

    def test_import_main(self):
        """Test that main module can be imported."""
        from app import main
        assert main.app is not None
        assert hasattr(main, 'health')
        assert hasattr(main, 'metrics')

    def test_config_values(self):
        """Test config module."""
        from app.core import config
        assert hasattr(config.settings, 'database_url')
        assert hasattr(config.settings, 'jwt_secret')
        assert hasattr(config.settings, 'prometheus_enabled')
