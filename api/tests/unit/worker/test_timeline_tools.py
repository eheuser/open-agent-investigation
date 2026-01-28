"""
Unit tests for worker timeline tools.
Tests batch embedding generation for timeline entries.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


@pytest.mark.unit
class TestBatchGenerateEmbeddings:
    """Test batch_generate_embeddings function."""

    async def test_batch_generate_embeddings_success(self):
        """
        Test successful batch generation of embeddings for timeline entries without embeddings.
        """
        from worker.tools.timeline_tools import batch_generate_embeddings

        db = AsyncMock()
        investigation_id = str(uuid4())
        user_id = 1

        # Mock query for entries without embeddings
        entries_result = MagicMock()
        entries_result.fetchall.return_value = [
            (1,),
            (2,),
            (3,),
        ]
        db.execute.return_value = entries_result

        # Mock the embedding service
        with patch(
            "worker.tools.timeline_tools.generate_embeddings_for_timeline_entries",
            return_value=3,
        ) as mock_generate:
            count = await batch_generate_embeddings(
                db=db,
                investigation_id=investigation_id,
                user_id=user_id,
            )

            assert count == 3
            # Verify the service was called with correct entry IDs
            mock_generate.assert_called_once_with(
                db=db,
                entry_ids=[1, 2, 3],
                user_id=user_id,
            )

    async def test_batch_generate_embeddings_no_entries(self):
        """
        Test that batch generation returns zero when no entries need embeddings.
        """
        from worker.tools.timeline_tools import batch_generate_embeddings

        db = AsyncMock()
        investigation_id = str(uuid4())
        user_id = 1

        # Mock empty query result
        empty_result = MagicMock()
        empty_result.fetchall.return_value = []
        db.execute.return_value = empty_result

        with patch(
            "worker.tools.timeline_tools.generate_embeddings_for_timeline_entries"
        ) as mock_generate:
            count = await batch_generate_embeddings(
                db=db,
                investigation_id=investigation_id,
                user_id=user_id,
            )

            assert count == 0
            # Service should not be called for empty list
            mock_generate.assert_not_called()

    async def test_batch_generate_embeddings_large_batch(self):
        """
        Test batch generation with many entries.
        """
        from worker.tools.timeline_tools import batch_generate_embeddings

        db = AsyncMock()
        investigation_id = str(uuid4())
        user_id = 1

        # Create 200 entries without embeddings
        entries = [(i,) for i in range(1, 201)]
        entries_result = MagicMock()
        entries_result.fetchall.return_value = entries
        db.execute.return_value = entries_result

        # Mock the embedding service
        with patch(
            "worker.tools.timeline_tools.generate_embeddings_for_timeline_entries",
            return_value=200,
        ) as mock_generate:
            count = await batch_generate_embeddings(
                db=db,
                investigation_id=investigation_id,
                user_id=user_id,
            )

            assert count == 200
            # Verify all entry IDs were passed
            call_args = mock_generate.call_args
            assert len(call_args.kwargs["entry_ids"]) == 200

    async def test_batch_generate_embeddings_handles_exception(self):
        """
        Test that batch generation handles exceptions gracefully.
        """
        from worker.tools.timeline_tools import batch_generate_embeddings

        db = AsyncMock()
        investigation_id = str(uuid4())
        user_id = 1

        # Mock query to return entries
        entries_result = MagicMock()
        entries_result.fetchall.return_value = [(1,), (2,)]
        db.execute.return_value = entries_result

        # Mock service to raise exception
        with patch(
            "worker.tools.timeline_tools.generate_embeddings_for_timeline_entries",
            side_effect=Exception("Embedding service error"),
        ):
            count = await batch_generate_embeddings(
                db=db,
                investigation_id=investigation_id,
                user_id=user_id,
            )

            # Should return 0 on error
            assert count == 0

    async def test_batch_generate_embeddings_filters_by_investigation(self):
        """
        Test that batch generation only processes entries for the specified investigation.
        """
        from worker.tools.timeline_tools import batch_generate_embeddings

        db = AsyncMock()
        investigation_id = str(uuid4())
        user_id = 1

        # Mock query result
        entries_result = MagicMock()
        entries_result.fetchall.return_value = [(10,), (20,), (30,)]
        db.execute.return_value = entries_result

        with patch(
            "worker.tools.timeline_tools.generate_embeddings_for_timeline_entries",
            return_value=3,
        ) as mock_generate:
            await batch_generate_embeddings(
                db=db,
                investigation_id=investigation_id,
                user_id=user_id,
            )

            # Verify the SQL query was executed (to filter by investigation)
            db.execute.assert_called_once()
            # Check that the SQL contains investigation_id filter
            sql_call = db.execute.call_args[0][0]
            assert "investigation_id" in str(sql_call).lower()
