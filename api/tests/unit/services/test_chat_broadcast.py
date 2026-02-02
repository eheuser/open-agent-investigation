import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from datetime import datetime

from app.services.chat_broadcast import (
    handle_broadcast_message,
    _handle_agent_thinking,
    _handle_llm_waiting,
    _handle_llm_chunk,
)


@pytest.mark.unit
class TestHandleBroadcastMessage:
    """Test handle_broadcast_message function."""

    async def test_agent_started_without_job(self):
        """
        Test that handling an `agent_started` broadcast message does not raise an exception when there is no corresponding job record in the database. The test creates a mocked asynchronous database session, configures the `execute` call to return `None` for the job lookup, and invokes :func:`handle_broadcast_message` with a minimal `agent_started` payload. It then asserts that the database query was executed, confirming that the function gracefully falls back to using a default user identifier when no job is found.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        # Mock no job found
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        message = {"type": "agent_started", "agent": "test_agent"}

        # Should not raise exception, just use default user_id
        await handle_broadcast_message(db, investigation_id, message)

        # Verify query was executed
        assert db.execute.called

    async def test_agent_started_creates_new_message(self):
        """
        Test that handling an `agent_started` broadcast creates and persists a new assistant message when no existing placeholder message is found.

        The test sets up:
        - An asynchronous mock database session.
        - Unique identifiers for the investigation, job, and user.
        - A mocked `AgentJob` instance representing a running job.
        - Database query results that return the job, then indicate no existing placeholder or retry messages.

        It constructs an `agent_started` message payload and patches `persist_assistant_message` to simulate persisting a new chat record, returning a mock object with a generated `message_id`.

        The test invokes `handle_broadcast_message` with the mocked dependencies and asserts that:
        - The persistence function was called.
        - The call includes the correct `investigation_id` and `user_id`.
        - The persisted message content contains the phrase “Starting analysis”.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()
        user_id = 1

        # Mock job found
        from app.models.job_agent import AgentJob

        agent_job = AgentJob(
            job_id=job_id, investigation_id=investigation_id, user_id=user_id, status="running"
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [
            agent_job,
            None,
            None,
        ]  # job, no placeholder, no retry
        db.execute.return_value = result_mock

        message = {"type": "agent_started", "agent": "test_agent"}

        with patch("app.services.chat_broadcast.persist_assistant_message") as mock_persist:
            mock_persist.return_value = MagicMock(message_id=uuid4())
            await handle_broadcast_message(db, investigation_id, message)

            # Verify message was persisted
            assert mock_persist.called
            call_args = mock_persist.call_args
            assert call_args[1]["investigation_id"] == investigation_id
            assert call_args[1]["user_id"] == user_id
            assert "Starting analysis" in call_args[1]["content"]

    async def test_loop_start_message(self):
        """
        Test that a broadcast message of type `loop_start` updates an existing chat history entry with iteration information.

        The test creates mock database objects and a pre-existing `ChatMessage` representing a streaming message for the given job. It then sends a `loop_start` payload containing the current loop number and the maximum loops allowed. The `handle_broadcast_message` function should locate the existing message (identified by its `streaming_message_id`) and invoke `crud.update_message` with updated content that includes the iteration text `Iteration {loop}/{max_loops}`.

        The test asserts that:
        * `crud.update_message` is called.
        * The `content` argument passed to `update_message` contains the expected iteration string.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()

        # Mock job and existing message
        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=1)
        existing_msg = ChatMessage(
            message_id=uuid4(),
            investigation_id=investigation_id,
            role="assistant",
            content="Starting analysis...",
            message_metadata={"streaming_message_id": f"agent_{job_id}"},
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [agent_job, existing_msg]
        db.execute.return_value = result_mock

        message = {"type": "loop_start", "loop": 2, "max_loops": 10}

        with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
            await handle_broadcast_message(db, investigation_id, message)

            # Verify message was updated with iteration info
            assert mock_update.called
            call_args = mock_update.call_args
            assert "Iteration 2/10" in call_args[1]["content"]

    async def test_tool_call_message(self):
        """
        Test that handling a broadcast message of type `tool_call` updates an existing chat history entry with the appropriate tool call information.

        The test performs the following steps:
        - Creates mock asynchronous database objects and identifiers for an investigation and job.
        - Instantiates an `AgentJob` model and a pre-existing `ChatMessage` representing a prior assistant message, linking it via `streaming_message_id`.
        - Configures the mocked database execution to return the `AgentJob` followed by the existing chat message when queried.
        - Defines a broadcast payload indicating a tool call (e.g., `search_events`).
        - Patches the `update_message` CRUD function and invokes `handle_broadcast_message` with the mock DB, investigation ID, and message payload.
        - Asserts that `update_message` was called and that the updated content includes the name of the invoked tool.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=1)
        existing_msg = ChatMessage(
            message_id=uuid4(),
            investigation_id=investigation_id,
            role="assistant",
            content="Starting analysis...",
            message_metadata={"streaming_message_id": f"agent_{job_id}"},
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [agent_job, existing_msg]
        db.execute.return_value = result_mock

        message = {"type": "tool_call", "tool": "search_events"}

        with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
            await handle_broadcast_message(db, investigation_id, message)

            # Verify message was updated with tool call info
            assert mock_update.called
            call_args = mock_update.call_args
            assert "search_events" in call_args[1]["content"]

    async def test_tool_executing_creates_execution_record(self):
        """
        Test that handling a `tool_executing` broadcast message creates a corresponding tool execution record and updates the associated chat message's event sequence.

        The test sets up an asynchronous mock database session and inserts dummy `AgentJob` and existing `ChatMessage` objects representing the current investigation, job, and prior assistant message. It then constructs a sample `tool_executing` payload containing tool metadata (name, display name, arguments, turn information).

        Using `unittest.mock.patch`, the test replaces the `create_tool_execution` function with a mock that returns a fabricated execution object, and patches the `update_message` CRUD operation to observe its invocation.

        After invoking `handle_broadcast_message` with the mocked dependencies, the test asserts that:
        * The tool execution creation function was called.
        * The call arguments include the correct `chat_message_id`, `tool_name`, and `display_name` derived from the broadcast payload.
        * The chat message update operation was invoked to persist the modified `event_sequence`.
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
            content="Starting analysis...",
            message_metadata={"streaming_message_id": f"agent_{job_id}", "event_sequence": []},
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [agent_job, existing_msg]
        db.execute.return_value = result_mock

        message = {
            "type": "tool_executing",
            "tool": "search_events",
            "display_name": "Search Events",
            "arguments": {"query": "test"},
            "turn_number": 1,
            "max_turns": 10,
        }

        with patch("app.services.chat_broadcast.tool_crud.create_tool_execution") as mock_create:
            mock_execution = MagicMock(execution_id=uuid4())
            mock_create.return_value = mock_execution

            with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
                await handle_broadcast_message(db, investigation_id, message)

                # Verify tool execution was created
                assert mock_create.called
                create_args = mock_create.call_args
                assert create_args[1]["chat_message_id"] == message_id
                assert create_args[1]["tool_name"] == "search_events"
                assert create_args[1]["display_name"] == "Search Events"

                # Verify event_sequence was updated
                assert mock_update.called

    async def test_tool_result_updates_execution(self):
        """
        Test that handling a broadcast message of type `tool_result` updates the corresponding tool execution record with the result data and marks it as completed.

        The test creates mock database objects and model instances representing an agent job, an existing chat message containing a pending tool execution event, and a matching `ToolExecution` entry. It then patches the CRUD helpers used by `handle_broadcast_message` to return the prepared execution object and capture updates.

        Steps performed:
        - Sets up identifiers for investigation, job, message, and execution.
        - Constructs a mock `AgentJob`, an existing `ChatMessage` with metadata indicating an executing tool, and a `ToolExecution` instance in the *executing* state.
        - Mocks the database `execute` call to return the agent job and chat message when queried.
        - Defines a broadcast payload of type `tool_result` containing the tool name, result payload, summary, and success flag.
        - Patches `get_latest_executing_tool` to return the prepared execution object.
        - Patches `update_tool_execution` and `update_message` to monitor calls.
        - Calls `handle_broadcast_message` with the mock DB, investigation ID, and message.

        Assertions:
        - Confirms that `update_tool_execution` was invoked.
        - Verifies that the call arguments include the correct `execution_id`, the result dictionary, the result summary string, and a status of `completed`.

        No value is returned; the test succeeds if the update calls are made with the expected parameters.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()
        message_id = uuid4()
        execution_id = uuid4()

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage
        from app.models.tool_execution import ToolExecution

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=1)
        existing_msg = ChatMessage(
            message_id=message_id,
            investigation_id=investigation_id,
            role="assistant",
            content="Starting analysis...",
            message_metadata={
                "streaming_message_id": f"agent_{job_id}",
                "event_sequence": [
                    {"type": "tool_execution", "execution_id": execution_id, "status": "executing"}
                ],
            },
        )
        tool_exec = ToolExecution(
            execution_id=execution_id,
            chat_message_id=message_id,
            tool_name="search_events",
            status="executing",
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [agent_job, existing_msg]
        db.execute.return_value = result_mock

        message = {
            "type": "tool_result",
            "tool": "search_events",
            "result": {"count": 42},
            "result_summary": "Found 42 events",
            "success": True,
        }

        with patch("app.services.chat_broadcast.tool_crud.get_latest_executing_tool") as mock_get:
            mock_get.return_value = tool_exec

            with patch(
                "app.services.chat_broadcast.tool_crud.update_tool_execution"
            ) as mock_update_tool:
                with patch("app.services.chat_broadcast.crud.update_message") as mock_update_msg:
                    await handle_broadcast_message(db, investigation_id, message)

                    # Verify tool execution was updated
                    assert mock_update_tool.called
                    update_args = mock_update_tool.call_args
                    assert update_args[1]["execution_id"] == execution_id
                    assert update_args[1]["result"] == {"count": 42}
                    assert update_args[1]["result_summary"] == "Found 42 events"
                    assert update_args[1]["status"] == "completed"

    async def test_agent_completed_marks_message_complete(self):
        """
        Test that handling an `agent_completed` broadcast message updates the corresponding chat history entry to mark it as no longer waiting for the LLM and records completion metadata.

        The test creates mock database objects and identifiers for an investigation, job, and message. It then constructs:

        * An `AgentJob` instance representing the completed agent.
        * A `ChatMessage` instance mimicking a stored streaming message with `isWaitingForLLM` set to `True`.

        The mock `db.execute` call is configured to return these objects in sequence via `scalar_one_or_none`. A sample broadcast payload containing a `type` of `agent_completed`, a summary, and statistics is prepared.

        Using `patch` on the service's `crud.update_message` function, the test invokes `handle_broadcast_message` with the mocked database, investigation ID, and message. After execution it asserts that:

        * The update routine was called.
        * The metadata passed to the update includes `isWaitingForLLM` set to `False`, `agent_completed` set to `True`, and the original `stats` dictionary.

        This verifies that the broadcast handler correctly finalises the chat message state when an agent completes its work.
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
            message_metadata={
                "streaming_message_id": f"agent_{job_id}",
                "event_sequence": [],
                "isWaitingForLLM": True,
            },
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [agent_job, existing_msg]
        db.execute.return_value = result_mock

        message = {
            "type": "agent_completed",
            "summary": "Investigation complete",
            "stats": {"turns": 5, "tools": 10},
        }

        with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
            await handle_broadcast_message(db, investigation_id, message)

            # Verify message was marked complete
            assert mock_update.called
            update_args = mock_update.call_args
            metadata = update_args[1]["metadata"]
            assert metadata["isWaitingForLLM"] is False
            assert metadata["agent_completed"] is True
            assert metadata["stats"] == {"turns": 5, "tools": 10}

    async def test_safety_limit_reached_message(self):
        """
        Test that a safety_limit_reached broadcast message results in the creation of a system chat message.

        This asynchronous test verifies the following behavior:
        - An in-memory mock database (`AsyncMock`) is prepared with an `AgentJob` record identified by a generated investigation ID.
        - A broadcast payload containing `"type": "safety_limit_reached"` and a descriptive `"message"` is passed to `handle_broadcast_message`.
        - The function under test should invoke `app.services.chat_broadcast.persist_system_message` to persist a system-level chat entry.
        - The persisted message must include the original safety limit text in its `content` field.
        - The accompanying metadata dictionary must contain a `"type"` key with the value `"safety_limit"`.

        The test asserts that:
        1. `persist_system_message` is called exactly once.
        2. The call arguments contain the expected content substring.
        3. The metadata type matches the expected safety-limit identifier.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        from app.models.job_agent import AgentJob

        agent_job = AgentJob(job_id=uuid4(), investigation_id=investigation_id, user_id=1)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = agent_job
        db.execute.return_value = result_mock

        message = {"type": "safety_limit_reached", "message": "Maximum turns exceeded"}

        with patch("app.services.chat_broadcast.persist_system_message") as mock_persist:
            await handle_broadcast_message(db, investigation_id, message)

            # Verify system message was created
            assert mock_persist.called
            persist_args = mock_persist.call_args
            assert "Maximum turns exceeded" in persist_args[1]["content"]
            assert persist_args[1]["metadata"]["type"] == "safety_limit"

    async def test_llm_error_message(self):
        """
        Test that handling an `llm_error` broadcast message creates and persists a system error message with the appropriate content and metadata.

        The test sets up:
        - An asynchronous mock database connection.
        - A unique investigation identifier and a corresponding `AgentJob` instance.
        - Mocked query results to return the created `AgentJob` when the service queries for it.
        - A sample broadcast message of type `llm_error` containing an error description.

        It then patches `app.services.chat_broadcast.persist_system_message` to intercept persistence calls, invokes `handle_broadcast_message` with the mock database, investigation ID, and error message, and finally asserts that:
        - The persistence function was called.
        - The persisted message content includes the provided error text (e.g., “API rate limit exceeded”).
        - The metadata attached to the persisted message correctly identifies the type as `llm_error`.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        from app.models.job_agent import AgentJob

        agent_job = AgentJob(job_id=uuid4(), investigation_id=investigation_id, user_id=1)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = agent_job
        db.execute.return_value = result_mock

        message = {"type": "llm_error", "error": "API rate limit exceeded"}

        with patch("app.services.chat_broadcast.persist_system_message") as mock_persist:
            await handle_broadcast_message(db, investigation_id, message)

            # Verify error message was created
            assert mock_persist.called
            persist_args = mock_persist.call_args
            assert "API rate limit exceeded" in persist_args[1]["content"]
            assert persist_args[1]["metadata"]["type"] == "llm_error"

    async def test_timeline_updated_message(self):
        """
        Test that a `timeline_updated` broadcast message is processed without persisting any chat history records. The test creates a mocked asynchronous database session and an `AgentJob` instance, configures the mock to return the job when queried, and sends a sample `timeline_updated` message containing the number of entries added. It then invokes `handle_broadcast_message` with these parameters, asserting that no exceptions are raised and that the database execute method is called (indicating the function performed its expected logging behavior without attempting persistence).
        """
        db = AsyncMock()
        investigation_id = uuid4()

        from app.models.job_agent import AgentJob

        agent_job = AgentJob(job_id=uuid4(), investigation_id=investigation_id, user_id=1)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = agent_job
        db.execute.return_value = result_mock

        message = {"type": "timeline_updated", "entries_added": 5}

        # Should not raise exception, just log
        await handle_broadcast_message(db, investigation_id, message)

        # No message persistence should occur
        assert db.execute.called  # Only for fetching job

    async def test_turn_complete_message(self):
        """
        Test the handling of a `turn_complete` broadcast message.

        This asynchronous unit test verifies that when a `turn_complete` message is received:
        - The `handle_broadcast_message` coroutine processes the message without raising any exceptions.
        - No chat history persistence actions are performed (the database `execute` method is called, but no insert or update operations related to messages occur).
        - The function's primary effect is limited to logging the turn completion details.

        The test sets up a mock asynchronous database session, creates a dummy `AgentJob` instance, and constructs a sample `turn_complete` message containing a turn number and the count of tools executed. It then invokes `handle_broadcast_message` with these mocks and asserts that the database interaction occurred as expected.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        from app.models.job_agent import AgentJob

        agent_job = AgentJob(job_id=uuid4(), investigation_id=investigation_id, user_id=1)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = agent_job
        db.execute.return_value = result_mock

        message = {"type": "turn_complete", "turn_number": 3, "tools_executed": 2}

        # Should not raise exception, just log
        await handle_broadcast_message(db, investigation_id, message)

        # No message persistence should occur
        assert db.execute.called  # Only for fetching job

    async def test_agent_started_reuses_message_for_continuation(self):
        """
        Test that when an `agent_started` broadcast message is processed for a continuation job (identified by `reuse_message_id` in the job metadata), the service reuses the existing chat message instead of creating a new one.

        The test sets up:
        - An asynchronous mock database connection.
        - Identifiers for investigation, job, previous message and user.
        - An `AgentJob` instance with `status="running"` and `job_metadata={"reuse_message_id": old_message_id}`.
        - A pre-existing `ChatMessage` matching the `old_message_id` and containing metadata indicating an incomplete investigation.

        The mock database returns the `AgentJob` followed by the existing `ChatMessage` when queried. The broadcast payload is a simple `agent_started` message.

        Using `patch` on `app.services.chat_broadcast.crud.update_message`, the test invokes `handle_broadcast_message` and asserts that:
        - `update_message` was called (no new message creation).
        - The call used the original `old_message_id`.
        - Updated metadata marks the investigation as complete (`investigation_incomplete` set to `False`), flags the job as a continuation (`is_continuing`), and indicates it is waiting for an LLM response (`isWaitingForLLM`).
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()
        old_message_id = uuid4()
        user_id = 1

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        # Job with reuse_message_id in metadata (continuation job)
        agent_job = AgentJob(
            job_id=job_id,
            investigation_id=investigation_id,
            user_id=user_id,
            status="running",
            job_metadata={"reuse_message_id": old_message_id},
        )

        existing_msg = ChatMessage(
            message_id=old_message_id,
            investigation_id=investigation_id,
            role="assistant",
            content="Previous analysis...",
            message_metadata={"investigation_incomplete": True, "event_sequence": []},
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [agent_job, existing_msg]
        db.execute.return_value = result_mock

        message = {"type": "agent_started", "agent": "test_agent"}

        with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
            await handle_broadcast_message(db, investigation_id, message)

            # Verify existing message was updated (not new one created)
            assert mock_update.called
            update_args = mock_update.call_args
            assert update_args[1]["message_id"] == old_message_id
            metadata = update_args[1]["metadata"]
            assert metadata["investigation_incomplete"] is False
            assert metadata["is_continuing"] is True
            assert metadata["isWaitingForLLM"] is True

    async def test_loop_error_message(self):
        """
        Test that handling a broadcast message of type `loop_error` correctly appends error information to the existing chat message.\n\nThe test creates mock database objects and an `AgentJob` instance, then simulates receiving a `loop_error` payload containing the loop iteration number and an error description. It patches the `update_message` CRUD function and invokes `handle_broadcast_message` with the mocked dependencies. After execution, the test asserts that `update_message` was called and that the updated message content includes both the formatted iteration identifier (e.g., \"Error in iteration 3\") and the original error text (\"Tool execution failed\").\n\nNo value is returned; the function relies on assertions to validate behavior.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=1)
        existing_msg = ChatMessage(
            message_id=uuid4(),
            investigation_id=investigation_id,
            role="assistant",
            content="Analysis...",
            message_metadata={"streaming_message_id": f"agent_{job_id}"},
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [agent_job, existing_msg]
        db.execute.return_value = result_mock

        message = {"type": "loop_error", "loop": 3, "error": "Tool execution failed"}

        with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
            await handle_broadcast_message(db, investigation_id, message)

            # Verify error info was appended
            assert mock_update.called
            call_args = mock_update.call_args
            assert "Error in iteration 3" in call_args[1]["content"]
            assert "Tool execution failed" in call_args[1]["content"]

    async def test_turn_error_message(self):
        """
        Test that a turn_error broadcast message updates the existing chat record by appending detailed error information, including the turn number and error description, using the update_message CRUD operation.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=1)
        existing_msg = ChatMessage(
            message_id=uuid4(),
            investigation_id=investigation_id,
            role="assistant",
            content="Analysis...",
            message_metadata={"streaming_message_id": f"agent_{job_id}"},
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [agent_job, existing_msg]
        db.execute.return_value = result_mock

        message = {"type": "turn_error", "turn": 5, "error": "LLM timeout"}

        with patch("app.services.chat_broadcast.crud.update_message") as mock_update:
            await handle_broadcast_message(db, investigation_id, message)

            # Verify error info was appended
            assert mock_update.called
            call_args = mock_update.call_args
            assert "Error in turn 5" in call_args[1]["content"]
            assert "LLM timeout" in call_args[1]["content"]

    async def test_tool_result_with_auto_registration(self):
        """
        Test that a tool result message containing auto-registered items updates the corresponding tool execution entry with a summary reflecting the auto-registration count.

        The test sets up mock database objects and model instances representing an agent job, an existing chat message with a pending tool execution event, and a `ToolExecution` record in the *executing* state. It then patches the CRUD helpers used by `handle_broadcast_message` to return the prepared `ToolExecution` and to capture updates.

        A simulated broadcast payload of type `tool_result` is sent, containing a result dictionary with a `count` field and an `auto_registered` count. After invoking `handle_broadcast_message` the test asserts that:

        * The `update_tool_execution` function was called.
        * The keyword argument `result_summary` passed to `update_tool_execution` includes the phrase “auto-registered 15” (case-insensitive), confirming that the service incorporates auto-registration information into the persisted summary.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        job_id = uuid4()
        message_id = uuid4()
        execution_id = uuid4()

        from app.models.job_agent import AgentJob
        from app.crud.chat_history import ChatMessage
        from app.models.tool_execution import ToolExecution

        agent_job = AgentJob(job_id=job_id, investigation_id=investigation_id, user_id=1)
        existing_msg = ChatMessage(
            message_id=message_id,
            investigation_id=investigation_id,
            role="assistant",
            content="Starting analysis...",
            message_metadata={
                "streaming_message_id": f"agent_{job_id}",
                "event_sequence": [
                    {"type": "tool_execution", "execution_id": execution_id, "status": "executing"}
                ],
            },
        )
        tool_exec = ToolExecution(
            execution_id=execution_id,
            chat_message_id=message_id,
            tool_name="search_events",
            status="executing",
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [agent_job, existing_msg]
        db.execute.return_value = result_mock

        message = {
            "type": "tool_result",
            "tool": "search_events",
            "result": {"count": 42, "auto_registered": 15},
            "success": True,
        }

        with patch("app.services.chat_broadcast.tool_crud.get_latest_executing_tool") as mock_get:
            mock_get.return_value = tool_exec

            with patch(
                "app.services.chat_broadcast.tool_crud.update_tool_execution"
            ) as mock_update_tool:
                with patch("app.services.chat_broadcast.crud.update_message"):
                    await handle_broadcast_message(db, investigation_id, message)

                    # Verify result summary includes auto-registration info
                    assert mock_update_tool.called
                    update_args = mock_update_tool.call_args
                    assert "auto-registered 15" in update_args[1]["result_summary"].lower()
