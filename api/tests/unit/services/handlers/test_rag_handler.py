"""
Unit tests for rag_handler module.

Tests RAG query handling with vector similarity search.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import numpy as np

from app.services.handlers.rag_handler import (
    _deduplicate_and_rerank,
    persist_rag_tool_executions,
    handle_rag_query,
    _expand_query_with_llm,
)
from app.services.rag.retriever import EmbeddingChunk


@pytest.mark.unit
class TestDeduplicateAndRerank:
    """Test _deduplicate_and_rerank function."""

    def test_deduplicate_identical_chunks(self):
        """
        Test deduplication of identical chunks by keeping only the highest-scoring instance.

        Creates two `EmbeddingChunk` objects with identical `text` but different scores.
        Calls `_deduplicate_and_rerank` with a generous `top_k` value and asserts that:
        - The result contains a single chunk, confirming duplicate removal.
        - The retained chunk has the higher score (0.9), verifying that the function prefers higher-scoring duplicates.
        """
        chunks = [
            EmbeddingChunk(id=1, owner_type="chat", owner_id=100, text="Text 1", score=0.9),
            EmbeddingChunk(
                id=2, owner_type="chat", owner_id=100, text="Text 1", score=0.8
            ),  # Duplicate
        ]

        result = _deduplicate_and_rerank(chunks, top_k=10)

        # Should keep only the higher scoring one
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_deduplicate_keeps_highest_score(self):
        """
        Test that the deduplication routine retains only the highest-scoring chunk when multiple chunks share the same owner attributes.

        The test constructs three `EmbeddingChunk` instances with identical `owner_type`, `owner_id` and `text` values but differing `score` fields. It then calls `_deduplicate_and_rerank` with a generous `top_k` limit, expecting the function to collapse these duplicates into a single entry.

        Assertions verify that:
        - The resulting list contains exactly one chunk.
        - The retained chunk has the maximum score (0.9) among the inputs.
        """
        chunks = [
            EmbeddingChunk(id=1, owner_type="chat", owner_id=100, text="Text", score=0.7),
            EmbeddingChunk(id=2, owner_type="chat", owner_id=100, text="Text", score=0.9),
            EmbeddingChunk(id=3, owner_type="chat", owner_id=100, text="Text", score=0.8),
        ]

        result = _deduplicate_and_rerank(chunks, top_k=10)

        assert len(result) == 1
        assert result[0].score == 0.9

    def test_rerank_by_score(self):
        """
        Test that the `_deduplicate_and_rerank` helper sorts a list of `EmbeddingChunk` objects in descending order by their `score` attribute and returns all items when `top_k` exceeds the number of chunks. The test creates three chunks with distinct scores (0.5, 0.9, 0.7), invokes the function with `top_k=10`, and asserts that the result contains three elements ordered from highest to lowest score (0.9, 0.7, 0.5).
        """
        chunks = [
            EmbeddingChunk(id=1, owner_type="chat", owner_id=1, text="Low", score=0.5),
            EmbeddingChunk(id=2, owner_type="chat", owner_id=2, text="High", score=0.9),
            EmbeddingChunk(id=3, owner_type="chat", owner_id=3, text="Medium", score=0.7),
        ]

        result = _deduplicate_and_rerank(chunks, top_k=10)

        assert len(result) == 3
        assert result[0].score == 0.9  # Highest first
        assert result[1].score == 0.7
        assert result[2].score == 0.5

    def test_respects_top_k_limit(self):
        """
        Test that the deduplication and reranking helper respects the `top_k` argument by returning only the requested number of highest-scoring chunks and preserving descending score order.
        """
        chunks = [
            EmbeddingChunk(
                id=i, owner_type="chat", owner_id=i, text=f"Text {i}", score=1.0 - i * 0.1
            )
            for i in range(10)
        ]

        result = _deduplicate_and_rerank(chunks, top_k=3)

        assert len(result) == 3
        # Should be top 3 scores
        assert result[0].score >= result[1].score >= result[2].score

    def test_empty_chunks(self):
        """
        Test that deduplication and reranking on an empty list of chunks returns an empty list without errors. This verifies the function handles the edge case where no input data is provided.
        """
        result = _deduplicate_and_rerank([], top_k=10)

        assert result == []

    def test_different_owner_types_not_deduplicated(self):
        """
        Test that `_deduplicate_and_rerank` retains chunks with different `owner_type` values, ensuring they are not considered duplicates and both appear in the returned list.
        """
        chunks = [
            EmbeddingChunk(id=1, owner_type="chat", owner_id=100, text="Text", score=0.9),
            EmbeddingChunk(id=2, owner_type="timeline", owner_id=100, text="Text", score=0.8),
        ]

        result = _deduplicate_and_rerank(chunks, top_k=10)

        # Should keep both (different owner_type)
        assert len(result) == 2


@pytest.mark.unit
class TestPersistRAGToolExecutions:
    """Test persist_rag_tool_executions function."""

    async def test_persist_with_expansion_and_chunks(self):
        """
        Test persisting both expansion and retrieval executions.

        This asynchronous unit test verifies that `persist_rag_tool_executions` correctly creates and stores two separate RAG tool execution records-one for the query expansion step and one for the chunk retrieval step-when provided with a message identifier, an empty event sequence, a list of expanded terms, and a collection of chunk metadata.

        The test uses an `AsyncMock` database object to capture calls to `add` and `flush`, assigning sequential execution IDs via a side-effect function. After invoking the persistence helper, it asserts that exactly two execution IDs are returned, that the mock database's `add` method was called twice (once per execution), and that `flush` was also invoked twice to simulate committing each record.
        """
        db = AsyncMock()
        message_id = 1

        event_sequence = []
        expanded_terms = ["term1", "term2", "term3"]
        chunks_data = [
            {"owner_type": "chat", "owner_id": 1, "text": "Text 1", "score": 0.9},
            {"owner_type": "timeline", "owner_id": 2, "text": "Text 2", "score": 0.8},
        ]

        # Mock flush to simulate ID assignment
        mock_tool1 = MagicMock()
        mock_tool1.execution_id = 100
        mock_tool2 = MagicMock()
        mock_tool2.execution_id = 101

        execution_id_counter = 100

        def add_side_effect(obj):
            """
            Adds a unique execution identifier to the given object as a side effect.\n\nParameters\n----------\nobj : any\n    The target object that will receive an `execution_id` attribute.\n\nSide Effects\n------------\n- Assigns `obj.execution_id` with the current value of the enclosing\n  `execution_id_counter`.\n- Increments `execution_id_counter` so subsequent calls assign a new,\n  sequential identifier.\n\nNotes\n-----\nThis function relies on the presence of a mutable `execution_id_counter`\nvariable in the surrounding scope (e.g., defined with `nonlocal` or\n`global`). It is intended for internal use where objects need to be\ntracked uniquely during execution.
            """
            nonlocal execution_id_counter
            obj.execution_id = execution_id_counter
            execution_id_counter += 1

        db.add = MagicMock(side_effect=add_side_effect)

        execution_ids = await persist_rag_tool_executions(
            db=db,
            message_id=message_id,
            event_sequence=event_sequence,
            expanded_terms=expanded_terms,
            chunks_data=chunks_data,
        )

        # Should create 2 executions (expansion + retrieval)
        assert len(execution_ids) == 2
        assert db.add.call_count == 2
        assert db.flush.call_count == 2

    async def test_persist_only_chunks(self):
        """
        Test case for persisting only retrieval-type RAG tool executions without any query expansion.\n\nSets up an asynchronous mock database and invokes `persist_rag_tool_executions` with an empty `expanded_terms` list and a single chunk representing a retrieval result. Verifies that exactly one execution record is created (the retrieval step) and that the database `add` method is called once, with the generated execution receiving an `execution_id` of `100` via the side-effect mock. The test asserts both the length of the returned `execution_ids` list and the call count on the mocked `add` method.
        """
        db = AsyncMock()
        message_id = 1

        event_sequence = []
        expanded_terms = []  # No expansion
        chunks_data = [
            {"owner_type": "chat", "owner_id": 1, "text": "Text 1", "score": 0.9},
        ]

        def add_side_effect(obj):
            """
            Adds a side-effect attribute to the given object.

            Parameters
            ----------
            obj : object
                The target object that will receive a new attribute.

            Side Effects
            ------------
            Sets `obj.execution_id` to `100`.

            Returns
            -------
            None

            Raises
            ------
            AttributeError
                If `obj` does not allow setting new attributes.
            """
            obj.execution_id = 100

        db.add = MagicMock(side_effect=add_side_effect)

        execution_ids = await persist_rag_tool_executions(
            db=db,
            message_id=message_id,
            event_sequence=event_sequence,
            expanded_terms=expanded_terms,
            chunks_data=chunks_data,
        )

        # Should create only 1 execution (retrieval)
        assert len(execution_ids) == 1
        assert db.add.call_count == 1

    async def test_persist_only_expansion(self):
        """
        Test that persisting only query expansion without any chunk data creates a single RAG tool execution entry and calls the database add method exactly once. It verifies the returned list of execution IDs contains one element and that the mock DB's add method was invoked a single time.
        """
        db = AsyncMock()
        message_id = 1

        event_sequence = []
        expanded_terms = ["term1", "term2"]
        chunks_data = []  # No chunks

        def add_side_effect(obj):
            """
            Adds a side-effect attribute to the given object.

            The function assigns an `execution_id` attribute with a fixed value of `100` to
            the supplied `obj`. This is primarily intended for use in tests where a mock
            object needs to simulate having been processed by a component that records an
            execution identifier.

            Args:
                obj: Any mutable Python object that can have attributes set on it (e.g., an
                    instance of a class or a SimpleNamespace).

            Raises:
                AttributeError: If `obj` does not allow setting new attributes.
            """
            obj.execution_id = 100

        db.add = MagicMock(side_effect=add_side_effect)

        execution_ids = await persist_rag_tool_executions(
            db=db,
            message_id=message_id,
            event_sequence=event_sequence,
            expanded_terms=expanded_terms,
            chunks_data=chunks_data,
        )

        # Should create only 1 execution (expansion)
        assert len(execution_ids) == 1
        assert db.add.call_count == 1

    async def test_persist_nothing(self):
        """
        Test that persisting tool executions does nothing when no tools were used: creates an AsyncMock database, calls persist_rag_tool_executions with empty event sequence, expanded terms, and chunk data, then asserts that the returned list of execution IDs is empty and that the database's add method was never called.
        """
        db = AsyncMock()
        message_id = 1

        execution_ids = await persist_rag_tool_executions(
            db=db, message_id=message_id, event_sequence=[], expanded_terms=[], chunks_data=[]
        )

        # Should create no executions
        assert len(execution_ids) == 0
        assert db.add.call_count == 0

    async def test_persist_handles_exception(self):
        """
        Test that persisting RAG tool executions propagates exceptions raised by the database flush operation, ensuring error handling is correctly triggered when a database error occurs during persistence.
        """
        db = AsyncMock()
        db.flush = AsyncMock(side_effect=Exception("Database error"))
        message_id = 1

        expanded_terms = ["term1"]
        chunks_data = []

        with pytest.raises(Exception, match="Database error"):
            await persist_rag_tool_executions(
                db=db,
                message_id=message_id,
                event_sequence=[],
                expanded_terms=expanded_terms,
                chunks_data=chunks_data,
            )

    async def test_persist_creates_correct_summaries(self):
        """
        Test that `persist_rag_tool_executions` creates and stores the correct tool execution summaries.\n\nThe test sets up an asynchronous mock database (`db`) and defines a message identifier, expanded query terms, and a list of chunk data representing retrieved sources. It then configures the mock's `add` method to assign incremental `execution_id` values and record each added tool execution object in `added_tools`.\n\nAfter invoking `persist_rag_tool_executions` with the prepared inputs, the test asserts that:\n\n* Exactly two tool executions were added - one for query expansion and one for source retrieval.\n* The first added tool has `tool_name` equal to `\"expand_query\"`, its `result_summary` mentions the three search terms, and it includes a specific expanded term (e.g., `lsass.exe`).\n* The second added tool has `tool_name` equal to `\"retrieve_sources\"`, its `display_name` contains the phrase `\"2 results\"`, and its `result` dictionary holds a `sources` list of length two.\n\nThis verifies that the persistence layer correctly records both the expansion and retrieval steps with appropriate metadata.
        """
        db = AsyncMock()
        message_id = 1

        expanded_terms = ["lsass.exe", "mimikatz", "credential"]
        chunks_data = [
            {"owner_type": "chat", "owner_id": 1, "text": "A" * 100, "score": 0.9},
            {"owner_type": "timeline", "owner_id": 2, "text": "B" * 100, "score": 0.8},
        ]

        # Track what was added
        added_tools = []
        execution_id_counter = 100

        def add_side_effect(obj):
            """
            Adds a side-effect object to the current execution context.

            This helper assigns a unique `execution_id` to *obj*, increments the internal
            counter used for generating subsequent identifiers, and records the object in
            the list of added tools.

            Args:
                obj: An object that will receive an `execution_id` attribute. The object
                     is expected to be mutable so the identifier can be attached.

            Side Effects:
                - Modifies `obj.execution_id` by setting it to the current value of
                  `execution_id_counter`.
                - Increments the non-local `execution_id_counter` for future calls.
                - Appends `obj` to the surrounding `added_tools` collection.
            """
            nonlocal execution_id_counter
            obj.execution_id = execution_id_counter
            execution_id_counter += 1
            added_tools.append(obj)

        db.add = MagicMock(side_effect=add_side_effect)

        await persist_rag_tool_executions(
            db=db,
            message_id=message_id,
            event_sequence=[],
            expanded_terms=expanded_terms,
            chunks_data=chunks_data,
        )

        # Verify expansion tool
        assert len(added_tools) == 2
        assert added_tools[0].tool_name == "expand_query"
        assert "3 search terms" in added_tools[0].result_summary
        assert "lsass.exe" in added_tools[0].result_summary

        # Verify retrieval tool
        assert added_tools[1].tool_name == "retrieve_sources"
        assert "2 results" in added_tools[1].display_name
        assert len(added_tools[1].result["sources"]) == 2


@pytest.mark.unit
class TestExpandQueryWithLLM:
    """Test _expand_query_with_llm function."""

    @pytest.mark.asyncio
    async def test_expand_query_success(self):
        """
        Test that query expansion using the LLM service succeeds and returns a list of extracted terms.

        The test patches `LLMConfig.from_db_config` and `LLMService` to provide a mock LLM service whose
        `extract_text_response` coroutine returns a comma-separated string of terms. It then calls
        `_expand_query_with_llm` with a sample query ("credential access") and asserts that:

        * The returned list contains exactly four items.
        * Specific expected terms such as `lsass.exe` and `mimikatz` are present in the result.
        """
        mock_config = MagicMock()

        with patch("app.services.handlers.rag_handler.LLMConfig.from_db_config") as mock_llm_config:
            with patch("app.services.handlers.rag_handler.LLMService") as MockLLMService:
                mock_service = AsyncMock()
                mock_service.extract_text_response.return_value = (
                    "lsass.exe, mimikatz, sam database, credential dumping"
                )
                MockLLMService.return_value = mock_service

                terms = await _expand_query_with_llm("credential access", mock_config)

        assert len(terms) == 4
        assert "lsass.exe" in terms
        assert "mimikatz" in terms

    @pytest.mark.asyncio
    async def test_expand_query_limits_to_7_terms(self):
        """
        Test that query expansion via the LLM service respects the maximum limit of seven terms.

        The test patches the configuration loader and the LLM service to simulate extracting ten comma-separated terms from a mock response. It then invokes `_expand_query_with_llm` with a sample query and verifies that the resulting list is truncated to exactly seven items, ensuring the implementation correctly enforces the term limit.
        """
        mock_config = MagicMock()

        with patch("app.services.handlers.rag_handler.LLMConfig.from_db_config"):
            with patch("app.services.handlers.rag_handler.LLMService") as MockLLMService:
                mock_service = AsyncMock()
                # Return 10 terms
                mock_service.extract_text_response.return_value = (
                    "term1, term2, term3, term4, term5, term6, term7, term8, term9, term10"
                )
                MockLLMService.return_value = mock_service

                terms = await _expand_query_with_llm("test query", mock_config)

        # Should limit to 7
        assert len(terms) == 7

    @pytest.mark.asyncio
    async def test_expand_query_empty_response(self):
        """
        Test that _expand_query_with_llm correctly handles an empty response from the LLM service by returning an empty list of terms. The function patches LLMConfig.from_db_config and replaces LLMService with a mock that returns an empty string for extract_text_response, then asserts that the resulting term list is empty.
        """
        mock_config = MagicMock()

        with patch("app.services.handlers.rag_handler.LLMConfig.from_db_config"):
            with patch("app.services.handlers.rag_handler.LLMService") as MockLLMService:
                mock_service = AsyncMock()
                mock_service.extract_text_response.return_value = ""
                MockLLMService.return_value = mock_service

                terms = await _expand_query_with_llm("test", mock_config)

        assert terms == []

    @pytest.mark.asyncio
    async def test_expand_query_exception(self):
        """
        Test that _expand_query_with_llm gracefully handles exceptions raised by the LLM service and returns an empty list instead of propagating the error. The test mocks LLMConfig.from_db_config and replaces LLMService with an AsyncMock whose call_llm method raises a generic Exception, then verifies that the function under test returns [] when an error occurs.
        """
        mock_config = MagicMock()

        with patch("app.services.handlers.rag_handler.LLMConfig.from_db_config"):
            with patch("app.services.handlers.rag_handler.LLMService") as MockLLMService:
                mock_service = AsyncMock()
                mock_service.call_llm.side_effect = Exception("LLM error")
                MockLLMService.return_value = mock_service

                terms = await _expand_query_with_llm("test", mock_config)

        # Should return empty list on error
        assert terms == []

    @pytest.mark.asyncio
    async def test_expand_query_strips_whitespace(self):
        """
        Test that the query expansion logic removes surrounding whitespace from each term returned by the LLM service.

        The test sets up a mock configuration and patches the `LLMConfig.from_db_config` and `LLMService` classes used within `_expand_query_with_llm`.
        A mocked `extract_text_response` method returns a comma-separated string where each term is padded with spaces.

        After invoking `_expand_query_with_llm`, the test asserts that every term in the resulting list has been stripped of leading and trailing whitespace, ensuring the function correctly cleans up LLM output before further processing.
        """
        mock_config = MagicMock()

        with patch("app.services.handlers.rag_handler.LLMConfig.from_db_config"):
            with patch("app.services.handlers.rag_handler.LLMService") as MockLLMService:
                mock_service = AsyncMock()
                mock_service.extract_text_response.return_value = "  term1  ,  term2  ,  term3  "
                MockLLMService.return_value = mock_service

                terms = await _expand_query_with_llm("test", mock_config)

        assert all(term == term.strip() for term in terms)


@pytest.mark.unit
class TestHandleRAGQuery:
    """Test handle_rag_query function."""

    @pytest.mark.asyncio
    async def test_handle_rag_no_llm_config(self):
        """
        Test that `handle_rag_query` returns an error chunk when no active LLM configuration can be retrieved.

        The test sets up a mock asynchronous database connection and a random investigation ID, then patches
        `app.services.handlers.rag_handler.get_active_llm_config` to return `None` (simulating the absence of a configured LLM).

        It invokes `handle_rag_query` with a sample query and a limit of one result, collects all yielded chunks,
        and asserts that:

        * Exactly one chunk is produced.
        * The chunk's `type` field equals `"error"`.
        * The `content` field contains the message `"No active LLM configuration"`, indicating the expected error condition.
        """
        db = AsyncMock()
        inv_id = uuid4()

        with patch("app.services.handlers.rag_handler.get_active_llm_config", return_value=None):
            chunks = []
            async for chunk in handle_rag_query(db, inv_id, "test query", 1):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "error"
        assert "No active LLM configuration" in chunks[0]["content"]

    @pytest.mark.asyncio
    async def test_handle_rag_no_embedding_provider(self):
        """
        Test that `handle_rag_query` yields an error chunk when the active LLM configuration lacks an embedding provider. The test patches `get_active_llm_config` to return a config with `embedding_provider` set to `None` and then iterates over the async generator returned by `handle_rag_query`. It asserts that exactly one chunk is produced, that its type is `"error"`, and that the error message mentions missing embedding configuration.
        """
        db = AsyncMock()
        inv_id = uuid4()

        mock_config = MagicMock()
        mock_config.embedding_provider = None

        with patch(
            "app.services.handlers.rag_handler.get_active_llm_config", return_value=mock_config
        ):
            chunks = []
            async for chunk in handle_rag_query(db, inv_id, "test query", 1):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "error"
        assert "embedding configuration" in chunks[0]["content"].lower()

    @pytest.mark.asyncio
    async def test_handle_rag_no_embedding_api_url(self):
        """
        Test that handle_rag_query raises an error when the embedding provider is configured without an API URL.

        The test sets up:
        - An async mock database (`db`).
        - A random invitation ID (`inv_id`).
        - A configuration where `embedding_provider` is set to "openai" but `embedding_api_url` is `None`.

        It patches `app.services.handlers.rag_handler.get_active_llm_config` to return the incomplete config, then iterates over the asynchronous generator returned by `handle_rag_query`. The collected chunks are examined to ensure:
        - Exactly one chunk is produced.
        - The chunk type is `"error"`.
        - The error message contains the phrase `"API URL"` indicating the missing configuration.
        """
        db = AsyncMock()
        inv_id = uuid4()

        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = None

        with patch(
            "app.services.handlers.rag_handler.get_active_llm_config", return_value=mock_config
        ):
            chunks = []
            async for chunk in handle_rag_query(db, inv_id, "test query", 1):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "error"
        assert "API URL" in chunks[0]["content"]

    @pytest.mark.asyncio
    async def test_handle_rag_no_embedding_model(self):
        """
        Test that handle_rag_query raises an error response when the active LLM configuration lacks an embedding model name.

        The test sets up:
        - An asynchronous mock database (`db`).
        - A random inventory identifier (`inv_id`).
        - A mocked LLM configuration where `embedding_provider`, `embedding_api_url`, and `embedding_api_key` are defined but `embedding_model_name` is `None`.

        Using `patch` to replace `app.services.handlers.rag_handler.get_active_llm_config` with the mock config, the test invokes `handle_rag_query` with a simple query and a limit of 1. It collects all yielded chunks into a list.

        Assertions verify that:
        - Exactly one chunk is returned.
        - The chunk type is `"error"`.
        - The error message mentions "model name", confirming that the missing embedding model triggers the expected error handling path.
        """
        db = AsyncMock()
        inv_id = uuid4()

        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "http://api.example.com"
        mock_config.embedding_api_key = "key123"
        mock_config.embedding_model_name = None

        with patch(
            "app.services.handlers.rag_handler.get_active_llm_config", return_value=mock_config
        ):
            chunks = []
            async for chunk in handle_rag_query(db, inv_id, "test query", 1):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "error"
        assert "model name" in chunks[0]["content"].lower()

    @pytest.mark.asyncio
    async def test_handle_rag_success(self):
        """
        Test successful RAG query flow.

        This coroutine sets up a fully mocked environment to exercise the `handle_rag_query` function end-to-end. It:

        * Creates an async mock database connection and a random investigation identifier.
        * Mocks a configuration object with all required LLM and embedding settings.
        * Provides a fake investigation instance with a title.
        * Supplies two pre-constructed `EmbeddingChunk` objects that represent relevant retrieved documents.
        * Patches the following components used by `handle_rag_query`:
          - `get_active_llm_config` to return the mocked configuration.
          - `_expand_query_with_llm` to simulate query expansion, returning a list of terms.
          - `Embedder` and its `embed` method to produce deterministic embedding vectors.
          - `Retriever` and its `retrieve` method to return the fake chunks.
          - `get_investigation` to supply the mocked investigation.
          - `RAGContextManager.prepare_context` to provide a static system prompt and query string.
          - `LLMService` and its `extract_text_response` method to produce a fixed answer.

        The test then iterates over the asynchronous generator returned by `handle_rag_query` and collects all yielded chunks. It asserts that:

        * Exactly one chunk is produced.
        * The chunk type is `answer_chunk`.
        * The content matches the mocked LLM response (`"This is the answer"`).
        * The metadata reports a `sources_count` of `2`, reflecting the two retrieved chunks.

        No exceptions are expected; any error would cause the test to fail.
        """
        db = AsyncMock()
        inv_id = uuid4()

        # Mock config with all required fields
        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "http://api.example.com"
        mock_config.embedding_api_key = "key123"
        mock_config.embedding_model_name = "text-embedding-ada-002"
        mock_config.provider = "openai"
        mock_config.api_endpoint = "http://api.example.com"
        mock_config.api_key = "key123"
        mock_config.model_name = "gpt-4"
        mock_config.max_context_length = 8192
        mock_config.temperature = 0.7
        mock_config.top_p = None
        mock_config.top_k = None
        mock_config.min_p = None
        mock_config.timeout = 300

        # Mock investigation
        mock_investigation = MagicMock()
        mock_investigation.title = "Test Investigation"

        # Mock chunks
        mock_chunks = [
            EmbeddingChunk(id=1, owner_type="chat", owner_id=1, text="Relevant text 1", score=0.9),
            EmbeddingChunk(
                id=2, owner_type="timeline", owner_id=2, text="Relevant text 2", score=0.8
            ),
        ]

        with patch(
            "app.services.handlers.rag_handler.get_active_llm_config", return_value=mock_config
        ):
            with patch(
                "app.services.handlers.rag_handler._expand_query_with_llm",
                return_value=["term1", "term2"],
            ):
                with patch("app.services.handlers.rag_handler.Embedder") as MockEmbedder:
                    with patch("app.services.handlers.rag_handler.Retriever") as MockRetriever:
                        with patch(
                            "app.services.handlers.rag_handler.get_investigation",
                            return_value=mock_investigation,
                        ):
                            with patch(
                                "app.services.handlers.rag_handler.RAGContextManager.prepare_context",
                                return_value=("system", "query"),
                            ):
                                with patch(
                                    "app.services.handlers.rag_handler.LLMService"
                                ) as MockLLMService:
                                    # Mock embedder
                                    mock_embedder = AsyncMock()
                                    mock_embedder.embed.return_value = [
                                        np.array([0.1, 0.2]),
                                        np.array([0.3, 0.4]),
                                        np.array([0.5, 0.6]),
                                    ]
                                    MockEmbedder.return_value = mock_embedder

                                    # Mock retriever
                                    mock_retriever = AsyncMock()
                                    mock_retriever.retrieve.return_value = mock_chunks
                                    MockRetriever.return_value = mock_retriever

                                    # Mock LLM service
                                    mock_llm_service = AsyncMock()
                                    mock_llm_service.extract_text_response.return_value = (
                                        "This is the answer"
                                    )
                                    MockLLMService.return_value = mock_llm_service

                                    chunks = []
                                    async for chunk in handle_rag_query(
                                        db, inv_id, "test query", 1
                                    ):
                                        chunks.append(chunk)

        # Should yield answer_chunk
        assert len(chunks) == 1
        assert chunks[0]["type"] == "answer_chunk"
        assert chunks[0]["content"] == "This is the answer"
        assert chunks[0]["metadata"]["sources_count"] == 2

    @pytest.mark.asyncio
    async def test_handle_rag_embedding_failure(self):
        """
        Test that the RAG query handler correctly reports an error when embedding generation fails.

        This test sets up mocks for:
        - The active LLM configuration returned by `get_active_llm_config`.
        - The query expansion function `_expand_query_with_llm` to return no additional queries.
        - The `Embedder` class, whose `embed` coroutine is mocked to return an empty list, simulating a failure to produce embeddings.

        The test then invokes `handle_rag_query` with a mock database connection, a generated invitation ID, and a sample query. It collects all yielded chunks into a list and asserts that:
        - Exactly one chunk is produced.
        - The chunk's `type` field equals `"error"`, indicating an error response.
        - The `content` field contains the message `"Failed to generate query embeddings"`, confirming that the handler detected the embedding failure and emitted the appropriate error.
        """
        db = AsyncMock()
        inv_id = uuid4()

        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "http://api.example.com"
        mock_config.embedding_api_key = "key123"
        mock_config.embedding_model_name = "text-embedding-ada-002"

        with patch(
            "app.services.handlers.rag_handler.get_active_llm_config", return_value=mock_config
        ):
            with patch("app.services.handlers.rag_handler._expand_query_with_llm", return_value=[]):
                with patch("app.services.handlers.rag_handler.Embedder") as MockEmbedder:
                    # Mock embedder returns empty list
                    mock_embedder = AsyncMock()
                    mock_embedder.embed.return_value = []
                    MockEmbedder.return_value = mock_embedder

                    chunks = []
                    async for chunk in handle_rag_query(db, inv_id, "test query", 1):
                        chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "error"
        assert "Failed to generate query embeddings" in chunks[0]["content"]

    @pytest.mark.asyncio
    async def test_handle_rag_retrieval_error(self):
        """
        Test that the RAG query handler correctly handles an exception raised during document retrieval. The test sets up mocks for configuration, query expansion, embedding, and retrieval components, configuring the retriever mock to raise an Exception when its `retrieve` method is called. It then invokes `handle_rag_query` with a sample query and collects the asynchronous output chunks. After execution, the test asserts that exactly one chunk is produced, that the chunk's `type` field is set to `"error"`, and that the `content` field contains an error message indicating failure to retrieve context. This verifies that the handler gracefully captures retrieval errors and returns a structured error response instead of propagating the exception.
        """
        db = AsyncMock()
        inv_id = uuid4()

        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "http://api.example.com"
        mock_config.embedding_api_key = "key123"
        mock_config.embedding_model_name = "text-embedding-ada-002"

        with patch(
            "app.services.handlers.rag_handler.get_active_llm_config", return_value=mock_config
        ):
            with patch("app.services.handlers.rag_handler._expand_query_with_llm", return_value=[]):
                with patch("app.services.handlers.rag_handler.Embedder") as MockEmbedder:
                    with patch("app.services.handlers.rag_handler.Retriever") as MockRetriever:
                        mock_embedder = AsyncMock()
                        mock_embedder.embed.return_value = [np.array([0.1, 0.2])]
                        MockEmbedder.return_value = mock_embedder

                        mock_retriever = AsyncMock()
                        mock_retriever.retrieve.side_effect = Exception("Retrieval error")
                        MockRetriever.return_value = mock_retriever

                        chunks = []
                        async for chunk in handle_rag_query(db, inv_id, "test query", 1):
                            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "error"
        assert "Failed to retrieve context" in chunks[0]["content"]

    @pytest.mark.asyncio
    async def test_handle_rag_llm_synthesis_error(self):
        """
        Test that handle_rag_query correctly handles an exception raised by the LLM synthesis step.

        The test sets up mocks for all external dependencies used by `handle_rag_query`:
        * Configuration returned by `get_active_llm_config`.
        * Query expansion via `_expand_query_with_llm` (returns an empty list).
        * Embedding generation through a mocked `Embedder` instance.
        * Document retrieval using a mocked `Retriever` instance that returns a single `EmbeddingChunk`.
        * Investigation lookup via `get_investigation`.
        * Context preparation by `RAGContextManager.prepare_context` (returns a dummy system prompt and query).
        * LLM service call through `LLMService` which is configured to raise an `Exception` with the message `"LLM error"`.

        The test invokes `handle_rag_query` with the mocked database, investigation ID, a sample query string, and a limit of 1. It collects all async-generated chunks into a list.

        Assertions verify that:
        * Exactly one chunk is produced.
        * The chunk type is `"error"`, indicating error handling was triggered.
        * The chunk content contains the phrase `"LLM synthesis failed"`, confirming that the exception from the LLM service was caught and transformed into an appropriate error message.
        """
        db = AsyncMock()
        inv_id = uuid4()

        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "http://api.example.com"
        mock_config.embedding_api_key = "key123"
        mock_config.embedding_model_name = "text-embedding-ada-002"
        mock_config.provider = "openai"
        mock_config.api_endpoint = "http://api.example.com"
        mock_config.api_key = "key123"
        mock_config.model_name = "gpt-4"
        mock_config.max_context_length = 8192
        mock_config.temperature = 0.7
        mock_config.top_p = None
        mock_config.top_k = None
        mock_config.min_p = None
        mock_config.timeout = 300

        mock_investigation = MagicMock()
        mock_investigation.title = "Test"

        mock_chunks = [
            EmbeddingChunk(id=1, owner_type="chat", owner_id=1, text="Text", score=0.9),
        ]

        with patch(
            "app.services.handlers.rag_handler.get_active_llm_config", return_value=mock_config
        ):
            with patch("app.services.handlers.rag_handler._expand_query_with_llm", return_value=[]):
                with patch("app.services.handlers.rag_handler.Embedder") as MockEmbedder:
                    with patch("app.services.handlers.rag_handler.Retriever") as MockRetriever:
                        with patch(
                            "app.services.handlers.rag_handler.get_investigation",
                            return_value=mock_investigation,
                        ):
                            with patch(
                                "app.services.handlers.rag_handler.RAGContextManager.prepare_context",
                                return_value=("system", "query"),
                            ):
                                with patch(
                                    "app.services.handlers.rag_handler.LLMService"
                                ) as MockLLMService:
                                    mock_embedder = AsyncMock()
                                    mock_embedder.embed.return_value = [np.array([0.1, 0.2])]
                                    MockEmbedder.return_value = mock_embedder

                                    mock_retriever = AsyncMock()
                                    mock_retriever.retrieve.return_value = mock_chunks
                                    MockRetriever.return_value = mock_retriever

                                    # Mock LLM service to raise exception
                                    mock_llm_service = AsyncMock()
                                    mock_llm_service.call_llm.side_effect = Exception("LLM error")
                                    MockLLMService.return_value = mock_llm_service

                                    chunks = []
                                    async for chunk in handle_rag_query(
                                        db, inv_id, "test query", 1
                                    ):
                                        chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "error"
        assert "LLM synthesis failed" in chunks[0]["content"]

    @pytest.mark.asyncio
    async def test_handle_rag_empty_llm_response(self):
        """
        Test that handle_rag_query correctly reports an error when the LLM service returns an empty string response.

        The test sets up a full mock environment for the RAG handler, including:
        - A mocked database connection (`db`).
        - An investigation identifier (`inv_id`).
        - Configuration objects required by the handler (embedding and LLM settings).
        - Mocked domain objects such as `EmbeddingChunk` and an investigation instance.
        - Patches for all external dependencies used inside `handle_rag_query`: configuration retrieval, query expansion, embedder, retriever, investigation lookup, context preparation, and the LLM service.

        Within the patched context:
        1. The embedder returns a deterministic embedding vector.
        2. The retriever yields a single relevant chunk.
        3. The LLM service’s `extract_text_response` method is forced to return an empty string, simulating a failure to generate a response.

        The test then iterates over the asynchronous generator returned by `handle_rag_query`, collecting all yielded chunks into a list.

        Assertions verify that:
        - Exactly one chunk is produced.
        - The chunk type is `"error"`.
        - The error message contains the phrase `"No response from LLM"` indicating proper handling of the empty LLM output.
        """
        db = AsyncMock()
        inv_id = uuid4()

        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "http://api.example.com"
        mock_config.embedding_api_key = "key123"
        mock_config.embedding_model_name = "text-embedding-ada-002"
        mock_config.provider = "openai"
        mock_config.api_endpoint = "http://api.example.com"
        mock_config.api_key = "key123"
        mock_config.model_name = "gpt-4"
        mock_config.max_context_length = 8192
        mock_config.temperature = 0.7
        mock_config.top_p = None
        mock_config.top_k = None
        mock_config.min_p = None
        mock_config.timeout = 300

        mock_investigation = MagicMock()
        mock_investigation.title = "Test"

        mock_chunks = [
            EmbeddingChunk(id=1, owner_type="chat", owner_id=1, text="Text", score=0.9),
        ]

        with patch(
            "app.services.handlers.rag_handler.get_active_llm_config", return_value=mock_config
        ):
            with patch("app.services.handlers.rag_handler._expand_query_with_llm", return_value=[]):
                with patch("app.services.handlers.rag_handler.Embedder") as MockEmbedder:
                    with patch("app.services.handlers.rag_handler.Retriever") as MockRetriever:
                        with patch(
                            "app.services.handlers.rag_handler.get_investigation",
                            return_value=mock_investigation,
                        ):
                            with patch(
                                "app.services.handlers.rag_handler.RAGContextManager.prepare_context",
                                return_value=("system", "query"),
                            ):
                                with patch(
                                    "app.services.handlers.rag_handler.LLMService"
                                ) as MockLLMService:
                                    mock_embedder = AsyncMock()
                                    mock_embedder.embed.return_value = [np.array([0.1, 0.2])]
                                    MockEmbedder.return_value = mock_embedder

                                    mock_retriever = AsyncMock()
                                    mock_retriever.retrieve.return_value = mock_chunks
                                    MockRetriever.return_value = mock_retriever

                                    # Mock LLM service to return empty response
                                    mock_llm_service = AsyncMock()
                                    mock_llm_service.extract_text_response.return_value = ""
                                    MockLLMService.return_value = mock_llm_service

                                    chunks = []
                                    async for chunk in handle_rag_query(
                                        db, inv_id, "test query", 1
                                    ):
                                        chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "error"
        assert "No response from LLM" in chunks[0]["content"]
