"""
Comprehensive integration tests for list_events endpoint.
Tests all code paths in the complex list_events function.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
import json
from datetime import datetime, timedelta


@pytest.mark.integration
class TestListEventsBasic:
    """Test basic list_events functionality."""

    async def test_list_events_returns_structure(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test that list_events returns the correct response structure."""
        # Insert a test event
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test_event', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"test": "data"})
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "count" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["events"], list)

    async def test_list_events_default_pagination(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test default pagination parameters."""
        # Insert 150 events
        for i in range(150):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, NOW(), 'test', :payload)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "payload": json.dumps({"index": i})
                }
            )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        # Default limit is 100
        assert len(data["events"]) == 100
        assert data["limit"] == 100
        assert data["total"] == 150

    async def test_list_events_custom_limit(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test custom limit parameter."""
        for i in range(50):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, NOW(), 'test', '{}'::jsonb)
                """),
                {"inv_id": str(test_investigation.investigation_id)}
            )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 25}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 25
        assert data["limit"] == 25

    async def test_list_events_with_offset(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test offset parameter for pagination."""
        for i in range(30):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, NOW(), 'test', :payload)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "payload": json.dumps({"index": i})
                }
            )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 10, "offset": 20}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 10
        assert data["offset"] == 20
        assert data["total"] == 30


@pytest.mark.integration
class TestListEventsFiltering:
    """Test all filtering options in list_events."""

    async def test_filter_by_event_type(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test event_type filter."""
        # Insert different event types
        for event_type in ["type_a", "type_b", "type_c"]:
            for i in range(5):
                await db_session.execute(
                    text("""
                        INSERT INTO events (investigation_id, event_ts, event_type, payload)
                        VALUES (:inv_id, NOW(), :event_type, '{}'::jsonb)
                    """),
                    {
                        "inv_id": str(test_investigation.investigation_id),
                        "event_type": event_type
                    }
                )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"event_type": "type_a"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        for event in data["events"]:
            assert event["event_type"] == "type_a"

    async def test_filter_by_start_date(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test start_date filter."""
        base_time = datetime.utcnow()
        
        # Insert events with different timestamps
        for i in range(10):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, :event_ts, 'test', '{}'::jsonb)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_ts": base_time - timedelta(days=i)
                }
            )
        await db_session.commit()

        # Filter for events from last 5 days
        start_date = (base_time - timedelta(days=5)).isoformat()
        
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"start_date": start_date}
        )

        assert response.status_code == 200
        data = response.json()
        # Should get 6 events (days 0-5 inclusive)
        assert data["total"] == 6

    async def test_filter_by_end_date(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test end_date filter."""
        base_time = datetime.utcnow()
        
        for i in range(10):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, :event_ts, 'test', '{}'::jsonb)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_ts": base_time + timedelta(days=i)
                }
            )
        await db_session.commit()

        # Filter for events up to 5 days from now
        end_date = (base_time + timedelta(days=5)).isoformat()
        
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"end_date": end_date}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 6

    async def test_filter_by_date_range(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test both start_date and end_date filters together."""
        base_time = datetime.utcnow()
        
        for i in range(20):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, :event_ts, 'test', '{}'::jsonb)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_ts": base_time - timedelta(days=i)
                }
            )
        await db_session.commit()

        start_date = (base_time - timedelta(days=10)).isoformat()
        end_date = (base_time - timedelta(days=5)).isoformat()
        
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"start_date": start_date, "end_date": end_date}
        )

        assert response.status_code == 200
        data = response.json()
        # Should get events from days 5-10 (6 events)
        assert data["total"] == 6

    async def test_filter_by_search_text(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test search parameter for full-text search."""
        # Insert events with searchable content
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'security_4624', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"TargetUserName": "Administrator"})
            }
        )
        
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'security_4625', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"TargetUserName": "Guest"})
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"search": "Administrator"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_filter_by_search_in_event_type(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test that search also matches event_type field."""
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'evtx_security_4624', '{}'::jsonb)
            """),
            {"inv_id": str(test_investigation.investigation_id)}
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"search": "security"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1


@pytest.mark.integration
class TestListEventsJSONBQueries:
    """Test JSONB query parameters in list_events."""

    async def test_jsonb_equality_operator(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test JSONB query with = operator."""
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"EventID": "4624", "User": "admin"})
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "EventID",
                "jsonb_operator_0": "=",
                "jsonb_value_0": "4624"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_jsonb_not_equal_operator(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test JSONB query with != operator."""
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"Status": "success"})
            }
        )
        
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"Status": "failure"})
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "Status",
                "jsonb_operator_0": "!=",
                "jsonb_value_0": "success"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_jsonb_like_operator_with_wildcards(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test JSONB LIKE operator with * wildcards."""
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"ProcessName": "C:\\\\Windows\\\\System32\\\\cmd.exe"})
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "ProcessName",
                "jsonb_operator_0": "LIKE",
                "jsonb_value_0": "*cmd*"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_jsonb_ilike_operator(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test JSONB ILIKE operator (case-insensitive)."""
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"UserName": "Administrator"})
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "UserName",
                "jsonb_operator_0": "ILIKE",
                "jsonb_value_0": "*admin*"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_jsonb_contains_operator(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test JSONB CONTAINS operator."""
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"CommandLine": "powershell.exe -encodedCommand ABC123"})
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "CommandLine",
                "jsonb_operator_0": "CONTAINS",
                "jsonb_value_0": "encodedCommand"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_jsonb_starts_with_operator(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test JSONB STARTS_WITH operator."""
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"Path": "C:\\\\Windows\\\\System32\\\\notepad.exe"})
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "Path",
                "jsonb_operator_0": "STARTS_WITH",
                "jsonb_value_0": "C:\\\\Windows"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_jsonb_ends_with_operator(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test JSONB ENDS_WITH operator."""
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"Executable": "malware.exe"})
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "Executable",
                "jsonb_operator_0": "ENDS_WITH",
                "jsonb_value_0": ".exe"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_jsonb_field_exists_check(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test JSONB query that checks field existence (empty value)."""
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"SpecialField": "exists"})
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "SpecialField",
                "jsonb_operator_0": "=",
                "jsonb_value_0": ""  # Empty value checks existence
            }
        )

        assert response.status_code == 200

    async def test_jsonb_multiple_queries(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test multiple JSONB queries combined with AND logic."""
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({
                    "EventID": "4624",
                    "LogonType": "10",
                    "UserName": "admin"
                })
            }
        )
        
        # Insert event that only matches first condition
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({
                    "EventID": "4624",
                    "LogonType": "2"
                })
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "EventID",
                "jsonb_operator_0": "=",
                "jsonb_value_0": "4624",
                "jsonb_path_1": "LogonType",
                "jsonb_operator_1": "=",
                "jsonb_value_1": "10"
            }
        )

        assert response.status_code == 200
        data = response.json()
        # Should only match first event
        assert data["total"] == 1


@pytest.mark.integration
class TestListEventsSorting:
    """Test sorting options in list_events."""

    async def test_sort_descending_default(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test default descending sort order."""
        base_time = datetime.utcnow()
        
        for i in range(5):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, :event_ts, 'test', :payload)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_ts": base_time - timedelta(minutes=i),
                    "payload": json.dumps({"index": i})
                }
            )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        events = data["events"]
        
        # First event should be most recent (index 0)
        assert events[0]["payload"]["index"] == 0
        assert events[-1]["payload"]["index"] == 4

    async def test_sort_ascending(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test ascending sort order."""
        base_time = datetime.utcnow()
        
        for i in range(5):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, :event_ts, 'test', :payload)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_ts": base_time - timedelta(minutes=i),
                    "payload": json.dumps({"index": i})
                }
            )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"order": "asc"}
        )

        assert response.status_code == 200
        data = response.json()
        events = data["events"]
        
        # First event should be oldest (index 4)
        assert events[0]["payload"]["index"] == 4
        assert events[-1]["payload"]["index"] == 0


@pytest.mark.integration
class TestListEventsCombined:
    """Test combining multiple filters together."""

    async def test_all_filters_combined(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test combining event_type, date range, search, JSONB, and pagination."""
        base_time = datetime.utcnow()
        
        # Insert matching event
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, :event_ts, 'security_4624', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "event_ts": base_time - timedelta(hours=1),
                "payload": json.dumps({
                    "EventID": "4624",
                    "LogonType": "10",
                    "UserName": "Administrator"
                })
            }
        )
        
        # Insert non-matching events
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, :event_ts, 'security_4625', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "event_ts": base_time - timedelta(hours=1),
                "payload": json.dumps({"EventID": "4625"})
            }
        )
        await db_session.commit()

        start_date = (base_time - timedelta(days=1)).isoformat()
        end_date = base_time.isoformat()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "event_type": "security_4624",
                "start_date": start_date,
                "end_date": end_date,
                "search": "Administrator",
                "jsonb_path_0": "LogonType",
                "jsonb_operator_0": "=",
                "jsonb_value_0": "10",
                "order": "desc",
                "limit": 10,
                "offset": 0
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["count"] == 1


@pytest.mark.integration
class TestListEventsErrorHandling:
    """Test error handling in list_events."""

    async def test_invalid_start_date_format(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """Test that invalid start_date format returns 400."""
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"start_date": "not-a-date"}
        )

        assert response.status_code == 400
        assert "start_date" in response.json()["detail"].lower()

    async def test_invalid_end_date_format(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """Test that invalid end_date format returns 400."""
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"end_date": "invalid-date-string"}
        )

        assert response.status_code == 400
        assert "end_date" in response.json()["detail"].lower()

    async def test_invalid_jsonb_operator(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """Test that invalid JSONB operator returns 400."""
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "field",
                "jsonb_operator_0": "INVALID_OP",
                "jsonb_value_0": "value"
            }
        )

        assert response.status_code == 400
        assert "operator" in response.json()["detail"].lower()

    async def test_count_query_with_all_filters(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test that count query correctly applies all the same filters as main query."""
        base_time = datetime.utcnow()
        
        # Insert 10 matching events
        for i in range(10):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, :event_ts, 'match_type', :payload)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_ts": base_time - timedelta(hours=i),
                    "payload": json.dumps({"Status": "active"})
                }
            )
        
        # Insert 5 non-matching events (different type)
        for i in range(5):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, :event_ts, 'other_type', :payload)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_ts": base_time - timedelta(hours=i),
                    "payload": json.dumps({"Status": "active"})
                }
            )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "event_type": "match_type",
                "limit": 5  # Only return 5, but total should be 10
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 5  # Returned in this page
        assert data["total"] == 10  # Total matching
