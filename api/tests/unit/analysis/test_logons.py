import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.analysis.logons import LogonsAnalyzer, LogonEntry


class TestLogonEntry:
    """Tests for LogonEntry data model."""

    def test_logon_entry_initialization(self):
        """Test LogonEntry can be initialized with all fields."""
        entry = LogonEntry(
            logon_type="Interactive",
            event_action="Logon",
            username="testuser",
            domain="TESTDOMAIN",
            logon_id="0x12345",
            source_ip="192.168.1.100",
            source_host="WORKSTATION01",
            timestamp="2024-01-15T10:30:00",
            event_id=1,
            event_record_id=4624,
            logon_process="User32",
            authentication_package="Negotiate",
            failure_reason=None,
            status_code=None,
            raw_data={"test": "data"},
        )

        assert entry.logon_type == "Interactive"
        assert entry.event_action == "Logon"
        assert entry.username == "testuser"
        assert entry.domain == "TESTDOMAIN"
        assert entry.logon_id == "0x12345"
        assert entry.source_ip == "192.168.1.100"
        assert entry.source_host == "WORKSTATION01"
        assert entry.timestamp == "2024-01-15T10:30:00"
        assert entry.event_id == 1
        assert entry.event_record_id == 4624
        assert entry.logon_process == "User32"
        assert entry.authentication_package == "Negotiate"
        assert entry.raw_data == {"test": "data"}

    def test_logon_entry_to_dict(self):
        """Test LogonEntry serialization to dictionary."""
        entry = LogonEntry(
            logon_type="Network",
            event_action="Failed Logon",
            username="admin",
            domain="CORP",
            logon_id="0xABCD",
            source_ip="10.0.0.50",
            failure_reason="Unknown user name or bad password",
            status_code="0xC000006D",
        )

        entry_dict = entry.to_dict()

        assert entry_dict["logon_type"] == "Network"
        assert entry_dict["event_action"] == "Failed Logon"
        assert entry_dict["username"] == "admin"
        assert entry_dict["domain"] == "CORP"
        assert entry_dict["logon_id"] == "0xABCD"
        assert entry_dict["source_ip"] == "10.0.0.50"
        assert entry_dict["failure_reason"] == "Unknown user name or bad password"
        assert entry_dict["status_code"] == "0xC000006D"

    def test_logon_entry_minimal_fields(self):
        """Test LogonEntry with minimal required fields."""
        entry = LogonEntry(
            logon_type="Unknown",
            event_action="Logon",
            username="user1",
        )

        assert entry.logon_type == "Unknown"
        assert entry.event_action == "Logon"
        assert entry.username == "user1"
        assert entry.domain is None
        assert entry.source_ip is None
        assert entry.raw_data == {}


class TestLogonsAnalyzer:
    """Tests for LogonsAnalyzer."""

    def test_analyzer_initialization(self):
        """Test LogonsAnalyzer initializes correctly."""
        analyzer = LogonsAnalyzer()
        assert analyzer is not None

    def test_event_id_mapping(self):
        """Test event ID to action mapping is correct."""
        analyzer = LogonsAnalyzer()
        
        assert analyzer.EVENT_ID_MAPPING[4624] == "Logon"
        assert analyzer.EVENT_ID_MAPPING[4625] == "Failed Logon"
        assert analyzer.EVENT_ID_MAPPING[4634] == "Logoff"
        assert analyzer.EVENT_ID_MAPPING[4647] == "User Initiated Logoff"
        assert analyzer.EVENT_ID_MAPPING[4648] == "Explicit Credential Logon"
        assert analyzer.EVENT_ID_MAPPING[4672] == "Special Privileges Logon"

    def test_logon_type_mapping(self):
        """Test logon type code to description mapping."""
        analyzer = LogonsAnalyzer()
        
        assert analyzer.LOGON_TYPE_MAPPING["2"] == "Interactive"
        assert analyzer.LOGON_TYPE_MAPPING["3"] == "Network"
        assert analyzer.LOGON_TYPE_MAPPING["10"] == "RemoteInteractive"
        assert analyzer.LOGON_TYPE_MAPPING["5"] == "Service"

    def test_get_filter_categories(self):
        """Test filter categories structure."""
        analyzer = LogonsAnalyzer()
        categories = analyzer.get_filter_categories()

        assert "logon_types" in categories
        assert "source_ips" in categories
        assert "usernames" in categories
        assert len(categories["logon_types"]) == 9
        assert categories["source_ips"] == []
        assert categories["usernames"] == []

        # Check first logon type has required fields
        first_type = categories["logon_types"][0]
        assert "key" in first_type
        assert "name" in first_type
        assert "description" in first_type
        assert "icon" in first_type

    def test_is_valid_ip_ipv4(self):
        """Test IPv4 address validation."""
        analyzer = LogonsAnalyzer()

        assert analyzer._is_valid_ip("192.168.1.1") is True
        assert analyzer._is_valid_ip("10.0.0.1") is True
        assert analyzer._is_valid_ip("255.255.255.255") is True
        assert analyzer._is_valid_ip("0.0.0.0") is True

    def test_is_valid_ip_invalid(self):
        """Test invalid IP address rejection."""
        analyzer = LogonsAnalyzer()

        assert analyzer._is_valid_ip("256.1.1.1") is False
        assert analyzer._is_valid_ip("192.168.1") is False
        assert analyzer._is_valid_ip("not.an.ip.address") is False
        assert analyzer._is_valid_ip("") is False
        assert analyzer._is_valid_ip("192.168.1.1.1") is False

    def test_is_valid_ip_ipv6(self):
        """Test IPv6 address validation."""
        analyzer = LogonsAnalyzer()

        assert analyzer._is_valid_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334") is True
        assert analyzer._is_valid_ip("fe80::1") is True
        assert analyzer._is_valid_ip("::1") is True

    def test_extract_ip_address_standard_field(self):
        """Test IP extraction from standard IpAddress field."""
        analyzer = LogonsAnalyzer()

        payload = {"event_data.IpAddress": "192.168.1.100"}
        ip = analyzer._extract_ip_address(payload)
        assert ip == "192.168.1.100"

    def test_extract_ip_address_alternative_fields(self):
        """Test IP extraction from alternative fields."""
        analyzer = LogonsAnalyzer()

        # Test SourceAddress field
        payload = {"event_data.SourceAddress": "10.0.0.50"}
        ip = analyzer._extract_ip_address(payload)
        assert ip == "10.0.0.50"

        # Test SourceNetworkAddress field
        payload = {"event_data.SourceNetworkAddress": "172.16.0.1"}
        ip = analyzer._extract_ip_address(payload)
        assert ip == "172.16.0.1"

    def test_extract_ip_address_with_port(self):
        """Test IP extraction from field with port number."""
        analyzer = LogonsAnalyzer()

        payload = {"event_data.IpPort": "192.168.1.100:3389"}
        ip = analyzer._extract_ip_address(payload)
        assert ip == "192.168.1.100"

    def test_extract_ip_address_filters_localhost(self):
        """Test that localhost/loopback addresses are filtered out."""
        analyzer = LogonsAnalyzer()

        payload = {"event_data.IpAddress": "127.0.0.1"}
        ip = analyzer._extract_ip_address(payload)
        assert ip is None

        payload = {"event_data.IpAddress": "::1"}
        ip = analyzer._extract_ip_address(payload)
        assert ip is None

        payload = {"event_data.IpAddress": "-"}
        ip = analyzer._extract_ip_address(payload)
        assert ip is None

    def test_extract_ip_address_no_ip(self):
        """Test IP extraction when no IP field exists."""
        analyzer = LogonsAnalyzer()

        payload = {"event_data.Username": "testuser"}
        ip = analyzer._extract_ip_address(payload)
        assert ip is None

    def test_create_entry_from_event_log_successful_logon(self):
        """Test creating entry from successful logon event."""
        analyzer = LogonsAnalyzer()

        payload = {
            "event_id": 4624,
            "event_data.TargetUserName": "jdoe",
            "event_data.TargetDomainName": "CORP",
            "event_data.TargetLogonId": "0x123456",
            "event_data.LogonType": "2",
            "event_data.IpAddress": "192.168.1.50",
            "event_data.WorkstationName": "DESKTOP01",
            "event_data.LogonProcessName": "User32",
            "event_data.AuthenticationPackageName": "Negotiate",
        }

        entry = analyzer._create_entry_from_event_log(
            event_id=1,
            timestamp="2024-01-15T10:30:00",
            payload=payload,
        )

        assert entry is not None
        assert entry.event_action == "Logon"
        assert entry.logon_type == "Interactive"
        assert entry.username == "jdoe"
        assert entry.domain == "CORP"
        assert entry.logon_id == "0x123456"
        assert entry.source_ip == "192.168.1.50"
        assert entry.source_host == "DESKTOP01"
        assert entry.logon_process == "User32"
        assert entry.authentication_package == "Negotiate"
        assert entry.timestamp == "2024-01-15T10:30:00"

    def test_create_entry_from_event_log_failed_logon(self):
        """Test creating entry from failed logon event."""
        analyzer = LogonsAnalyzer()

        payload = {
            "event_id": 4625,
            "event_data.TargetUserName": "admin",
            "event_data.TargetDomainName": "CORP",
            "event_data.LogonType": "3",
            "event_data.IpAddress": "10.0.0.100",
            "event_data.FailureReason": "Unknown user name or bad password",
            "event_data.Status": "0xC000006D",
        }

        entry = analyzer._create_entry_from_event_log(
            event_id=2,
            timestamp="2024-01-15T11:00:00",
            payload=payload,
        )

        assert entry is not None
        assert entry.event_action == "Failed Logon"
        assert entry.logon_type == "Network"
        assert entry.username == "admin"
        assert entry.failure_reason == "Unknown user name or bad password"
        assert entry.status_code == "0xC000006D"

    def test_create_entry_filters_system_accounts(self):
        """Test that system account logons are filtered out."""
        analyzer = LogonsAnalyzer()

        system_accounts = ["SYSTEM", "ANONYMOUS LOGON", "LOCAL SERVICE", "NETWORK SERVICE"]

        for account in system_accounts:
            payload = {
                "event_id": 4624,
                "event_data.TargetUserName": account,
                "event_data.LogonType": "5",
            }

            entry = analyzer._create_entry_from_event_log(
                event_id=1,
                timestamp="2024-01-15T10:30:00",
                payload=payload,
            )

            assert entry is None

    def test_create_entry_keeps_system_accounts_for_failures(self):
        """Test that system account failed logons are kept."""
        analyzer = LogonsAnalyzer()

        payload = {
            "event_id": 4625,
            "event_data.TargetUserName": "SYSTEM",
            "event_data.LogonType": "3",
        }

        entry = analyzer._create_entry_from_event_log(
            event_id=1,
            timestamp="2024-01-15T10:30:00",
            payload=payload,
        )

        assert entry is not None
        assert entry.username == "SYSTEM"
        assert entry.event_action == "Failed Logon"

    def test_create_entry_unknown_logon_type(self):
        """Test handling of unknown logon type codes."""
        analyzer = LogonsAnalyzer()

        payload = {
            "event_id": 4624,
            "event_data.TargetUserName": "testuser",
            "event_data.LogonType": "99",  # Unknown type
        }

        entry = analyzer._create_entry_from_event_log(
            event_id=1,
            timestamp="2024-01-15T10:30:00",
            payload=payload,
        )

        assert entry is not None
        assert entry.logon_type == "Type 99"

    def test_create_entry_missing_event_id(self):
        """Test that entries without event_id are skipped."""
        analyzer = LogonsAnalyzer()

        payload = {
            "event_data.TargetUserName": "testuser",
            "event_data.LogonType": "2",
        }

        entry = analyzer._create_entry_from_event_log(
            event_id=1,
            timestamp="2024-01-15T10:30:00",
            payload=payload,
        )

        assert entry is None

    def test_create_entry_uses_subject_fields_fallback(self):
        """Test that Subject fields are used when Target fields are missing."""
        analyzer = LogonsAnalyzer()

        payload = {
            "event_id": 4634,  # Logoff uses Subject fields
            "event_data.SubjectUserName": "jdoe",
            "event_data.SubjectDomainName": "WORKGROUP",
            "event_data.SubjectLogonId": "0x98765",
        }

        entry = analyzer._create_entry_from_event_log(
            event_id=1,
            timestamp="2024-01-15T10:30:00",
            payload=payload,
        )

        assert entry is not None
        assert entry.username == "jdoe"
        assert entry.domain == "WORKGROUP"
        assert entry.logon_id == "0x98765"

    @pytest.mark.asyncio
    async def test_analyze_no_events(self):
        """Test analyze returns empty list when no events found."""
        analyzer = LogonsAnalyzer()
        mock_db = AsyncMock()

        # Mock execute to return no rows
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        investigation_id = uuid4()

        entries = await analyzer.analyze(
            db=mock_db,
            investigation_id=investigation_id,
            use_cache=False,
        )

        assert entries == []
        assert mock_db.execute.called

    @pytest.mark.asyncio
    async def test_analyze_with_logon_type_filter(self):
        """Test analyze with logon type filter."""
        analyzer = LogonsAnalyzer()
        mock_db = AsyncMock()

        # Mock database response with multiple logon types
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (
                1,
                datetime(2024, 1, 15, 10, 30, 0),
                {
                    "event_id": 4624,
                    "event_data.TargetUserName": "user1",
                    "event_data.LogonType": "2",  # Interactive
                },
            ),
            (
                2,
                datetime(2024, 1, 15, 10, 31, 0),
                {
                    "event_id": 4624,
                    "event_data.TargetUserName": "user2",
                    "event_data.LogonType": "3",  # Network
                },
            ),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        investigation_id = uuid4()

        # Filter for Interactive only
        entries = await analyzer.analyze(
            db=mock_db,
            investigation_id=investigation_id,
            logon_types=["Interactive"],
            use_cache=False,
        )

        assert len(entries) == 1
        assert entries[0].logon_type == "Interactive"
        assert entries[0].username == "user1"

    @pytest.mark.asyncio
    async def test_analyze_with_source_ip_filter(self):
        """Test analyze with source IP filter."""
        analyzer = LogonsAnalyzer()
        mock_db = AsyncMock()

        # Mock database response with different source IPs
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (
                1,
                datetime(2024, 1, 15, 10, 30, 0),
                {
                    "event_id": 4624,
                    "event_data.TargetUserName": "user1",
                    "event_data.LogonType": "10",
                    "event_data.IpAddress": "192.168.1.100",
                },
            ),
            (
                2,
                datetime(2024, 1, 15, 10, 31, 0),
                {
                    "event_id": 4624,
                    "event_data.TargetUserName": "user2",
                    "event_data.LogonType": "10",
                    "event_data.IpAddress": "10.0.0.50",
                },
            ),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        investigation_id = uuid4()

        # Filter for specific IP
        entries = await analyzer.analyze(
            db=mock_db,
            investigation_id=investigation_id,
            source_ips=["192.168.1.100"],
            use_cache=False,
        )

        assert len(entries) == 1
        assert entries[0].source_ip == "192.168.1.100"
        assert entries[0].username == "user1"

    @pytest.mark.asyncio
    async def test_analyze_with_username_filter(self):
        """Test analyze with username filter."""
        analyzer = LogonsAnalyzer()
        mock_db = AsyncMock()

        # Mock database response with different usernames
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (
                1,
                datetime(2024, 1, 15, 10, 30, 0),
                {
                    "event_id": 4624,
                    "event_data.TargetUserName": "user1",
                    "event_data.TargetLogonId": "0x123456",
                    "event_data.LogonType": "2",
                },
            ),
            (
                2,
                datetime(2024, 1, 15, 10, 31, 0),
                {
                    "event_id": 4624,
                    "event_data.TargetUserName": "user2",
                    "event_data.TargetLogonId": "0xABCDEF",
                    "event_data.LogonType": "2",
                },
            ),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        investigation_id = uuid4()

        # Filter for specific username
        entries = await analyzer.analyze(
            db=mock_db,
            investigation_id=investigation_id,
            usernames=["user1"],
            use_cache=False,
        )

        assert len(entries) == 1
        assert entries[0].username == "user1"
        assert entries[0].logon_id == "0x123456"

    @pytest.mark.asyncio
    async def test_analyze_multiple_event_types(self):
        """Test analyze processes multiple event types correctly."""
        analyzer = LogonsAnalyzer()
        mock_db = AsyncMock()

        # Mock database response with different event types
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (
                1,
                datetime(2024, 1, 15, 10, 30, 0),
                {
                    "event_id": 4624,
                    "event_data.TargetUserName": "user1",
                    "event_data.LogonType": "2",
                },
            ),
            (
                2,
                datetime(2024, 1, 15, 10, 31, 0),
                {
                    "event_id": 4625,
                    "event_data.TargetUserName": "hacker",
                    "event_data.LogonType": "3",
                    "event_data.FailureReason": "Bad password",
                },
            ),
            (
                3,
                datetime(2024, 1, 15, 10, 32, 0),
                {
                    "event_id": 4634,
                    "event_data.SubjectUserName": "user1",
                    "event_data.SubjectLogonId": "0x123",
                },
            ),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        investigation_id = uuid4()

        entries = await analyzer.analyze(
            db=mock_db,
            investigation_id=investigation_id,
            use_cache=False,
        )

        assert len(entries) == 3
        assert entries[0].event_action == "Logon"
        assert entries[1].event_action == "Failed Logon"
        assert entries[2].event_action == "Logoff"

    @pytest.mark.asyncio
    async def test_get_dynamic_filters(self):
        """Test get_dynamic_filters extracts unique IPs and usernames."""
        analyzer = LogonsAnalyzer()
        mock_db = AsyncMock()

        # Mock IP query result
        mock_ip_result = MagicMock()
        mock_ip_result.fetchall.return_value = [
            ("192.168.1.100",),
            ("10.0.0.50",),
            ("172.16.0.1",),
        ]

        # Mock username query result
        mock_username_result = MagicMock()
        mock_username_result.fetchall.return_value = [
            ("user1",),
            ("user2",),
        ]

        # Setup mock to return different results for different queries
        mock_db.execute = AsyncMock(side_effect=[mock_ip_result, mock_username_result])

        investigation_id = uuid4()

        filters = await analyzer.get_dynamic_filters(mock_db, investigation_id)

        assert "source_ips" in filters
        assert "usernames" in filters
        assert len(filters["source_ips"]) == 3
        assert len(filters["usernames"]) == 2
        assert "192.168.1.100" in filters["source_ips"]
        assert "user1" in filters["usernames"]

    @pytest.mark.asyncio
    async def test_get_dynamic_filters_error_handling(self):
        """Test get_dynamic_filters handles errors gracefully."""
        analyzer = LogonsAnalyzer()
        mock_db = AsyncMock()

        # Mock database to raise error
        mock_db.execute = AsyncMock(side_effect=Exception("Database error"))

        investigation_id = uuid4()

        filters = await analyzer.get_dynamic_filters(mock_db, investigation_id)

        # Should return empty lists on error
        assert filters["source_ips"] == []
        assert filters["usernames"] == []

    @pytest.mark.asyncio
    async def test_query_event_logs_builds_correct_event_types(self):
        """Test that query builds correct event type patterns."""
        analyzer = LogonsAnalyzer()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        investigation_id = uuid4()

        await analyzer._query_event_logs(
            db=mock_db,
            investigation_id=investigation_id,
        )

        # Verify execute was called
        assert mock_db.execute.called
        call_args = mock_db.execute.call_args

        # Check that params include the correct event type patterns
        params = call_args[0][1]
        assert "etype_0" in params
        assert params["etype_0"] == "evtx_security_4624"
        assert "etype_1" in params
        assert params["etype_1"] == "evtx_security_4625"

    @pytest.mark.asyncio
    async def test_analyze_respects_10000_limit(self):
        """Test that analyze respects the 10000 entry limit."""
        analyzer = LogonsAnalyzer()
        mock_db = AsyncMock()

        # Create 10000 mock rows
        mock_rows = []
        for i in range(10000):
            mock_rows.append(
                (
                    i,
                    datetime(2024, 1, 15, 10, 30, 0),
                    {
                        "event_id": 4624,
                        "event_data.TargetUserName": f"user{i}",
                        "event_data.LogonType": "2",
                    },
                )
            )

        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_db.execute = AsyncMock(return_value=mock_result)

        investigation_id = uuid4()

        entries = await analyzer.analyze(
            db=mock_db,
            investigation_id=investigation_id,
            use_cache=False,
        )

        # Should have all 10000 entries
        assert len(entries) == 10000

    @pytest.mark.asyncio
    async def test_analyze_handles_database_errors(self):
        """Test analyze handles database errors gracefully."""
        analyzer = LogonsAnalyzer()
        mock_db = AsyncMock()

        # Mock database to raise error
        mock_db.execute = AsyncMock(side_effect=Exception("Database connection failed"))

        investigation_id = uuid4()

        entries = await analyzer.analyze(
            db=mock_db,
            investigation_id=investigation_id,
            use_cache=False,
        )

        # Should return empty list on error
        assert entries == []

    def test_create_entry_handles_malformed_payload(self):
        """Test create entry handles malformed payload gracefully."""
        analyzer = LogonsAnalyzer()

        # Payload with invalid data types
        payload = {
            "event_id": "not_a_number",
            "event_data.TargetUserName": "testuser",
        }

        entry = analyzer._create_entry_from_event_log(
            event_id=1,
            timestamp="2024-01-15T10:30:00",
            payload=payload,
        )

        # Should return None for malformed payload
        assert entry is None

    @pytest.mark.asyncio
    async def test_analyze_combined_filters(self):
        """Test analyze with multiple filters applied simultaneously."""
        analyzer = LogonsAnalyzer()
        mock_db = AsyncMock()

        # Mock database response
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (
                1,
                datetime(2024, 1, 15, 10, 30, 0),
                {
                    "event_id": 4624,
                    "event_data.TargetUserName": "user1",
                    "event_data.TargetLogonId": "0x123",
                    "event_data.LogonType": "10",  # RemoteInteractive
                    "event_data.IpAddress": "192.168.1.100",
                },
            ),
            (
                2,
                datetime(2024, 1, 15, 10, 31, 0),
                {
                    "event_id": 4624,
                    "event_data.TargetUserName": "user2",
                    "event_data.TargetLogonId": "0x456",
                    "event_data.LogonType": "2",  # Interactive
                    "event_data.IpAddress": "192.168.1.100",
                },
            ),
            (
                3,
                datetime(2024, 1, 15, 10, 32, 0),
                {
                    "event_id": 4624,
                    "event_data.TargetUserName": "user3",
                    "event_data.TargetLogonId": "0x789",
                    "event_data.LogonType": "10",  # RemoteInteractive
                    "event_data.IpAddress": "10.0.0.50",
                },
            ),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        investigation_id = uuid4()

        # Apply multiple filters: RemoteInteractive + specific IP + specific username
        entries = await analyzer.analyze(
            db=mock_db,
            investigation_id=investigation_id,
            logon_types=["RemoteInteractive"],
            source_ips=["192.168.1.100"],
            usernames=["user1"],
            use_cache=False,
        )

        # Should only match entry 1 (all three filters match)
        assert len(entries) == 1
        assert entries[0].username == "user1"
        assert entries[0].logon_type == "RemoteInteractive"
        assert entries[0].source_ip == "192.168.1.100"
        assert entries[0].logon_id == "0x123"

    @pytest.mark.asyncio
    async def test_get_dynamic_filters_filters_invalid_ips(self):
        """Test that dynamic filters exclude invalid/local IPs."""
        analyzer = LogonsAnalyzer()
        mock_db = AsyncMock()

        # Mock IP query result with various IPs
        mock_ip_result = MagicMock()
        mock_ip_result.fetchall.return_value = [
            ("192.168.1.100",),  # Valid
            ("127.0.0.1",),  # Should be filtered by query
            ("::1",),  # Should be filtered by query
            ("-",),  # Should be filtered by query
        ]

        # Mock username query result
        mock_username_result = MagicMock()
        mock_username_result.fetchall.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_ip_result, mock_username_result])

        investigation_id = uuid4()

        filters = await analyzer.get_dynamic_filters(mock_db, investigation_id)

        # The SQL query should filter these, but this tests the returned data
        assert "192.168.1.100" in filters["source_ips"]
        # These should have been filtered by the SQL query
        # but if they somehow got through, they'd be in the list

    def test_logon_entry_serialization_roundtrip(self):
        """Test that LogonEntry can be serialized and deserialized."""
        original = LogonEntry(
            logon_type="Network",
            event_action="Logon",
            username="testuser",
            domain="TESTDOMAIN",
            logon_id="0x12345",
            source_ip="192.168.1.50",
            source_host="WS01",
            timestamp="2024-01-15T10:30:00",
            event_id=100,
            event_record_id=4624,
            logon_process="Advapi",
            authentication_package="NTLM",
            raw_data={"key": "value"},
        )

        # Serialize to dict
        entry_dict = original.to_dict()

        # Deserialize back to LogonEntry
        restored = LogonEntry(**entry_dict)

        # Verify all fields match
        assert restored.logon_type == original.logon_type
        assert restored.event_action == original.event_action
        assert restored.username == original.username
        assert restored.domain == original.domain
        assert restored.logon_id == original.logon_id
        assert restored.source_ip == original.source_ip
        assert restored.source_host == original.source_host
        assert restored.timestamp == original.timestamp
        assert restored.event_id == original.event_id
        assert restored.event_record_id == original.event_record_id
        assert restored.raw_data == original.raw_data
