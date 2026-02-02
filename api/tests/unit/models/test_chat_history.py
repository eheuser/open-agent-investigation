import pytest
from uuid import uuid4
from datetime import datetime
from app.models.chat_history import ChatMessage


@pytest.mark.unit
class TestChatMessageModel:
    """Test ChatMessage model."""

    def test_create_user_message(self):
        """
        Test the creation of a user-role ChatMessage instance, ensuring that the role, content, and metadata are correctly assigned.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="user",
            content="What happened on this system?",
            message_metadata={"intent": "general_query"},
        )

        assert message.role == "user"
        assert message.content == "What happened on this system?"
        assert message.message_metadata["intent"] == "general_query"

    def test_create_assistant_message(self):
        """
        Test the creation of an assistant-role ChatMessage instance and verify that its role attribute is set correctly and that the provided content contains the expected substring.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="assistant",
            content="Based on the timeline, I found suspicious activity.",
        )

        assert message.role == "assistant"
        assert "suspicious activity" in message.content

    def test_create_tool_message(self):
        """
        Test that creating a tool-role ChatMessage correctly stores its role, associated tool call identifier, and name attributes.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="tool",
            content='{"results": ["event1", "event2"]}',
            tool_call_id="call_123",
            name="search_timeline",
        )

        assert message.role == "tool"
        assert message.tool_call_id == "call_123"
        assert message.name == "search_timeline"

    def test_create_system_message(self):
        """
        Test that a ChatMessage instance can be created with the role set to `system` and that the `role` attribute of the resulting object matches the expected value. The test constructs a message using a fresh UUID for `investigation_id`, a placeholder user identifier, and sample system content, then asserts that `message.role` equals `"system"`.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="system",
            content="You are a forensic investigator.",
        )

        assert message.role == "system"

    def test_message_with_tool_calls(self):
        """
        Test that an assistant-role ChatMessage correctly stores and exposes tool call data.

        The test creates a single tool call payload containing an identifier, type, and function specification with name `search_timeline` and JSON-encoded arguments. It then instantiates a `ChatMessage` with `role="assistant"`, no textual content, and the prepared `tool_calls` list.

        Assertions verify that:
        - The `tool_calls` attribute is populated (not `None`).
        - Exactly one tool call entry exists.
        - The nested function name matches the expected value `search_timeline`.
        """
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "search_timeline",
                    "arguments": '{"query": "suspicious"}',
                },
            }
        ]

        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="assistant",
            content=None,
            tool_calls=tool_calls,
        )

        assert message.tool_calls is not None
        assert len(message.tool_calls) == 1
        assert message.tool_calls[0]["function"]["name"] == "search_timeline"

    def test_message_default_flags(self):
        """
        Test that a newly created ChatMessage instance has its boolean flag attributes set to their default True values when explicitly provided. The test constructs a message with include_in_llm_context and visible_in_ui both set to True, then asserts that these attributes on the resulting object are indeed True.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="user",
            content="Test",
            include_in_llm_context=True,
            visible_in_ui=True,
        )

        assert message.include_in_llm_context is True
        assert message.visible_in_ui is True

    def test_message_custom_flags(self):
        """
        Test that custom boolean flags on a `ChatMessage` instance are set correctly.\n\nCreates a system-role message with `include_in_llm_context` and `visible_in_ui` explicitly set to `False` and verifies that these attributes retain the provided values.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="system",
            content="Internal note",
            include_in_llm_context=False,
            visible_in_ui=False,
        )

        assert message.include_in_llm_context is False
        assert message.visible_in_ui is False

    def test_message_with_parent(self):
        """
        Test that a ChatMessage correctly stores and exposes its parent_message_id attribute when initialized with a parent relationship.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="assistant",
            content="Follow-up response",
            parent_message_id=123,
        )

        assert message.parent_message_id == 123

    def test_message_metadata_empty_dict(self):
        """
        Test that creating a ChatMessage with an explicitly empty metadata dictionary stores an empty dict in the message_metadata attribute.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="user",
            content="Test",
            message_metadata={},
        )

        assert message.message_metadata == {}

    def test_message_metadata_complex(self):
        """
        Test creation of a ChatMessage with complex nested metadata, verifying that numeric and list values are preserved correctly in the resulting message instance.
        """
        metadata = {
            "intent": "timeline_query",
            "confidence": 0.95,
            "entities": ["user123", "file.exe"],
            "timestamp_range": {
                "start": "2024-01-01",
                "end": "2024-01-31",
            },
        }

        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="user",
            content="Test",
            message_metadata=metadata,
        )

        assert message.message_metadata["confidence"] == 0.95
        assert "user123" in message.message_metadata["entities"]

    def test_message_unicode_content(self):
        """
        Test that a ChatMessage instance correctly stores Unicode content and preserves it when accessed. This verifies that Japanese characters are retained in the `content` attribute.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="user",
            content="このシステムで何が起こったのですか？",
        )

        assert "このシステム" in message.content

    def test_message_long_content(self):
        """
        Test that a ChatMessage can store and retrieve very long content without truncation.

        Creates a message with 10 000 characters of filler text and asserts the stored content length matches the original size.
        """
        long_content = "x" * 10000

        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="assistant",
            content=long_content,
        )

        assert len(message.content) == 10000

    def test_message_type_field(self):
        """
        Verify that a ChatMessage created with a specific `message_type` retains that value, ensuring the `message_type` field is stored and accessible as expected.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="user",
            content="Test",
            message_type="question",
        )

        assert message.message_type == "question"

    def test_to_openai_format_user(self):
        """
        Test that converting a user-role ChatMessage instance to the OpenAI API format produces a dictionary with the correct "role" and "content" keys, matching the original message attributes.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="user",
            content="What happened?",
        )

        openai_format = message.to_openai_format()

        assert openai_format["role"] == "user"
        assert openai_format["content"] == "What happened?"

    def test_to_openai_format_assistant(self):
        """
        Test converting an assistant-role ChatMessage instance to the dictionary format expected by OpenAI’s API.

        The test creates a ChatMessage with role set to `"assistant"`, a sample content string, and required identifiers. It then calls :meth:`ChatMessage.to_openai_format` and asserts that the returned mapping contains the correct `role` and `content` keys matching the original message attributes. This verifies that the conversion logic preserves both the role designation and the textual payload for assistant messages.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="assistant",
            content="I found 5 events.",
        )

        openai_format = message.to_openai_format()

        assert openai_format["role"] == "assistant"
        assert openai_format["content"] == "I found 5 events."

    def test_to_openai_format_with_tool_calls(self):
        """
        Test converting an assistant ChatMessage containing tool calls into the OpenAI API format.

        The test creates a message with:
        - role set to `assistant`
        - no direct content
        - a list of `tool_calls` representing function invocations

        It then calls :meth:`ChatMessage.to_openai_format` and asserts that:
        - The resulting dictionary has its `role` field equal to `assistant`.
        - The `tool_calls` key is present in the output, confirming proper serialization of tool call data.
        """
        tool_calls = [{"id": "call_1", "function": {"name": "search"}}]

        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="assistant",
            content=None,
            tool_calls=tool_calls,
        )

        openai_format = message.to_openai_format()

        assert openai_format["role"] == "assistant"
        assert "tool_calls" in openai_format

    def test_to_openai_format_tool_response(self):
        """
        Test converting a ChatMessage with role "tool" into the OpenAI message format and verify that the resulting dictionary includes the correct role, tool_call_id, and name fields.
        """
        message = ChatMessage(
            investigation_id=uuid4(),
            user_id=1,
            role="tool",
            content='{"results": []}',
            tool_call_id="call_123",
            name="search_timeline",
        )

        openai_format = message.to_openai_format()

        assert openai_format["role"] == "tool"
        assert openai_format["tool_call_id"] == "call_123"
        assert openai_format["name"] == "search_timeline"

    def test_repr_format(self):
        """
        Test that the `__repr__` method of :class:`ChatMessage` returns a string containing the class name and key attribute values.

        The test creates a `ChatMessage` instance with known values for `message_id`, `investigation_id`, `user_id`, `role`, `content`, `include_in_llm_context`, and `visible_in_ui`. It then obtains the representation via :func:`repr` and asserts that the resulting string includes:

        * The class name `ChatMessage`.
        * The message identifier formatted as `id=42`.
        * The role formatted as `role='user'`.
        * The string form of the provided `investigation_id` UUID.
        * The flag `include_in_llm=True` (derived from `include_in_llm_context`).
        * The flag `visible_in_ui=True`.

        No exceptions are expected; the test passes if all substrings are present in the representation.
        """
        inv_id = uuid4()
        message = ChatMessage(
            message_id=42,
            investigation_id=inv_id,
            user_id=1,
            role="user",
            content="Test message",
            include_in_llm_context=True,
            visible_in_ui=True,
        )

        repr_str = repr(message)

        assert "ChatMessage" in repr_str
        assert "id=42" in repr_str
        assert "role='user'" in repr_str
        assert str(inv_id) in repr_str
        assert "include_in_llm=True" in repr_str
        assert "visible_in_ui=True" in repr_str
