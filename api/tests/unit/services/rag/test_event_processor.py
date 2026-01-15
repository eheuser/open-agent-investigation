"""
Unit tests for event_processor module.

Tests event formatting and processing logic for RAG/timeline features.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import json

from app.services.rag.event_processor import (
    _format_event_for_timeline,
    _format_sysmon_event,
    _format_security_event,
    _format_system_event,
    _format_powershell_event,
    _format_mft_event,
    _format_registry_event,
    _format_prefetch_event,
    _format_lnk_event,
    _format_generic_event,
    _batch_create_embeddings,
)


@pytest.mark.unit
class TestFormatSysmonEvent:
    """Test _format_sysmon_event function."""

    def test_process_creation_event_1(self):
        """
        Test that formatting a Sysmon Event ID 1 (Process Creation) payload produces a title containing “Process Created” and the executable name, and a description that includes both the command line arguments and the parent process image.
        """
        payload = {
            "event_data.Image": "C:\\Windows\\System32\\cmd.exe",
            "event_data.CommandLine": "cmd.exe /c whoami",
            "event_data.ParentImage": "C:\\Windows\\explorer.exe",
        }

        title, description = _format_sysmon_event("1", payload)

        assert "Process Created" in title
        assert "cmd.exe" in title
        assert "whoami" in description
        assert "explorer.exe" in description

    def test_network_connection_event_3(self):
        """
        Test that the Sysmon Event ID 3 formatter correctly generates a title containing “Network Connection” and the executable name, and a description that includes the destination IP and port formatted as “IP:Port”.
        """
        payload = {
            "event_data.Image": "C:\\Program Files\\Chrome\\chrome.exe",
            "event_data.DestinationIp": "192.168.1.100",
            "event_data.DestinationPort": "443",
        }

        title, description = _format_sysmon_event("3", payload)

        assert "Network Connection" in title
        assert "chrome.exe" in title
        assert "192.168.1.100:443" in description

    def test_file_created_event_11(self):
        """
        Test that the Sysmon formatter correctly generates a title and description for a File Created event (ID 11), ensuring the target filename appears in the title and the originating image name appears in the description.
        """
        payload = {
            "event_data.Image": "C:\\Windows\\System32\\notepad.exe",
            "event_data.TargetFilename": "C:\\Users\\test\\document.txt",
        }

        title, description = _format_sysmon_event("11", payload)

        assert "File Created" in title
        assert "document.txt" in title
        assert "notepad.exe" in description

    def test_generic_sysmon_event(self):
        """
        Test that formatting an unknown Sysmon event (ID 99) produces a title containing the generic event identifier and returns a string description. The payload is minimal, ensuring the formatter handles unexpected fields without error.
        """
        payload = {"SomeField": "SomeValue"}

        title, description = _format_sysmon_event("99", payload)

        assert "Sysmon Event 99" in title
        assert isinstance(description, str)


@pytest.mark.unit
class TestFormatSecurityEvent:
    """Test _format_security_event function."""

    def test_successful_logon_4624(self):
        """
        Test that the security event formatter correctly creates a title and description for Event ID 4624 (Successful Logon) using sample payload data. The test verifies that the generated title contains the phrase “Successful Logon” and the target user name, and that the description includes the logon type and IP address extracted from the payload.
        """
        payload = {
            "event_data.TargetUserName": "Administrator",
            "event_data.LogonType": "10",
            "event_data.IpAddress": "192.168.1.50",
        }

        title, description = _format_security_event("4624", payload)

        assert "Successful Logon" in title
        assert "Administrator" in title
        assert "Logon Type: 10" in description
        assert "192.168.1.50" in description

    def test_failed_logon_4625(self):
        """
        Test that the security event formatter correctly handles Event ID 4625 (Failed Logon) by generating a title containing “Failed Logon” and the target username, and a description that includes the source IP address from the provided payload.
        """
        payload = {"event_data.TargetUserName": "admin", "event_data.IpAddress": "10.0.0.100"}

        title, description = _format_security_event("4625", payload)

        assert "Failed Logon" in title
        assert "admin" in title
        assert "10.0.0.100" in description

    def test_process_creation_4688(self):
        """
        Test that the security event formatter correctly handles Event ID 4688 (Process Creation) by generating an appropriate title containing “Process Created” and the executable name, and a description that includes the command line invocation. The test supplies a payload with `NewProcessName` and `CommandLine`, invokes `_format_security_event`, and asserts that the resulting strings contain the expected substrings.
        """
        payload = {
            "event_data.NewProcessName": "C:\\Windows\\System32\\powershell.exe",
            "event_data.CommandLine": "powershell -enc ZQBj...",
        }

        title, description = _format_security_event("4688", payload)

        assert "Process Created" in title
        assert "powershell.exe" in title
        assert "powershell -enc" in description

    def test_user_account_created_4720(self):
        """
        Test that the security event formatter correctly generates a title and description for Event ID 4720 (User Account Created). The test supplies a payload containing the target user name, invokes `_format_security_event` with the event ID and payload, and verifies that the resulting title includes both the expected event description ("User Account Created") and the specific user name from the payload.
        """
        payload = {"event_data.TargetUserName": "newuser"}

        title, description = _format_security_event("4720", payload)

        assert "User Account Created" in title
        assert "newuser" in title

    def test_service_installation_7045(self):
        """
        Test that the formatter for Security Event ID 7045 correctly generates a title containing “Service Installed” and the service name, and produces a description that includes the basename of the image path (e.g., “malware.exe”).
        """
        payload = {
            "event_data.ServiceName": "MaliciousService",
            "event_data.ImagePath": "C:\\Temp\\malware.exe",
        }

        title, description = _format_security_event("7045", payload)

        assert "Service Installed" in title
        assert "MaliciousService" in title
        assert "malware.exe" in description


@pytest.mark.unit
class TestFormatSystemEvent:
    """Test _format_system_event function."""

    def test_service_installation_7045(self):
        """
        Test that the System event formatter correctly handles Event ID 7045 (service installation). It builds a payload with a service name and image path, invokes `_format_system_event`, and asserts that the generated title contains “Service Installed” and the service name, while the description includes the executable filename.
        """
        payload = {
            "event_data.ServiceName": "TestService",
            "event_data.ImagePath": "C:\\Windows\\service.exe",
        }

        title, description = _format_system_event("7045", payload)

        assert "Service Installed" in title
        assert "TestService" in title
        assert "service.exe" in description

    def test_generic_system_event(self):
        """
        Test that the generic system event formatter produces a title containing the correct event identifier.

        The test constructs a minimal payload dictionary and invokes `_format_system_event` with an arbitrary event ID ("100"). It then asserts that the returned title includes the expected string "System Event 100", confirming that the formatting logic correctly incorporates the event type and identifier.
        """
        payload = {"Field": "Value"}

        title, description = _format_system_event("100", payload)

        assert "System Event 100" in title


@pytest.mark.unit
class TestFormatPowerShellEvent:
    """Test _format_powershell_event function."""

    def test_powershell_script_execution(self):
        """
        Test that the PowerShell event formatter correctly generates a title containing “PowerShell Execution” and includes the script snippet (e.g., “Get-Process”) in the description when given a payload with a ScriptBlockText field.
        """
        payload = {
            "event_data.ScriptBlockText": "Get-Process | Where-Object {$_.Name -eq 'explorer'}"
        }

        title, description = _format_powershell_event("4104", payload)

        assert "PowerShell Execution" in title
        assert "Get-Process" in description


@pytest.mark.unit
class TestFormatMFTEvent:
    """Test _format_mft_event function."""

    def test_mft_file_activity(self):
        """
        Test that the MFT file-activity formatter produces a title containing “File Activity” and the filename.

        The test builds a payload with a Windows path to a suspicious executable, calls `_format_mft_event` and asserts that the returned title includes the generic “File Activity” label as well as the specific filename (`suspicious.exe`). No assertions are made on the description content.
        """
        payload = {
            "path": "C:\\Users\\test\\Downloads\\suspicious.exe",
            "file_path": "C:\\Users\\test\\Downloads\\suspicious.exe",
        }

        title, description = _format_mft_event(payload)

        assert "File Activity" in title
        assert "suspicious.exe" in title


@pytest.mark.unit
class TestFormatRegistryEvent:
    """Test _format_registry_event function."""

    def test_registry_key_access(self):
        """
        Test that the registry event formatter produces a title containing “Registry Key” and includes the final component (“Run”) of the provided key path. The payload supplies a sample Windows Registry key path, which is passed to `_format_registry_event`; the resulting title and description are then verified for expected content.
        """
        payload = {"key_path": "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"}

        title, description = _format_registry_event(payload)

        assert "Registry Key" in title
        assert "Run" in title


@pytest.mark.unit
class TestFormatPrefetchEvent:
    """Test _format_prefetch_event function."""

    def test_prefetch_execution(self):
        """
        Test that the prefetch event formatter correctly generates a title containing the word “Prefetch” and the executable name, and that the description includes the run count from the payload.
        """
        payload = {"executable": "NOTEPAD.EXE", "run_count": 42}

        title, description = _format_prefetch_event(payload)

        assert "Prefetch" in title
        assert "NOTEPAD.EXE" in title
        assert "Run Count: 42" in description


@pytest.mark.unit
class TestFormatLnkEvent:
    """Test _format_lnk_event function."""

    def test_lnk_file_reference(self):
        """
        Test that the LNK event formatter generates a title containing "LNK File" and includes the executable name from the target path in the title. The payload provides a Windows command executable path, and the test asserts both expected substrings appear in the formatted title.
        """
        payload = {"target_path": "C:\\Windows\\System32\\cmd.exe"}

        title, description = _format_lnk_event(payload)

        assert "LNK File" in title
        assert "cmd.exe" in title


@pytest.mark.unit
class TestFormatGenericEvent:
    """Test _format_generic_event function."""

    def test_generic_event_formatting(self):
        """
        Test that generic unknown events are formatted correctly.

        Creates a sample payload with mixed data types and passes it along with a custom event type to the internal `_format_generic_event` helper. Asserts that the returned title and description strings are generated as expected for an unrecognized event category.
        """
        payload = {"key": "value", "number": 123}

        title, description = _format_generic_event("custom_event_type", payload)
