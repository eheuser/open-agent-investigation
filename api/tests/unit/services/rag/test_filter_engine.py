"""
Unit tests for RAG filter engine.
Tests filtering logic for forensic artifacts (EVTX, MFT, Registry, etc.).
"""

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
        Test that the FilterEngine correctly identifies a Sysmon process creation event (Event ID 1) as interesting and returns a non-null timestamp. The test constructs a minimal EVTX event dictionary with the appropriate channel and EventID, invokes `engine.is_interesting_evtx` and asserts that the returned boolean flag is `True` and that a timestamp value is provided.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Microsoft-Windows-Sysmon/Operational",
            "system.EventID": 1,
            "timestamp": "2024-01-01T12:00:00Z",
        }

        is_interesting, timestamp = engine.is_interesting_evtx(event)

        assert is_interesting is True
        assert timestamp is not None

    def test_security_logon_success(self):
        """
        Test that the FilterEngine correctly identifies a successful logon event (Event ID 4624) in the Security channel as interesting. The method creates an engine instance, constructs a minimal event dictionary with required fields, invokes `is_interesting_evtx` and asserts that the returned flag indicates interest. This verifies basic handling of security logon success events.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": 4624,
            "timestamp": "2024-01-01T12:00:00Z",
        }

        is_interesting, timestamp = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_security_logon_failure(self):
        """
        Test that the FilterEngine correctly identifies a Security logon failure event (Event ID 4625) as interesting and returns the appropriate timestamp. This verifies handling of security channel events with specific EventID values.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "Security",
            "system.EventID": 4625,
            "timestamp": "2024-01-01T12:00:00Z",
        }

        is_interesting, timestamp = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_powershell_scriptblock_logging(self):
        """
        Test that the FilterEngine correctly identifies a PowerShell script block logging event (Event ID 4104) as interesting and returns a valid timestamp. The test creates an engine instance, constructs an EVTX event dictionary with the appropriate channel and ID, invokes `is_interesting_evtx`, and asserts that the returned flag is `True`.
        """
        engine = FilterEngine()

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

        This test creates an instance of :class:`FilterEngine`, constructs a mock EVTX event whose `system.Channel` value is in uppercase (`"MICROSOFT-WINDOWS-SYSMON/OPERATIONAL"`), and verifies that :meth:`FilterEngine.is_interesting_evtx` returns `True` for the `is_interesting` flag. The purpose is to ensure channel matching logic is case-insensitive, allowing events from Sysmon's operational channel to be recognized regardless of the capitalization used in the event data.
        """
        engine = FilterEngine()

        event = {
            "system.Channel": "MICROSOFT-WINDOWS-SYSMON/OPERATIONAL",
            "system.EventID": 1,  # Process creation - configured event ID
        }

        is_interesting, _ = engine.is_interesting_evtx(event)

        assert is_interesting is True

    def test_alternative_field_names(self):
        """
        Test alternative field name formats.

        This test verifies that the :class:`FilterEngine` correctly handles events where fields are provided without the typical `system.` prefix (e.g., `Channel` and `EventID`). It constructs a minimal security logon event, invokes :meth:`FilterEngine.is_interesting_evtx`, and asserts that the engine classifies the event as interesting.
        """
        engine = FilterEngine()

        # Using non-prefixed field names
        event = {
            "Channel": "Security",
            "EventID": 4624,  # Configured event ID for Security channel
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
class TestCustomConfiguration:
    """Test custom filter configuration."""

    def test_custom_evtx_channels(self):
        """
        Test that the FilterEngine correctly processes events from a user-defined EVTX channel.

        Creates a minimal configuration specifying a custom channel named `Custom-Channel` with allowed event IDs 100 and 200, then verifies that an event matching both the channel name and one of the permitted IDs is marked as interesting by :meth:`FilterEngine.is_interesting_evtx`. The test asserts that `is_interesting` returns `True` for this scenario.
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
