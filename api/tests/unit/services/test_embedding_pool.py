"""
Unit tests for embedding pool service.
"""
import pytest
from unittest.mock import AsyncMock, patch
import uuid

from app.services.embedding_pool import (
    add_events_to_pool,
    flush_embedding_pool,
    get_pool_statistics,
    POOL_FLUSH_SIZE,
)


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
        """Test adding events that exceed threshold triggers flush."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Add 2500 events (exceeds 2000 threshold)
        event_ids = list(range(1, 2501))
        
        jobs_created = await add_events_to_pool(db, inv_id, 1, event_ids)
        
        # Should flush and create 1 job with all events
        assert jobs_created == 1
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_events_cumulative_threshold(self):
        """Test that cumulative adds trigger flush at threshold."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # First add: 1000 events (below threshold)
        jobs1 = await add_events_to_pool(db, inv_id, 1, list(range(1, 1001)))
        assert jobs1 == 0  # Pooled, not flushed
        
        # Second add: 1500 more events (cumulative 2500, exceeds threshold)
        jobs2 = await add_events_to_pool(db, inv_id, 1, list(range(1001, 2501)))
        assert jobs2 == 1  # Should trigger flush
        db.add.assert_called_once()
        db.commit.assert_called_once()


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
        """Test that POOL_FLUSH_SIZE is set correctly."""
        assert POOL_FLUSH_SIZE == 2000
        assert isinstance(POOL_FLUSH_SIZE, int)
        assert POOL_FLUSH_SIZE > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
