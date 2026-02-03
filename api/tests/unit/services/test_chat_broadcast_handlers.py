import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime

from app.services.chat_broadcast import (
    _handle_agent_thinking,
    _handle_llm_waiting,
    _handle_llm_chunk,
    _handle_agent_error,
    _handle_agent_cancelled,
    _handle_user_stopped,
    _handle_investigation_incomplete,
)


@pytest.mark.unit
class TestAgentThinkingHandler:
    """Test _handle_agent_thinking function."""

    async def test_adds_thinking_to_event_sequence(self):
        """
        Test that a thinking event is correctly appended to the message's metadata event_sequence and that the update operation is invoked with the expected changes. This test sets up mock database access, creates an agent job and an existing chat message, patches internal helpers to return the prepared message, invokes the `_handle_agent_thinking` handler, and asserts that `crud.update_message` was called with metadata containing a single "thinking" event whose content includes the provided thinking text.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()
        message_id = uuid4()

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=1)
        existing_msg = ChatMessage(
            message_id=message_id,
            investigation_id=investigation_id,
            role="assistant",
            content="Analysis...",
            message_metadata={"streaming_message_id": f"agent_{job_id}", "event_sequence": []},
        )

        message = {"content": "Found 10 suspicious events"}

        with patch("app.services.chat_broadcast._get_streaming_message", return_value=existing_msg):
            with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
                await _handle_agent_thinking(db, investigation_id, agent_job, message)

                # Verify message was updated
                assert mock_update.called
                update_args = mock_update.call_args
                metadata = update_args[1]["metadata"]
                assert len(metadata["event_sequence"]) == 1
                assert metadata["event_sequence"][0]["type"] == "thinking"
                assert "Found 10 suspicious events" in metadata["event_sequence"][0]["content"]

    async def test_skips_duplicate_content(self):
        """
        Test that duplicate thinking content is not added.

        This asynchronous unit test verifies that when an agent's thinking event contains content identical to the last chunk already stored in the chat history, the handler `_handle_agent_thinking` does not trigger an update to the message record.

        The test sets up mock database access and a pre-existing `ChatMessage` with specific metadata, patches the internal streaming lookup and the CRUD update function, invokes the handler, and asserts that no update call was made, confirming duplicate detection works as intended.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()
        message_id = uuid4()

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=1)
        existing_msg = ChatMessage(
            message_id=message_id,
            investigation_id=investigation_id,
            role="assistant",
            content="Analysis... Duplicate content",
            message_metadata={"streaming_message_id": f"agent_{job_id}", "event_sequence": []},
        )

        message = {"content": "Duplicate content"}

        with patch("app.services.chat_broadcast._get_streaming_message", return_value=existing_msg):
            with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
                await _handle_agent_thinking(db, investigation_id, agent_job, message)

                # Verify message was NOT updated (duplicate detected)
                assert not mock_update.called


@pytest.mark.unit
class TestLLMWaitingHandler:
    """Test _handle_llm_waiting function."""

    async def test_sets_waiting_flag(self):
        """
        Test that the `_handle_llm_waiting` coroutine sets the `isWaitingForLLM` flag to `True` in the message metadata.

        The test creates mock database and identifiers for an investigation, job, and message. It constructs an `AgentJob` instance and a `ChatMessage` representing an existing assistant message with `isWaitingForLLM` initially `False`.

        Using `patch` it mocks:

        * `app.services.chat_broadcast._get_streaming_message` to return the prepared `existing_msg`.
        * `app.services.chat_broadcast.crud.update_message` to capture calls made by the handler.

        The coroutine `_handle_llm_waiting` is invoked with the mock database, investigation ID, agent job, and an empty message payload. After execution, the test asserts that `update_message` was called and verifies that the metadata passed to it contains `isWaitingForLLM` set to `True`.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()
        message_id = uuid4()

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=1)
        existing_msg = ChatMessage(
            message_id=message_id,
            investigation_id=investigation_id,
            role="assistant",
            content="Analysis...",
            message_metadata={"streaming_message_id": f"agent_{job_id}", "isWaitingForLLM": False},
        )

        message = {}

        with patch("app.services.chat_broadcast._get_streaming_message", return_value=existing_msg):
            with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
                await _handle_llm_waiting(db, investigation_id, agent_job, message)

                # Verify waiting flag was set
                assert mock_update.called
                update_args = mock_update.call_args
                metadata = update_args[1]["metadata"]
                assert metadata["isWaitingForLLM"] is True


@pytest.mark.unit
class TestLLMChunkHandler:
    """Test _handle_llm_chunk function."""

    async def test_appends_chunk_and_clears_waiting(self):
        """
        Test that when an LLM chunk is processed the existing message content is appended with the new chunk and the waiting flag in the metadata is cleared. The test sets up mock database access, creates identifiers for investigation, job, and message, and constructs a stub `AgentJob` and a pre-existing `ChatMessage` marked as waiting for an LLM response. It patches the internal `_get_streaming_message` function to return the existing message and intercepts the `crud.update_message` call. After invoking `_handle_llm_chunk`, the test asserts that the update operation was called, that the new content includes both the original text and the appended chunk, and that the metadata field `isWaitingForLLM` is set to `False`.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()
        message_id = uuid4()

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=1)
        existing_msg = ChatMessage(
            message_id=message_id,
            investigation_id=investigation_id,
            role="assistant",
            content="Analysis...",
            message_metadata={"streaming_message_id": f"agent_{job_id}", "isWaitingForLLM": True},
        )

        message = {"content": " more text"}

        with patch("app.services.chat_broadcast._get_streaming_message", return_value=existing_msg):
            with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
                await _handle_llm_chunk(db, investigation_id, agent_job, message)

                # Verify chunk was appended and flag cleared
                assert mock_update.called
                update_args = mock_update.call_args
                assert "Analysis... more text" in update_args[1]["content"]
                metadata = update_args[1]["metadata"]
                assert metadata["isWaitingForLLM"] is False


@pytest.mark.unit
class TestAgentErrorHandler:
    """Test _handle_agent_error function."""

    async def test_marks_message_as_error(self):
        """
        Test that an agent error correctly updates the chat message metadata.

        This asynchronous test verifies that when `_handle_agent_error` is invoked:
        - The existing streaming message is retrieved.
        - The `isWaitingForLLM` flag in the message metadata is cleared.
        - An `agent_error` flag is set to `True`.
        - Any additional statistics provided in the error payload (e.g., `stats`) are stored in the metadata.

        The test uses mocked database access, a fabricated `AgentJob` instance, and patches for internal helper functions. It asserts that the CRUD update function is called with the expected modified metadata.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()
        message_id = uuid4()
        user_id = 1

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=user_id)
        existing_msg = ChatMessage(
            message_id=message_id,
            investigation_id=investigation_id,
            role="assistant",
            content="Analysis...",
            message_metadata={
                "streaming_message_id": f"agent_{job_id}",
                "event_sequence": [],
                "isWaitingForLLM": True,
            },
        )

        message = {"summary": "Error occurred during analysis", "stats": {"turns": 3}}

        with patch("app.services.chat_broadcast._get_streaming_message", return_value=existing_msg):
            with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
                await _handle_agent_error(db, investigation_id, user_id, agent_job, message)

                # Verify error flag was set
                assert mock_update.called
                update_args = mock_update.call_args
                metadata = update_args[1]["metadata"]
                assert metadata["isWaitingForLLM"] is False
                assert metadata["agent_error"] is True
                assert metadata["stats"] == {"turns": 3}


@pytest.mark.unit
class TestAgentCancelledHandler:
    """Test _handle_agent_cancelled function."""

    async def test_marks_message_as_cancelled(self):
        """
        Test that when an agent cancellation event is handled, the corresponding chat message metadata is updated to clear the waiting flag and set the cancelled flag. The test creates mock database and entities, patches internal helpers to return a predefined existing message, invokes the handler, and asserts that the update operation was called with metadata where `isWaitingForLLM` is False and `agent_cancelled` is True.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()
        message_id = uuid4()
        user_id = 1

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=user_id)
        existing_msg = ChatMessage(
            message_id=message_id,
            investigation_id=investigation_id,
            role="assistant",
            content="Analysis...",
            message_metadata={
                "streaming_message_id": f"agent_{job_id}",
                "event_sequence": [],
                "isWaitingForLLM": True,
            },
        )

        message = {"summary": "Investigation cancelled by user", "stats": {"turns": 2}}

        with patch("app.services.chat_broadcast._get_streaming_message", return_value=existing_msg):
            with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
                await _handle_agent_cancelled(db, investigation_id, user_id, agent_job, message)

                # Verify cancelled flag was set
                assert mock_update.called
                update_args = mock_update.call_args
                metadata = update_args[1]["metadata"]
                assert metadata["isWaitingForLLM"] is False
                assert metadata["agent_cancelled"] is True


@pytest.mark.unit
class TestUserStoppedHandler:
    """Test _handle_user_stopped function."""

    async def test_creates_stop_message(self):
        """
        Test that a stop message is created when a user stops the conversation.

        This asynchronous unit test verifies that `_handle_user_stopped`:
        - Retrieves the current streaming assistant message via `_get_streaming_message`.
        - Updates the existing message metadata appropriately.
        - Persists a new assistant message indicating the user-initiated stop.

        The test asserts that `persist_assistant_message` is called, and checks that:
        - The persisted content contains the phrase `stopped by user`.
        - The metadata includes `type` set to `user_stopped`.
        - The metadata correctly records the turn number from the incoming `message` payload.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()
        message_id = uuid4()
        user_id = 1

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=user_id)
        existing_msg = ChatMessage(
            message_id=message_id,
            investigation_id=investigation_id,
            role="assistant",
            content="Analysis...",
            message_metadata={"streaming_message_id": f"agent_{job_id}", "isWaitingForLLM": True},
        )

        message = {"turn": 3}

        with patch("app.services.chat_broadcast._get_streaming_message", return_value=existing_msg):
            with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
                with patch("app.services.chat_broadcast.persist_assistant_message") as mock_persist:
                    await _handle_user_stopped(db, investigation_id, user_id, agent_job, message)

                    # Verify stop message was created
                    assert mock_persist.called
                    persist_args = mock_persist.call_args
                    assert "stopped by user" in persist_args[1]["content"]
                    assert persist_args[1]["metadata"]["type"] == "user_stopped"
                    assert persist_args[1]["metadata"]["turn"] == 3


@pytest.mark.unit
class TestInvestigationIncompleteHandler:
    """Test _handle_investigation_incomplete function."""

    async def test_marks_investigation_incomplete_with_choices(self):
        """
        Test that an incomplete investigation message is correctly updated with metadata flags and choice options.

        This test verifies that when `_handle_investigation_incomplete` processes a message indicating an unfinished investigation, it:
        - Retrieves the existing streaming message.
        - Calls `crud.update_message` to modify the stored message.
        - Sets `isWaitingForLLM` to `False`.
        - Adds the flag `investigation_incomplete` set to `True`.
        - Marks `can_continue` as `False`.
        - Stores the provided list of investigation choices under `investigation_choices`.
        - Appends a single entry to the `event_sequence` list.

        The test uses mocked database and service components, constructs sample identifiers and payload data, patches internal helpers, invokes the handler, and asserts that the update call contains the expected metadata changes.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()
        message_id = uuid4()
        user_id = 1

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=user_id)
        existing_msg = ChatMessage(
            message_id=message_id,
            investigation_id=investigation_id,
            role="assistant",
            content="Analysis...",
            message_metadata={
                "streaming_message_id": f"agent_{job_id}",
                "event_sequence": [],
                "isWaitingForLLM": True,
            },
        )

        choices = [
            {"id": 1, "title": "Continue analysis", "description": "Keep investigating"},
            {"id": 2, "title": "Generate report", "description": "Summarize findings"},
        ]

        message = {
            "summary": "Investigation incomplete - more to analyze",
            "stats": {"turns": 10},
            "choices": choices,
        }

        with patch("app.services.chat_broadcast._get_streaming_message", return_value=existing_msg):
            with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
                await _handle_investigation_incomplete(
                    db, investigation_id, user_id, agent_job, message
                )

                # Verify incomplete flag and choices were set
                assert mock_update.called
                update_args = mock_update.call_args
                metadata = update_args[1]["metadata"]
                assert metadata["isWaitingForLLM"] is False
                assert metadata["investigation_incomplete"] is True
                assert metadata["can_continue"] is False
                assert metadata["investigation_choices"] == choices
                assert len(metadata["event_sequence"]) == 1  # Summary added
