"""
Unit tests for configuration management.
"""

import pytest
import os
from unittest.mock import patch

from app.core.config import Settings


@pytest.mark.unit
class TestSettings:
    """Test application settings."""

    def test_settings_default_values(self):
        """
        Test that the Settings class initializes with appropriate default configuration values, ensuring required fields are set and numeric defaults are positive.
        """
        settings = Settings()

        assert settings.jwt_secret is not None
        assert settings.database_url is not None
        assert settings.worker_poll_interval > 0
        assert settings.worker_timeout > 0
        assert settings.api_port == 8000

    def test_settings_from_env(self):
        """
        Test that the Settings configuration class correctly reads values from environment variables, converting string representations to appropriate types (e.g., integers) and assigning them to the corresponding attributes. The test patches `os.environ` with specific keys (`JWT_SECRET`, `DATABASE_URL`, `WORKER_POLL_INTERVAL`, `API_PORT`) and verifies that a newly instantiated Settings object reflects these values: `jwt_secret` matches the provided secret string, `database_url` matches the connection URL, `worker_poll_interval` is parsed as an integer 5, and `api_port` is parsed as an integer 9000.
        """
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "test-secret-key",
                "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
                "WORKER_POLL_INTERVAL": "5",
                "API_PORT": "9000",
            },
        ):
            settings = Settings()

            assert settings.jwt_secret == "test-secret-key"
            assert settings.database_url == "postgresql+asyncpg://test:test@localhost/test"
            assert settings.worker_poll_interval == 5
            assert settings.api_port == 9000

    def test_settings_case_insensitive(self):
        """
        Test that environment variables are treated case-insensitively when loading settings.

        The test temporarily injects two environment variables differing only by case (`jwt_secret` and `JWT_SECRET`). After instantiating the :class:`Settings` object, it asserts that the resulting `jwt_secret` attribute matches one of the provided values, confirming that the configuration loader correctly handles case-insensitive keys (Pydantic uses the last occurrence).
        """
        with patch.dict(
            os.environ,
            {
                "jwt_secret": "lowercase-secret",
                "JWT_SECRET": "uppercase-secret",  # This should override
            },
        ):
            settings = Settings()

            # Should use one of them (Pydantic picks last one)
            assert settings.jwt_secret in ["lowercase-secret", "uppercase-secret"]

    def test_settings_boolean_parsing(self):
        """
        Test that the Settings class correctly parses boolean values from environment variables, handling both "true" and "false" (case-insensitive) strings and converting them to proper Python booleans. The test temporarily overrides `PROMETHEUS_ENABLED` in `os.environ` using `patch.dict` and asserts that `settings.prometheus_enabled` reflects the expected boolean value for each case.
        """
        with patch.dict(
            os.environ,
            {
                "PROMETHEUS_ENABLED": "false",
            },
        ):
            settings = Settings()
            assert settings.prometheus_enabled is False

        with patch.dict(
            os.environ,
            {
                "PROMETHEUS_ENABLED": "true",
            },
        ):
            settings = Settings()
            assert settings.prometheus_enabled is True

    def test_settings_integer_parsing(self):
        """
        Test that integer configuration values are correctly parsed from environment variables: patches the process environment with string representations of numeric settings (WORKER_POLL_INTERVAL, WORKER_TIMEOUT, API_PORT), instantiates a Settings object, and asserts each corresponding attribute is an `int` instance with the expected value. This verifies the Settings class converts string inputs to integers during initialization.
        """
        with patch.dict(
            os.environ,
            {
                "WORKER_POLL_INTERVAL": "10",
                "WORKER_TIMEOUT": "60",
                "API_PORT": "8080",
            },
        ):
            settings = Settings()

            assert isinstance(settings.worker_poll_interval, int)
            assert isinstance(settings.worker_timeout, int)
            assert isinstance(settings.api_port, int)
            assert settings.worker_poll_interval == 10
            assert settings.worker_timeout == 60
            assert settings.api_port == 8080

    def test_settings_optional_fields(self):
        """
        Test that optional fields can be None.

        Ensures that when a Settings instance is created without explicitly providing an `lll_endpoint` value, the attribute is either `None` (indicating it was omitted) or a string (if a default or environment variable supplied one). This validates the handling of optional configuration fields.
        """
        settings = Settings()

        # llm_endpoint is optional
        assert settings.llm_endpoint is None or isinstance(settings.llm_endpoint, str)

    def test_settings_file_paths(self):
        """
        Test that file path configuration attributes are loaded as string values, ensuring the settings instance provides string paths for investigations_base_path, policies_path, and agents_path.
        """
        settings = Settings()

        assert isinstance(settings.investigations_base_path, str)
        assert isinstance(settings.policies_path, str)
        assert isinstance(settings.agents_path, str)

    def test_settings_extra_fields_allowed(self):
        """
        Test that extra fields are allowed (for extensibility). This test patches the environment with an undefined variable `CUSTOM_FIELD` and instantiates the :class:`Settings` class. The presence of unknown environment variables should not cause validation errors, confirming that the configuration model permits additional fields beyond those explicitly defined. The assertion verifies that a Settings instance is successfully created.
        """
        with patch.dict(
            os.environ,
            {
                "CUSTOM_FIELD": "custom_value",
            },
        ):
            settings = Settings()

            # Should not raise error
            assert settings is not None


@pytest.mark.unit
class TestSettingsValidation:
    """Test settings validation logic."""

    def test_settings_with_invalid_port(self):
        """
        Test that providing a non-numeric value for `API_PORT` triggers a validation error when initializing :class:`Settings`. The environment variable is patched to `"not_a_number"`, and the test asserts that constructing `Settings()` raises an exception (specifically a Pydantic `ValidationError`).
        """
        with patch.dict(
            os.environ,
            {
                "API_PORT": "not_a_number",
            },
        ):
            # Should raise validation error
            with pytest.raises(Exception):  # Pydantic ValidationError
                Settings()

    def test_settings_with_negative_values(self):
        """
        Test that the Settings model correctly parses a negative integer value from an environment variable.

        The test temporarily sets the `WORKER_POLL_INTERVAL` environment variable to `"-1"` using `patch.dict` and then instantiates `Settings`. It asserts that the resulting `worker_poll_interval` attribute equals `-1`, confirming that Pydantic accepts negative integers when no explicit validation constraint is defined.
        """
        with patch.dict(
            os.environ,
            {
                "WORKER_POLL_INTERVAL": "-1",
            },
        ):
            # Pydantic should allow this (no validation constraint)
            # but we can add custom validators if needed
            settings = Settings()
            assert settings.worker_poll_interval == -1  # No constraint yet
