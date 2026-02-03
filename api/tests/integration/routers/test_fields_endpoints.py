import pytest
from httpx import AsyncClient
from sqlalchemy import text
import json
from datetime import datetime, timedelta


@pytest.mark.integration
class TestEventsFieldsEndpoint:
    """Test GET /api/v1/events/{investigation_id}/fields endpoint."""

    async def test_get_fields_no_events(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that requesting fields when no events exist returns empty list.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["fields"] == []
        assert data["count"] == 0
        assert data["event_types_sampled"] == 0

    async def test_get_fields_single_event_type(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test field discovery with a single event type.
        Verifies that window function samples up to 10 events.
        """
        # Insert 15 events with different fields
        for i in range(15):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, NOW(), :event_type, :payload)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_type": "test_event",
                    "payload": json.dumps({
                        f"field_{i}": f"value_{i}",
                        "common_field": "common_value"
                    })
                }
            )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should discover at least 10 unique fields (field_0 through field_9)
        assert data["count"] >= 10
        assert "common_field" in data["fields"]
        # Should sample 10 events (window function limit)
        assert data["event_types_sampled"] == 10

    async def test_get_fields_multiple_event_types(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test field discovery with multiple event types.
        Verifies that 10 events per type are sampled.
        """
        # Insert 15 events for each of 3 event types
        for type_idx in range(3):
            for i in range(15):
                await db_session.execute(
                    text("""
                        INSERT INTO events (investigation_id, event_ts, event_type, payload)
                        VALUES (:inv_id, NOW(), :event_type, :payload)
                    """),
                    {
                        "inv_id": str(test_investigation.investigation_id),
                        "event_type": f"type_{type_idx}",
                        "payload": json.dumps({
                            f"type{type_idx}_field_{i}": f"value_{i}",
                            "shared_field": "shared"
                        })
                    }
                )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should sample 30 events (10 per type * 3 types)
        assert data["event_types_sampled"] == 30
        # Should discover fields from all types
        assert "shared_field" in data["fields"]
        assert data["count"] >= 10

    async def test_get_fields_with_event_type_filter(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test field discovery when filtering by specific event type.
        """
        # Insert events for multiple types
        for type_idx in range(2):
            for i in range(5):
                await db_session.execute(
                    text("""
                        INSERT INTO events (investigation_id, event_ts, event_type, payload)
                        VALUES (:inv_id, NOW(), :event_type, :payload)
                    """),
                    {
                        "inv_id": str(test_investigation.investigation_id),
                        "event_type": f"type_{type_idx}",
                        "payload": json.dumps({f"type{type_idx}_field": f"value_{i}"})
                    }
                )
        await db_session.commit()

        # Request fields for specific type
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/fields",
            headers=auth_headers,
            params={"event_type": "type_0"}
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should only sample from type_0
        assert "type0_field" in data["fields"]
        assert "type1_field" not in data["fields"]
        assert data["event_types_sampled"] == 5  # Only 5 events of type_0

    async def test_get_fields_handles_jsonb_and_string_payloads(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test that field discovery works with both JSONB and string payloads.
        """
        # Insert event with JSONB payload
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'jsonb_type', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"jsonb_field": "value"})
            }
        )
        
        # Insert event with string payload (shouldn't happen but test resilience)
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'string_type', '{"string_field": "value"}'::jsonb)
            """),
            {
                "inv_id": str(test_investigation.investigation_id)
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should discover fields from both payload types
        assert "jsonb_field" in data["fields"] or "string_field" in data["fields"]

    async def test_get_fields_performance_with_large_dataset(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test that field discovery completes quickly even with many events.
        This verifies the window function + index optimization works.
        """
        # Insert 100 events across 5 types
        for type_idx in range(5):
            for i in range(20):
                await db_session.execute(
                    text("""
                        INSERT INTO events (investigation_id, event_ts, event_type, payload)
                        VALUES (:inv_id, NOW(), :event_type, :payload)
                    """),
                    {
                        "inv_id": str(test_investigation.investigation_id),
                        "event_type": f"perf_type_{type_idx}",
                        "payload": json.dumps({f"field_{i}": f"value_{i}"})
                    }
                )
        await db_session.commit()

        # Request should complete within 2 seconds
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/fields",
            headers=auth_headers,
            timeout=2.0
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should sample 50 events (10 per type * 5 types)
        assert data["event_types_sampled"] == 50


@pytest.mark.integration
class TestTimelineFieldsEndpoint:
    """Test GET /api/v1/timeline/{investigation_id}/fields endpoint."""

    async def test_get_timeline_fields_no_entries(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that requesting timeline fields when no entries exist returns empty list.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["fields"] == []
        assert data["count"] == 0
        assert data["entries_sampled"] == 0

    async def test_get_timeline_fields_from_entry_data(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test field discovery from timeline entry data field.
        """
        # Create timeline entries with rich data
        for i in range(5):
            await db_session.execute(
                text("""
                    INSERT INTO timeline_entries 
                    (investigation_id, timestamp, entry_type, title, data)
                    VALUES (:inv_id, NOW(), 'finding', :title, :data)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "title": f"Entry {i}",
                    "data": json.dumps({
                        f"data_field_{i}": f"value_{i}",
                        "common_data_field": "common"
                    })
                }
            )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should discover fields from entry data
        assert "common_data_field" in data["fields"]
        assert data["count"] >= 5

    async def test_get_timeline_fields_from_linked_events(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test that timeline fields endpoint discovers fields from linked event payloads
        when entry data is sparse (< 10 fields).
        """
        # Create events with rich payloads
        event_ids = []
        for i in range(5):
            result = await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, NOW(), :event_type, :payload)
                    RETURNING event_id
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_type": "rich_event",
                    "payload": json.dumps({
                        "EventID": f"{4624 + i}",
                        "TargetUserName": f"user_{i}",
                        "SourceIP": f"192.168.1.{i}",
                        "LogonType": "10",
                        f"unique_field_{i}": f"value_{i}"
                    })
                }
            )
            event_ids.append(result.scalar())
        
        # Create timeline entries with minimal data linking to rich events
        for event_id in event_ids:
            await db_session.execute(
                text("""
                    INSERT INTO timeline_entries 
                    (investigation_id, event_id, timestamp, entry_type, title, data)
                    VALUES (:inv_id, :event_id, NOW(), 'event', 'Test', '{}'::jsonb)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_id": event_id
                }
            )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should discover fields from linked event payloads
        assert "EventID" in data["fields"]
        assert "TargetUserName" in data["fields"]
        assert "SourceIP" in data["fields"]
        assert "LogonType" in data["fields"]
        assert data["count"] >= 4

    async def test_get_timeline_fields_with_event_type_filter(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test timeline field discovery filtered by event type.
        """
        # Create events of different types
        for type_idx in range(2):
            result = await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, NOW(), :event_type, :payload)
                    RETURNING event_id
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_type": f"type_{type_idx}",
                    "payload": json.dumps({f"type{type_idx}_field": f"value"})
                }
            )
            event_id = result.scalar()
            
            # Create timeline entry
            await db_session.execute(
                text("""
                    INSERT INTO timeline_entries 
                    (investigation_id, event_id, timestamp, entry_type, title, data)
                    VALUES (:inv_id, :event_id, NOW(), 'event', 'Entry', '{}'::jsonb)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_id": event_id
                }
            )
        await db_session.commit()

        # Request fields for specific event type
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields",
            headers=auth_headers,
            params={"event_type": "type_0"}
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should only find fields from type_0
        assert "type0_field" in data["fields"]
        assert "type1_field" not in data["fields"]

    async def test_get_timeline_fields_samples_multiple_per_type(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test that timeline /fields samples 10 entries per event type.
        """
        # Create 15 events of same type with different fields
        event_ids = []
        for i in range(15):
            result = await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, NOW(), :event_type, :payload)
                    RETURNING event_id
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_type": "multi_sample_type",
                    "payload": json.dumps({f"field_{i}": f"value_{i}"})
                }
            )
            event_ids.append(result.scalar())
        
        # Create timeline entries
        for event_id in event_ids:
            await db_session.execute(
                text("""
                    INSERT INTO timeline_entries 
                    (investigation_id, event_id, timestamp, entry_type, title, data)
                    VALUES (:inv_id, :event_id, NOW(), 'event', 'Entry', '{}'::jsonb)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_id": event_id
                }
            )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should sample 10 entries (window function limit)
        assert data["entries_sampled"] == 10
        # Should discover at least 10 fields
        assert data["count"] >= 10

    async def test_get_timeline_fields_with_nested_payload(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test that timeline fields endpoint extracts nested payload fields.
        """
        # Create event with nested payload
        result = await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'nested_event', :payload)
                RETURNING event_id
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({
                    "EventID": "4624",
                    "EventData": {
                        "TargetUserName": "admin",
                        "SourceIP": "192.168.1.1"
                    }
                })
            }
        )
        event_id = result.scalar()
        
        # Create timeline entry with data containing nested payload
        await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, event_id, timestamp, entry_type, title, data)
                VALUES (:inv_id, :event_id, NOW(), 'event', 'Entry', :data)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "event_id": event_id,
                "data": json.dumps({
                    "payload": {
                        "NestedField1": "value1",
                        "NestedField2": "value2"
                    }
                })
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should extract both top-level and nested payload fields
        assert "payload" in data["fields"] or "NestedField1" in data["fields"]

    async def test_get_timeline_fields_respects_visibility(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test that hidden timeline entries are excluded from field sampling.
        """
        # Create event
        result = await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test_event', :payload)
                RETURNING event_id
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"visible_field": "value"})
            }
        )
        event_id_visible = result.scalar()
        
        result = await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test_event', :payload)
                RETURNING event_id
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"hidden_field": "value"})
            }
        )
        event_id_hidden = result.scalar()
        
        # Create visible entry
        await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, event_id, timestamp, entry_type, title, data, is_visible)
                VALUES (:inv_id, :event_id, NOW(), 'event', 'Visible', '{}'::jsonb, true)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "event_id": event_id_visible
            }
        )
        
        # Create hidden entry
        await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, event_id, timestamp, entry_type, title, data, is_visible)
                VALUES (:inv_id, :event_id, NOW(), 'event', 'Hidden', '{}'::jsonb, false)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "event_id": event_id_hidden
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should only sample from visible entries
        assert "visible_field" in data["fields"]
        assert "hidden_field" not in data["fields"]

    async def test_get_timeline_fields_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that requesting timeline fields without auth returns 401.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestFieldsEndpointEdgeCases:
    """Test edge cases for both fields endpoints."""

    async def test_events_fields_with_null_payload(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test that events with null payloads don't crash field discovery.
        """
        # This shouldn't be possible with NOT NULL constraint, but test resilience
        # Insert normal event
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'normal', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"field": "value"})
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "field" in data["fields"]

    async def test_timeline_fields_with_empty_data(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test timeline fields when entries have empty data but link to events.
        This is the common case - timeline entries reference events without duplicating data.
        """
        # Create event with payload
        result = await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'security_event', :payload)
                RETURNING event_id
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({
                    "EventID": "4624",
                    "TargetUserName": "admin",
                    "LogonType": "10"
                })
            }
        )
        event_id = result.scalar()
        
        # Create timeline entry with empty data
        await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, event_id, timestamp, entry_type, title, data)
                VALUES (:inv_id, :event_id, NOW(), 'event', 'Logon Event', '{}'::jsonb)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "event_id": event_id
            }
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should fall back to sampling from linked event payload
        assert "EventID" in data["fields"]
        assert "TargetUserName" in data["fields"]
        assert "LogonType" in data["fields"]

    async def test_fields_endpoints_return_sorted_fields(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test that both endpoints return fields in alphabetical order.
        """
        # Insert event with unsorted field names
        await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test', :payload)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({
                    "zebra": "z",
                    "alpha": "a",
                    "mike": "m",
                    "bravo": "b"
                })
            }
        )
        await db_session.commit()

        # Test events endpoint
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        fields = response.json()["fields"]
        
        # Should be sorted alphabetically
        assert fields == sorted(fields)
        assert fields[0] == "alpha"
        assert fields[-1] == "zebra"


@pytest.mark.integration
class TestEventsEndpointCoverage:
    """Additional tests to improve coverage of events.py router."""

    async def test_list_events_with_pagination(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test events pagination with limit and offset."""
        # Insert 25 events
        for i in range(25):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, NOW(), 'page_test', :payload)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "payload": json.dumps({"index": i})
                }
            )
        await db_session.commit()

        # First page
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 10, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 10
        assert data["total"] == 25
        assert data["limit"] == 10
        assert data["offset"] == 0

        # Second page
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 10, "offset": 10}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 10
        assert data["offset"] == 10

    async def test_list_events_with_event_type_filter(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test filtering events by event_type."""
        # Insert events of different types
        for type_name in ["type_a", "type_b"]:
            for i in range(5):
                await db_session.execute(
                    text("""
                        INSERT INTO events (investigation_id, event_ts, event_type, payload)
                        VALUES (:inv_id, NOW(), :event_type, :payload)
                    """),
                    {
                        "inv_id": str(test_investigation.investigation_id),
                        "event_type": type_name,
                        "payload": json.dumps({"data": i})
                    }
                )
        await db_session.commit()

        # Filter by type_a
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

    async def test_list_events_count_query_with_filters(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test that count query correctly applies all filters."""
        from datetime import datetime, timedelta
        
        # Insert events with different timestamps
        base_time = datetime.utcnow()
        for i in range(10):
            await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, :event_ts, 'count_test', :payload)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_ts": base_time - timedelta(days=i),
                    "payload": json.dumps({"index": i})
                }
            )
        await db_session.commit()

        # Filter by date range
        start_date = (base_time - timedelta(days=5)).isoformat()
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"start_date": start_date}
        )

        assert response.status_code == 200
        data = response.json()
        # Should only get events from last 5 days
        assert data["total"] == 6  # Days 0-5 inclusive

    async def test_get_event_types_with_multiple_types(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test event-types endpoint returns all types with counts."""
        # Insert events of different types with different counts
        type_counts = {"type_x": 10, "type_y": 5, "type_z": 3}
        
        for event_type, count in type_counts.items():
            for i in range(count):
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
            f"/api/v1/events/{test_investigation.investigation_id}/event-types",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_types"] == 3
        
        # Verify counts are correct
        type_dict = {et["event_type"]: et["count"] for et in data["event_types"]}
        assert type_dict["type_x"] == 10
        assert type_dict["type_y"] == 5
        assert type_dict["type_z"] == 3

    async def test_paste_events_creates_file(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """Test that paste endpoint saves the raw file."""
        json_data = json.dumps([{"event_type": "pasted", "test": "data"}])

        response = await async_client.post(
            f"/api/v1/events/paste?investigation_id={test_investigation.investigation_id}",
            headers={**auth_headers, "Content-Type": "text/plain"},
            content=json_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert "file_saved" in data
        assert data["file_saved"].endswith(".json")


@pytest.mark.integration
class TestTimelineEndpointCoverage:
    """Additional tests to improve coverage of timeline.py router."""

    async def test_get_timeline_with_pagination(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test timeline pagination."""
        # Create 25 timeline entries
        for i in range(25):
            await db_session.execute(
                text("""
                    INSERT INTO timeline_entries 
                    (investigation_id, timestamp, entry_type, title, data)
                    VALUES (:inv_id, NOW(), 'event', :title, '{}'::jsonb)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "title": f"Entry {i}"
                }
            )
        await db_session.commit()

        # First page
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 10, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["entries"]) == 10
        assert data["total"] == 25

    async def test_get_timeline_count_with_filters(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test that timeline count query applies all filters correctly."""
        # Create entries of different types
        for entry_type in ["event", "finding"]:
            for i in range(5):
                await db_session.execute(
                    text("""
                        INSERT INTO timeline_entries 
                        (investigation_id, timestamp, entry_type, title, data)
                        VALUES (:inv_id, NOW(), :entry_type, :title, '{}'::jsonb)
                    """),
                    {
                        "inv_id": str(test_investigation.investigation_id),
                        "entry_type": entry_type,
                        "title": f"{entry_type} {i}"
                    }
                )
        await db_session.commit()

        # Filter by entry_type
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"entry_type": "event"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5

    async def test_create_timeline_entry_success(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """Test successful timeline entry creation."""
        from datetime import datetime
        
        entry_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "entry_type": "finding",
            "title": "Test Finding",
            "description": "This is a test finding",
            "data": {"severity": "high"},
            "tags": ["test", "automated"],
            "is_visible": True
        }

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries",
            headers=auth_headers,
            json=entry_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Finding"
        assert data["entry_type"] == "finding"
        assert "entry_id" in data

    async def test_create_timeline_entry_with_event_id(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test creating timeline entry linked to an event."""
        from datetime import datetime
        
        # Create an event first
        result = await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'test_event', :payload)
                RETURNING event_id
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "payload": json.dumps({"test": "data"})
            }
        )
        event_id = result.scalar()
        await db_session.commit()

        entry_data = {
            "event_id": event_id,
            "timestamp": datetime.utcnow().isoformat(),
            "entry_type": "event",
            "title": "Linked Event Entry",
            "data": {},
            "tags": [],
            "is_visible": True
        }

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries",
            headers=auth_headers,
            json=entry_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["event_id"] == event_id

    async def test_create_timeline_entry_duplicate_event_id(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test that creating duplicate timeline entry for same event returns 409."""
        from datetime import datetime
        
        # Create an event
        result = await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), 'dup_test', '{}'::jsonb)
                RETURNING event_id
            """),
            {"inv_id": str(test_investigation.investigation_id)}
        )
        event_id = result.scalar()
        
        # Create first timeline entry
        await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, event_id, timestamp, entry_type, title, data)
                VALUES (:inv_id, :event_id, NOW(), 'event', 'First', '{}'::jsonb)
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "event_id": event_id
            }
        )
        await db_session.commit()

        # Try to create duplicate
        entry_data = {
            "event_id": event_id,
            "timestamp": datetime.utcnow().isoformat(),
            "entry_type": "event",
            "title": "Duplicate",
            "data": {},
            "tags": [],
            "is_visible": True
        }

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries",
            headers=auth_headers,
            json=entry_data
        )

        assert response.status_code == 409
        assert "already on the timeline" in response.json()["detail"]

    async def test_update_timeline_entry_success(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test successful timeline entry update."""
        # Create entry
        result = await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, timestamp, entry_type, title, description, data)
                VALUES (:inv_id, NOW(), 'event', 'Original', 'Original desc', '{}'::jsonb)
                RETURNING entry_id
            """),
            {"inv_id": str(test_investigation.investigation_id)}
        )
        entry_id = result.scalar()
        await db_session.commit()

        # Update it
        update_data = {
            "title": "Updated Title",
            "description": "Updated description"
        }

        response = await async_client.patch(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/{entry_id}",
            headers=auth_headers,
            json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["description"] == "Updated description"

    async def test_delete_timeline_entry_success(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test successful timeline entry deletion."""
        # Create entry
        result = await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, timestamp, entry_type, title, data)
                VALUES (:inv_id, NOW(), 'event', 'To Delete', '{}'::jsonb)
                RETURNING entry_id
            """),
            {"inv_id": str(test_investigation.investigation_id)}
        )
        entry_id = result.scalar()
        await db_session.commit()

        # Delete it
        response = await async_client.delete(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/{entry_id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        assert "deleted" in response.json()["message"]

    async def test_get_timeline_entry_with_notes(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test getting a single timeline entry with its notes."""
        # Create entry
        result = await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, timestamp, entry_type, title, data)
                VALUES (:inv_id, NOW(), 'event', 'Entry with notes', '{}'::jsonb)
                RETURNING entry_id
            """),
            {"inv_id": str(test_investigation.investigation_id)}
        )
        entry_id = result.scalar()
        await db_session.commit()

        # Add notes
        for i in range(3):
            await db_session.execute(
                text("""
                    INSERT INTO timeline_notes (entry_id, user_id, note_text)
                    VALUES (:entry_id, 1, :note_text)
                """),
                {
                    "entry_id": entry_id,
                    "note_text": f"Note {i}"
                }
            )
        await db_session.commit()

        # Get entry
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/{entry_id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["notes"]) == 3

    async def test_create_note_success(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test creating a note on a timeline entry."""
        # Create entry
        result = await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, timestamp, entry_type, title, data)
                VALUES (:inv_id, NOW(), 'event', 'Entry', '{}'::jsonb)
                RETURNING entry_id
            """),
            {"inv_id": str(test_investigation.investigation_id)}
        )
        entry_id = result.scalar()
        await db_session.commit()

        # Create note
        note_data = {"note_text": "This is a test note"}

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/{entry_id}/notes",
            headers=auth_headers,
            json=note_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["note_text"] == "This is a test note"
        assert "note_id" in data

    async def test_get_notes_for_entry(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test getting all notes for a timeline entry."""
        # Create entry
        result = await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, timestamp, entry_type, title, data)
                VALUES (:inv_id, NOW(), 'event', 'Entry', '{}'::jsonb)
                RETURNING entry_id
            """),
            {"inv_id": str(test_investigation.investigation_id)}
        )
        entry_id = result.scalar()
        
        # Add notes
        for i in range(3):
            await db_session.execute(
                text("""
                    INSERT INTO timeline_notes (entry_id, user_id, note_text)
                    VALUES (:entry_id, 1, :note_text)
                """),
                {
                    "entry_id": entry_id,
                    "note_text": f"Note {i}"
                }
            )
        await db_session.commit()

        # Get notes
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/{entry_id}/notes",
            headers=auth_headers
        )

        assert response.status_code == 200
        notes = response.json()
        assert len(notes) == 3

    async def test_update_note_success(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test updating a timeline note."""
        # Create entry and note
        result = await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, timestamp, entry_type, title, data)
                VALUES (:inv_id, NOW(), 'event', 'Entry', '{}'::jsonb)
                RETURNING entry_id
            """),
            {"inv_id": str(test_investigation.investigation_id)}
        )
        entry_id = result.scalar()
        
        result = await db_session.execute(
            text("""
                INSERT INTO timeline_notes (entry_id, user_id, note_text)
                VALUES (:entry_id, 1, 'Original note')
                RETURNING note_id
            """),
            {"entry_id": entry_id}
        )
        note_id = result.scalar()
        await db_session.commit()

        # Update note
        update_data = {"note_text": "Updated note text"}

        response = await async_client.patch(
            f"/api/v1/timeline/{test_investigation.investigation_id}/notes/{note_id}",
            headers=auth_headers,
            json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["note_text"] == "Updated note text"

    async def test_delete_note_success(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test deleting a timeline note."""
        # Create entry and note
        result = await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, timestamp, entry_type, title, data)
                VALUES (:inv_id, NOW(), 'event', 'Entry', '{}'::jsonb)
                RETURNING entry_id
            """),
            {"inv_id": str(test_investigation.investigation_id)}
        )
        entry_id = result.scalar()
        
        result = await db_session.execute(
            text("""
                INSERT INTO timeline_notes (entry_id, user_id, note_text)
                VALUES (:entry_id, 1, 'Note to delete')
                RETURNING note_id
            """),
            {"entry_id": entry_id}
        )
        note_id = result.scalar()
        await db_session.commit()

        # Delete note
        response = await async_client.delete(
            f"/api/v1/timeline/{test_investigation.investigation_id}/notes/{note_id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        assert "deleted" in response.json()["message"]

    async def test_get_timeline_stats_with_data(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """Test timeline stats endpoint with actual data."""
        # Create diverse timeline entries
        for entry_type in ["event", "finding", "observation"]:
            for i in range(3):
                await db_session.execute(
                    text("""
                        INSERT INTO timeline_entries 
                        (investigation_id, timestamp, entry_type, title, data, tags)
                        VALUES (:inv_id, NOW(), :entry_type, :title, '{}'::jsonb, :tags)
                    """),
                    {
                        "inv_id": str(test_investigation.investigation_id),
                        "entry_type": entry_type,
                        "title": f"{entry_type} {i}",
                        "tags": [f"tag_{entry_type}", "common"]
                    }
                )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/stats",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_entries"] == 9
        assert data["entries_by_type"]["event"] == 3
        assert data["entries_by_type"]["finding"] == 3
        assert data["entries_by_type"]["observation"] == 3
        assert "common" in data["tags"]
        assert len(data["tags"]) == 4  # tag_event, tag_finding, tag_observation, common
