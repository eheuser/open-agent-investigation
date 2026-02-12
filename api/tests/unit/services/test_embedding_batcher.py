"""
Unit tests for embedding batcher service.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
import uuid
import multiprocessing as mp
from datetime import datetime

from app.services.embedding_batcher import (
    queue_events_for_embedding,
    get_queue_size,
    initialize_event_queue,
    set_event_queue,
    start_embedding_batcher,
    stop_embedding_batcher,
)
from app.services import embedding_batcher

# Access constants from the module
BATCH_SIZE = 500
BATCH_TIMEOUT = 3.0


@pytest.mark.unit
class TestQueueEventsForEmbedding:
    """Test queue_events_for_embedding function."""

    def test_queue_events_success(self):
        """Test queueing events successfully."""
        # Create a real queue for testing
        manager = mp.Manager()
        test_queue = manager.Queue()
        
        # Initialize the module-level queue
        from app.services import embedding_batcher
        embedding_batcher._event_queue = test_queue
        
        investigation_id = uuid.uuid4()
        user_id = 1
        event_ids = [1, 2, 3, 4, 5]
        
        # Queue the events
        queue_events_for_embedding(investigation_id, user_id, event_ids)
        
        # Verify events were queued (one tuple per event)
        assert test_queue.qsize() == 5
        
        # Get the first queued item (tuple format: investigation_id, user_id, event_id)
        queued_item = test_queue.get(timeout=1)
        
        assert queued_item[0] == investigation_id
        assert queued_item[1] == user_id
        assert queued_item[2] == 1  # First event ID

    def test_queue_events_empty_list(self):
        """Test queueing an empty list of events."""
        manager = mp.Manager()
        test_queue = manager.Queue()
        
        from app.services import embedding_batcher
        embedding_batcher._event_queue = test_queue
        
        investigation_id = uuid.uuid4()
        user_id = 1
        event_ids = []
        
        # Queue empty list
        queue_events_for_embedding(investigation_id, user_id, event_ids)
        
        # Should not queue anything for empty list
        assert test_queue.empty()

    def test_queue_events_without_initialization(self):
        """Test queueing events when queue is not initialized."""
        from app.services import embedding_batcher
        embedding_batcher._event_queue = None
        
        investigation_id = uuid.uuid4()
        user_id = 1
        event_ids = [1, 2, 3]
        
        # Should log warning but not raise (graceful degradation)
        queue_events_for_embedding(investigation_id, user_id, event_ids)
        # No exception raised, function returns silently

    def test_queue_events_large_batch(self):
        """Test queueing a large batch of events."""
        manager = mp.Manager()
        test_queue = manager.Queue()
        
        from app.services import embedding_batcher
        embedding_batcher._event_queue = test_queue
        
        investigation_id = uuid.uuid4()
        user_id = 1
        event_ids = list(range(1, 10001))  # 10,000 events
        
        queue_events_for_embedding(investigation_id, user_id, event_ids)
        
        # Should queue 10,000 individual tuples
        assert test_queue.qsize() == 10000


@pytest.mark.unit
class TestGetQueueSize:
    """Test get_queue_size function."""

    def test_get_queue_size_empty(self):
        """Test getting queue size when empty."""
        manager = mp.Manager()
        test_queue = manager.Queue()
        
        from app.services import embedding_batcher
        embedding_batcher._event_queue = test_queue
        
        size = get_queue_size()
        assert size == 0

    def test_get_queue_size_with_items(self):
        """Test getting queue size with items."""
        manager = mp.Manager()
        test_queue = manager.Queue()
        
        from app.services import embedding_batcher
        embedding_batcher._event_queue = test_queue
        
        # Add some items
        test_queue.put({"test": 1})
        test_queue.put({"test": 2})
        test_queue.put({"test": 3})
        
        size = get_queue_size()
        assert size == 3

    def test_get_queue_size_without_initialization(self):
        """Test getting queue size when not initialized."""
        from app.services import embedding_batcher
        embedding_batcher._event_queue = None
        
        size = get_queue_size()
        assert size == 0  # Returns 0 when not initialized


@pytest.mark.unit
class TestQueueInitialization:
    """Test queue initialization functions."""

    def test_initialize_event_queue(self):
        """Test initializing the event queue."""
        queue = initialize_event_queue()
        
        assert queue is not None
        assert hasattr(queue, 'put')
        assert hasattr(queue, 'get')
        assert hasattr(queue, 'qsize')

    def test_set_event_queue(self):
        """Test setting the event queue."""
        manager = mp.Manager()
        test_queue = manager.Queue()
        
        set_event_queue(test_queue)
        
        from app.services import embedding_batcher
        assert embedding_batcher._event_queue is test_queue

    def test_set_event_queue_none(self):
        """Test setting event queue to None."""
        set_event_queue(None)
        
        from app.services import embedding_batcher
        assert embedding_batcher._event_queue is None


@pytest.mark.unit
class TestBatcherLifecycle:
    """Test batcher process lifecycle."""

    @patch('app.services.embedding_batcher.mp.Process')
    def test_start_embedding_batcher(self, mock_process_class):
        """Test starting the embedding batcher."""
        # Setup mock process
        mock_process = MagicMock()
        mock_process.is_alive.return_value = False
        mock_process_class.return_value = mock_process
        
        # Initialize the queue first
        from app.services import embedding_batcher
        manager = mp.Manager()
        test_queue = manager.Queue()
        embedding_batcher._event_queue = test_queue
        
        # Start batcher (no arguments - uses global queue)
        start_embedding_batcher()
        
        # Verify process was created and started
        mock_process_class.assert_called_once()
        call_kwargs = mock_process_class.call_args[1]
        assert call_kwargs['name'] == 'EmbeddingBatcher'
        assert call_kwargs['daemon'] is True
        assert 'target' in call_kwargs
        assert 'args' in call_kwargs
        
        mock_process.start.assert_called_once()

    def test_stop_embedding_batcher_not_running(self):
        """Test stopping batcher when not running."""
        from app.services import embedding_batcher
        embedding_batcher._batcher_process = None
        embedding_batcher._stop_event = None
        
        # Should not raise an error
        stop_embedding_batcher()

    @patch('app.services.embedding_batcher.logger')
    def test_stop_embedding_batcher_running(self, mock_logger):
        """Test stopping a running batcher."""
        from app.services import embedding_batcher
        
        # Create mock process and stop event
        mock_process = MagicMock()
        mock_process.is_alive.return_value = False  # Stops after first join
        mock_stop_event = MagicMock()
        
        embedding_batcher._batcher_process = mock_process
        embedding_batcher._stop_event = mock_stop_event
        
        # Stop the batcher
        stop_embedding_batcher()
        
        # Verify stop event was set
        mock_stop_event.set.assert_called_once()
        
        # Verify process was joined (with timeout)
        assert mock_process.join.called
        assert mock_process.join.call_args[1]['timeout'] == 10

    @patch('app.services.embedding_batcher.logger')
    def test_stop_embedding_batcher_timeout(self, mock_logger):
        """Test stopping batcher with timeout."""
        from app.services import embedding_batcher
        
        # Create mock process that doesn't stop
        mock_process = MagicMock()
        mock_process.is_alive.side_effect = [True, True, False]  # Still alive after first join, stops after terminate
        mock_stop_event = MagicMock()
        
        embedding_batcher._batcher_process = mock_process
        embedding_batcher._stop_event = mock_stop_event
        
        # Stop the batcher
        stop_embedding_batcher()
        
        # Verify terminate was called
        mock_process.terminate.assert_called_once()
        
        # Verify join was called multiple times
        assert mock_process.join.call_count >= 1


@pytest.mark.unit
class TestBatcherConstants:
    """Test batcher configuration constants."""

    def test_batcher_batch_size(self):
        """Test BATCH_SIZE constant."""
        assert embedding_batcher.BATCH_SIZE == 500
        assert isinstance(embedding_batcher.BATCH_SIZE, int)
        assert embedding_batcher.BATCH_SIZE > 0

    def test_batcher_timeout(self):
        """Test BATCH_TIMEOUT constant."""
        assert embedding_batcher.BATCH_TIMEOUT == 3.0
        assert isinstance(embedding_batcher.BATCH_TIMEOUT, float)
        assert embedding_batcher.BATCH_TIMEOUT > 0


@pytest.mark.unit
class TestBatcherIntegration:
    """Integration tests for batcher functionality."""

    def test_queue_and_retrieve(self):
        """Test queueing and retrieving events."""
        manager = mp.Manager()
        test_queue = manager.Queue()
        
        from app.services import embedding_batcher
        embedding_batcher._event_queue = test_queue
        
        # Queue multiple events
        inv_id_1 = uuid.uuid4()
        inv_id_2 = uuid.uuid4()
        
        queue_events_for_embedding(inv_id_1, 1, [1, 2, 3])
        queue_events_for_embedding(inv_id_2, 2, [4, 5, 6])
        queue_events_for_embedding(inv_id_1, 1, [7, 8, 9])  # Same investigation
        
        # Verify all events are queued (9 individual tuples)
        assert test_queue.qsize() == 9
        
        # Retrieve and verify first few events
        event1 = test_queue.get(timeout=1)
        assert event1[0] == inv_id_1  # investigation_id
        assert event1[1] == 1  # user_id
        assert event1[2] == 1  # event_id
        
        event2 = test_queue.get(timeout=1)
        assert event2[0] == inv_id_1
        assert event2[2] == 2  # Second event ID from first batch

    def test_queue_format(self):
        """Test that queued events have correct tuple format."""
        manager = mp.Manager()
        test_queue = manager.Queue()
        
        from app.services import embedding_batcher
        embedding_batcher._event_queue = test_queue
        
        inv_id = uuid.uuid4()
        queue_events_for_embedding(inv_id, 1, [1, 2, 3])
        
        # Get first event
        event = test_queue.get(timeout=1)
        
        # Should be a tuple of (investigation_id, user_id, event_id)
        assert isinstance(event, tuple)
        assert len(event) == 3
        assert isinstance(event[0], uuid.UUID)
        assert isinstance(event[1], int)
        assert isinstance(event[2], int)


@pytest.mark.unit
class TestBatcherEdgeCases:
    """Test edge cases and error handling."""

    def test_queue_events_with_duplicate_ids(self):
        """Test queueing events with duplicate IDs."""
        manager = mp.Manager()
        test_queue = manager.Queue()
        
        from app.services import embedding_batcher
        embedding_batcher._event_queue = test_queue
        
        investigation_id = uuid.uuid4()
        event_ids = [1, 2, 2, 3, 3, 3, 4]  # Duplicates
        
        queue_events_for_embedding(investigation_id, 1, event_ids)
        
        # Should queue all events (including duplicates)
        assert test_queue.qsize() == 7

    def test_queue_events_with_negative_user_id(self):
        """Test queueing events with invalid user ID."""
        manager = mp.Manager()
        test_queue = manager.Queue()
        
        from app.services import embedding_batcher
        embedding_batcher._event_queue = test_queue
        
        investigation_id = uuid.uuid4()
        
        # Should still queue (validation happens elsewhere)
        queue_events_for_embedding(investigation_id, -1, [1, 2, 3])
        
        event = test_queue.get(timeout=1)
        assert event[1] == -1  # user_id is second element

    def test_queue_size_concurrent_access(self):
        """Test queue size with concurrent access."""
        manager = mp.Manager()
        test_queue = manager.Queue()
        
        from app.services import embedding_batcher
        embedding_batcher._event_queue = test_queue
        
        # Add items
        for i in range(10):
            test_queue.put({"id": i})
        
        # Get size
        size1 = get_queue_size()
        
        # Remove some items
        test_queue.get()
        test_queue.get()
        
        size2 = get_queue_size()
        
        assert size1 == 10
        assert size2 == 8


@pytest.mark.unit  
class TestBatcherProcessFunction:
    """Test the batcher process function behavior."""

    @patch('app.utils.http_log_handler.setup_worker_logging')
    @patch('app.services.embedding_batcher.batch_loop_sync')
    def test_start_batcher_process_logging_setup(self, mock_batch_loop, mock_setup_logging):
        """Test that batcher process sets up logging."""
        from app.services.embedding_batcher import start_batcher_process
        
        manager = mp.Manager()
        test_queue = manager.Queue()
        test_stop_event = mp.Event()
        
        # Mock batch_loop_sync to return immediately
        mock_batch_loop.return_value = None
        
        # Call the process function
        start_batcher_process(test_queue, test_stop_event)
        
        # Verify logging was set up
        mock_setup_logging.assert_called_once()
        call_kwargs = mock_setup_logging.call_args[1]
        assert call_kwargs['process_name'] == 'EmbeddingBatcher'

    @patch('app.utils.http_log_handler.setup_worker_logging')
    @patch('app.services.embedding_batcher.batch_loop_sync')
    def test_start_batcher_process_sets_queue(self, mock_batch_loop, mock_setup_logging):
        """Test that batcher process sets the event queue."""
        from app.services.embedding_batcher import start_batcher_process
        from app.services import embedding_batcher
        
        manager = mp.Manager()
        test_queue = manager.Queue()
        test_stop_event = mp.Event()
        
        # Reset module state
        embedding_batcher._event_queue = None
        
        # Mock batch_loop_sync to check queue state
        def check_queue_set(stop_event):
            # Verify queue was set
            assert embedding_batcher._event_queue is test_queue
        
        mock_batch_loop.side_effect = check_queue_set
        
        # Call the process function
        start_batcher_process(test_queue, test_stop_event)
        
        # Verify batch loop was called
        mock_batch_loop.assert_called_once_with(test_stop_event)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
