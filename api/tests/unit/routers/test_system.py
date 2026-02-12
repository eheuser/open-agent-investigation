"""
Unit tests for system status router.
Tests system statistics and health monitoring endpoints.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4

from app.routers.system import get_system_status


def create_full_mock_sequence(mock_execute_result, **overrides):
    """
    Helper to create full sequence of database query mocks with optional overrides.
    
    Query sequence (15 queries total):
    0. Investigation stats from materialized view
    1. Artifacts total (total, size_bytes) from system_stats_cache
    2. Artifacts by classification (TABLESAMPLE)
    3. Artifacts search count (scalar)
    4. Artifacts list (paginated)
    5. Events total (total, with_embeddings) from system_stats_cache
    6. Events by type (TABLESAMPLE)
    7. Embeddings total (scalar) from system_stats_cache
    8. Embeddings by owner type (TABLESAMPLE)
    9. Embeddings by model (TABLESAMPLE)
    10. Timeline stats (total, with_embeddings) from system_stats_cache
    11. Timeline by type (TABLESAMPLE)
    12. Jobs stats (rows of stat_key, stat_value) from system_stats_cache
    13. Users (total, admins, regular)
    14. Database health check (scalar)
    
    Note: events_by_investigation is derived from investigation stats (query 0), not a separate query
    """
    defaults = {
        "investigations": [],
        "artifacts_total": (0, 0),
        "artifacts_classification": [],
        "artifacts_search_count": 0,
        "artifacts_list": [],
        "events_total": (0, 0),  # (total, with_embeddings)
        "events_by_type": [],
        "events_by_investigation": [],
        "embeddings_total": 0,
        "embeddings_by_owner": [],
        "embeddings_by_model": [],
        "timeline_stats": (0, 0),  # (total, with_embeddings)
        "timeline_by_type": [],
        "job_stats": {},  # Dictionary of stat_key: stat_value
        "users": (0, 0, 0),
        "db_health": 1,
    }
    defaults.update(overrides)
    
    return [
        mock_execute_result(defaults["investigations"]),
        mock_execute_result(defaults["artifacts_total"]),
        mock_execute_result(defaults["artifacts_classification"]),
        mock_execute_result(scalar_value=defaults["artifacts_search_count"]),
        mock_execute_result(defaults["artifacts_list"]),
        mock_execute_result(defaults["events_total"]),
        mock_execute_result(defaults["events_by_type"]),
        # events_by_investigation removed - derived from investigation stats
        mock_execute_result(scalar_value=defaults["embeddings_total"]),
        mock_execute_result(defaults["embeddings_by_owner"]),
        mock_execute_result(defaults["embeddings_by_model"]),
        mock_execute_result(defaults["timeline_stats"]),
        mock_execute_result(defaults["timeline_by_type"]),
        mock_execute_result(list(defaults["job_stats"].items()) if defaults["job_stats"] else []),
        mock_execute_result(defaults["users"]),
        mock_execute_result(scalar_value=defaults["db_health"]),
    ]


@pytest.mark.unit
class TestGetSystemStatus:
    """Test get_system_status endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = AsyncMock()
        return db

    @pytest.fixture
    def mock_user(self):
        """Create mock current user."""
        user = MagicMock()
        user.username = "testuser"
        user.user_id = 1
        return user

    @pytest.fixture
    def mock_execute_result(self):
        """Create mock execute result with fetchone/fetchall."""
        def create_result(data=None, scalar_value=None):
            result = MagicMock()
            if scalar_value is not None:
                result.scalar.return_value = scalar_value
            if data is not None:
                if isinstance(data, list):
                    result.fetchall.return_value = data
                else:
                    result.fetchone.return_value = data
            else:
                result.fetchall.return_value = []
                result.fetchone.return_value = None
            return result
        return create_result

    async def test_returns_all_stat_categories(self, mock_db, mock_user, mock_execute_result):
        """Test that all statistics categories are returned."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            investigations=[(uuid4(), "Test Investigation", "testuser", datetime.utcnow(), 100, 80, 20, 80.0, 10, 8, 2, 80.0)],
            artifacts_total=(1000, 5000000),
            artifacts_classification=[("0", 400), ("1", 800), ("3", 200)],  # Estimates (4x multiplier)
            artifacts_search_count=350,
            artifacts_list=[(1, "test.evtx", "1", datetime.utcnow(), 1024, "Test Inv", b"abc123")],
            events_total=(10000, 8000),
            events_by_type=[("evtx_security_4624", 10000), ("evtx_sysmon_1", 6000)],  # Estimates (20x multiplier)
            embeddings_total=8500,
            embeddings_by_owner=[("tool", 80000), ("timeline", 5000)],  # Estimates (10x multiplier)
            embeddings_by_model=[("text-embedding-ada-002", 85000)],  # Estimates (10x multiplier)
            timeline_stats=(50, 45),
            timeline_by_type=[("event", 400), ("finding", 100)],  # Estimates (10x multiplier)
            job_stats={
                "jobs_parsing_pending": 2,
                "jobs_parsing_completed": 100,
                "jobs_agents_running": 1,
                "jobs_agents_completed": 50,
                "jobs_embedding_pending": 5,
                "jobs_embedding_completed": 200,
            },
            users=(10, 2, 8),
        )

        result = await get_system_status(
            db=mock_db,
            current_user=mock_user,
            artifacts_page=1,
            artifacts_page_size=20,
            artifacts_search="",
        )

        # Verify all categories are present
        assert "investigations" in result
        assert "artifacts" in result
        assert "events" in result
        assert "embeddings" in result
        assert "timeline" in result
        assert "jobs" in result
        assert "users" in result
        assert "database" in result

    async def test_investigations_detailed_structure(self, mock_db, mock_user, mock_execute_result):
        """Test investigations detailed statistics structure."""
        inv_id = uuid4()
        created_at = datetime.utcnow()
        
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            investigations=[
                (inv_id, "Test Investigation", "owner1", created_at, 100, 80, 20, 80.0, 10, 8, 2, 80.0),
                (uuid4(), "Another Investigation", "owner2", created_at, 50, 25, 25, 50.0, 5, 3, 2, 60.0),
            ]
        )

        result = await get_system_status(mock_db, mock_user)

        assert result["investigations"]["total"] == 2
        assert len(result["investigations"]["detailed"]) == 2
        
        first_inv = result["investigations"]["detailed"][0]
        assert first_inv["investigation_id"] == str(inv_id)
        assert first_inv["title"] == "Test Investigation"
        assert first_inv["owner"] == "owner1"
        assert first_inv["total_events"] == 100
        assert first_inv["events_with_embeddings"] == 80
        assert first_inv["events_without_embeddings"] == 20
        assert first_inv["event_embedding_coverage_percent"] == 80.0
        assert first_inv["total_timeline_entries"] == 10
        assert first_inv["timeline_with_embeddings"] == 8
        assert first_inv["timeline_without_embeddings"] == 2
        assert first_inv["timeline_embedding_coverage_percent"] == 80.0

    async def test_artifacts_pagination(self, mock_db, mock_user, mock_execute_result):
        """Test artifacts pagination parameters."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            artifacts_total=(1000, 5000000),
            artifacts_search_count=100,
            artifacts_list=[(21, "file21.evtx", "1", datetime.utcnow(), 1024, "Test", b"hash")]
        )

        result = await get_system_status(
            db=mock_db,
            current_user=mock_user,
            artifacts_page=2,
            artifacts_page_size=20,
            artifacts_search="",
        )

        assert result["artifacts"]["page"] == 2
        assert result["artifacts"]["page_size"] == 20
        assert result["artifacts"]["search_total"] == 100
        assert result["artifacts"]["total_pages"] == 5  # 100 / 20
        assert result["artifacts"]["has_more"] is True

    async def test_artifacts_search_filter(self, mock_db, mock_user, mock_execute_result):
        """Test artifacts search filtering."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            artifacts_total=(1000, 5000000),
            artifacts_search_count=5,
            artifacts_list=[
                (1, "Security.evtx", "1", datetime.utcnow(), 1024, "Test", b"hash"),
                (2, "Security-2.evtx", "1", datetime.utcnow(), 2048, "Test", b"hash2"),
            ]
        )

        result = await get_system_status(
            db=mock_db,
            current_user=mock_user,
            artifacts_page=1,
            artifacts_page_size=20,
            artifacts_search="Security",
        )

        assert result["artifacts"]["search_total"] == 5
        assert len(result["artifacts"]["list"]) == 2
        assert result["artifacts"]["list"][0]["filename"] == "Security.evtx"

    async def test_artifacts_page_size_capped_at_50(self, mock_db, mock_user, mock_execute_result):
        """Test that artifacts page size is capped at 50."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            artifacts_total=(1000, 5000000),
            artifacts_search_count=100,
        )

        result = await get_system_status(
            db=mock_db,
            current_user=mock_user,
            artifacts_page=1,
            artifacts_page_size=100,  # Request 100
            artifacts_search="",
        )

        # Should be capped at 50
        assert result["artifacts"]["page_size"] == 50

    async def test_events_embedding_coverage_calculation(self, mock_db, mock_user, mock_execute_result):
        """Test event embedding coverage percentage calculation."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            events_total=(1000, 750)  # total=1000, with_embeddings=750
        )

        result = await get_system_status(mock_db, mock_user)

        assert result["events"]["total"] == 1000
        assert result["events"]["events_with_embeddings"] == 750
        assert result["events"]["events_without_embeddings"] == 250
        assert result["events"]["embedding_coverage_percent"] == 75.0

    async def test_timeline_embedding_coverage_calculation(self, mock_db, mock_user, mock_execute_result):
        """Test timeline embedding coverage percentage calculation."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            timeline_stats=(100, 90),  # total=100, with_embeddings=90
            timeline_by_type=[("event", 70), ("finding", 30)]
        )

        result = await get_system_status(mock_db, mock_user)

        assert result["timeline"]["total"] == 100
        assert result["timeline"]["with_embeddings"] == 90
        assert result["timeline"]["embedding_coverage_percent"] == 90.0

    async def test_jobs_status_aggregation(self, mock_db, mock_user, mock_execute_result):
        """Test job status aggregation for all job types."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            job_stats={
                "jobs_parsing_pending": 5,
                "jobs_parsing_running": 2,
                "jobs_parsing_completed": 100,
                "jobs_parsing_failed": 3,
                "jobs_agents_pending": 1,
                "jobs_agents_completed": 50,
                "jobs_agents_failed": 2,
                "jobs_embedding_pending": 10,
                "jobs_embedding_running": 5,
                "jobs_embedding_completed": 200,
            }
        )

        result = await get_system_status(mock_db, mock_user)

        # Parsing jobs
        assert result["jobs"]["parsing"]["pending"] == 5
        assert result["jobs"]["parsing"]["running"] == 2
        assert result["jobs"]["parsing"]["completed"] == 100
        assert result["jobs"]["parsing"]["failed"] == 3

        # Agent jobs (no running jobs in mock data)
        assert result["jobs"]["agents"]["pending"] == 1
        assert result["jobs"]["agents"]["running"] == 0
        assert result["jobs"]["agents"]["completed"] == 50
        assert result["jobs"]["agents"]["failed"] == 2

        # Embedding jobs (no failed jobs in mock data)
        assert result["jobs"]["embedding"]["pending"] == 10
        assert result["jobs"]["embedding"]["running"] == 5
        assert result["jobs"]["embedding"]["completed"] == 200
        assert result["jobs"]["embedding"]["failed"] == 0

    async def test_users_role_aggregation(self, mock_db, mock_user, mock_execute_result):
        """Test user role aggregation."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            users=(15, 3, 12)
        )

        result = await get_system_status(mock_db, mock_user)

        assert result["users"]["total"] == 15
        assert result["users"]["admins"] == 3
        assert result["users"]["regular"] == 12

    async def test_database_health_check_success(self, mock_db, mock_user, mock_execute_result):
        """Test database health check when connection is successful."""
        mock_db.execute.side_effect = create_full_mock_sequence(mock_execute_result)

        result = await get_system_status(mock_db, mock_user)

        assert result["database"]["status"] == "connected"
        assert "message" not in result["database"]

    async def test_database_health_check_failure(self, mock_db, mock_user, mock_execute_result):
        """Test database health check when connection fails."""
        mocks = create_full_mock_sequence(mock_execute_result)
        mocks[-1] = Exception("Connection refused")  # Replace last (health check) with exception
        mock_db.execute.side_effect = mocks

        result = await get_system_status(mock_db, mock_user)

        assert result["database"]["status"] == "error"
        assert "Connection refused" in result["database"]["message"]

    async def test_handles_empty_database(self, mock_db, mock_user, mock_execute_result):
        """Test handling of empty database (no data)."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            events_total=(0, 0),
            timeline_stats=(0, 0),
            users=(1, 0, 1)
        )

        result = await get_system_status(mock_db, mock_user)

        # Should handle empty data gracefully
        assert result["investigations"]["total"] == 0
        assert result["artifacts"]["total"] == 0
        assert result["events"]["total"] == 0
        assert result["events"]["embedding_coverage_percent"] == 0.0
        assert result["timeline"]["total"] == 0
        assert result["timeline"]["embedding_coverage_percent"] == 0.0

    async def test_handles_null_owner_in_investigations(self, mock_db, mock_user, mock_execute_result):
        """Test handling of investigations with NULL owner (deleted user)."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            investigations=[(uuid4(), "Orphaned Investigation", None, datetime.utcnow(), 10, 5, 5, 50.0, 2, 1, 1, 50.0)]
        )

        result = await get_system_status(mock_db, mock_user)

        assert result["investigations"]["detailed"][0]["owner"] == "Unknown"

    async def test_artifacts_sha256_hex_conversion(self, mock_db, mock_user, mock_execute_result):
        """Test SHA256 hash is converted to hex string."""
        sha256_bytes = b'\xab\xcd\xef\x01\x23\x45\x67\x89' * 4  # 32 bytes
        
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            artifacts_total=(1, 1024),
            artifacts_search_count=1,
            artifacts_list=[(1, "test.bin", "2", datetime.utcnow(), 1024, "Test", sha256_bytes)]
        )

        result = await get_system_status(mock_db, mock_user)

        artifact = result["artifacts"]["list"][0]
        assert artifact["sha256"] == sha256_bytes.hex()
        assert len(artifact["sha256"]) == 64  # 32 bytes = 64 hex chars

    async def test_artifacts_null_sha256_handling(self, mock_db, mock_user, mock_execute_result):
        """Test handling of NULL SHA256 hash."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            artifacts_total=(1, 1024),
            artifacts_search_count=1,
            artifacts_list=[(1, "test.bin", "2", datetime.utcnow(), 1024, "Test", None)]
        )

        result = await get_system_status(mock_db, mock_user)

        artifact = result["artifacts"]["list"][0]
        assert artifact["sha256"] is None

    async def test_embedding_coverage_zero_division_handling(self, mock_db, mock_user, mock_execute_result):
        """Test that zero events doesn't cause division by zero."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            events_total=(0, 0, 0, None)
        )

        result = await get_system_status(mock_db, mock_user)

        assert result["events"]["total"] == 0
        assert result["events"]["embedding_coverage_percent"] == 0.0

    async def test_artifacts_storage_size_formatting(self, mock_db, mock_user, mock_execute_result):
        """Test artifacts storage size is calculated in MB."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            artifacts_total=(1000, 5_000_000_000)
        )

        result = await get_system_status(mock_db, mock_user)

        assert result["artifacts"]["total_size_bytes"] == 5_000_000_000
        assert result["artifacts"]["total_size_mb"] == 4768.37  # 5GB in MB

    async def test_events_by_type_limited_to_20(self, mock_db, mock_user, mock_execute_result):
        """Test that events by type is limited to top 20."""
        event_types = [(f"type_{i}", 100 - i) for i in range(25)]
        
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            events_total=(1000, 500),
            events_by_type=event_types[:20]
        )

        result = await get_system_status(mock_db, mock_user)

        assert len(result["events"]["by_type"]) == 20

    async def test_exception_handling(self, mock_db, mock_user):
        """Test that database exceptions are properly caught and reported."""
        mock_db.execute.side_effect = Exception("Database connection lost")

        with pytest.raises(Exception) as exc_info:
            await get_system_status(mock_db, mock_user)

        assert "Failed to retrieve system status" in str(exc_info.value)

    async def test_timestamp_isoformat_conversion(self, mock_db, mock_user, mock_execute_result):
        """Test that timestamps are converted to ISO format strings."""
        test_time = datetime(2024, 1, 15, 10, 30, 45)
        
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            investigations=[(uuid4(), "Test", "owner", test_time, 0, 0, 0, 0.0, 0, 0, 0, 0.0)],
            artifacts_list=[(1, "test.evtx", "1", test_time, 1024, "Test", b"hash")]
        )

        result = await get_system_status(mock_db, mock_user)

        # Check investigation timestamp
        inv_timestamp = result["investigations"]["detailed"][0]["created_at"]
        assert isinstance(inv_timestamp, str)
        assert inv_timestamp == test_time.isoformat()

        # Check artifact timestamp
        artifact_timestamp = result["artifacts"]["list"][0]["upload_ts"]
        assert isinstance(artifact_timestamp, str)
        assert artifact_timestamp == test_time.isoformat()

    async def test_embeddings_by_model_multiple_models(self, mock_db, mock_user, mock_execute_result):
        """Test embeddings grouped by multiple models."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            embeddings_total=10000,
            embeddings_by_model=[
                ("text-embedding-ada-002", 50000),  # Estimates (10x multiplier)
                ("nomic-embed-text", 30000),
                ("all-MiniLM-L6-v2", 20000),
            ]
        )

        result = await get_system_status(mock_db, mock_user)

        assert len(result["embeddings"]["by_model"]) == 3
        assert result["embeddings"]["by_model"][0]["model_name"] == "text-embedding-ada-002"
        assert result["embeddings"]["by_model"][0]["count"] == 50000  # Estimated

    async def test_embeddings_by_owner_type(self, mock_db, mock_user, mock_execute_result):
        """Test embeddings grouped by owner type."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            embeddings_total=10000,
            embeddings_by_owner=[
                ("tool", 80000),  # Estimates (10x multiplier)
                ("timeline", 15000),
                ("chat", 4000),
                ("note", 1000),
            ]
        )

        result = await get_system_status(mock_db, mock_user)

        assert len(result["embeddings"]["by_owner_type"]) == 4
        assert result["embeddings"]["by_owner_type"][0]["owner_type"] == "tool"
        assert result["embeddings"]["by_owner_type"][0]["count"] == 80000  # Estimated

    async def test_timeline_by_type_distribution(self, mock_db, mock_user, mock_execute_result):
        """Test timeline entries grouped by type."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            timeline_stats=(100, 70),
            timeline_by_type=[
                ("event", 700),  # Estimates (10x multiplier)
                ("finding", 200),
                ("observation", 80),
                ("note", 20),
            ]
        )

        result = await get_system_status(mock_db, mock_user)

        assert len(result["timeline"]["by_type"]) == 4
        assert result["timeline"]["by_type"][0]["entry_type"] == "event"
        assert result["timeline"]["by_type"][0]["count"] == 700  # Estimated

    async def test_artifacts_classification_names(self, mock_db, mock_user, mock_execute_result):
        """Test artifacts grouped by classification."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            artifacts_total=(500, 1000000),
            artifacts_classification=[
                ("0", 200),   # System Hive (estimated, 4x multiplier)
                ("1", 800),   # Log File
                ("2", 400),   # Binary
                ("3", 400),   # Archive
                ("4", 200),   # Unknown
            ]
        )

        result = await get_system_status(mock_db, mock_user)

        assert len(result["artifacts"]["by_classification"]) == 5
        # Verify all classification types are represented
        classifications = [item["classification"] for item in result["artifacts"]["by_classification"]]
        assert "0" in classifications
        assert "1" in classifications
        assert "2" in classifications
        assert "3" in classifications
        assert "4" in classifications

    async def test_artifacts_page_boundary_conditions(self, mock_db, mock_user, mock_execute_result):
        """Test artifacts pagination boundary conditions."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            artifacts_total=(100, 1000000),
            artifacts_search_count=100,
            artifacts_list=[
                (i, f"file{i}.evtx", "1", datetime.utcnow(), 1024, "Test", b"hash")
                for i in range(96, 101)
            ]
        )

        result = await get_system_status(
            db=mock_db,
            current_user=mock_user,
            artifacts_page=5,
            artifacts_page_size=20,
            artifacts_search="",
        )

        assert result["artifacts"]["page"] == 5
        assert result["artifacts"]["total_pages"] == 5
        assert result["artifacts"]["has_more"] is False  # Last page

    async def test_negative_page_number_handled(self, mock_db, mock_user, mock_execute_result):
        """Test that negative page numbers are normalized to 1."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            artifacts_total=(10, 1024),
            artifacts_search_count=10
        )

        result = await get_system_status(
            db=mock_db,
            current_user=mock_user,
            artifacts_page=-5,  # Negative page
            artifacts_page_size=20,
            artifacts_search="",
        )

        # Should be normalized to page 1
        assert result["artifacts"]["page"] == 1

    async def test_zero_page_size_handled(self, mock_db, mock_user, mock_execute_result):
        """Test that zero page size is normalized to 1."""
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            artifacts_total=(10, 1024),
            artifacts_search_count=10
        )

        result = await get_system_status(
            db=mock_db,
            current_user=mock_user,
            artifacts_page=1,
            artifacts_page_size=0,  # Zero page size
            artifacts_search="",
        )

        # Should be normalized to at least 1
        assert result["artifacts"]["page_size"] >= 1
        assert result["artifacts"]["page_size"] <= 50

    async def test_logs_username_on_success(self, mock_db, mock_user, mock_execute_result):
        """Test that successful retrieval logs the username."""
        mock_db.execute.side_effect = create_full_mock_sequence(mock_execute_result)

        with patch('app.routers.system.logger') as mock_logger:
            await get_system_status(mock_db, mock_user)
            
            # Verify logging
            mock_logger.info.assert_called()
            call_args = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("testuser" in arg for arg in call_args)

    async def test_events_by_investigation_sorted_by_count(self, mock_db, mock_user, mock_execute_result):
        """Test that events by investigation are sorted by count descending (derived from investigation stats)."""
        inv1 = uuid4()
        inv2 = uuid4()
        inv3 = uuid4()
        
        mock_db.execute.side_effect = create_full_mock_sequence(
            mock_execute_result,
            investigations=[
                (inv1, "High Volume Inv", "owner1", datetime.utcnow(), 5000, 4000, 1000, 80.0, 50, 40, 10, 80.0),
                (inv2, "Medium Volume Inv", "owner2", datetime.utcnow(), 2000, 1500, 500, 75.0, 20, 15, 5, 75.0),
                (inv3, "Low Volume Inv", "owner3", datetime.utcnow(), 100, 80, 20, 80.0, 5, 4, 1, 80.0),
            ],
            events_total=(7100, 5580),
        )

        result = await get_system_status(mock_db, mock_user)

        # Verify descending order (derived from investigation stats)
        assert result["events"]["by_investigation"][0]["event_count"] == 5000
        assert result["events"]["by_investigation"][1]["event_count"] == 2000
        assert result["events"]["by_investigation"][2]["event_count"] == 100
