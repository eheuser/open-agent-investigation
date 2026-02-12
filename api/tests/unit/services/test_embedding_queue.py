"""
Unit tests for embedding queue service.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import uuid

from app.services.embedding_queue import (
    queue_events_for_embedding,
    get_embedding_status,
    EMBEDDING_BATCH_SIZE,
)
from app.models.job_parsing import JobStatus


@pytest.mark.unit
class TestQueueEventsForEmbedding:
    """Test queue_events_for_embedding function."""

    @pytest.mark.asyncio
    async def test_queue_empty_events(self):
        """Test that queueing an empty list returns 0 jobs created."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        jobs_created = await queue_events_for_embedding(db, inv_id, 1, [])
        
        assert jobs_created == 0
        db.add.assert_not_called()
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_queue_single_batch(self):
        """Test queueing events that fit in a single batch."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Mock pending count query
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        db.execute.return_value = count_result
        
        # Queue 50 events (less than batch size)
        event_ids = list(range(1, 51))
        
        jobs_created = await queue_events_for_embedding(db, inv_id, 1, event_ids)
        
        assert jobs_created == 1
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_queue_multiple_batches(self):
        """Test queueing events that span multiple batches."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Mock pending count query (no backpressure)
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        db.execute.return_value = count_result
        
        # Queue 2500 events (2.5 batches at 1000 per batch)
        event_ids = list(range(1, 2501))
        
        jobs_created = await queue_events_for_embedding(db, inv_id, 1, event_ids)
        
        # Should create 3 jobs (1000, 1000, 500)
        assert jobs_created == 3
        assert db.add.call_count == 3
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_queue_adaptive_batching_moderate(self):
        """Test that moderate queue depth increases batch size."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Mock pending count query (moderate backpressure)
        count_result = MagicMock()
        count_result.scalar.return_value = 7  # Between 5 and 10
        db.execute.return_value = count_result
        
        # Queue 3000 events
        event_ids = list(range(1, 3001))
        
        jobs_created = await queue_events_for_embedding(db, inv_id, 1, event_ids)
        
        # With batch size of 1500 (1.5x normal), should create 2 jobs
        assert jobs_created == 2
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_queue_adaptive_batching_heavy(self):
        """Test that heavy queue depth uses largest batch size."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Mock pending count query (heavy backpressure)
        count_result = MagicMock()
        count_result.scalar.return_value = 15  # > 10
        db.execute.return_value = count_result
        
        # Queue 4000 events
        event_ids = list(range(1, 4001))
        
        jobs_created = await queue_events_for_embedding(db, inv_id, 1, event_ids)
        
        # With batch size of 2000 (2x normal), should create 2 jobs
        assert jobs_created == 2
        db.commit.assert_called_once()


@pytest.mark.unit
class TestGetEmbeddingStatus:
    """Test get_embedding_status function."""

    @pytest.mark.asyncio
    async def test_status_no_jobs(self):
        """Test status when no embedding jobs exist."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Mock empty result
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute.return_value = result_mock
        
        status = await get_embedding_status(db, inv_id)
        
        assert status["pending_jobs"] == 0
        assert status["running_jobs"] == 0
        assert status["completed_jobs"] == 0
        assert status["total_jobs"] == 0
        assert status["events_pending"] == 0
        assert status["events_completed"] == 0
        assert status["events_total"] == 0
        assert status["progress_percent"] == 100
        assert status["is_complete"] is True

    @pytest.mark.asyncio
    async def test_status_with_pending_jobs(self):
        """Test status with pending jobs."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Mock result with pending jobs
        result_mock = MagicMock()
        
        # Create mock row for pending jobs
        pending_row = MagicMock()
        pending_row.status = JobStatus.PENDING
        pending_row.job_count = 5
        pending_row.event_count = 500
        pending_row.events_processed = 0
        
        result_mock.all.return_value = [pending_row]
        db.execute.return_value = result_mock
        
        status = await get_embedding_status(db, inv_id)
        
        assert status["pending_jobs"] == 5
        assert status["running_jobs"] == 0
        assert status["completed_jobs"] == 0
        assert status["total_jobs"] == 5
        assert status["events_pending"] == 500
        assert status["events_completed"] == 0
        assert status["events_total"] == 500
        assert status["progress_percent"] == 0
        assert status["is_complete"] is False

    @pytest.mark.asyncio
    async def test_status_with_running_jobs(self):
        """Test status with running jobs."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Mock result with running jobs
        result_mock = MagicMock()
        
        running_row = MagicMock()
        running_row.status = JobStatus.RUNNING
        running_row.job_count = 2
        running_row.event_count = 200
        running_row.events_processed = 0
        
        result_mock.all.return_value = [running_row]
        db.execute = AsyncMock(return_value=result_mock)
        
        status = await get_embedding_status(db, inv_id)
        
        assert status["pending_jobs"] == 0
        assert status["running_jobs"] == 2
        assert status["completed_jobs"] == 0
        assert status["events_processing"] == 200  # All events in running jobs are being processed
        assert status["is_complete"] is False

    @pytest.mark.asyncio
    async def test_status_with_completed_jobs(self):
        """Test status with completed jobs."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Mock result with completed jobs
        result_mock = MagicMock()
        
        completed_row = MagicMock()
        completed_row.status = JobStatus.COMPLETED
        completed_row.job_count = 3
        completed_row.event_count = 300
        completed_row.events_processed = 300
        
        result_mock.all.return_value = [completed_row]
        db.execute.return_value = result_mock
        
        status = await get_embedding_status(db, inv_id)
        
        assert status["pending_jobs"] == 0
        assert status["running_jobs"] == 0
        assert status["completed_jobs"] == 3
        assert status["total_jobs"] == 3
        assert status["events_pending"] == 0
        assert status["events_completed"] == 300
        assert status["events_total"] == 300
        assert status["progress_percent"] == 100
        assert status["is_complete"] is True

    @pytest.mark.asyncio
    async def test_status_with_mixed_jobs(self):
        """Test status with pending, running, and completed jobs."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Mock result with mixed job statuses
        result_mock = MagicMock()
        
        pending_row = MagicMock()
        pending_row.status = JobStatus.PENDING
        pending_row.job_count = 2
        pending_row.event_count = 200
        pending_row.events_processed = 0
        
        running_row = MagicMock()
        running_row.status = JobStatus.RUNNING
        running_row.job_count = 1
        running_row.event_count = 100
        running_row.events_processed = 0
        
        completed_row = MagicMock()
        completed_row.status = JobStatus.COMPLETED
        completed_row.job_count = 3
        completed_row.event_count = 300
        completed_row.events_processed = 300
        
        result_mock.all.return_value = [pending_row, running_row, completed_row]
        db.execute = AsyncMock(return_value=result_mock)
        
        status = await get_embedding_status(db, inv_id)
        
        assert status["pending_jobs"] == 2
        assert status["running_jobs"] == 1
        assert status["completed_jobs"] == 3
        assert status["total_jobs"] == 6
        assert status["events_pending"] == 200  # Only pending jobs count as pending
        assert status["events_processing"] == 100  # Running jobs with unprocessed events
        assert status["events_completed"] == 300
        assert status["events_total"] == 600  # 200 + 100 + 300
        assert status["progress_percent"] == 50  # 300/600
        assert status["is_complete"] is False

    @pytest.mark.asyncio
    async def test_status_progress_calculation(self):
        """Test progress percentage calculation."""
        db = AsyncMock()
        inv_id = uuid.uuid4()
        
        # Mock result with partial completion
        result_mock = MagicMock()
        
        running_row = MagicMock()
        running_row.status = JobStatus.RUNNING
        running_row.job_count = 1
        running_row.event_count = 250
        running_row.events_processed = 0
        
        completed_row = MagicMock()
        completed_row.status = JobStatus.COMPLETED
        completed_row.job_count = 3
        completed_row.event_count = 750
        completed_row.events_processed = 750
        
        result_mock.all.return_value = [running_row, completed_row]
        db.execute.return_value = result_mock
        
        status = await get_embedding_status(db, inv_id)
        
        # 750 completed out of 1000 total = 75%
        assert status["progress_percent"] == 75
        assert status["is_complete"] is False


@pytest.mark.unit
class TestEmbeddingBatchSize:
    """Test batch size constant."""

    def test_batch_size_constant(self):
        """Test that EMBEDDING_BATCH_SIZE is set to expected value."""
        assert EMBEDDING_BATCH_SIZE == 1000
        assert isinstance(EMBEDDING_BATCH_SIZE, int)
        assert EMBEDDING_BATCH_SIZE > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
