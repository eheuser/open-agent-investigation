"""
Unit tests for embedding pool service.
"""
import pytest
from unittest.mock import AsyncMock, patch
import uuid

from app.services.embedding_pool import (
    add_events_to_pool,
    flush_embedding_pool,
    flush_investigation_pool,
    get_pool_statistics,
    start_pool_flusher,
    stop_pool_flusher,
    POOL_FLUSH_SIZE,
    POOL_FLUSH_TIMEOUT,
)
from app.models.job_embedding import EmbeddingJob
from app.models.job_parsing import JobStatus


@pytest.mark.unit
class TestAddEventsToPool:
    """Test add_events_to_pool function."""

    @pytest.mark.asyncio
    async def test_add_events_empty_list(self):
        """Test adding empty event list returns 0."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        jobs_created = await add_events_to_pool(db, inv_id, 1, [])
        
        assert jobs_created == 0

    @pytest.mark.asyncio
    async def test_add_events_below_threshold(self):
        """Test adding events below threshold pools them without creating jobs."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Add 100 events (below 2000 threshold)
        event_ids = list(range(1, 101))
        
        jobs_created = await add_events_to_pool(db, inv_id, 1, event_ids)
        
        # Should pool events but not create jobs yet
        assert jobs_created == 0

    @pytest.mark.asyncio
    async def test_add_events_exceeds_threshold(self):
        """Test adding events that exceed threshold does NOT auto-flush (disabled for determinism)."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Add 2500 events (exceeds old 2000 threshold, but auto-flush is disabled)
        event_ids = list(range(1, 2501))
        
        jobs_created = await add_events_to_pool(db, inv_id, 1, event_ids)
        
        # Auto-flush is disabled - should pool events without creating jobs
        assert jobs_created == 0
        db.add.assert_not_called()
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_events_cumulative_threshold(self):
        """Test that cumulative adds pool events (auto-flush disabled)."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # First add: 1000 events (below old threshold)
        jobs1 = await add_events_to_pool(db, inv_id, 1, list(range(1, 1001)))
        assert jobs1 == 0  # Pooled, not flushed
        
        # Second add: 1500 more events (cumulative 2500, exceeds old threshold)
        # But auto-flush is disabled, so should still pool
        jobs2 = await add_events_to_pool(db, inv_id, 1, list(range(1001, 2501)))
        assert jobs2 == 0  # Still pooled (auto-flush disabled)
        db.add.assert_not_called()
        db.commit.assert_not_called()


@pytest.mark.unit
class TestFlushEmbeddingPool:
    """Test flush_embedding_pool function."""

    @pytest.mark.asyncio
    async def test_flush_empty_pool(self):
        """Test flushing an empty pool returns 0."""
        db = AsyncMock()
        
        # Clear any pooled events from previous tests by flushing first
        await flush_embedding_pool(db)
        db.reset_mock()  # Reset mock call counts
        
        # Now flush again - should be empty and return 0
        jobs_created = await flush_embedding_pool(db)
        
        assert jobs_created == 0
        db.add.assert_not_called()  # No jobs should be created

    @pytest.mark.asyncio
    async def test_flush_with_pooled_events(self):
        """Test flushing pool with events creates jobs."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # First add events to pool (below threshold)
        await add_events_to_pool(db, inv_id, 1, list(range(1, 501)))
        
        # Now flush manually
        jobs_created = await flush_embedding_pool(db)
        
        # Should create 1 job with the pooled events
        assert jobs_created == 1


@pytest.mark.unit
class TestGetPoolStatistics:
    """Test get_pool_statistics function."""

    def test_get_pool_statistics_empty(self):
        """Test pool statistics when empty."""
        with patch('app.services.embedding_pool._embedding_pool') as mock_pool:
            mock_pool.get_pool_stats.return_value = {
                "pool_count": 0,
                "total_events": 0,
                "pools": [],
            }
            
            status = get_pool_statistics()
            
            assert status["pool_count"] == 0
            assert status["total_events"] == 0
            assert status["pools"] == []

    def test_get_pool_statistics_with_events(self):
        """Test pool statistics with pooled events."""
        inv_id = uuid.uuid4()
        
        with patch('app.services.embedding_pool._embedding_pool') as mock_pool:
            mock_pool.get_pool_stats.return_value = {
                "pool_count": 2,
                "total_events": 500,
                "pools": [
                    {"investigation_id": str(inv_id), "user_id": 1, "event_count": 300, "age_seconds": 10.5},
                    {"investigation_id": str(inv_id), "user_id": 2, "event_count": 200, "age_seconds": 5.2},
                ],
            }
            
            status = get_pool_statistics()
            
            assert status["pool_count"] == 2
            assert status["total_events"] == 500
            assert len(status["pools"]) == 2


@pytest.mark.unit
class TestPoolFlushSize:
    """Test pool flush size constant."""

    def test_pool_flush_size_value(self):
        """Test that POOL_FLUSH_SIZE is effectively disabled."""
        assert POOL_FLUSH_SIZE == 999999999  # Effectively disabled
        assert isinstance(POOL_FLUSH_SIZE, int)
        assert POOL_FLUSH_SIZE > 0


@pytest.mark.unit
class TestFlushInvestigationPool:
    """Test flush_investigation_pool function."""

    @pytest.mark.asyncio
    async def test_flush_investigation_pool_empty(self):
        """Test flushing investigation pool when empty."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Flush empty pool
        jobs_created = await flush_investigation_pool(db, inv_id)
        
        assert jobs_created == 0
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_investigation_pool_with_events(self):
        """Test flushing investigation pool with events."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Add events to pool for this investigation
        await add_events_to_pool(db, inv_id, 1, list(range(1, 501)))
        await add_events_to_pool(db, inv_id, 2, list(range(501, 1001)))
        
        # Flush this investigation's pool
        jobs_created = await flush_investigation_pool(db, inv_id)
        
        # Should create 2 jobs (one per user)
        assert jobs_created == 2
        assert db.add.call_count == 2
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_flush_investigation_pool_multiple_investigations(self):
        """Test that flushing one investigation doesn't affect others."""
        db = AsyncMock()
        inv_id_1 = uuid.uuid4()
        inv_id_2 = uuid.uuid4()
        
        # Add events for two investigations
        await add_events_to_pool(db, inv_id_1, 1, list(range(1, 101)))
        await add_events_to_pool(db, inv_id_2, 1, list(range(101, 201)))
        
        # Flush only first investigation
        jobs_created = await flush_investigation_pool(db, inv_id_1)
        
        # Should create 1 job
        assert jobs_created == 1
        
        # Second investigation should still have pooled events
        stats = get_pool_statistics()
        assert stats["pool_count"] == 1  # One pool remaining


@pytest.mark.unit
class TestPoolBatching:
    """Test pool batching behavior."""

    @pytest.mark.asyncio
    async def test_pool_batches_events_deterministically(self):
        """Test that pool creates deterministic batches."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Add 2500 events (should create 3 batches: 1000, 1000, 500)
        event_ids = list(range(1, 2501))
        await add_events_to_pool(db, inv_id, 1, event_ids)
        
        # Flush the pool
        jobs_created = await flush_investigation_pool(db, inv_id)
        
        # Should create 3 jobs (batches of 1000)
        assert jobs_created == 3
        assert db.add.call_count == 3

    @pytest.mark.asyncio
    async def test_pool_deduplicates_events(self):
        """Test that pool deduplicates event IDs."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Add same events multiple times
        await add_events_to_pool(db, inv_id, 1, [1, 2, 3])
        await add_events_to_pool(db, inv_id, 1, [2, 3, 4])  # Duplicates
        await add_events_to_pool(db, inv_id, 1, [3, 4, 5])  # More duplicates
        
        # Flush the pool
        jobs_created = await flush_investigation_pool(db, inv_id)
        
        # Should create 1 job
        assert jobs_created == 1
        
        # Get the created job
        job = db.add.call_args[0][0]
        assert isinstance(job, EmbeddingJob)
        
        # Should have unique event IDs: [1, 2, 3, 4, 5]
        assert len(job.event_ids) == 5
        assert set(job.event_ids) == {1, 2, 3, 4, 5}

    @pytest.mark.asyncio
    async def test_pool_sorts_events(self):
        """Test that pool sorts event IDs for deterministic batching."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Add events in random order
        await add_events_to_pool(db, inv_id, 1, [5, 3, 1, 4, 2])
        
        # Flush the pool
        jobs_created = await flush_investigation_pool(db, inv_id)
        
        assert jobs_created == 1
        
        # Get the created job
        job = db.add.call_args[0][0]
        
        # Event IDs should be sorted
        assert job.event_ids == [1, 2, 3, 4, 5]


@pytest.mark.unit
class TestPoolStatistics:
    """Test pool statistics functionality."""

    @pytest.mark.asyncio
    async def test_statistics_reflect_pooled_events(self):
        """Test that statistics accurately reflect pooled events."""
        # Clear any existing pools
        await flush_embedding_pool(AsyncMock())
        
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Add events
        await add_events_to_pool(db, inv_id, 1, list(range(1, 101)))  # 100 events
        await add_events_to_pool(db, inv_id, 2, list(range(101, 201)))  # 100 events
        
        # Get statistics
        stats = get_pool_statistics()
        
        assert stats["pool_count"] == 2  # Two pools (different users)
        assert stats["total_events"] == 200  # 100 + 100
        assert len(stats["pools"]) == 2

    @pytest.mark.asyncio
    async def test_statistics_include_pool_details(self):
        """Test that statistics include detailed pool information."""
        # Clear any existing pools
        await flush_embedding_pool(AsyncMock())
        
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Add events
        await add_events_to_pool(db, inv_id, 1, list(range(1, 51)))
        
        # Get statistics
        stats = get_pool_statistics()
        
        assert len(stats["pools"]) == 1
        pool_info = stats["pools"][0]
        
        assert pool_info["investigation_id"] == str(inv_id)
        assert pool_info["user_id"] == 1
        assert pool_info["event_count"] == 50
        assert "age_seconds" in pool_info
        assert pool_info["age_seconds"] >= 0


@pytest.mark.unit
class TestPoolConstants:
    """Test pool configuration constants."""

    def test_pool_flush_timeout(self):
        """Test POOL_FLUSH_TIMEOUT constant."""
        assert POOL_FLUSH_TIMEOUT == 999999  # Effectively disabled
        assert isinstance(POOL_FLUSH_TIMEOUT, int)
        assert POOL_FLUSH_TIMEOUT > 0


@pytest.mark.unit
class TestPoolEdgeCases:
    """Test edge cases for pool functionality."""

    @pytest.mark.asyncio
    async def test_add_events_multiple_users_same_investigation(self):
        """Test adding events for multiple users in same investigation."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Add events for different users
        await add_events_to_pool(db, inv_id, 1, [1, 2, 3])
        await add_events_to_pool(db, inv_id, 2, [4, 5, 6])
        await add_events_to_pool(db, inv_id, 3, [7, 8, 9])
        
        # Flush should create separate jobs per user
        jobs_created = await flush_investigation_pool(db, inv_id)
        
        assert jobs_created == 3  # One job per user

    @pytest.mark.asyncio
    async def test_flush_pool_with_commit_error(self):
        """Test that flush handles commit errors gracefully."""
        db = AsyncMock()
        db.commit = AsyncMock(side_effect=Exception("Database error"))
        db.rollback = AsyncMock()
        
        inv_id = uuid.uuid4()
        
        # Add events
        await add_events_to_pool(db, inv_id, 1, [1, 2, 3])
        
        # Flush should handle error
        jobs_created = await flush_investigation_pool(db, inv_id)
        
        # Should return 0 on error
        assert jobs_created == 0
        
        # Should call rollback
        db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_events_preserves_order_in_pool(self):
        """Test that adding events multiple times preserves all events."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Add events in multiple calls
        await add_events_to_pool(db, inv_id, 1, [1, 2])
        await add_events_to_pool(db, inv_id, 1, [3, 4])
        await add_events_to_pool(db, inv_id, 1, [5, 6])
        
        # Flush
        jobs_created = await flush_investigation_pool(db, inv_id)
        
        assert jobs_created == 1
        
        # Get the created job
        job = db.add.call_args[0][0]
        
        # Should have all 6 events in sorted order
        assert job.event_ids == [1, 2, 3, 4, 5, 6]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
