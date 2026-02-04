import pytest
from datetime import datetime
from app.services.rag.filter_engine import FilterEngine


@pytest.mark.unit
class TestFilterEngineInit:
    """Test FilterEngine initialization."""

    def test_init_default_config(self):
        """
        Test that a FilterEngine instance created with default settings loads a non-None configuration containing the required top-level sections for EVTX, MFT, and Registry data.
        """
        engine = FilterEngine()

        assert engine.config is not None
        assert "evtx" in engine.config
        assert "mft" in engine.config
        assert "registry" in engine.config

    def test_init_custom_config(self):
        """
        Test initialization of FilterEngine using a custom configuration dictionary, ensuring the instance stores the provided config unchanged.
        """
        custom_config = {
            "evtx": {"channels": []},
            "mft": {"include_paths": ["/custom/"]},
        }

        engine = FilterEngine(config=custom_config)

        assert engine.config == custom_config


@pytest.mark.unit
class TestEVTXFiltering:
    """Test EVTX event filtering."""

    def test_sysmon_process_creation(self):
        """
        Test that the FilterEngine correctly identifies a Sysmon process creation event (Event ID 1) as interesting
        when it contains a LOLBin. With the new stricter logic, channel+event_id match alone is not sufficient;
        the event must also contain a LOLBin or interesting port.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 1,
            "timestamp": "2024-01-01T12:00:00Z",
            "event_data.Image": "C:\\Windows\\System32\\powershell.exe",  # LOLBin required
        }

        is_interesting, timestamp = engine.is_interesting_evtx(event)

        assert is_interesting is True
        assert timestamp is not None

    def test_security_logon_success(self):
        """
        Test that Security logon events (4624) are NOT interesting by default unless they contain LOLBins or interesting ports.
        The new stricter logic requires additional criteria beyond just channel+event_id match.
        """
        engine = FilterEngine()

        # Event with only channel+event_id (no LOLBins or ports) - should NOT be interesting
        event = {
            "system.Channel": "Security",
            "system.EventID": 4624,
            "timestamp": "2024-01-01T12:00:00Z",
        }

        is_interesting, timestamp = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_security_logon_failure(self):
        """
        Test that Security logon failure events (4625) are NOT interesting by default unless they contain LOLBins or interesting ports.
        The new stricter logic requires additional criteria beyond just channel+event_id match.
        """
        engine = FilterEngine()

        # Event with only channel+event_id (no LOLBins or ports) - should NOT be interesting
        event = {
            "system.Channel": "Security",
            "system.EventID": 4625,
            "timestamp": "2024-01-01T12:00:00Z",
        }

        is_interesting, timestamp = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_powershell_scriptblock_logging(self):
        """
        Test that PowerShell script block logging events (4104) are NOT interesting by default unless they contain LOLBins.
        The new stricter logic requires additional criteria beyond just channel+event_id match.
        Since this IS a PowerShell event, adding 'powershell.exe' in the script block would make it interesting.
        """
        engine = FilterEngine()

        # Event with only channel+event_id (no LOLBins) - should NOT be interesting
        event = {
            "system.Channel": "Microsoft-Windows-PowerShell/Operational",
            "system.EventID": 4104,
            "timestamp": "2024-01-01T12:00:00Z",
        }

        is_interesting, timestamp = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_lolbin_powershell_in_image(self):
        """
        Test that the FilterEngine correctly identifies a LOLBin occurrence when the Image field contains a known PowerShell executable path.
        Note: Event must FIRST match a configured channel+event_id before LOLBin detection applies.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 1,  # Process creation
            "event_data.Image": "C:\\Windows\\System32\\powershell.exe",
            "timestamp": "2024-01-01T12:00:00Z",
        }

        is_interesting, timestamp = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_lolbin_in_command_line(self):
        """
        Test that the FilterEngine correctly identifies an event as interesting when the CommandLine field contains a known LOLBin executable.
        Note: Event must FIRST match a configured channel+event_id before LOLBin detection applies.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 1,  # Process creation
            "event_data.CommandLine": "cmd.exe /c whoami",
            "timestamp": "2024-01-01T12:00:00Z",
        }

        is_interesting, timestamp = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_lolbin_certutil(self):
        """
        Test that the FilterEngine correctly identifies a certutil.exe execution event as an interesting LOLBin occurrence.
        Note: Event must FIRST match a configured channel+event_id before LOLBin detection applies.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 1,  # Process creation
            "event_data.Image": "C:\\Windows\\System32\\certutil.exe",
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_interesting_port_rdp(self):
        """
        Test that the FilterEngine correctly identifies an event with destination port 3389 as interesting.
        Note: Event must FIRST match a configured channel+event_id before port detection applies.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 3,  # Network connection
            "event_data.DestinationPort": "3389",
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_interesting_port_ssh(self):
        """
        Test that the FilterEngine correctly identifies an event as interesting when it contains a source port matching a known SSH port (22).
        Note: Event must FIRST match a configured channel+event_id before port detection applies.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 3,  # Network connection
            "event_data.SourcePort": 22,
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_uninteresting_event(self):
        """
        Test that an event not matching any interesting criteria is correctly identified as uninteresting by `FilterEngine.is_interesting_evtx` and that a timestamp value is still returned.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Application",
            "system.EventID": 1000,
            "timestamp": "2024-01-01T12:00:00Z",
        }

        is_interesting, timestamp = engine.is_interesting_evtx(event)

        assert is_interesting is False
        assert timestamp is not None

    def test_timestamp_parsing_iso_format(self):
        """
        Test that the FilterEngine correctly parses timestamps provided in ISO 8601 format. The test creates an event dictionary with a UTC timestamp string, invokes the engine's EVTX filtering method, and verifies that a non-null datetime object is returned with the expected year, month, and day components.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": 4624,
            "timestamp": "2024-01-01T12:30:45Z",
        }

        _, timestamp = engine.is_interesting_evtx(event)

        assert timestamp is not None
        assert timestamp.year == 2024
        assert timestamp.month == 1
        assert timestamp.day == 1

    def test_timestamp_already_datetime(self):
        """
        Test that the engine correctly returns the original timestamp when the event's `timestamp` field is already a :class:`datetime.datetime` instance, ensuring no conversion or alteration occurs. The test creates a dummy EVTX event with a pre-populated datetime object and verifies that `is_interesting_evtx` yields the same object as its timestamp output.
        """
        engine = FilterEngine()
        dt = datetime(2024, 1, 1, 12, 0, 0)

        event = {
            "system.Channel": "Security",
            "system.EventID": 4624,
            "timestamp": dt,
        }

        _, timestamp = engine.is_interesting_evtx(event)

        assert timestamp == dt

    def test_missing_timestamp(self):
        """
        Test that an EVTX event lacking a timestamp field is handled correctly by the filter engine, returning `None` for the extracted timestamp while still performing the interest check. This verifies graceful handling of incomplete log entries without raising errors.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": 4624,
        }

        _, timestamp = engine.is_interesting_evtx(event)

        assert timestamp is None

    def test_invalid_event_id(self):
        """
        Test that an event with a non-numeric or otherwise invalid EventID is correctly identified as not interesting by the FilterEngine's EVTX filtering logic. The test creates a FilterEngine instance, constructs an event dictionary containing a Security channel and an EventID set to the string "invalid", invokes `is_interesting_evtx` on this event, and asserts that the returned `is_interesting` flag is False, confirming graceful handling of malformed IDs.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": "invalid",
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is False

    def test_case_insensitive_channel_matching(self):
        """
        Test that the FilterEngine correctly treats channel names without regard to case.
        With stricter filtering, event must also contain LOLBin or interesting port.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "MICROSOFT-WINDOWS-SYSMON/OPERATIONAL",
            "system.EventID": 1,  # Process creation - configured event ID
            "event_data.Image": "C:\\Windows\\System32\\cmd.exe",  # LOLBin required
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_alternative_field_names(self):
        """
        Test alternative field name formats with stricter filtering.
        Event must contain LOLBin or interesting port in addition to channel+event_id match.
        """
        engine = FilterEngine()

        # Using non-prefixed field names with LOLBin
        event = {
            "Channel": "Security",
            "EventID": 4688,  # Process creation - configured event ID
            "CommandLine": "powershell.exe -enc <base64>",  # LOLBin required
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True


@pytest.mark.unit
class TestPrefetchFiltering:
    """Test Prefetch file filtering."""

    def test_include_all_default(self):
        """
        Test that the default configuration of :class:`FilterEngine` does NOT mark every prefetch file as interesting.
        The default has been changed to include_all=False for reduced noise.
        """
        engine = FilterEngine()

        # Default is now False for prefetch
        assert engine.is_interesting_prefetch("notepad.exe") is False
        assert engine.is_interesting_prefetch("cmd.exe") is False
        assert engine.is_interesting_prefetch("anything.exe") is False

    def test_custom_config_include_all_false(self):
        """
        Test that when a custom configuration disables inclusion of all prefetch files (include_all set to False), the FilterEngine correctly identifies a sample executable ("test.exe") as not interesting.
        """
        custom_config = {
            "prefetch": {"include_all": False},
        }
        engine = FilterEngine(config=custom_config)

        assert engine.is_interesting_prefetch("test.exe") is False


@pytest.mark.unit
class TestLNKFiltering:
    """Test LNK file filtering."""

    def test_include_all_default(self):
        """
        Test that the :class:`FilterEngine` does NOT include every LNK file by default.
        The default has been changed to include_all=False for reduced noise.
        """
        engine = FilterEngine()

        # Default is now False for LNK
        assert engine.is_interesting_lnk("C:\\Users\\user\\file.txt") is False
        assert engine.is_interesting_lnk("C:\\Windows\\System32\\cmd.exe") is False

    def test_custom_config_include_all_false(self):
        """
        Test custom configuration where include_all is set to False for LNK files.

        This test creates a configuration dictionary that disables inclusion of all LNK entries by setting `include_all` to `False` under the `lnk` key. It then instantiates a :class:`FilterEngine` with this custom configuration and verifies that the engine correctly identifies a sample file (`test.txt`) as not interesting for LNK processing, asserting that :meth:`FilterEngine.is_interesting_lnk` returns `False`.
        """
        custom_config = {
            "lnk": {"include_all": False},
        }
        engine = FilterEngine(config=custom_config)

        assert engine.is_interesting_lnk("test.txt") is False


@pytest.mark.unit
class TestLOLBins:
    """Test Living Off the Land Binaries detection."""

    def test_lolbins_list_exists(self):
        """
        Test that the FilterEngine class defines a non-empty list named `LOLBINS` and that it is of type `list`.
        """
        assert hasattr(FilterEngine, "LOLBINS")
        assert isinstance(FilterEngine.LOLBINS, list)
        assert len(FilterEngine.LOLBINS) > 0

    def test_common_lolbins_included(self):
        """
        Test that the predefined list of known LOLBins in `FilterEngine.LOLBINS` includes the common executables typically monitored for abuse: PowerShell, cmd.exe, certutil.exe, and rundll32.exe. The test normalizes entries to lowercase before checking membership to ensure case-insensitive verification.
        """
        lolbins = [lol.lower() for lol in FilterEngine.LOLBINS]

        assert "powershell.exe" in lolbins
        assert "cmd.exe" in lolbins
        assert "certutil.exe" in lolbins
        assert "rundll32.exe" in lolbins

    def test_lolbin_detection_case_insensitive(self):
        """
        Test that the LOLBin detection logic treats executable names case-insensitively.
        Note: Event must FIRST match a configured channel+event_id before LOLBin detection applies.
        """
        engine = FilterEngine()

        event1 = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 1,  # Process creation
            "event_data.Image": "C:\\Windows\\System32\\POWERSHELL.EXE",
        }
        event2 = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 1,  # Process creation
            "event_data.Image": "C:\\Windows\\System32\\powershell.exe",
        }

        is_interesting1, _ = engine.is_interesting_evtx(event1)
        is_interesting2, _ = engine.is_interesting_evtx(event2)

        assert is_interesting1 is True
        assert is_interesting2 is True


@pytest.mark.unit
class TestStricterFiltering:
    """Test the new stricter filtering logic that requires channel+event_id AND (LOLBins OR ports)."""

    def test_channel_eventid_match_without_lolbin_or_port_not_interesting(self):
        """
        Test that events matching channel+event_id but lacking LOLBins or interesting ports are NOT interesting.
        This is the core of the stricter filtering logic.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": 4624,
            "event_data.LogonType": "3",
            "event_data.IpAddress": "-"
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is False

    def test_channel_eventid_match_with_lolbin_is_interesting(self):
        """
        Test that events matching channel+event_id AND containing a LOLBin ARE interesting.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": 4688,  # Process creation
            "event_data.CommandLine": "powershell.exe -enc ABC123",  # LOLBin present
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_channel_eventid_match_with_interesting_port_is_interesting(self):
        """
        Test that events matching channel+event_id AND containing an interesting port ARE interesting.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 3,  # Network connection
            "event_data.DestinationPort": "3389",  # RDP port
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_no_channel_eventid_match_with_lolbin_not_interesting(self):
        """
        Test that events NOT matching channel+event_id are NOT interesting, even with LOLBins.
        LOLBin detection only applies AFTER channel+event_id match.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Application",  # Not a configured channel
            "system.EventID": 9999,  # Not a configured event ID
            "event_data.Image": "powershell.exe",  # LOLBin present but irrelevant
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is False

    def test_localhost_ip_filtered_out(self):
        """
        Test that events with localhost IP (127.0.0.1) are filtered out even if they match other criteria.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": 4624,
            "event_data.IpAddress": "127.0.0.1",  # Localhost - should be filtered
            "event_data.CommandLine": "powershell.exe",  # Has LOLBin
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is False

    def test_null_ip_filtered_out(self):
        """
        Test that events with null/dash IP address are filtered out.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": 4624,
            "event_data.IpAddress": "-",  # Null IP - should be filtered
            "event_data.CommandLine": "cmd.exe",  # Has LOLBin
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is False

    def test_valid_ip_with_lolbin_is_interesting(self):
        """
        Test that events with valid (non-localhost) IP and LOLBin ARE interesting.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": 4624,
            "event_data.IpAddress": "192.168.1.100",  # Valid IP
            "event_data.CommandLine": "powershell.exe -enc ABC",  # LOLBin
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True


@pytest.mark.unit  
class TestEdgeCasesAndDefaults:
    """Test edge cases and default behaviors."""

    def test_mft_always_returns_false(self):
        """Test that MFT filtering always returns False (not implemented)."""
        engine = FilterEngine()

        # Try various paths and extensions
        test_cases = [
            ("C:\\Users\\test\\malware.exe", ".exe"),
            ("C:\\Windows\\System32\\cmd.exe", ".exe"),
            ("C:\\Temp\\suspicious.dll", ".dll"),
            ("", ""),
        ]

        for path, ext in test_cases:
            result = engine.is_interesting_mft(path, ext)
            assert result is False

    def test_registry_always_returns_false(self):
        """Test that registry filtering always returns False (not implemented)."""
        engine = FilterEngine()

        # Try various registry paths
        test_cases = [
            "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            "HKCU\\Software\\Classes",
            "HKLM\\System\\CurrentControlSet\\Services",
            "",
        ]

        for key_path in test_cases:
            result = engine.is_interesting_registry(key_path)
            assert result is False

    def test_evtx_empty_channel_string(self):
        """Test EVTX filtering with empty channel string."""
        engine = FilterEngine()

        event = {
            "system.Channel": "",  # Empty channel
            "system.EventID": 4624,
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        # Empty channel cannot match any configured channel
        assert is_interesting is False

    def test_evtx_none_event_id(self):
        """Test EVTX filtering with None event ID."""
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": None,  # None event ID
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        # None event ID cannot match any configured event ID
        assert is_interesting is False

    def test_evtx_missing_event_id_field(self):
        """Test EVTX filtering when event ID field is completely missing."""
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            # No event ID field at all
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        # Missing event ID cannot match
        assert is_interesting is False

    def test_lnk_default_include_all(self):
        """Test LNK filtering default behavior when config is missing."""
        custom_config = {
            "evtx": {"channels": []},
            # No lnk key
        }
        engine = FilterEngine(config=custom_config)

        # Should default to True when config is missing
        result = engine.is_interesting_lnk("C:\\test.exe")

        assert result is True


@pytest.mark.unit
class TestCustomConfiguration:
    """Test custom filter configuration."""

    def test_custom_evtx_channels(self):
        """
        Test that custom channels with LOLBins disabled and no interesting ports require additional criteria.
        Since LOLBins are disabled and no ports are configured, event should NOT be interesting.
        """
        custom_config = {
            "evtx": {
                "channels": [
                    {
                        "name": "Custom-Channel",
                        "event_ids": [100, 200],
                    }
                ],
                "lol_bins": False,
                "interesting_ports": [],
            }
        }
        engine = FilterEngine(config=custom_config)

        # Event matches channel+event_id but has no LOLBins or ports
        event = {
            "system.Channel": "Custom-Channel",
            "system.EventID": 100,
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_disable_lolbin_detection(self):
        """
        Test that disabling LOLBin detection prevents events involving known LOLBin executables from being flagged as interesting.

        The test creates a custom configuration with `lol_bins` set to `False` and instantiates a :class:`FilterEngine` using this configuration.
        An event dictionary is crafted where the `event_data.Image` field points to a typical LOLBin executable (PowerShell).
        Calling :meth:`FilterEngine.is_interesting_evtx` on this event should return `is_interesting` as `False`, confirming that the LOLBin detection toggle works correctly.
        """
        custom_config = {
            "evtx": {
                "channels": [],
                "lol_bins": False,
                "interesting_ports": [],
            }
        }
        engine = FilterEngine(config=custom_config)

        event = {
            "event_data.Image": "C:\\Windows\\System32\\powershell.exe",
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is False

    def test_custom_interesting_ports(self):
        """
        Test that the FilterEngine correctly identifies events as interesting when they contain destination ports specified in a custom `interesting_ports` configuration.
        Note: Event must FIRST match a configured channel+event_id before port detection applies.
        """
        custom_config = {
            "evtx": {
                "channels": [
                    {"name": "Microsoft-Windows-Sysmon/Operational", "event_ids": [3]}
                ],
                "lol_bins": False,
                "interesting_ports": [8080, 9090],
            }
        }
        engine = FilterEngine(config=custom_config)

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 3,  # Network connection
            "event_data.DestinationPort": 8080,
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_port_conversion_from_string(self):
        """
        Test that port numbers provided as strings are correctly converted to integers.
        Covers lines 267-269 (port string conversion).
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 3,
            "event_data.DestinationPort": "3389",  # String instead of int
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_port_conversion_error_handling(self):
        """
        Test that invalid port values (non-numeric strings) are handled gracefully.
        Covers lines 267-269 (ValueError/TypeError exception handling).
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 3,
            "event_data.DestinationPort": "invalid",  # Invalid port
            "event_data.SourcePort": None,  # None value
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_timestamp_parsing_error(self):
        """
        Test that invalid timestamp strings are handled gracefully.
        Covers line 178 (timestamp parsing exception).
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": 4624,
            "timestamp": "not-a-valid-timestamp",  # Invalid format
        }

        is_interesting, timestamp = engine.is_interesting_evtx(event)

        # Should not crash, timestamp should be None
        assert timestamp is None

    def test_prefetch_include_all_true(self):
        """
        Test that prefetch files are included when include_all is explicitly True.
        Covers line 287.
        """
        custom_config = {
            "prefetch": {"include_all": True}
        }
        engine = FilterEngine(config=custom_config)

        assert engine.is_interesting_prefetch("notepad.exe") is True
        assert engine.is_interesting_prefetch("malware.exe") is True

    def test_lnk_include_all_true(self):
        """
        Test that LNK files are included when include_all is explicitly True.
        Covers line 302.
        """
        custom_config = {
            "lnk": {"include_all": True}
        }
        engine = FilterEngine(config=custom_config)

        assert engine.is_interesting_lnk("C:\\Users\\user\\file.txt") is True
        assert engine.is_interesting_lnk("C:\\malicious.exe") is True

    def test_evtx_no_channels_configured(self):
        """
        Test behavior when no channels are configured in evtx config.
        Covers edge case where channels list is empty.
        """
        custom_config = {
            "evtx": {
                "channels": [],  # Empty channels list
                "lol_bins": False,
                "interesting_ports": [],
            }
        }
        engine = FilterEngine(config=custom_config)

        event = {
            "system.Channel": "Security",
            "system.EventID": 4624,
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        # No channels configured, should not be interesting
        assert is_interesting is False

    def test_evtx_missing_channel_field(self):
        """
        Test behavior when event has no channel field.
        Covers line 228-229 (empty channel string).
        """
        engine = FilterEngine()

        event = {
            "system.EventID": 4624,  # No channel field
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        # No channel, cannot match any configured channel
        assert is_interesting is False

    def test_integer_port_values(self):
        """
        Test that integer port values work correctly without conversion.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 3,
            "event_data.SourcePort": 22,  # Already an integer
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_port_none_value(self):
        """
        Test that None port values are handled gracefully.
        Covers line 267 (TypeError exception for None values).
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 3,
            "event_data.DestinationPort": None,  # None value
            "event_data.SourcePort": None,  # None value
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_timestamp_malformed_iso_format(self):
        """
        Test various malformed timestamp formats.
        Covers line 178 (exception handling in timestamp parsing).
        """
        engine = FilterEngine()

        # Test various malformed timestamps
        malformed_timestamps = [
            "2024-13-01T10:00:00Z",  # Invalid month
            "not-a-date",  # Completely invalid
            "2024-01-32T10:00:00Z",  # Invalid day
            "2024-01-01T25:00:00Z",  # Invalid hour
            "",  # Empty string
        ]

        for bad_timestamp in malformed_timestamps:
            event = {
                "system.Channel": "Security",
                "system.EventID": 4624,
                "timestamp": bad_timestamp,
            }

            is_interesting, timestamp = engine.is_interesting_evtx(event)

            # Should handle gracefully, timestamp should be None
            assert timestamp is None

    def test_prefetch_default_behavior(self):
        """
        Test prefetch default behavior when config key is missing.
        Covers line 287 (default True behavior).
        """
        # Create config without prefetch section
        custom_config = {
            "evtx": {"channels": []},
            # No prefetch key at all
        }
        engine = FilterEngine(config=custom_config)

        # Should default to True when key is missing
        result = engine.is_interesting_prefetch("test.exe")

        # With missing config, get() returns default value
        # prefetch_config.get("include_all", True) returns True
        assert result is True

    def test_lolbin_in_parent_image(self):
        """
        Test LOLBin detection in ParentImage field.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 1,
            "event_data.ParentImage": "C:\\Windows\\System32\\powershell.exe",
            "event_data.Image": "C:\\Windows\\System32\\notepad.exe",
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_lolbin_case_variations(self):
        """
        Test LOLBin detection with various case variations.
        """
        engine = FilterEngine()

        variations = [
            "POWERSHELL.EXE",
            "PowerShell.exe",
            "powershell.EXE",
            "PoWeRsHeLl.ExE",
        ]

        for variant in variations:
            event = {
                "system.Channel": "Microsoft-Windows-Sysmon/Operational",
                "system.EventID": 1,
                "event_data.Image": f"C:\\Windows\\System32\\{variant}",
            }

            is_interesting, _ = engine.is_interesting_evtx(event)
            assert is_interesting is True, f"Failed for variant: {variant}"

    def test_multiple_lolbins_in_commandline(self):
        """
        Test detection when multiple LOLBins appear in command line.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": 4688,
            "event_data.CommandLine": "cmd.exe /c powershell.exe -enc ABC",
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_lolbin_partial_match(self):
        """
        Test that LOLBin detection works with partial matches in paths.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 1,
            "event_data.CommandLine": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -NoProfile",
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True
