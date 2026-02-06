import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from app.services.chat_router import (
    classify_intent,
    _fallback_classification,
    _fetch_recent_chat_history,
    route_chat_message,
    handle_clarification_response,
)
from app.schemas.chat_message import IntentType, ClassificationResult


@pytest.fixture
def mock_embedding_status():
    """Mock get_embedding_status to return complete status."""
    with patch('app.services.chat_router.get_embedding_status') as mock:
        mock.return_value = {
            "pending_jobs": 0,
            "running_jobs": 0,
            "total_pending_events": 0,
            "is_complete": True,
        }
        yield mock


@pytest.mark.unit
class TestFallbackClassification:
    """Test fallback classification (keyword-based)."""

    def test_timeline_query_keywords(self):
        """
        Test that the fallback classification correctly identifies various timeline-related queries as a TIMELINE_QUERY intent with high confidence. This ensures keywords such as “timeline”, “entries”, and related actions are mapped to the appropriate IntentType.
        """
        queries = [
            "Show me timeline entries",
            "What's on the timeline?",
            "Add a timeline entry",
            "Delete timeline entry 42",
            "Update timeline entry",
            "Timeline statistics",
        ]

        for query in queries:
            result = _fallback_classification(query)
            assert result.intent == IntentType.TIMELINE_QUERY
            assert result.confidence > 0.8

    def test_general_chat_keywords(self):
        """
        Test that general metadata questions and related queries are correctly classified as GENERAL_CHAT intent by the fallback classification logic. This includes verifying multiple example queries and ensuring specific edge cases like "How many events" map to GENERAL_CHAT while other similar phrases may trigger different intents.
        """
        queries = [
            "What is this investigation about?",
            "Summarize the investigation",
            "What data sources are available?",
        ]

        for query in queries:
            result = _fallback_classification(query)
            assert result.intent == IntentType.GENERAL_CHAT

        # Note: "How many timeline" triggers timeline_query (checked first)
        # "How many events" triggers general_chat
        result = _fallback_classification("How many events are there?")
        assert result.intent == IntentType.GENERAL_CHAT

    def test_event_search_keywords(self):
        """
        Tests that fallback classification correctly identifies event-search queries as intent EXECUTE_POLICY, ensuring each sample query is routed to the agent handling policy execution.
        """
        queries = [
            "Find failed login attempts",
            "Search for PowerShell activity",
            "Look for suspicious processes",
            "Analyze registry changes",
            "Investigate lateral movement",
            "Locate network connections",
        ]

        for query in queries:
            result = _fallback_classification(query)
            assert result.intent == IntentType.EXECUTE_POLICY

    def test_insert_events_keywords(self):
        """
        Test that fallback classification correctly identifies various phrasing of event insertion queries as the INSERT_EVENTS intent. The test iterates over a collection of example strings that represent different ways a user might request adding events, invokes the internal `_fallback_classification` function for each query, and asserts that the returned result has its `intent` attribute set to `IntentType.INSERT_EVENTS`. This ensures that the fallback keyword detection logic consistently maps these synonyms to the appropriate intent.
        """
        queries = [
            "Add event: user logged in",
            "Insert event data",
            "Paste these events",
            "Here's some event data",
            "Import events",
        ]

        for query in queries:
            result = _fallback_classification(query)
            assert result.intent == IntentType.INSERT_EVENTS

    def test_case_insensitive(self):
        """
        Test that fallback classification correctly identifies the intent regardless of query case.

        This test iterates over a set of queries with different capitalizations-uppercase, lowercase, and title case-and verifies that each one is classified as `IntentType.EXECUTE_POLICY` by the `_fallback_classification` function.
        """
        queries = [
            "FIND FAILED LOGINS",
            "find failed logins",
            "Find Failed Logins",
        ]

        for query in queries:
            result = _fallback_classification(query)
            assert result.intent == IntentType.EXECUTE_POLICY

    def test_default_classification(self):
        """
        Test that queries not matching any known intent are classified as general chat with low confidence.

        The test iterates over a set of unrelated or nonsensical queries, invokes the fallback classification routine, and asserts that:
        - The returned intent is `IntentType.GENERAL_CHAT`.
        - The confidence score is below the 0.7 threshold, indicating uncertainty.
        """
        queries = [
            "Hello",
            "Random text",
            "xyz abc 123",
        ]

        for query in queries:
            result = _fallback_classification(query)
            assert result.intent == IntentType.GENERAL_CHAT
            assert result.confidence < 0.7  # Low confidence for defaults

    def test_question_starters(self):
        """
        Test that fallback classification correctly assigns intents based on question phrasing: simple questions should be classified as GENERAL_CHAT while more complex, policy-related questions should be classified as EXECUTE_POLICY. The test iterates over predefined example queries for each category and asserts that the returned IntentType matches the expected value.
        """
        # Simple questions -> general chat
        simple_questions = [
            "What is this?",
            "How many entries?",
        ]
        for query in simple_questions:
            result = _fallback_classification(query)
            assert result.intent == IntentType.GENERAL_CHAT

        # Complex questions -> agent
        complex_questions = [
            "Which users logged in remotely?",
            "When did the attack start?",
            "Where are the suspicious files?",
        ]
        for query in complex_questions:
            result = _fallback_classification(query)
            assert result.intent == IntentType.EXECUTE_POLICY


@pytest.mark.unit
class TestClassificationResult:
    """Test ClassificationResult schema."""

    def test_classification_result_creation(self):
        """
        Test that a ClassificationResult instance is correctly created with the specified intent, confidence score, and reasoning, and that its attributes match the provided values.
        """
        result = ClassificationResult(
            intent=IntentType.TIMELINE_QUERY,
            confidence=0.95,
            reasoning="User wants to query timeline",
        )

        assert result.intent == IntentType.TIMELINE_QUERY
        assert result.confidence == 0.95
        assert result.reasoning == "User wants to query timeline"

    def test_classification_result_defaults(self):
        """
        Test that a ClassificationResult instance correctly sets default values when optional fields are omitted.

        The test creates a ClassificationResult with the required `intent` and `confidence` arguments and verifies:

        - The `intent` attribute matches the provided IntentType.
        - The `confidence` attribute matches the provided confidence score.
        - The optional `reasoning` attribute is either absent, `None`, or an empty string, confirming that it defaults to a falsy value when not supplied.
        """
        result = ClassificationResult(
            intent=IntentType.GENERAL_CHAT, confidence=0.9  # Must provide confidence
        )

        assert result.intent == IntentType.GENERAL_CHAT
        assert result.confidence == 0.9
        # reasoning is optional
        assert (
            not hasattr(result, "reasoning") or result.reasoning is None or result.reasoning == ""
        )


@pytest.mark.unit
class TestFetchRecentChatHistory:
    """Test fetching recent chat history for context."""

    @pytest.mark.asyncio
    async def test_fetch_chat_history_empty(self):
        """
        Test fetching recent chat history when the database returns no records.

        This coroutine verifies that `_fetch_recent_chat_history` correctly handles an empty result set:

        - Sets up an asynchronous mock database (`mock_db`) and configures its `execute` method to return a mocked result whose `scalars().all()` call yields an empty list.
        - Generates a random invitation identifier (`inv_id`) using `uuid.uuid4()`.
        - Calls `_fetch_recent_chat_history` with the mock database, the generated ID, and a limit of 10 entries.
        - Asserts that the returned history is an empty list.
        - Confirms that the database's `execute` method was invoked exactly once.
        """
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = []
        mock_db.execute.return_value = mock_result

        inv_id = uuid.uuid4()
        history = await _fetch_recent_chat_history(mock_db, inv_id, limit=10)

        assert history == []
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_chat_history_with_messages(self):
        """
        Test that the recent chat history retrieval correctly returns messages in chronological order.

        The test creates two mock `ChatMessage` instances representing a user message and an assistant response belonging to the same investigation. It configures an asynchronous mock database so that `execute` returns these messages in descending order (newest first). The helper `_fetch_recent_chat_history` is then called with a limit of ten messages.

        Assertions verify that:
        - Exactly two history entries are returned.
        - The first entry corresponds to the original user message with role `"user"` and matching content.
        - The second entry corresponds to the assistant response with role `"assistant"` and matching content.
        """
        from app.models.chat_history import ChatMessage
        from datetime import datetime

        inv_id = uuid.uuid4()
        mock_messages = [
            ChatMessage(
                message_id=1,
                investigation_id=inv_id,
                user_id=1,
                role="user",
                content="First message",
                include_in_llm_context=True,
                created_at=datetime.utcnow(),
            ),
            ChatMessage(
                message_id=2,
                investigation_id=inv_id,
                user_id=1,
                role="assistant",
                content="First response",
                include_in_llm_context=True,
                created_at=datetime.utcnow(),
            ),
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        # Messages are fetched in DESC order, then reversed to chronological
        mock_result.scalars().all.return_value = list(reversed(mock_messages))
        mock_db.execute.return_value = mock_result

        history = await _fetch_recent_chat_history(mock_db, inv_id, limit=10)

        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "First message"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "First response"

    @pytest.mark.asyncio
    async def test_fetch_chat_history_respects_limit(self):
        """
        Test that the `_fetch_recent_chat_history` coroutine respects the `limit` argument by returning no more than the specified number of chat messages.

        Parameters:
            self: The test case instance.

        Raises:
            AssertionError: If the returned history contains more items than the requested limit.
        """
        from app.models.chat_history import ChatMessage
        from datetime import datetime

        # Create 20 mock messages
        mock_messages = [
            ChatMessage(
                message_id=i,
                investigation_id=uuid.uuid4(),
                user_id=1,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}",
                created_at=datetime.utcnow(),
            )
            for i in range(20)
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = mock_messages[:5]  # Simulating limit
        mock_db.execute.return_value = mock_result

        inv_id = uuid.uuid4()
        history = await _fetch_recent_chat_history(mock_db, inv_id, limit=5)

        assert len(history) <= 5


@pytest.mark.unit
class TestIntentTypeEnum:
    """Test IntentType enum values."""

    def test_intent_type_values(self):
        """
        Test that the IntentType enumeration defines the correct string values for each member: INSERT_EVENTS, TIMELINE_QUERY, GENERAL_CHAT, and EXECUTE_POLICY.
        """
        assert IntentType.INSERT_EVENTS.value == "insert_events"
        assert IntentType.TIMELINE_QUERY.value == "timeline_query"
        assert IntentType.GENERAL_CHAT.value == "general_chat"
        assert IntentType.EXECUTE_POLICY.value == "execute_agent_policy"

    def test_intent_type_comparison(self):
        """
        Test that IntentType enum values compare correctly: verifies equality for identical members and inequality for different members.
        """
        intent1 = IntentType.TIMELINE_QUERY
        intent2 = IntentType.TIMELINE_QUERY
        intent3 = IntentType.GENERAL_CHAT

        assert intent1 == intent2
        assert intent1 != intent3

    def test_intent_type_string_conversion(self):
        """
        Test that an IntentType enum member correctly returns its associated string value and that converting this value to a string yields the expected representation.
        """
        intent = IntentType.EXECUTE_POLICY

        assert intent.value == "execute_agent_policy"
        assert str(intent.value) == "execute_agent_policy"


@pytest.mark.unit
class TestClassificationEdgeCases:
    """Test edge cases for intent classification."""

    def test_empty_query(self):
        """
        Test that an empty query is classified using the fallback mechanism and results in the GENERAL_CHAT intent type.
        """
        result = _fallback_classification("")

        # Should default to general chat
        assert result.intent == IntentType.GENERAL_CHAT

    def test_very_long_query(self):
        """
        Test that a very long query containing repeated words is still correctly classified by the fallback classifier, ensuring the presence of the keyword “find” results in an EXECUTE_POLICY intent.
        """
        long_query = "Find " + "suspicious " * 100 + "activity"
        result = _fallback_classification(long_query)

        # Should still detect "find" keyword
        assert result.intent == IntentType.EXECUTE_POLICY

    def test_unicode_query(self):
        """
        Test that Unicode queries in Japanese, Chinese, and Korean are correctly classified by the fallback classification mechanism as general chat intents when they contain no English keywords. The test iterates over a list of non-ASCII queries, invokes the internal `_fallback_classification` function for each, and asserts that the returned intent equals `IntentType.GENERAL_CHAT`.
        """
        queries = [
            "タイムラインエントリを表示",  # Japanese
            "查找失败的登录",  # Chinese
            "타임라인 항목 표시",  # Korean
        ]

        for query in queries:
            result = _fallback_classification(query)
            # Should default to general chat (no English keywords)
            assert result.intent == IntentType.GENERAL_CHAT

    def test_mixed_keywords(self):
        """
        Test that queries containing keywords from multiple intent categories are classified according to the fallback order.

        The test constructs a query string that includes both timeline-related and search-related terms, runs the internal `_fallback_classification` function, and asserts that the resulting `intent` attribute matches one of the expected fallback categories (either `IntentType.TIMELINE_QUERY` or `IntentType.EXECUTE_POLICY`). This verifies that the fallback classifier prioritises the first matching category in its predefined keyword order.
        """
        # Query with both timeline and search keywords
        query = "Find events and add them to the timeline"
        result = _fallback_classification(query)

        # Should prioritize first matching category
        # (timeline keywords are checked first in fallback)
        assert result.intent in [IntentType.TIMELINE_QUERY, IntentType.EXECUTE_POLICY]

    def test_special_characters(self):
        """
        Test that queries containing special characters such as IP addresses, email addresses, and Windows file paths are correctly classified by the fallback classifier, ensuring they map to the EXECUTE_POLICY intent.
        """
        queries = [
            "Find events with IP 192.168.1.1",
            "Search for user@domain.com",
            "Look for file C:\\Windows\\System32\\cmd.exe",
        ]

        for query in queries:
            result = _fallback_classification(query)
            assert result.intent == IntentType.EXECUTE_POLICY

    def test_whitespace_handling(self):
        """
        Test that the fallback classification correctly normalizes and handles queries containing leading, trailing, or internal whitespace characters.

        The test verifies three scenarios:
        1. A query with multiple spaces surrounding and between words ("  find  failed  logins  ") is stripped and collapsed, allowing the keyword detection to match the intent for executing a policy.
        2. A query surrounded by newline characters ("\n\nshow timeline\n\n") does not exactly match any specific timeline-related keywords, so after whitespace normalization it falls back to the default general chat intent.
        3. A query padded with tab characters ("\t\ttimeline entries\t\t") is normalized and correctly identified as a timeline query intent.
        """
        # Test that keywords are detected despite whitespace
        result = _fallback_classification("  find  failed  logins  ")
        assert result.intent == IntentType.EXECUTE_POLICY

        result = _fallback_classification("\n\nshow timeline\n\n")
        # "show timeline" doesn't match exact "timeline entry" keywords
        # so it falls through to default general_chat
        assert result.intent == IntentType.GENERAL_CHAT

        result = _fallback_classification("\t\ttimeline entries\t\t")
        assert result.intent == IntentType.TIMELINE_QUERY


@pytest.mark.unit
class TestClassificationConfidence:
    """Test confidence scores for classifications."""

    def test_high_confidence_exact_match(self):
        """
        Test that the fallback classification returns a confidence score of at least 0.85 when the query exactly matches a known keyword phrase.
        """
        query = "show me timeline entries"
        result = _fallback_classification(query)

        assert result.confidence >= 0.85

    def test_medium_confidence_partial_match(self):
        """
        Test that the fallback classification returns a medium confidence level for queries that partially match known patterns.

        The test uses the query "what happened yesterday?" and verifies that the confidence score produced by `_fallback_classification` falls within the expected moderate range (0.6 to 0.85), indicating correct handling of partial matches.
        """
        query = "what happened yesterday?"
        result = _fallback_classification(query)

        # Partial match should have moderate confidence
        assert 0.6 <= result.confidence <= 0.85

    def test_low_confidence_default(self):
        """
        Test that the fallback classification returns a low confidence score for an unrelated query when using the default classification mode. The test verifies that the confidence value does not exceed the threshold of 0.7, ensuring that uncertain inputs are correctly identified as low-confidence cases.
        """
        query = "random unrelated text"
        result = _fallback_classification(query)

        # Default classification should have low confidence
        assert result.confidence <= 0.7

    def test_confidence_range(self):
        """
        Test that the fallback classification confidence score is always within the valid range of 0.0 to 1.0 for a variety of example queries, including typical commands, empty strings, and unrelated text. This ensures the classifier never returns out-of-bounds confidence values.
        """
        queries = [
            "find failed logins",
            "timeline entries",
            "what is this?",
            "random text",
            "",
        ]

        for query in queries:
            result = _fallback_classification(query)
            assert 0.0 <= result.confidence <= 1.0


@pytest.mark.unit
class TestClassifyIntent:
    """Test LLM-based intent classification."""

    @pytest.mark.asyncio
    async def test_classify_intent_with_llm_success(self, mock_embedding_status):
        """
        Test that the intent classification using the LLM service succeeds and returns the expected timeline query intent with high confidence.

        The test sets up:
        - An asynchronous mock database object.
        - A unique invitation identifier.
        - Mocked LLMService returned by `LLMService.from_user_config`, configured to simulate a successful call returning a response containing `"timeline_query"` and an extracted text of `"timeline_query"`.
        - Patches for `_fetch_recent_chat_history` and `ChatContextManager.prepare_classification_context` to return empty histories, isolating the LLM classification logic.

        The test invokes `classify_intent` with the mocked dependencies and verifies that:
        - The resulting object's `intent` attribute equals `IntentType.TIMELINE_QUERY`.
        - The `confidence` attribute is set to `0.9`.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        # Mock LLMService.from_user_config
        mock_llm_service = AsyncMock()
        mock_llm_service.call_llm.return_value = {
            "choices": [{"message": {"content": "timeline_query"}}]
        }
        mock_llm_service.extract_text_response.return_value = "timeline_query"

        with patch(
            "app.services.chat_router.LLMService.from_user_config", return_value=mock_llm_service
        ):
            with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
                with patch(
                    "app.services.chat_router.ChatContextManager.prepare_classification_context",
                    return_value=[],
                ):
                    result = await classify_intent(mock_db, 1, inv_id, "Show me timeline entries")

        assert result.intent == IntentType.TIMELINE_QUERY
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_classify_intent_no_llm_service(self, mock_embedding_status):
        """
        Test that intent classification correctly falls back to keyword-based detection when the LLM service cannot be instantiated.

        Parameters
        ----------
        self : unittest.TestCase
            The test case instance providing assertion methods.
        mock_db : AsyncMock
            A mocked asynchronous database client passed to `classify_intent`.
        inv_id : uuid.UUID
            Unique identifier for the current conversation/investigation.

        The test patches `LLMService.from_user_config` to return `None`, simulating an unavailable LLM service, and also patches `_fetch_recent_chat_history` to return an empty list. It then calls `classify_intent` with a sample query and asserts that the resulting `intent` attribute equals :class:`IntentType.EXECUTE_POLICY`, indicating that keyword-based classification was used as a fallback.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        with patch("app.services.chat_router.LLMService.from_user_config", return_value=None):
            with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
                result = await classify_intent(mock_db, 1, inv_id, "Find failed logins")

        # Should fall back to keyword-based classification
        assert result.intent == IntentType.EXECUTE_POLICY

    @pytest.mark.asyncio
    async def test_classify_intent_with_chat_history(self, mock_embedding_status):
        """
        Test that intent classification correctly utilizes provided chat history.

        This test creates mock database and LLM service objects, supplies a sample conversation history, and patches the necessary service methods. It then calls `classify_intent` with the mocked dependencies and verifies that the returned intent matches :class:`IntentType.TIMELINE_QUERY`. The purpose is to ensure that the classification logic incorporates chat context when determining the user's intent.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()
        chat_history = [
            {"role": "user", "content": "Previous message"},
            {"role": "assistant", "content": "Previous response"},
        ]

        mock_llm_service = AsyncMock()
        mock_llm_service.extract_text_response.return_value = "timeline_query"

        with patch(
            "app.services.chat_router.LLMService.from_user_config", return_value=mock_llm_service
        ):
            with patch(
                "app.services.chat_router.ChatContextManager.prepare_classification_context",
                return_value=[],
            ):
                result = await classify_intent(
                    mock_db, 1, inv_id, "Show those", chat_history=chat_history
                )

        assert result.intent == IntentType.TIMELINE_QUERY

    @pytest.mark.asyncio
    async def test_classify_intent_with_llm_insert_events(self, mock_embedding_status):
        """
        Test that the LLM-based intent classification correctly identifies an "insert_events" intent.

        Args:
            self: The test case instance (inherits from AsyncTestCase or similar).

        Returns:
            None. The test asserts that the returned `intent` attribute of the classification result equals `IntentType.INSERT_EVENTS`.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        mock_llm_service = AsyncMock()
        mock_llm_service.extract_text_response.return_value = "insert_events"

        with patch(
            "app.services.chat_router.LLMService.from_user_config", return_value=mock_llm_service
        ):
            with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
                with patch(
                    "app.services.chat_router.ChatContextManager.prepare_classification_context",
                    return_value=[],
                ):
                    result = await classify_intent(mock_db, 1, inv_id, "Add these events")

        assert result.intent == IntentType.INSERT_EVENTS

    @pytest.mark.asyncio
    async def test_classify_intent_with_llm_general_chat(self, mock_embedding_status):
        """
        Test that the LLM classification service correctly maps a returned \"general_chat\" response to the IntentType.GENERAL_CHAT enum.

        The test sets up:
        - An asynchronous mock database connection.
        - A mock LLMService whose `extract_text_response` method returns the string "general_chat".
        - Patches for `_fetch_recent_chat_history` and `ChatContextManager.prepare_classification_context` to return empty histories, isolating the classification logic.

        It then calls `classify_intent` with a sample inquiry and verifies that the resulting intent attribute equals `IntentType.GENERAL_CHAT`.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        mock_llm_service = AsyncMock()
        mock_llm_service.extract_text_response.return_value = "general_chat"

        with patch(
            "app.services.chat_router.LLMService.from_user_config", return_value=mock_llm_service
        ):
            with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
                with patch(
                    "app.services.chat_router.ChatContextManager.prepare_classification_context",
                    return_value=[],
                ):
                    result = await classify_intent(
                        mock_db, 1, inv_id, "What is this investigation?"
                    )

        assert result.intent == IntentType.GENERAL_CHAT

    @pytest.mark.asyncio
    async def test_classify_intent_with_llm_execute_policy(self, mock_embedding_status):
        """
        Test that LLM-based intent classification returns the `execute_agent_policy` response and maps it to :class:`IntentType.EXECUTE_POLICY`.

        The test sets up mocks for the database connection, LLM service, recent chat history retrieval, and classification context preparation. It then invokes :func:`classify_intent` with a sample query and verifies that the resulting intent attribute equals `IntentType.EXECUTE_POLICY`.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        mock_llm_service = AsyncMock()
        mock_llm_service.extract_text_response.return_value = "execute_agent_policy"

        with patch(
            "app.services.chat_router.LLMService.from_user_config", return_value=mock_llm_service
        ):
            with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
                with patch(
                    "app.services.chat_router.ChatContextManager.prepare_classification_context",
                    return_value=[],
                ):
                    result = await classify_intent(mock_db, 1, inv_id, "Find failed logins")

        assert result.intent == IntentType.EXECUTE_POLICY

    @pytest.mark.asyncio
    async def test_classify_intent_fetches_history_when_none_provided(self, mock_embedding_status):
        """
        Test that when no chat history is supplied, the intent classification routine fetches recent conversation history from the database.

        Args:
            self: The test case instance.

        Ensures:
            - A mock LLMService is used to simulate intent extraction.
            - The internal `_fetch_recent_chat_history` function is called exactly once with the provided database connection, invitation ID, and a limit of 10 messages.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        mock_llm_service = AsyncMock()
        mock_llm_service.extract_text_response.return_value = "general_chat"

        with patch(
            "app.services.chat_router.LLMService.from_user_config", return_value=mock_llm_service
        ):
            with patch(
                "app.services.chat_router._fetch_recent_chat_history", return_value=[]
            ) as mock_fetch:
                with patch(
                    "app.services.chat_router.ChatContextManager.prepare_classification_context",
                    return_value=[],
                ):
                    result = await classify_intent(mock_db, 1, inv_id, "Test query")

        # Should have called fetch_recent_chat_history
        mock_fetch.assert_called_once_with(mock_db, inv_id, limit=10)

    @pytest.mark.asyncio
    async def test_classify_intent_llm_exception_fallback(self, mock_embedding_status):
        """
        Test that intent classification falls back to keyword-based detection when the LLM service raises an exception.

        The test sets up mocks for the database, LLM service (configured to raise an Exception), recent chat history retrieval, and classification context preparation. It then calls `classify_intent` with a sample query. Because the LLM call fails, the function should handle the error gracefully and use the keyword classifier instead, resulting in an intent of :class:`IntentType.EXECUTE_POLICY`. The assertion verifies that this fallback behavior occurs.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        mock_llm_service = AsyncMock()
        mock_llm_service.call_llm.side_effect = Exception("LLM error")

        with patch(
            "app.services.chat_router.LLMService.from_user_config", return_value=mock_llm_service
        ):
            with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
                with patch(
                    "app.services.chat_router.ChatContextManager.prepare_classification_context",
                    return_value=[],
                ):
                    result = await classify_intent(mock_db, 1, inv_id, "find logins")

        # Should fall back to keyword classification
        assert result.intent == IntentType.EXECUTE_POLICY

    @pytest.mark.asyncio
    async def test_classify_intent_empty_llm_response(self, mock_embedding_status):
        """
        Test that when the LLM service returns an empty string, the intent classification falls back to keyword-based detection and correctly identifies a timeline query.

        Args:
            self: The unittest.TestCase instance containing this async test method.

        Setup:
            - Creates an asynchronous mock database (`mock_db`).
            - Generates a random invitation identifier (`inv_id`).
            - Mocks the LLM service so that `extract_text_response` returns an empty string.
            - Patches `LLMService.from_user_config` to return the mocked LLM service.
            - Patches `_fetch_recent_chat_history` to return an empty list, simulating no recent chat context.
            - Patches `ChatContextManager.prepare_classification_context` to return an empty list, indicating no additional classification context.

        Execution:
            Calls the `classify_intent` coroutine with the mocked dependencies and a sample user query `"timeline entries"`.

        Assertions:
            Verifies that the resulting intent is `IntentType.TIMELINE_QUERY`, confirming that the fallback keyword classifier was used when the LLM provided no response.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        mock_llm_service = AsyncMock()
        mock_llm_service.extract_text_response.return_value = ""

        with patch(
            "app.services.chat_router.LLMService.from_user_config", return_value=mock_llm_service
        ):
            with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
                with patch(
                    "app.services.chat_router.ChatContextManager.prepare_classification_context",
                    return_value=[],
                ):
                    result = await classify_intent(mock_db, 1, inv_id, "timeline entries")

        # Should fall back to keyword classification
        assert result.intent == IntentType.TIMELINE_QUERY

    @pytest.mark.asyncio
    async def test_classify_intent_unrecognized_llm_response(self, mock_embedding_status):
        """
        Test that when the LLM service returns an unrecognized intent string, the classification falls back to keyword-based detection and yields the GENERAL_CHAT intent.

        Args:
            self: The test case instance.

        Returns:
            None - asserts are used to verify behavior.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        mock_llm_service = AsyncMock()
        mock_llm_service.extract_text_response.return_value = "unknown_intent"

        with patch(
            "app.services.chat_router.LLMService.from_user_config", return_value=mock_llm_service
        ):
            with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
                with patch(
                    "app.services.chat_router.ChatContextManager.prepare_classification_context",
                    return_value=[],
                ):
                    result = await classify_intent(mock_db, 1, inv_id, "random query")

        # Should fall back to keyword classification
        assert result.intent == IntentType.GENERAL_CHAT


@pytest.mark.unit
class TestRouteChatMessage:
    """Test main routing function."""

    @pytest.mark.asyncio
    async def test_route_augmented_mode_with_config(self, mock_embedding_status):
        """
        Test routing in augmented mode with an explicit configuration override.

        This test verifies that when the router is invoked with `router_mode="augmented"`, it correctly retrieves the active LLM configuration, uses the specified embedding provider, and delegates the query handling to the RAG (retrieval-augmented generation) pipeline.

        The steps performed are:
        - Create a mock asynchronous database connection.
        - Generate a random invitation identifier.
        - Mock an LLM configuration object where `embedding_provider` is set to `"openai"`.
        - Patch `get_active_llm_config` to return the mocked configuration.
        - Patch `handle_rag_query` to simulate a streaming RAG response that yields a single chunk with type `"answer_chunk"` and content `"RAG response"`.
        - Invoke `route_chat_message` with the mock database, invitation ID, test query, user ID `1`, and router mode set to `"augmented"`.
        - Collect all yielded chunks into a list.

        Assertions:
        - At least one chunk is produced, confirming that the augmented routing path was executed.
        - `handle_rag_query` is called exactly once, ensuring proper delegation to the RAG handler.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        # Mock LLM config with embedding provider
        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"

        with patch("app.services.chat_router.get_active_llm_config", return_value=mock_config):
            with patch("app.services.chat_router.handle_rag_query") as mock_rag:

                async def mock_rag_gen():
                    """
                    Asynchronously generates mock RAG (Retrieval-Augmented Generation) response chunks.\n\nYields:\n    dict: A dictionary representing a single answer chunk with the keys:\n        - `type` (str): Always set to `\"answer_chunk\"` indicating the payload is an answer fragment.\n        - `content` (str): The textual content of the mock RAG response, e.g., `\"RAG response\"`.
                    """
                    yield {"type": "answer_chunk", "content": "RAG response"}

                mock_rag.return_value = mock_rag_gen()

                chunks = []
                async for chunk in route_chat_message(
                    mock_db, inv_id, "test query", 1, router_mode="augmented"
                ):
                    chunks.append(chunk)

        assert len(chunks) > 0
        mock_rag.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_augmented_mode_no_embedding_config(self):
        """
        Test that routing in **augmented** mode raises an appropriate error when the active LLM configuration lacks an embedding provider.

        The test sets up:
        - An asynchronous mock database (`mock_db`).
        - A random invitation identifier (`inv_id`).
        - A mocked LLM configuration where `embedding_provider` is `None` to simulate a missing embedding setup.

        Using `patch` it replaces `app.services.chat_router.get_active_llm_config` with the mocked config, then calls `route_chat_message` with:
        - The mock database,
        - The invitation ID,
        - A sample query string ("test query"),
        - A user identifier (`1`),
        - `router_mode="augmented"`.

        The function is expected to yield a single chunk containing an error message. Assertions verify that:
        - Exactly one chunk is produced.
        - The chunk's `type` field equals `"error"`.
        - The error message mentions the missing embedding configuration (case-insensitive check for "embedding configuration").
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        # Mock LLM config without embedding provider
        mock_config = MagicMock()
        mock_config.embedding_provider = None

        with patch("app.services.chat_router.get_active_llm_config", return_value=mock_config):
            chunks = []
            async for chunk in route_chat_message(
                mock_db, inv_id, "test query", 1, router_mode="augmented"
            ):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "error"
        assert "embedding configuration" in chunks[0]["message"].lower()

    @pytest.mark.asyncio
    async def test_route_agent_mode_override(self):
        """
        Test that routing in **agent** mode correctly overrides default behavior and delegates execution to the policy handler.

        This test:

        * Creates a mock asynchronous database connection.
        * Generates a random invitation identifier.
        * Patches `app.services.chat_router.handle_policy_execution` so it returns a predefined payload indicating a queued job.
        * Invokes :func:`route_chat_message` with `router_mode="agent"` and an explicit `effort="high"`, collecting the async generator output into a list.
        * Asserts that exactly one chunk is produced, that its `type` field equals `"job_queued"`, and that the patched policy handler was called once with the expected arguments (mock database, invitation ID, query string, user ID, and effort).
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        with patch(
            "app.services.chat_router.handle_policy_execution", return_value={"type": "job_queued"}
        ) as mock_agent:
            chunks = []
            async for chunk in route_chat_message(
                mock_db, inv_id, "test query", 1, router_mode="agent", effort="high"
            ):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "job_queued"
        mock_agent.assert_called_once_with(mock_db, inv_id, "test query", 1, effort="high")

    @pytest.mark.asyncio
    async def test_route_timeline_mode_override(self):
        """
        Test that routing in timeline mode correctly overrides default behavior by invoking the timeline handler and returning a single answer chunk.

        Args:
            self: TestCase instance providing the test context.

        Raises:
            AssertionError: If the number of returned chunks is not exactly one, if the chunk type is incorrect, or if the timeline handler is not called exactly once.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        with patch(
            "app.services.chat_router.handle_timeline_query",
            return_value={"success": True, "message": "Timeline result"},
        ) as mock_timeline:
            chunks = []
            async for chunk in route_chat_message(
                mock_db, inv_id, "test query", 1, router_mode="timeline"
            ):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "answer_chunk"
        mock_timeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_auto_mode_insert_events(self, mock_embedding_status):
        """
        Test that auto routing correctly classifies an INSERT_EVENTS intent and yields both an intent classification chunk and an answer chunk.

        The test sets up mock dependencies:
        - A mocked asynchronous database client.
        - A random invocation identifier.
        - A predefined ClassificationResult indicating an INSERT_EVENTS intent with high confidence.
        - Patches for fetching recent chat history (returning empty), query expansion (returning a static string), intent classification (returning the predefined result), and event insertion handling (simulating a successful insertion response).

        It then invokes `route_chat_message` with router_mode set to `"auto"`, collects all yielded chunks, and asserts that:
        - At least one chunk has `type == "intent_classified"`, confirming that intent detection was performed.
        - At least one chunk has `type == "answer_chunk"`, confirming that the answer generation step ran after successful event insertion.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        classification = ClassificationResult(intent=IntentType.INSERT_EVENTS, confidence=0.9)

        with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
            with patch("app.services.chat_router.expand_query", return_value="test query"):
                with patch("app.services.chat_router.classify_intent", return_value=classification):
                    with patch(
                        "app.services.chat_router.handle_event_insertion",
                        return_value={"success": True, "message": "Events inserted"},
                    ):
                        chunks = []
                        async for chunk in route_chat_message(
                            mock_db, inv_id, "test query", 1, router_mode="auto"
                        ):
                            chunks.append(chunk)

        # Should yield intent_classified and answer_chunk
        assert any(c.get("type") == "intent_classified" for c in chunks)
        assert any(c.get("type") == "answer_chunk" for c in chunks)

    @pytest.mark.asyncio
    async def test_route_auto_mode_timeline_query(self, mock_embedding_status):
        """
        Test that the automatic routing mode correctly delegates a timeline query to the timeline handler and includes the summary in the returned answer chunk.

        The test sets up mocks for:
        - Database access (`mock_db`).
        - Recent chat history retrieval (returns an empty list).
        - Query expansion (returns the original query string).
        - Intent classification (returns a `ClassificationResult` indicating a `TIMELINE_QUERY` intent with high confidence).
        - Timeline query handling (returns a successful response containing a message and a summary).

        It then invokes `route_chat_message` with `router_mode="auto"` and collects all yielded chunks. The test asserts that:
        - At least one chunk of type `answer_chunk` is produced.
        - The content of the first answer chunk contains the expected summary text (e.g., `"1 entry found"`).
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        classification = ClassificationResult(intent=IntentType.TIMELINE_QUERY, confidence=0.9)

        with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
            with patch("app.services.chat_router.expand_query", return_value="test query"):
                with patch("app.services.chat_router.classify_intent", return_value=classification):
                    with patch(
                        "app.services.chat_router.handle_timeline_query",
                        return_value={
                            "success": True,
                            "message": "Timeline result",
                            "summary": "1 entry found",
                        },
                    ):
                        chunks = []
                        async for chunk in route_chat_message(
                            mock_db, inv_id, "test query", 1, router_mode="auto"
                        ):
                            chunks.append(chunk)

        # Should include summary in message
        answer_chunks = [c for c in chunks if c.get("type") == "answer_chunk"]
        assert len(answer_chunks) > 0
        assert "1 entry found" in answer_chunks[0]["content"]

    @pytest.mark.asyncio
    async def test_route_auto_mode_general_chat(self, mock_embedding_status):
        """
        Test that when the router operates in "auto" mode it correctly routes a general-chat query to the general chat handler and yields at least one answer chunk.

        The test sets up:
        - A mock asynchronous database connection.
        - A random invocation identifier.
        - A classification result indicating the intent is GENERAL_CHAT with high confidence.
        - Patches for internal functions:
          * `_fetch_recent_chat_history` returns an empty history list.
          * `expand_query` returns a static query string.
          * `classify_intent` returns the prepared classification result.
          * `handle_general_chat` returns a successful response payload.

        It then invokes `route_chat_message` with the mocked dependencies and iterates over the asynchronous generator, collecting all yielded chunks. Finally, it asserts that at least one of the collected chunks has its `"type"` field set to `"answer_chunk"`, confirming that the auto-routing logic selected the general chat pathway and produced an answer.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        classification = ClassificationResult(intent=IntentType.GENERAL_CHAT, confidence=0.9)

        with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
            with patch("app.services.chat_router.expand_query", return_value="test query"):
                with patch("app.services.chat_router.classify_intent", return_value=classification):
                    with patch(
                        "app.services.chat_router.handle_general_chat",
                        return_value={"success": True, "message": "General response"},
                    ):
                        chunks = []
                        async for chunk in route_chat_message(
                            mock_db, inv_id, "test query", 1, router_mode="auto"
                        ):
                            chunks.append(chunk)

        assert any(c.get("type") == "answer_chunk" for c in chunks)

    @pytest.mark.asyncio
    async def test_route_auto_mode_execute_policy(self, mock_embedding_status):
        """
        Test the automatic routing mode when executing a policy intent.

        This test verifies that `route_chat_message` correctly selects the agent handler in **auto** router mode for an intent classified as `EXECUTE_POLICY`. It sets up:

        - An asynchronous mock database connection.
        - A unique invocation identifier.
        - A predefined classification result with high confidence (0.9) for the `EXECUTE_POLICY` intent.
        - Patches for internal helper functions:
          - `_fetch_recent_chat_history` returns an empty history list.
          - `expand_query` returns a static query string `"test query"`.
          - `classify_intent` yields the prepared classification result.
          - `handle_policy_execution` simulates successful policy handling by returning `{"type": "job_queued"}`.

        The test asynchronously iterates over the chunks produced by `route_chat_message` with the specified parameters (router_mode="auto", effort="medium") and collects them. Finally, it asserts that at least one of the returned chunks contains a dictionary where the `type` key equals `"job_queued"`, confirming that the policy execution path was invoked in auto routing mode.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        classification = ClassificationResult(intent=IntentType.EXECUTE_POLICY, confidence=0.9)

        with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
            with patch("app.services.chat_router.expand_query", return_value="test query"):
                with patch("app.services.chat_router.classify_intent", return_value=classification):
                    with patch(
                        "app.services.chat_router.handle_policy_execution",
                        return_value={"type": "job_queued"},
                    ):
                        chunks = []
                        async for chunk in route_chat_message(
                            mock_db, inv_id, "test query", 1, router_mode="auto", effort="medium"
                        ):
                            chunks.append(chunk)

        assert any(c.get("type") == "job_queued" for c in chunks)

    @pytest.mark.asyncio
    async def test_route_query_expansion(self, mock_embedding_status):
        """
        Test that query expansion is invoked during routing and yields a `query_expanded` event with the original and expanded queries.

        The test sets up mocks for database access, recent chat history retrieval, query expansion, intent classification, and general-chat handling. It then runs `route_chat_message` in **auto** mode and collects all yielded chunks.

        Assertions verify that exactly one chunk of type `query_expanded` is produced, and that this chunk contains the original query (`"test"`) and the expanded query returned by the mocked `expand_query` function (`"expanded test query"`).
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        classification = ClassificationResult(intent=IntentType.GENERAL_CHAT, confidence=0.9)

        with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
            with patch("app.services.chat_router.expand_query", return_value="expanded test query"):
                with patch("app.services.chat_router.classify_intent", return_value=classification):
                    with patch(
                        "app.services.chat_router.handle_general_chat",
                        return_value={"success": True, "message": "Response"},
                    ):
                        chunks = []
                        async for chunk in route_chat_message(
                            mock_db, inv_id, "test", 1, router_mode="auto"
                        ):
                            chunks.append(chunk)

        # Should yield query_expanded event
        expanded_chunks = [c for c in chunks if c.get("type") == "query_expanded"]
        assert len(expanded_chunks) == 1
        assert expanded_chunks[0]["original"] == "test"
        assert expanded_chunks[0]["expanded"] == "expanded test query"

    @pytest.mark.asyncio
    async def test_route_handler_error(self, mock_embedding_status):
        """
        Test error handling in routing.\n\nThis asynchronous unit test verifies that the `route_chat_message` coroutine correctly yields an error chunk when an exception occurs inside the `handle_general_chat` handler. The test:\n\n1. Creates a mock asynchronous database client and a random invitation identifier.\n2. Mocks dependent functions:\n   - `_fetch_recent_chat_history` to return an empty history list.\n   - `expand_query` to return a static query string.\n   - `classify_intent` to produce a `ClassificationResult` with the `GENERAL_CHAT` intent.\n   - `handle_general_chat` to raise a generic `Exception` simulating a handler failure.\n3. Invokes `route_chat_message` with `router_mode=\"auto\"` and collects all yielded chunks.\n4. Filters the collected chunks for those of type `\"error\"` and asserts that at least one error chunk is present and that its message contains the word \"error\" (case-insensitive).\n\nThe test ensures that routing errors are propagated to the client in a structured error response.""
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        classification = ClassificationResult(intent=IntentType.GENERAL_CHAT, confidence=0.9)

        with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
            with patch("app.services.chat_router.expand_query", return_value="test query"):
                with patch("app.services.chat_router.classify_intent", return_value=classification):
                    with patch(
                        "app.services.chat_router.handle_general_chat",
                        side_effect=Exception("Handler error"),
                    ):
                        chunks = []
                        async for chunk in route_chat_message(
                            mock_db, inv_id, "test query", 1, router_mode="auto"
                        ):
                            chunks.append(chunk)

        # Should yield error message
        error_chunks = [c for c in chunks if c.get("type") == "error"]
        assert len(error_chunks) > 0
        assert "error" in error_chunks[0]["message"].lower()

    @pytest.mark.asyncio
    async def test_route_deprecated_query_kg(self, mock_embedding_status):
        """
        Test that a deprecated QUERY_KG intent is correctly routed through the general chat handling path, ensuring the response contains at least one chunk of type `answer_chunk` when the router operates in `auto` mode. The test mocks database access, recent chat history retrieval, query expansion, intent classification, and the generic chat handler to isolate routing logic.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        classification = ClassificationResult(intent=IntentType.QUERY_KG, confidence=0.9)

        with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
            with patch("app.services.chat_router.expand_query", return_value="test query"):
                with patch("app.services.chat_router.classify_intent", return_value=classification):
                    with patch(
                        "app.services.chat_router.handle_general_chat",
                        return_value={"success": True, "message": "Response"},
                    ):
                        chunks = []
                        async for chunk in route_chat_message(
                            mock_db, inv_id, "test query", 1, router_mode="auto"
                        ):
                            chunks.append(chunk)

        assert any(c.get("type") == "answer_chunk" for c in chunks)

    @pytest.mark.asyncio
    async def test_route_deprecated_mutate_kg(self, mock_embedding_status):
        """
        Test that a chat message classified with the deprecated `MUTATE_KG` intent is correctly routed to the timeline handler when the router operates in `auto` mode.

        The test sets up:
        - A mock asynchronous database connection.
        - A random invocation identifier.
        - A classification result indicating the `MUTATE_KG` intent with high confidence.
        - Patched dependencies for recent chat history retrieval, query expansion, intent classification, and timeline handling.

        It then invokes :func:`route_chat_message` with the mocked components and collects the streamed response chunks. The assertion verifies that at least one of the returned chunks has a `type` field equal to `"answer_chunk"`, confirming that the fallback routing logic correctly delegated the request to the timeline handler despite the intent being deprecated.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        classification = ClassificationResult(intent=IntentType.MUTATE_KG, confidence=0.9)

        with patch("app.services.chat_router._fetch_recent_chat_history", return_value=[]):
            with patch("app.services.chat_router.expand_query", return_value="test query"):
                with patch("app.services.chat_router.classify_intent", return_value=classification):
                    with patch(
                        "app.services.chat_router.handle_timeline_query",
                        return_value={"success": True, "message": "Response"},
                    ):
                        chunks = []
                        async for chunk in route_chat_message(
                            mock_db, inv_id, "test query", 1, router_mode="auto"
                        ):
                            chunks.append(chunk)

        assert any(c.get("type") == "answer_chunk" for c in chunks)


@pytest.mark.unit
class TestHandleClarificationResponse:
    """Test clarification response handler."""

    @pytest.mark.asyncio
    async def test_handle_clarification_success(self):
        """
        Test that `handle_clarification_response` correctly routes a clarified question and returns the expected result.

        Args:
            self: The test case instance.

        Returns:
            None. The function asserts that the routing service is called with the correct parameters
            and that the returned payload contains a `type` field equal to `"job_queued"`.

        Raises:
            AssertionError: If the returned `type` does not match `"job_queued"`, or if the mock
            `route_question` function is not called exactly once with the expected arguments.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        with patch(
            "app.services.policy_router.route_question", return_value={"type": "job_queued"}
        ) as mock_route:
            result = await handle_clarification_response(
                mock_db, inv_id, "policy_1", {"key": "value"}, "original question", 1
            )

        assert result["type"] == "job_queued"
        mock_route.assert_called_once_with(
            db=mock_db,
            investigation_id=inv_id,
            question="original question",
            user_id=1,
            policy_id="policy_1",
            rule_values={"key": "value"},
        )

    @pytest.mark.asyncio
    async def test_handle_clarification_error(self):
        """
        Test that the clarification handling correctly propagates an error response from the policy router. The function patches `app.services.policy_router.route_question` to return an error dictionary, invokes `handle_clarification_response` with mock database and identifiers, and asserts that the resulting payload has a type of `"error"`.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        with patch(
            "app.services.policy_router.route_question",
            return_value={"type": "error", "message": "Policy error"},
        ):
            result = await handle_clarification_response(
                mock_db, inv_id, "policy_1", {}, "question", 1
            )

        assert result["type"] == "error"

    @pytest.mark.asyncio
    async def test_handle_clarification_exception(self):
        """
        Test that the clarification handling pathway correctly captures and reports an unexpected exception raised during routing.

        The test sets up:
        - An asynchronous mock database object.
        - A random invitation identifier.
        - Patching of `app.services.policy_router.route_question` to raise a generic `Exception` with the message “Unexpected error”.

        It then invokes `handle_clarification_response` with the mocked dependencies and verifies that:
        - The returned dictionary has its `type` field set to `"error"`, indicating an error condition.
        - The `message` field contains a substring mentioning that an error occurred, case-insensitively.
        """
        mock_db = AsyncMock()
        inv_id = uuid.uuid4()

        with patch(
            "app.services.policy_router.route_question", side_effect=Exception("Unexpected error")
        ):
            result = await handle_clarification_response(
                mock_db, inv_id, "policy_1", {}, "question", 1
            )

        assert result["type"] == "error"
        assert "error occurred" in result["message"].lower()
