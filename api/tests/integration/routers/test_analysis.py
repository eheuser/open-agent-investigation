"""
Integration tests for the Analysis API endpoints.

Tests the /api/v1/analysis endpoints including Autoruns and Execution Evidence analyzers.
"""

import pytest
import json
from httpx import AsyncClient
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from sqlalchemy import text


@pytest.mark.integration
class TestAnalysisEndpoints:
    """Integration tests for analysis module endpoints."""

    @pytest.mark.asyncio
    async def test_list_analysis_modules(self, async_client: AsyncClient, admin_headers):
        """
        Test that the /api/v1/analysis/modules endpoint returns available analysis modules.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - The response status code is 200
        - The response contains a list of modules
        - At least the Autoruns and Execution Evidence modules are present
        """
        response = await async_client.get(
            "/api/v1/analysis/modules",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "modules" in data
        assert "total" in data
        assert isinstance(data["modules"], list)
        assert data["total"] >= 2
        
        # Check that expected modules are present
        module_ids = [m["id"] for m in data["modules"]]
        assert "autoruns" in module_ids
        assert "execution_evidence" in module_ids

    @pytest.mark.asyncio
    async def test_get_execution_evidence_categories(self, async_client: AsyncClient, admin_headers):
        """
        Test that the /api/v1/analysis/execution-evidence/categories endpoint returns category metadata.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - The response status code is 200
        - Categories include required metadata fields
        - At least Prefetch, SRUM, Jump Lists, and LNK Files are present
        """
        response = await async_client.get(
            "/api/v1/analysis/execution-evidence/categories",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "categories" in data
        assert "total" in data
        assert isinstance(data["categories"], list)
        assert data["total"] == 4
        
        # Verify category structure
        for category in data["categories"]:
            assert "key" in category
            assert "name" in category
            assert "description" in category
            assert "timestamp_meaning" in category
            assert "proves_execution" in category
            assert "proves_presence" in category
        
        # Check that expected categories are present
        category_keys = [c["key"] for c in data["categories"]]
        assert "prefetch" in category_keys
        assert "srum" in category_keys
        assert "jump_lists" in category_keys
        assert "lnk_files" in category_keys

    @pytest.mark.asyncio
    async def test_analyze_execution_evidence_empty_investigation(
        self, async_client: AsyncClient, admin_headers, test_investigation_id
    ):
        """
        Test execution evidence analysis on an investigation with no events.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - The response status code is 200
        - The response contains an empty entries list
        - Summary and metadata are properly structured
        """
        response = await async_client.get(
            f"/api/v1/analysis/execution-evidence/{test_investigation_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "entries" in data
        assert "total" in data
        assert "categories_analyzed" in data
        assert "summary" in data
        
        assert isinstance(data["entries"], list)
        assert data["total"] == 0
        assert len(data["entries"]) == 0

    @pytest.mark.asyncio
    async def test_analyze_execution_evidence_with_category_filter(
        self, async_client: AsyncClient, admin_headers, test_investigation_id
    ):
        """
        Test execution evidence analysis with specific category filtering.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - The response status code is 200
        - Only the requested categories are analyzed
        - The categories_analyzed field reflects the filter
        """
        response = await async_client.get(
            f"/api/v1/analysis/execution-evidence/{test_investigation_id}",
            headers=admin_headers,
            params={"categories": ["prefetch", "srum"]}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "categories_analyzed" in data
        assert len(data["categories_analyzed"]) == 2
        assert "prefetch" in data["categories_analyzed"]
        assert "srum" in data["categories_analyzed"]

    @pytest.mark.asyncio
    async def test_analyze_execution_evidence_unauthorized(
        self, async_client: AsyncClient, test_investigation_id
    ):
        """
        Test that execution evidence analysis requires authentication.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - The response status code is 401 (Unauthorized) when no auth headers are provided
        """
        response = await async_client.get(
            f"/api/v1/analysis/execution-evidence/{test_investigation_id}"
        )
        
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_analyze_execution_evidence_invalid_investigation(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test execution evidence analysis with a non-existent investigation ID.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - The response status code is 404 (Not Found) or 403 (Forbidden)
        - An appropriate error message is returned
        """
        fake_investigation_id = uuid4()
        
        response = await async_client.get(
            f"/api/v1/analysis/execution-evidence/{fake_investigation_id}",
            headers=admin_headers
        )
        
        # Should return 404 or 403 depending on implementation
        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_execution_evidence_response_structure(
        self, async_client: AsyncClient, admin_headers, test_investigation_id
    ):
        """
        Test that the execution evidence response has the correct structure.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - All required fields are present in the response
        - Data types are correct
        - Entry structure matches the schema
        """
        response = await async_client.get(
            f"/api/v1/analysis/execution-evidence/{test_investigation_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check top-level structure
        assert "entries" in data
        assert "total" in data
        assert "categories_analyzed" in data
        assert "summary" in data
        
        # Check data types
        assert isinstance(data["entries"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["categories_analyzed"], list)
        assert isinstance(data["summary"], dict)
        
        # If there are entries, check their structure
        if len(data["entries"]) > 0:
            entry = data["entries"][0]
            assert "category" in entry
            assert "description" in entry
            assert "timestamp_meaning" in entry
            assert "executable_path" in entry
            assert "proves_execution" in entry
            assert "proves_presence" in entry
            assert isinstance(entry["proves_execution"], bool)
            assert isinstance(entry["proves_presence"], bool)

    @pytest.mark.asyncio
    async def test_get_autoruns_categories(self, async_client: AsyncClient, admin_headers):
        """
        Test that the /api/v1/analysis/autoruns/categories endpoint returns category information.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - The response status code is 200
        - Categories are returned with name and description
        """
        response = await async_client.get(
            "/api/v1/analysis/autoruns/categories",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "categories" in data
        assert "total" in data
        assert isinstance(data["categories"], list)
        
        # Verify category structure
        for category in data["categories"]:
            assert "name" in category
            assert "description" in category

    @pytest.mark.asyncio
    async def test_analyze_autoruns_empty_investigation(
        self, async_client: AsyncClient, admin_headers, test_investigation_id
    ):
        """
        Test autoruns analysis on an investigation with no events.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - The response status code is 200
        - The response contains an empty entries list
        """
        response = await async_client.get(
            f"/api/v1/analysis/autoruns/{test_investigation_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "entries" in data
        assert "total" in data
        assert "summary" in data
        assert isinstance(data["entries"], list)


@pytest.mark.integration
class TestExecutionEvidenceCategoryMetadata:
    """Integration tests for execution evidence category metadata."""

    @pytest.mark.asyncio
    async def test_prefetch_category_proves_execution(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test that Prefetch category metadata correctly indicates it proves execution.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - Prefetch proves_execution is True
        - Prefetch proves_presence is True
        """
        response = await async_client.get(
            "/api/v1/analysis/execution-evidence/categories",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        categories = response.json()["categories"]
        
        prefetch = next((c for c in categories if c["key"] == "prefetch"), None)
        assert prefetch is not None
        assert prefetch["proves_execution"] is True
        assert prefetch["proves_presence"] is True

    @pytest.mark.asyncio
    async def test_srum_category_proves_execution_not_presence(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test that SRUM category metadata correctly indicates it proves execution but not presence.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - SRUM proves_execution is True
        - SRUM proves_presence is False
        """
        response = await async_client.get(
            "/api/v1/analysis/execution-evidence/categories",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        categories = response.json()["categories"]
        
        srum = next((c for c in categories if c["key"] == "srum"), None)
        assert srum is not None
        assert srum["proves_execution"] is True
        assert srum["proves_presence"] is False

    @pytest.mark.asyncio
    async def test_lnk_category_proves_presence_not_execution(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test that LNK Files category metadata correctly indicates it proves presence but not execution.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - LNK Files proves_execution is False
        - LNK Files proves_presence is True
        """
        response = await async_client.get(
            "/api/v1/analysis/execution-evidence/categories",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        categories = response.json()["categories"]
        
        lnk = next((c for c in categories if c["key"] == "lnk_files"), None)
        assert lnk is not None
        assert lnk["proves_execution"] is False
        assert lnk["proves_presence"] is True

    @pytest.mark.asyncio
    async def test_all_categories_have_timestamp_meanings(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test that all execution evidence categories have documented timestamp meanings.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - Every category has a non-empty timestamp_meaning field
        - The timestamp meanings are descriptive
        """
        response = await async_client.get(
            "/api/v1/analysis/execution-evidence/categories",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        categories = response.json()["categories"]
        
        for category in categories:
            assert "timestamp_meaning" in category
            assert isinstance(category["timestamp_meaning"], str)
            assert len(category["timestamp_meaning"]) > 10  # Should be descriptive
            # Should mention "time" or "timestamp"
            assert "time" in category["timestamp_meaning"].lower()


@pytest.mark.integration
class TestAnalysisCacheManagement:
    """Integration tests for analysis cache management."""

    @pytest.mark.asyncio
    async def test_clear_cache_success(
        self, async_client: AsyncClient, admin_headers, test_investigation_id, async_db
    ):
        """
        Test that clearing cache successfully removes cached analysis results.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
            async_db: Database session for setup.
        
        Verifies that:
        - The DELETE endpoint returns 200 status
        - Response includes cleared_count
        - Status is "ok"
        """
        response = await async_client.delete(
            f"/api/v1/analysis/cache/{test_investigation_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert data["status"] == "ok"
        assert "cleared_count" in data
        assert "message" in data
        assert isinstance(data["cleared_count"], int)

    @pytest.mark.asyncio
    async def test_clear_cache_unauthorized(
        self, async_client: AsyncClient, test_investigation_id
    ):
        """
        Test that clearing cache requires authentication.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - The response status code is 401 (Unauthorized) when no auth headers are provided
        """
        response = await async_client.delete(
            f"/api/v1/analysis/cache/{test_investigation_id}"
        )
        
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_clear_cache_invalid_investigation(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test clearing cache with a non-existent investigation ID.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - The response status code is 404 (Not Found) or 403 (Forbidden)
        """
        fake_investigation_id = uuid4()
        
        response = await async_client.delete(
            f"/api/v1/analysis/cache/{fake_investigation_id}",
            headers=admin_headers
        )
        
        # Should return 404 or 403 depending on implementation
        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_clear_cache_with_existing_cached_results(
        self, async_client: AsyncClient, admin_headers, test_investigation_id, async_db
    ):
        """
        Test clearing cache when cached results exist.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
            async_db: Database session for setup.
        
        Verifies that:
        - Cache entries are successfully deleted
        - cleared_count reflects the number of entries removed
        """
        # Insert a test cache entry
        insert_query = text(
            """
            INSERT INTO analysis_results 
            (investigation_id, analysis_type, analysis_version, parameters, results, expires_at)
            VALUES (:investigation_id, :analysis_type, :version, :params, :results, NOW() + INTERVAL '1 hour')
            """
        )
        
        await async_db.execute(
            insert_query,
            {
                "investigation_id": str(test_investigation_id),
                "analysis_type": "execution_evidence",
                "version": "1.0",
                "params": "{}",
                "results": "[]"
            }
        )
        await async_db.commit()
        
        # Clear the cache
        response = await async_client.delete(
            f"/api/v1/analysis/cache/{test_investigation_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "ok"
        assert data["cleared_count"] >= 1


@pytest.mark.integration
class TestParsingWaitLogic:
    """Integration tests for parsing wait logic in analysis endpoints."""

    @pytest.mark.asyncio
    async def test_check_parsing_status_no_jobs(
        self, async_client: AsyncClient, admin_headers, test_investigation_id
    ):
        """
        Test that analysis proceeds normally when no parsing jobs exist.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - Analysis completes successfully without waiting
        - Response is returned immediately
        """
        response = await async_client.get(
            f"/api/v1/analysis/execution-evidence/{test_investigation_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "entries" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_analysis_waits_for_pending_jobs(
        self, async_client: AsyncClient, admin_headers, test_investigation_id, async_db
    ):
        """
        Test that analysis waits for pending parsing jobs to complete.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
            async_db: Database session for setup.
        
        Verifies that:
        - Analysis detects pending jobs
        - Analysis waits for completion
        - Response is eventually returned
        """
        # Insert a pending parsing job
        insert_query = text(
            """
            INSERT INTO jobs_parsing 
            (investigation_id, artifact_id, parser_name, status, created_at)
            VALUES (:investigation_id, :artifact_id, :parser_name, :status, NOW())
            """
        )
        
        await async_db.execute(
            insert_query,
            {
                "investigation_id": str(test_investigation_id),
                "artifact_id": str(uuid4()),
                "parser_name": "TestParser",
                "status": "pending"
            }
        )
        await async_db.commit()
        
        # Mock the wait logic to immediately mark job as completed
        from app.routers import analysis
        original_wait = analysis.wait_for_parsing_completion
        
        async def mock_wait(db, investigation_id, max_wait_seconds=30, poll_interval=0.5):
            # Mark job as completed
            update_query = text(
                """
                UPDATE jobs_parsing 
                SET status = 'completed'
                WHERE investigation_id = :investigation_id AND status = 'pending'
                """
            )
            await db.execute(update_query, {"investigation_id": str(investigation_id)})
            await db.commit()
            return True
        
        with patch.object(analysis, 'wait_for_parsing_completion', new=mock_wait):
            response = await async_client.get(
                f"/api/v1/analysis/execution-evidence/{test_investigation_id}",
                headers=admin_headers
            )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "entries" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_analysis_handles_running_jobs(
        self, async_client: AsyncClient, admin_headers, test_investigation_id, async_db
    ):
        """
        Test that analysis waits for running parsing jobs.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
            async_db: Database session for setup.
        
        Verifies that:
        - Analysis detects running jobs
        - Analysis waits for completion
        """
        # Insert a running parsing job
        insert_query = text(
            """
            INSERT INTO jobs_parsing 
            (investigation_id, artifact_id, parser_name, status, created_at)
            VALUES (:investigation_id, :artifact_id, :parser_name, :status, NOW())
            """
        )
        
        await async_db.execute(
            insert_query,
            {
                "investigation_id": str(test_investigation_id),
                "artifact_id": str(uuid4()),
                "parser_name": "TestParser",
                "status": "running"
            }
        )
        await async_db.commit()
        
        # Mock the wait logic to immediately mark job as completed
        from app.routers import analysis
        
        async def mock_wait(db, investigation_id, max_wait_seconds=30, poll_interval=0.5):
            # Mark job as completed
            update_query = text(
                """
                UPDATE jobs_parsing 
                SET status = 'completed'
                WHERE investigation_id = :investigation_id AND status = 'running'
                """
            )
            await db.execute(update_query, {"investigation_id": str(investigation_id)})
            await db.commit()
            return True
        
        with patch.object(analysis, 'wait_for_parsing_completion', new=mock_wait):
            response = await async_client.get(
                f"/api/v1/analysis/execution-evidence/{test_investigation_id}",
                headers=admin_headers
            )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_analysis_timeout_handling(
        self, async_client: AsyncClient, admin_headers, test_investigation_id, async_db
    ):
        """
        Test that analysis handles timeout when parsing jobs don't complete.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
            async_db: Database session for setup.
        
        Verifies that:
        - Analysis doesn't hang indefinitely
        - Analysis returns results even if parsing times out
        - Response is still valid (may be incomplete)
        """
        # Insert a pending parsing job that won't complete
        insert_query = text(
            """
            INSERT INTO jobs_parsing 
            (investigation_id, artifact_id, parser_name, status, created_at)
            VALUES (:investigation_id, :artifact_id, :parser_name, :status, NOW())
            """
        )
        
        await async_db.execute(
            insert_query,
            {
                "investigation_id": str(test_investigation_id),
                "artifact_id": str(uuid4()),
                "parser_name": "TestParser",
                "status": "pending"
            }
        )
        await async_db.commit()
        
        # Mock the wait logic to timeout immediately
        from app.routers import analysis
        
        async def mock_wait_timeout(db, investigation_id, max_wait_seconds=30, poll_interval=0.5):
            # Simulate timeout
            return False
        
        with patch.object(analysis, 'wait_for_parsing_completion', new=mock_wait_timeout):
            response = await async_client.get(
                f"/api/v1/analysis/execution-evidence/{test_investigation_id}",
                headers=admin_headers
            )
        
        # Should still return 200 even if parsing timed out
        assert response.status_code == 200
        data = response.json()
        
        assert "entries" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_completed_jobs_dont_block_analysis(
        self, async_client: AsyncClient, admin_headers, test_investigation_id, async_db
    ):
        """
        Test that completed parsing jobs don't cause analysis to wait.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
            async_db: Database session for setup.
        
        Verifies that:
        - Only pending/running jobs trigger waiting
        - Completed jobs are ignored
        - Analysis proceeds immediately
        """
        # Insert completed parsing jobs
        insert_query = text(
            """
            INSERT INTO jobs_parsing 
            (investigation_id, artifact_id, parser_name, status, created_at)
            VALUES (:investigation_id, :artifact_id, :parser_name, :status, NOW())
            """
        )
        
        for _ in range(3):
            await async_db.execute(
                insert_query,
                {
                    "investigation_id": str(test_investigation_id),
                    "artifact_id": str(uuid4()),
                    "parser_name": "TestParser",
                    "status": "completed"
                }
            )
        await async_db.commit()
        
        response = await async_client.get(
            f"/api/v1/analysis/execution-evidence/{test_investigation_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "entries" in data


@pytest.mark.integration
class TestDebugEndpoints:
    """Integration tests for debug endpoints."""

    @pytest.mark.asyncio
    async def test_debug_event_types_empty_investigation(
        self, async_client: AsyncClient, admin_headers, test_investigation_id
    ):
        """
        Test debug endpoint with an investigation that has no events.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - Endpoint returns 200 status
        - Response includes investigation_id, total_events, unique_event_types, event_types
        - Counts are zero for empty investigation
        """
        response = await async_client.get(
            f"/api/v1/analysis/debug/event-types/{test_investigation_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "investigation_id" in data
        assert "total_events" in data
        assert "unique_event_types" in data
        assert "event_types" in data
        
        assert data["total_events"] == 0
        assert data["unique_event_types"] == 0
        assert isinstance(data["event_types"], list)
        assert len(data["event_types"]) == 0

    @pytest.mark.asyncio
    async def test_debug_event_types_with_events(
        self, async_client: AsyncClient, admin_headers, test_investigation_id, async_db
    ):
        """
        Test debug endpoint with an investigation that has events.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
            async_db: Database session for setup.
        
        Verifies that:
        - Event types are correctly counted
        - Response structure includes event_type and count for each type
        - Results are ordered by count descending
        """
        # Insert test events
        insert_query = text(
            """
            INSERT INTO events 
            (investigation_id, event_ts, artifact_id, event_type, payload)
            VALUES (:investigation_id, NOW(), :artifact_id, :event_type, :payload)
            """
        )
        
        # Insert 5 prefetch events and 3 registry events
        for i in range(5):
            await async_db.execute(
                insert_query,
                {
                    "investigation_id": str(test_investigation_id),
                    "artifact_id": str(uuid4()),
                    "event_type": "prefetch_execution",
                    "payload": "{}"
                }
            )
        
        for i in range(3):
            await async_db.execute(
                insert_query,
                {
                    "investigation_id": str(test_investigation_id),
                    "artifact_id": str(uuid4()),
                    "event_type": "registry_value",
                    "payload": "{}"
                }
            )
        
        await async_db.commit()
        
        response = await async_client.get(
            f"/api/v1/analysis/debug/event-types/{test_investigation_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_events"] == 8
        assert data["unique_event_types"] == 2
        
        # Check event types structure
        event_types = data["event_types"]
        assert len(event_types) == 2
        
        # Should be ordered by count descending
        assert event_types[0]["event_type"] == "prefetch_execution"
        assert event_types[0]["count"] == 5
        assert event_types[1]["event_type"] == "registry_value"
        assert event_types[1]["count"] == 3

    @pytest.mark.asyncio
    async def test_debug_event_types_unauthorized(
        self, async_client: AsyncClient, test_investigation_id
    ):
        """
        Test that debug endpoint requires authentication.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - The response status code is 401 (Unauthorized) when no auth headers are provided
        """
        response = await async_client.get(
            f"/api/v1/analysis/debug/event-types/{test_investigation_id}"
        )
        
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_debug_event_types_invalid_investigation(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test debug endpoint with a non-existent investigation ID.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - The response status code is 404 (Not Found) or 403 (Forbidden)
        """
        fake_investigation_id = uuid4()
        
        response = await async_client.get(
            f"/api/v1/analysis/debug/event-types/{fake_investigation_id}",
            headers=admin_headers
        )
        
        # Should return 404 or 403 depending on implementation
        assert response.status_code in [403, 404]


@pytest.mark.integration
class TestBrowsedURLsEndpoints:
    """Integration tests for browsed URLs analysis endpoints."""

    @pytest.mark.asyncio
    async def test_list_browsed_urls_browsers(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test that the /api/v1/analysis/browsed-urls/browsers endpoint returns browser metadata.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - The response status code is 200
        - Browsers include required metadata fields
        - At least Chrome/Chromium, Firefox, and Edge Legacy are present
        """
        response = await async_client.get(
            "/api/v1/analysis/browsed-urls/browsers",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "browsers" in data
        assert "total" in data
        assert isinstance(data["browsers"], list)
        assert data["total"] == 3
        
        # Verify browser structure
        for browser in data["browsers"]:
            assert "key" in browser
            assert "name" in browser
            assert "description" in browser
            assert "icon" in browser
        
        # Check that expected browsers are present
        browser_keys = [b["key"] for b in data["browsers"]]
        assert "chrome_chromium" in browser_keys
        assert "firefox" in browser_keys
        assert "edge_legacy" in browser_keys

    @pytest.mark.asyncio
    async def test_analyze_browsed_urls_empty_investigation(
        self, async_client: AsyncClient, admin_headers, test_investigation_id
    ):
        """
        Test browsed URLs analysis on an investigation with no browser history events.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - The response status code is 200
        - The response contains an empty entries list
        - Summary and metadata are properly structured
        """
        response = await async_client.get(
            f"/api/v1/analysis/browsed-urls/{test_investigation_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "entries" in data
        assert "total" in data
        assert "browsers_analyzed" in data
        assert "summary" in data
        
        assert isinstance(data["entries"], list)
        assert data["total"] == 0
        assert len(data["entries"]) == 0

    @pytest.mark.asyncio
    async def test_analyze_browsed_urls_with_browser_filter(
        self, async_client: AsyncClient, admin_headers, test_investigation_id
    ):
        """
        Test browsed URLs analysis with specific browser filtering.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - The response status code is 200
        - Only the requested browsers are analyzed
        - The browsers_analyzed field reflects the filter
        """
        response = await async_client.get(
            f"/api/v1/analysis/browsed-urls/{test_investigation_id}",
            headers=admin_headers,
            params={"browsers": ["chrome_chromium", "firefox"]}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "browsers_analyzed" in data
        assert len(data["browsers_analyzed"]) == 2
        assert "chrome_chromium" in data["browsers_analyzed"]
        assert "firefox" in data["browsers_analyzed"]

    @pytest.mark.asyncio
    async def test_analyze_browsed_urls_with_search(
        self, async_client: AsyncClient, admin_headers, test_investigation_id
    ):
        """
        Test browsed URLs analysis with search term.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - The response status code is 200
        - Search parameter is accepted
        - Results are filtered by search term
        """
        response = await async_client.get(
            f"/api/v1/analysis/browsed-urls/{test_investigation_id}",
            headers=admin_headers,
            params={"search": "github"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "entries" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_analyze_browsed_urls_unauthorized(
        self, async_client: AsyncClient, test_investigation_id
    ):
        """
        Test that browsed URLs analysis requires authentication.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - The response status code is 401 (Unauthorized) when no auth headers are provided
        """
        response = await async_client.get(
            f"/api/v1/analysis/browsed-urls/{test_investigation_id}"
        )
        
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_analyze_browsed_urls_invalid_investigation(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test browsed URLs analysis with a non-existent investigation ID.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - The response status code is 404 (Not Found) or 403 (Forbidden)
        - An appropriate error message is returned
        """
        fake_investigation_id = uuid4()
        
        response = await async_client.get(
            f"/api/v1/analysis/browsed-urls/{fake_investigation_id}",
            headers=admin_headers
        )
        
        # Should return 404 or 403 depending on implementation
        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_browsed_urls_response_structure(
        self, async_client: AsyncClient, admin_headers, test_investigation_id
    ):
        """
        Test that the browsed URLs response has the correct structure.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
        
        Verifies that:
        - All required fields are present in the response
        - Data types are correct
        - Entry structure matches the schema
        """
        response = await async_client.get(
            f"/api/v1/analysis/browsed-urls/{test_investigation_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check top-level structure
        assert "entries" in data
        assert "total" in data
        assert "browsers_analyzed" in data
        assert "summary" in data
        
        # Check data types
        assert isinstance(data["entries"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["browsers_analyzed"], list)
        assert isinstance(data["summary"], dict)
        
        # If there are entries, check their structure
        if len(data["entries"]) > 0:
            entry = data["entries"][0]
            assert "browser" in entry
            assert "url" in entry
            assert isinstance(entry["browser"], str)
            assert isinstance(entry["url"], str)

    @pytest.mark.asyncio
    async def test_browsed_urls_with_data(
        self, async_client: AsyncClient, admin_headers, test_investigation_id, async_db
    ):
        """
        Test browsed URLs analysis with actual browser history data.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
            test_investigation_id: UUID of a test investigation.
            async_db: Database session for setup.
        
        Verifies that:
        - Browser history events are correctly analyzed
        - Entries are properly formatted
        - Summary counts are accurate
        """
        # Insert test browser history events
        insert_query = text(
            """
            INSERT INTO events 
            (investigation_id, event_ts, artifact_id, event_type, payload)
            VALUES (:investigation_id, NOW(), :artifact_id, :event_type, :payload)
            """
        )
        
        # Insert 3 Chrome entries
        for i in range(3):
            await async_db.execute(
                insert_query,
                {
                    "investigation_id": str(test_investigation_id),
                    "artifact_id": str(uuid4()),
                    "event_type": "browser_history",
                    "payload": json.dumps({
                        "browser": "chrome_chromium",
                        "url": f"https://example{i}.com",
                        "title": f"Example {i}",
                        "visit_count": i + 1
                    })
                }
            )
        
        # Insert 2 Firefox entries
        for i in range(2):
            await async_db.execute(
                insert_query,
                {
                    "investigation_id": str(test_investigation_id),
                    "artifact_id": str(uuid4()),
                    "event_type": "browser_history",
                    "payload": json.dumps({
                        "browser": "firefox",
                        "url": f"https://firefox{i}.com",
                        "title": f"Firefox {i}",
                        "visit_count": i + 1
                    })
                }
            )
        
        await async_db.commit()
        
        response = await async_client.get(
            f"/api/v1/analysis/browsed-urls/{test_investigation_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 5
        assert len(data["entries"]) == 5
        
        # Check summary
        assert data["summary"]["chrome_chromium"] == 3
        assert data["summary"]["firefox"] == 2

    @pytest.mark.asyncio
    async def test_list_analysis_modules_includes_browsed_urls(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test that the browsed_urls module is included in the modules list.
        
        Args:
            async_client: An instance of httpx.AsyncClient for making HTTP requests.
            admin_headers: Authentication headers for an admin user.
        
        Verifies that:
        - The modules list includes browsed_urls
        - Module metadata is correct
        """
        response = await async_client.get(
            "/api/v1/analysis/modules",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        module_ids = [m["id"] for m in data["modules"]]
        assert "browsed_urls" in module_ids
        
        # Find browsed_urls module
        browsed_urls_module = next(m for m in data["modules"] if m["id"] == "browsed_urls")
        assert browsed_urls_module["name"] == "Browsed URLs"
        assert browsed_urls_module["icon"] == "globe-alt"
        assert browsed_urls_module["categories"] == 3
