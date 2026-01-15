"""
Unit tests for chat message Pydantic schemas.
"""

import pytest
from pydantic import ValidationError
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.chat_message import (
    IntentType,
    MessageType,
    AgentEffort,
    RouterMode,
    QuestionMessage,
    ClarificationResponseMessage,
    ConfirmMutationMessage,
    IntentClassifiedMessage,
    AnswerChunkMessage,
    EventsInsertedMessage,
    MutationPreviewMessage,
    GraphMutatedMessage,
    JobQueuedMessage,
    ClarificationRequestMessage,
    ErrorMessage,
    ProgressUpdateMessage,
    GraphUpdateMessage,
    ClassificationResult,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatHistoryResponse,
    OpenAIMessage,
    ToolExecutionCreate,
    ToolExecutionUpdate,
    ToolExecutionResponse,
)


@pytest.mark.unit
class TestEnums:
    """Test enum definitions."""

    def test_intent_type_values(self):
        """
        Test that each member of the IntentType enum has the expected string value, ensuring the enum definitions match their intended identifiers.
        """
        assert IntentType.INSERT_EVENTS == "insert_events"
        assert IntentType.QUERY_KG == "query_knowledge_graph"
        assert IntentType.EXECUTE_POLICY == "execute_agent_policy"
        assert IntentType.GENERAL_CHAT == "general_chat"
        assert IntentType.TIMELINE_QUERY == "timeline_query"
        assert IntentType.RAG_QUERY == "rag_query"

    def test_message_type_values(self):
        """
        Test that each member of the :class:`MessageType` enumeration has the expected string value, ensuring the enum definitions match the documented API contract.
        """
        assert MessageType.QUESTION == "question"
        assert MessageType.ASSISTANT_ANSWER == "assistant_answer"
        assert MessageType.TIMELINE_QUERY == "timeline_query"
        assert MessageType.AGENT_CHAT == "agent_chat"
        assert MessageType.TOOL_EXECUTION == "tool_execution"
        assert MessageType.SUMMARY == "summary"
        assert MessageType.ERROR == "error"
        assert MessageType.SYSTEM == "system"

    def test_agent_effort_values(self):
        """
        Test that the :class:`AgentEffort` enumeration members correspond to their expected string values: `LOW` should be `"low"`, `MEDIUM` should be `"medium"`, and `HIGH` should be `"high"`.
        """
        assert AgentEffort.LOW == "low"
        assert AgentEffort.MEDIUM == "medium"
        assert AgentEffort.HIGH == "high"

    def test_agent_effort_max_iterations(self):
        """
        Test the `max_iterations` attribute of each :class:`AgentEffort` enum member.

        The test verifies that:
        - `AgentEffort.LOW.max_iterations` equals `5`,
        - `AgentEffort.MEDIUM.max_iterations` equals `15`,
        - `AgentEffort.HIGH.max_iterations` equals `30`.

        These assertions confirm that the enumeration correctly maps effort levels to their default iteration limits.
        """
        assert AgentEffort.LOW.max_iterations == 5
        assert AgentEffort.MEDIUM.max_iterations == 15
        assert AgentEffort.HIGH.max_iterations == 30

    def test_router_mode_values(self):
        """
        Test that the RouterMode enumeration members have the expected string values: AUTO should equal "auto", AGENT should equal "agent", and RAG should equal "rag".
        """
        assert RouterMode.AUTO == "auto"
        assert RouterMode.AGENT == "agent"
        assert RouterMode.RAG == "rag"


@pytest.mark.unit
class TestQuestionMessage:
    """Test QuestionMessage schema."""

    def test_question_minimal(self):
        """
        Test the creation of a `QuestionMessage` instance using only the required fields.

        The test verifies that:
        - The message type is correctly set to `"question"`.
        - The provided `text` value is stored unchanged.
        - Optional fields `effort` and `router_mode` fall back to their default values (`"medium"` and `"auto"`, respectively).
        """
        msg = QuestionMessage(text="What happened?")

        assert msg.type == "question"
        assert msg.text == "What happened?"
        assert msg.effort == "medium"  # Default
        assert msg.router_mode == "auto"  # Default

    def test_question_with_effort(self):
        """
        Test that creating a `QuestionMessage` with an explicit `effort` value correctly stores the provided effort attribute. The test constructs a message using `text="Analyze logs"` and `effort="high"`, then asserts that the `effort` field of the resulting object equals `"high"`. This verifies that custom effort levels are accepted and retained by the model.
        """
        msg = QuestionMessage(text="Analyze logs", effort="high")

        assert msg.effort == "high"

    def test_question_with_router_mode(self):
        """
        Test that a QuestionMessage correctly stores a custom router_mode value.

        This test creates a `QuestionMessage` instance with the text `"Search events"` and explicitly sets
        `router_mode` to `"agent"`. It then asserts that the `router_mode` attribute of the resulting object
        matches the provided value, verifying that the custom router mode is accepted and retained by the model.
        """
        msg = QuestionMessage(text="Search events", router_mode="agent")

        assert msg.router_mode == "agent"

    def test_question_missing_text(self):
        """
        Ensure that creating a QuestionMessage without providing the required `text` field raises a `ValidationError`.
        """
        with pytest.raises(ValidationError):
            QuestionMessage()


@pytest.mark.unit
class TestClarificationResponseMessage:
    """Test ClarificationResponseMessage schema."""

    def test_clarification_response(self):
        """
        Test the ClarificationResponseMessage schema by creating an instance with a specific policy ID and rule values, then verify that its type attribute equals "clarification_response", its policy_id matches the provided value, and the nested rule_values dictionary contains the expected entry for "effort". This ensures correct default handling and attribute assignment for clarification response messages.
        """
        msg = ClarificationResponseMessage(
            policy_id="event_search", rule_values={"effort": "medium", "max_results": 100}
        )

        assert msg.type == "clarification_response"
        assert msg.policy_id == "event_search"
        assert msg.rule_values["effort"] == "medium"


@pytest.mark.unit
class TestConfirmMutationMessage:
    """Test ConfirmMutationMessage schema."""

    def test_confirm_mutation_true(self):
        """
        Test that a ConfirmMutationMessage correctly reflects a confirmed mutation: creates the message with a specific mutation_id and confirmed=True, then asserts that its type is "confirm_mutation", the mutation_id matches the input, and the confirmed flag is True.
        """
        msg = ConfirmMutationMessage(mutation_id="mut_123", confirmed=True)

        assert msg.type == "confirm_mutation"
        assert msg.mutation_id == "mut_123"
        assert msg.confirmed is True

    def test_confirm_mutation_false(self):
        """
        Test that a ConfirmMutationMessage correctly records a negative confirmation.

        This test creates a `ConfirmMutationMessage` with `confirmed=False` and verifies that the `confirmed` attribute reflects this value.

        **Steps**
        - Instantiate `ConfirmMutationMessage` with `mutation_id="mut_456"` and `confirmed=False`.
        - Assert that `msg.confirmed` is `False`.

        No return value; raises an AssertionError if the condition fails.
        """
        msg = ConfirmMutationMessage(mutation_id="mut_456", confirmed=False)

        assert msg.confirmed is False


@pytest.mark.unit
class TestIntentClassifiedMessage:
    """Test IntentClassifiedMessage schema."""

    def test_intent_classified(self):
        """
        Test that an IntentClassifiedMessage instance correctly sets its type, intent, and confidence attributes when initialized with valid values.
        """
        msg = IntentClassifiedMessage(intent=IntentType.EXECUTE_POLICY, confidence=0.95)

        assert msg.type == "intent_classified"
        assert msg.intent == IntentType.EXECUTE_POLICY
        assert msg.confidence == 0.95

    def test_intent_classified_default_confidence(self):
        """
        Test that an IntentClassifiedMessage created with only an intent uses the default confidence value of 1.0.
        """
        msg = IntentClassifiedMessage(intent=IntentType.GENERAL_CHAT)

        assert msg.confidence == 1.0


@pytest.mark.unit
class TestAnswerChunkMessage:
    """Test AnswerChunkMessage schema."""

    def test_answer_chunk(self):
        """
        Test that an AnswerChunkMessage instance correctly sets and exposes its type, content, chunk identifier, and final-chunk flag.
        """
        msg = AnswerChunkMessage(content="This is a chunk", chunk_id=1, is_final=False)

        assert msg.type == "answer_chunk"
        assert msg.content == "This is a chunk"
        assert msg.chunk_id == 1
        assert msg.is_final is False

    def test_answer_chunk_final(self):
        """
        Test that an AnswerChunkMessage created with `is_final=True` correctly reports its final status and defaults its `chunk_id` to zero.
        """
        msg = AnswerChunkMessage(content="Final chunk", is_final=True)

        assert msg.is_final is True
        assert msg.chunk_id == 0  # Default


@pytest.mark.unit
class TestJobQueuedMessage:
    """Test JobQueuedMessage schema."""

    def test_job_queued_minimal(self):
        """
        Test that a JobQueuedMessage instantiated with only the required fields correctly sets its type and attributes, while optional fields remain None. The test creates a message with job_id, policy_id, and message, then verifies:
        - `type` equals `"job_queued"`.
        - `job_id`, `policy_id`, and `message` match the provided values.
        - Optional attributes `policy_title` and `estimated_duration` are unset (None).
        """
        msg = JobQueuedMessage(job_id=123, policy_id="event_search", message="Job created")

        assert msg.type == "job_queued"
        assert msg.job_id == 123
        assert msg.policy_id == "event_search"
        assert msg.message == "Job created"
        assert msg.policy_title is None
        assert msg.estimated_duration is None

    def test_job_queued_full(self):
        """
        Test that a JobQueuedMessage instantiated with all fields correctly stores and returns the provided values, specifically verifying the policy_title and estimated_duration attributes.
        """
        msg = JobQueuedMessage(
            job_id=123,
            policy_id="event_search",
            policy_title="Event Search",
            estimated_duration="5 minutes",
            message="Job created",
        )

        assert msg.policy_title == "Event Search"
        assert msg.estimated_duration == "5 minutes"


@pytest.mark.unit
class TestErrorMessage:
    """Test ErrorMessage schema."""

    def test_error_simple(self):
        """
        Test that an ErrorMessage instantiated with only a message field correctly sets its type to "error", stores the provided message, and leaves the optional details attribute as None.
        """
        msg = ErrorMessage(message="An error occurred")

        assert msg.type == "error"
        assert msg.message == "An error occurred"
        assert msg.details is None

    def test_error_with_details(self):
        """
        Test that an `ErrorMessage` instance correctly stores and exposes the optional `details` attribute when provided.
        """
        msg = ErrorMessage(message="Processing failed", details="Stack trace: ...")

        assert msg.details == "Stack trace: ..."


@pytest.mark.unit
class TestProgressUpdateMessage:
    """Test ProgressUpdateMessage schema."""

    def test_progress_update(self):
        """
        Test that a `ProgressUpdateMessage` instance correctly sets its fields and type.

        The test creates a `ProgressUpdateMessage` with:
        - `job_id` set to `123`
        - `progress` set to `0.5`
        - `message` set to `"Processing 50% complete"`

        It then asserts that:
        - The `type` attribute equals the string `"progress_update"`
        - The `job_id` attribute matches the provided value
        - The `progress` attribute matches the provided value
        - The `message` attribute matches the provided value.
        """
        msg = ProgressUpdateMessage(job_id=123, progress=0.5, message="Processing 50% complete")

        assert msg.type == "progress_update"
        assert msg.job_id == 123
        assert msg.progress == 0.5
        assert msg.message == "Processing 50% complete"

    def test_progress_update_complete(self):
        """
        Test that a ProgressUpdateMessage with a progress value of 1.0 (representing 100 % completion) correctly stores and returns the given progress value. The test constructs the message with a sample job identifier, a progress of exactly one, and a descriptive status string, then asserts that the `progress` attribute equals the expected full-completion value.
        """
        msg = ProgressUpdateMessage(job_id=123, progress=1.0, message="Complete")

        assert msg.progress == 1.0


@pytest.mark.unit
class TestGraphUpdateMessage:
    """Test GraphUpdateMessage schema."""

    def test_graph_update_minimal(self):
        """
        Test that a GraphUpdateMessage instantiated with only the required `investigation_id` field correctly defaults all optional counters to zero and sets the message type to `"graph_update"`. This verifies minimal initialization, default values for `nodes_added`, `edges_added`, and `nodes_updated`, and ensures the `type` attribute reflects the appropriate schema identifier.
        """
        msg = GraphUpdateMessage(investigation_id="inv-123")

        assert msg.type == "graph_update"
        assert msg.investigation_id == "inv-123"
        assert msg.nodes_added == 0
        assert msg.edges_added == 0
        assert msg.nodes_updated == 0

    def test_graph_update_full(self):
        """
        Test that a GraphUpdateMessage correctly stores all provided fields when fully populated. This verifies the `investigation_id`, `nodes_added`, `edges_added`, and `nodes_updated` attributes are set to the expected values.
        """
        msg = GraphUpdateMessage(
            investigation_id="inv-123", nodes_added=5, edges_added=10, nodes_updated=2
        )

        assert msg.nodes_added == 5
        assert msg.edges_added == 10
        assert msg.nodes_updated == 2


@pytest.mark.unit
class TestClassificationResult:
    """Test ClassificationResult schema."""

    def test_classification_minimal(self):
        """
        Test classification result with only the required intent field, verifying default confidence and empty reasoning.
        """
        result = ClassificationResult(intent=IntentType.GENERAL_CHAT)

        assert result.intent == IntentType.GENERAL_CHAT
        assert result.confidence == 1.0
        assert result.reasoning == ""

    def test_classification_full(self):
        """
        Test the ClassificationResult model by providing all fields and verifying that the confidence and reasoning attributes are correctly set. This ensures that the model stores and retrieves the intent, confidence score, and reasoning text as expected.
        """
        result = ClassificationResult(
            intent=IntentType.EXECUTE_POLICY,
            confidence=0.85,
            reasoning="User asked to search events",
        )

        assert result.confidence == 0.85
        assert result.reasoning == "User asked to search events"


@pytest.mark.unit
class TestChatMessageCreate:
    """Test ChatMessageCreate schema."""

    def test_create_minimal(self):
        """
        Test that creating a `ChatMessageCreate` instance with only the required `role` field correctly sets default values for all optional attributes.

        The test:
        - Instantiates `ChatMessageCreate` with `role="user"`.
        - Asserts that the `role` attribute is set to `"user"`.
        - Verifies that optional fields `message_type` and `content` remain `None`.
        - Checks that `metadata` defaults to an empty dictionary.
        - Confirms that both `include_in_llm_context` and `visible_in_ui` default to `True`.
        """
        msg = ChatMessageCreate(role="user")

        assert msg.role == "user"
        assert msg.message_type is None
        assert msg.content is None
        assert msg.metadata == {}
        assert msg.include_in_llm_context is True
        assert msg.visible_in_ui is True

    def test_create_full(self):
        """
        Test that a ChatMessageCreate instance can be instantiated with all possible fields and that each attribute retains the provided value. This verifies correct handling of role, message_type, content, name, tool_calls, tool_call_id, parent_message_id, metadata, include_in_llm_context, and visible_in_ui during object creation.
        """
        msg = ChatMessageCreate(
            role="assistant",
            message_type="assistant_answer",
            content="Response text",
            name="agent",
            tool_calls={"calls": []},
            tool_call_id="call_123",
            parent_message_id=1,
            metadata={"key": "value"},
            include_in_llm_context=True,
            visible_in_ui=True,
        )

        assert msg.role == "assistant"
        assert msg.message_type == "assistant_answer"
        assert msg.content == "Response text"
        assert msg.name == "agent"
        assert msg.tool_calls == {"calls": []}
        assert msg.tool_call_id == "call_123"
        assert msg.parent_message_id == 1
        assert msg.metadata == {"key": "value"}

    def test_create_tool_message(self):
        """
        Test that a ChatMessageCreate instance can be constructed with role set to "tool" and correctly stores the provided content, name, and tool_call_id attributes.
        """
        msg = ChatMessageCreate(
            role="tool",
            content='{"result": "success"}',
            name="search_events",
            tool_call_id="call_123",
        )

        assert msg.role == "tool"
        assert msg.name == "search_events"
        assert msg.tool_call_id == "call_123"


@pytest.mark.unit
class TestChatMessageResponse:
    """Test ChatMessageResponse schema."""

    def test_response_minimal(self):
        """
        Test that a ChatMessageResponse instance can be created with only the required fields and default values, verifying that minimal input data correctly populates the model attributes such as `message_id`, `investigation_id`, `role` and `content` while optional fields remain unset or retain their defaults.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        data = {
            "message_id": 1,
            "investigation_id": investigation_id,
            "user_id": 1,
            "role": "user",
            "message_type": None,
            "content": "Hello",
            "name": None,
            "tool_calls": None,
            "tool_call_id": None,
            "parent_message_id": None,
            "metadata": {},
            "include_in_llm_context": True,
            "visible_in_ui": True,
            "deleted_at": None,
            "created_at": created_at,
        }

        msg = ChatMessageResponse(**data)

        assert msg.message_id == 1
        assert msg.investigation_id == investigation_id
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_response_with_tool_executions(self):
        """
        Test that a ChatMessageResponse correctly includes and validates tool execution data.

        The test constructs a message payload containing a single tool execution entry with `execution_id`, `tool_name`, and `status`. It then instantiates a `ChatMessageResponse` from this payload and asserts:

        - The `tool_executions` attribute is present (not `None`).
        - Exactly one tool execution object is stored.
        - The stored tool execution’s `tool_name` matches the expected value `"search_events"`.

        This verifies that the response model properly parses, retains, and exposes tool execution information.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        data = {
            "message_id": 1,
            "investigation_id": investigation_id,
            "user_id": 1,
            "role": "assistant",
            "message_type": "agent_chat",
            "content": None,
            "name": None,
            "tool_calls": None,
            "tool_call_id": None,
            "parent_message_id": None,
            "metadata": {},
            "tool_executions": [
                {"execution_id": 1, "tool_name": "search_events", "status": "completed"}
            ],
            "include_in_llm_context": True,
            "visible_in_ui": True,
            "deleted_at": None,
            "created_at": created_at,
        }

        msg = ChatMessageResponse(**data)

        assert msg.tool_executions is not None
        assert len(msg.tool_executions) == 1
        assert msg.tool_executions[0]["tool_name"] == "search_events"


@pytest.mark.unit
class TestChatHistoryResponse:
    """Test ChatHistoryResponse schema."""

    def test_history_response(self):
        """
        Test that a `ChatHistoryResponse` correctly stores a list containing a single chat message and accurately reports its total count and LLM context count.

        The test creates a unique investigation identifier and timestamp, builds a minimal message dictionary with required fields, constructs a `ChatHistoryResponse` using this data, and asserts that:

        * Exactly one message is present in the `messages` attribute.
        * The `total_count` attribute equals `1`.
        * The `llm_context_count` attribute equals `1`.

        These assertions verify proper initialization and attribute assignment of the response model.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        messages = [
            {
                "message_id": 1,
                "investigation_id": investigation_id,
                "user_id": 1,
                "role": "user",
                "message_type": "question",
                "content": "Hello",
                "name": None,
                "tool_calls": None,
                "tool_call_id": None,
                "parent_message_id": None,
                "metadata": {},
                "include_in_llm_context": True,
                "visible_in_ui": True,
                "deleted_at": None,
                "created_at": created_at,
            }
        ]

        history = ChatHistoryResponse(messages=messages, total_count=1, llm_context_count=1)

        assert len(history.messages) == 1
        assert history.total_count == 1
        assert history.llm_context_count == 1


@pytest.mark.unit
class TestOpenAIMessage:
    """Test OpenAIMessage schema."""

    def test_openai_user_message(self):
        """
        Test that an OpenAIMessage created with role "user" correctly sets its attributes.

        This unit test verifies:
        - The `role` attribute is set to `"user"`.
        - The `content` attribute matches the provided string.
        - Optional fields `name` and `tool_calls` remain `None` when not supplied.
        """
        msg = OpenAIMessage(role="user", content="Hello")

        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.name is None
        assert msg.tool_calls is None

    def test_openai_assistant_with_tool_calls(self):
        """
        Test the OpenAIMessage model when creating an assistant-role message that includes tool call data.

        The test constructs an `OpenAIMessage` instance with:
        - `role` set to `"assistant"`,
        - `content` explicitly set to `None`,
        - `tool_calls` containing a dictionary with a single call entry (identified by `"call_123"`).

        It then asserts that:
        - The `role` attribute is correctly stored as `"assistant"`,
        - The `content` attribute remains `None`,
        - The `tool_calls` attribute is not `None` and thus properly parsed.
        """
        msg = OpenAIMessage(
            role="assistant", content=None, tool_calls={"calls": [{"id": "call_123"}]}
        )

        assert msg.role == "assistant"
        assert msg.content is None
        assert msg.tool_calls is not None

    def test_openai_tool_message(self):
        """
        Test that creating an OpenAIMessage with role set to "tool" correctly assigns and preserves the `role`, `name`, and `tool_call_id` fields.
        """
        msg = OpenAIMessage(
            role="tool",
            content='{"result": "success"}',
            name="search_events",
            tool_call_id="call_123",
        )

        assert msg.role == "tool"
        assert msg.name == "search_events"
        assert msg.tool_call_id == "call_123"


@pytest.mark.unit
class TestToolExecutionCreate:
    """Test ToolExecutionCreate schema."""

    def test_create_minimal(self):
        """
        Test that a `ToolExecutionCreate` instance can be instantiated with only the required fields and that optional attributes default to `None`. The test creates an object using `chat_message_id` and `tool_name`, then asserts that these values are set correctly while `display_name` and `arguments` remain unset (i.e., `None`).
        """
        exec_create = ToolExecutionCreate(chat_message_id=1, tool_name="search_events")

        assert exec_create.chat_message_id == 1
        assert exec_create.tool_name == "search_events"
        assert exec_create.display_name is None
        assert exec_create.arguments is None

    def test_create_full(self):
        """
        Test creating a full ToolExecutionCreate instance with all fields set.

        The test constructs a `ToolExecutionCreate` object providing explicit values for:
        - `chat_message_id`
        - `tool_name`
        - `display_name`
        - `arguments`
        - `execution_number`
        - `max_tools`

        It then asserts that the resulting object's attributes match the supplied values, verifying that the model correctly stores and returns each field.
        """
        exec_create = ToolExecutionCreate(
            chat_message_id=1,
            tool_name="search_events",
            display_name="Search Events",
            arguments={"query": "failed login", "limit": 100},
            execution_number=1,
            max_tools=10,
        )

        assert exec_create.display_name == "Search Events"
        assert exec_create.arguments == {"query": "failed login", "limit": 100}
        assert exec_create.execution_number == 1
        assert exec_create.max_tools == 10


@pytest.mark.unit
class TestToolExecutionUpdate:
    """Test ToolExecutionUpdate schema."""

    def test_update_result(self):
        """
        Test that a ToolExecutionUpdate instance correctly stores provided result data and summary while leaving the status attribute unset (None). Verifies that the `result` field matches the given dictionary, the `result_summary` field matches the supplied string, and the optional `status` field remains its default value.
        """
        update = ToolExecutionUpdate(result={"events": [1, 2, 3]}, result_summary="Found 3 events")

        assert update.result == {"events": [1, 2, 3]}
        assert update.result_summary == "Found 3 events"
        assert update.status is None

    def test_update_status(self):
        """
        Test updating tool execution status.

        Creates a `ToolExecutionUpdate` instance with the status set to `"completed"`, then verifies that:
        - The `status` attribute reflects the provided value.
        - The optional `result` attribute defaults to `None` when not supplied.
        """
        update = ToolExecutionUpdate(status="completed")

        assert update.status == "completed"
        assert update.result is None


@pytest.mark.unit
class TestToolExecutionResponse:
    """Test ToolExecutionResponse schema."""

    def test_response_minimal(self):
        """
        Test that a ToolExecutionResponse can be instantiated with only the required fields and default/optional values set to None, verifying that the minimal payload correctly assigns the execution_id, tool_name, status, and leaves finished_at unset.
        """
        started_at = datetime.now(timezone.utc)

        data = {
            "execution_id": 1,
            "chat_message_id": 1,
            "tool_name": "search_events",
            "display_name": None,
            "arguments": None,
            "result": None,
            "result_summary": None,
            "status": "executing",
            "execution_number": None,
            "max_tools": None,
            "started_at": started_at,
            "finished_at": None,
        }

        response = ToolExecutionResponse(**data)

        assert response.execution_id == 1
        assert response.tool_name == "search_events"
        assert response.status == "executing"
        assert response.finished_at is None

    def test_response_completed(self):
        """
        Test that a ToolExecutionResponse with status "completed" correctly stores its fields, including timestamps and result data. The test constructs a response using valid input data, verifies the `status` attribute equals "completed", checks that the `result` matches the provided dictionary, and confirms that the `finished_at` timestamp is set to the expected value.
        """
        started_at = datetime.now(timezone.utc)
        finished_at = datetime.now(timezone.utc)

        data = {
            "execution_id": 1,
            "chat_message_id": 1,
            "tool_name": "search_events",
            "display_name": "Search Events",
            "arguments": {"query": "test"},
            "result": {"events": []},
            "result_summary": "No events found",
            "status": "completed",
            "execution_number": 1,
            "max_tools": 10,
            "started_at": started_at,
            "finished_at": finished_at,
        }

        response = ToolExecutionResponse(**data)

        assert response.status == "completed"
        assert response.result == {"events": []}
        assert response.finished_at == finished_at


@pytest.mark.unit
class TestChatMessageSchemaEdgeCases:
    """Test edge cases for chat message schemas."""

    def test_question_with_very_long_text(self):
        """
        Test that a QuestionMessage can handle extremely long text content without truncation or errors, verifying the length of the stored text matches the input size.
        """
        long_text = "A" * 100000
        msg = QuestionMessage(text=long_text)

        assert len(msg.text) == 100000

    def test_question_with_unicode(self):
        """
        Test that a `QuestionMessage` correctly handles Unicode characters in its `text` field, ensuring both Japanese characters and emoji are preserved.
        """
        msg = QuestionMessage(text="質問: データを検索 🔍")

        assert "質問" in msg.text
        assert "🔍" in msg.text

    def test_error_message_with_unicode(self):
        """
        Test that an ErrorMessage instance correctly stores and returns Unicode characters in its fields.

        This verifies:
        - The `message` attribute contains the expected Japanese substring.
        - The `details` attribute contains the expected Japanese substring.
        """
        msg = ErrorMessage(message="エラー発生", details="詳細情報")

        assert "エラー" in msg.message
        assert "詳細" in msg.details

    def test_metadata_with_complex_nested_data(self):
        """
        Test that a `ChatMessageCreate` instance correctly stores and retrieves complex nested metadata structures, including dictionaries within dictionaries, lists, and boolean values. The assertion verifies that the deeply nested list under `"nested" -> "level1" -> "level2"` matches the expected content.
        """
        msg = ChatMessageCreate(
            role="user",
            metadata={
                "nested": {"level1": {"level2": ["item1", "item2"]}},
                "array": [1, 2, 3],
                "boolean": True,
            },
        )

        assert msg.metadata["nested"]["level1"]["level2"] == ["item1", "item2"]

    def test_tool_execution_with_large_result(self):
        """
        Test that a ToolExecutionUpdate correctly stores and returns a large result payload.

        The test creates a dictionary containing 10,000 event entries, instantiates a `ToolExecutionUpdate` with this payload, and asserts that the `result` attribute preserves all events by checking its length. This verifies that the model can handle large nested structures without truncation or data loss.
        """
        large_result = {"events": [{"id": i} for i in range(10000)]}
        update = ToolExecutionUpdate(result=large_result)

        assert len(update.result["events"]) == 10000

    def test_progress_update_boundaries(self):
        """
        Test that `ProgressUpdateMessage` correctly accepts and stores boundary progress values (0.0 and 1.0), ensuring the model validates these extremes without raising errors and that the stored `progress` attribute matches the input.
        """
        msg_zero = ProgressUpdateMessage(job_id=1, progress=0.0, message="Starting")
        msg_one = ProgressUpdateMessage(job_id=1, progress=1.0, message="Complete")

        assert msg_zero.progress == 0.0
        assert msg_one.progress == 1.0

    def test_clarification_request_with_many_rules(self):
        """
        Test that a `ClarificationRequestMessage` correctly stores a large list of missing rules.

        Creates 20 rule dictionaries, instantiates the message with these rules, and asserts that the `missing_rules` attribute contains exactly 20 entries. This verifies handling of many missing rules without errors.
        """
        missing_rules = [
            {"name": f"rule{i}", "description": f"Rule {i}", "type": "string"} for i in range(20)
        ]

        msg = ClarificationRequestMessage(
            policy_id="complex_policy",
            policy_title="Complex Policy",
            missing_rules=missing_rules,
            message="Please provide values",
        )

        assert len(msg.missing_rules) == 20
