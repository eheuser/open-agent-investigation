import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from app.services.rag.retriever import Retriever, EmbeddingChunk


@pytest.mark.unit
class TestEmbeddingChunk:
    """Test EmbeddingChunk dataclass."""

    def test_create_chunk(self):
        """
        Test creating an EmbeddingChunk instance and verify its attributes are correctly assigned.

        The test constructs an EmbeddingChunk with specific values for `id`, `owner_type`, `owner_id`, `text` and `score`. It then asserts that each of these fields matches the expected value and that the optional `metadata` attribute defaults to `None`. This ensures the dataclass initializes correctly without additional side effects.
        """
        chunk = EmbeddingChunk(
            id=1, owner_type="chat", owner_id=123, text="Test content", score=0.95
        )

        assert chunk.id == 1
        assert chunk.owner_type == "chat"
        assert chunk.owner_id == 123
        assert chunk.text == "Test content"
        assert chunk.score == 0.95
        assert chunk.metadata is None

    def test_create_chunk_with_metadata(self):
        """
        Test that an `EmbeddingChunk` instance correctly stores the supplied metadata dictionary upon creation, verifying that the `metadata` attribute matches the expected value.
        """
        chunk = EmbeddingChunk(
            id=1,
            owner_type="timeline",
            owner_id=456,
            text="Event text",
            score=0.88,
            metadata={"tags": ["important"]},
        )

        assert chunk.metadata == {"tags": ["important"]}


@pytest.mark.unit
class TestRetriever:
    """Test Retriever class."""

    def test_init(self):
        """
        Test that initializing a Retriever correctly assigns the provided asynchronous database client to the instance’s `db` attribute.
        """
        db = AsyncMock()

        retriever = Retriever(db)

        assert retriever.db == db

    async def test_retrieve_no_candidates(self):
        """
        Test that the retrieve method returns an empty list when the internal vector search yields no candidate documents for the given query vector and investigation identifier. The test sets up a mock database and patches the _vector_search method to return an empty list, then asserts that the result of retrieve is an empty list.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock empty vector search results
        with patch.object(retriever, "_vector_search", return_value=[]):
            query_vec = np.array([0.1, 0.2, 0.3])

            results = await retriever.retrieve(
                query_vec=query_vec, investigation_id="test-uuid", k=5
            )

            assert results == []

    async def test_retrieve_with_candidates(self):
        """
        Test that the `retrieve` method correctly returns populated result objects when candidate embeddings are found.

        The test sets up an asynchronous mock database and instantiates a :class:`Retriever`. It then mocks the internal `_vector_search` method to return a list of candidate tuples, each containing an identifier, owner type, owner ID, and distance. The `_load_texts` method is also mocked to return corresponding :class:`EmbeddingChunk` instances with text and score information.

        A sample query vector is created and passed to the `retrieve` coroutine along with an investigation identifier and a maximum result count (`k`). After awaiting the call, the test asserts that:

        * The number of results matches the number of mocked candidates.
        * The first result's `text` attribute equals `"Chat message"`.
        * The second result's `text` attribute equals `"Timeline entry"`, confirming that the retriever correctly maps candidate metadata to the loaded text chunks.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock vector search results
        candidates = [
            (1, "chat", 100, 0.1),  # (id, owner_type, owner_id, distance)
            (2, "timeline", 200, 0.2),
        ]

        # Mock chunks with text
        chunks = [
            EmbeddingChunk(id=1, owner_type="chat", owner_id=100, text="Chat message", score=0.9),
            EmbeddingChunk(
                id=2, owner_type="timeline", owner_id=200, text="Timeline entry", score=0.8
            ),
        ]

        with patch.object(retriever, "_vector_search", return_value=candidates):
            with patch.object(retriever, "_load_texts_with_events", return_value=chunks):
                query_vec = np.array([0.1, 0.2, 0.3])

                results = await retriever.retrieve(
                    query_vec=query_vec, investigation_id="test-uuid", k=5
                )

                assert len(results) == 2
                assert results[0].text == "Chat message"
                assert results[1].text == "Timeline entry"

    async def test_retrieve_limits_results(self):
        """
        Test that the `retrieve` method respects the maximum number of results specified by the `k` parameter.

        The test sets up a mock asynchronous database and a `Retriever` instance, then creates ten synthetic `EmbeddingChunk` objects while configuring the internal `_vector_search` and `_load_texts` methods to return predetermined candidates and chunks. By invoking `retrieve` with `k=3`, it verifies that only three results are returned, confirming that result limiting works as intended.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Create 10 chunks but request only 3
        chunks = [
            EmbeddingChunk(id=i, owner_type="chat", owner_id=i, text=f"Text {i}", score=0.9)
            for i in range(10)
        ]

        candidates = [(i, "chat", i, 0.1) for i in range(10)]

        with patch.object(retriever, "_vector_search", return_value=candidates):
            with patch.object(retriever, "_load_texts_with_events", return_value=chunks):
                query_vec = np.array([0.1, 0.2, 0.3])

                results = await retriever.retrieve(
                    query_vec=query_vec, investigation_id="test-uuid", k=3
                )

                assert len(results) == 3


@pytest.mark.unit
class TestRetrieverFetchText:
    """Test _fetch_text method."""

    async def test_fetch_chat_text(self):
        """
        Test that the Retriever correctly fetches chat message content from the database.\n\nThe test creates an asynchronous mock database and configures it to return a single row containing the expected chat text when queried. It then invokes the private `_fetch_text` method with a \"chat\" owner type and a sample identifier, awaiting its result. Finally, the test asserts that the returned string matches the mocked content.\n\nNo explicit arguments are passed to this test method; it operates on the `self` instance of the test case class. The expected return value is the chat message text retrieved from the mock database. No exceptions are anticipated during normal execution.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock database result
        result_mock = MagicMock()
        result_mock.fetchone.return_value = ("Chat message content",)
        db.execute.return_value = result_mock

        text = await retriever._fetch_text("chat", 123)

        assert text == "Chat message content"

    async def test_fetch_timeline_text(self):
        """
        Test that the retriever correctly fetches and returns the text content of a timeline entry by mocking the asynchronous database call and verifying the returned string matches the expected description.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock database result
        result_mock = MagicMock()
        result_mock.fetchone.return_value = ("Timeline: Entry description",)
        db.execute.return_value = result_mock

        text = await retriever._fetch_text("timeline", 456)

        assert text == "Timeline: Entry description"

    async def test_fetch_note_text(self):
        """
        Test that the Retriever correctly fetches note text from the database.\n\nThe test creates an asynchronous mock database connection and configures it to return a single row containing the expected note content when queried. It then calls the private `_fetch_text` method with the owner type `\"note\"` and a sample identifier, awaiting its result. Finally, the test asserts that the returned text matches the mocked content.\n\nNo exceptions are expected; any deviation from the expected string will cause the assertion to fail.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock database result
        result_mock = MagicMock()
        result_mock.fetchone.return_value = ("Note content here",)
        db.execute.return_value = result_mock

        text = await retriever._fetch_text("note", 789)

        assert text == "Note content here"

    async def test_fetch_tool_text(self):
        """
        Test that the Retriever correctly fetches and formats text for a tool/event entry.

        The test creates an asynchronous mock database connection and injects a fabricated row representing a tool/event record with:
        - An identifier string (`"evtx_sysmon_1"`).
        - A timestamp (`datetime(2024, 1, 1, 12, 0)`).
        - A JSON-encoded payload containing the `"Image": "cmd.exe"` field.

        The mock is configured so that `db.execute(...).fetchone()` returns this tuple. The test then calls the private `_fetch_text` coroutine with a `"tool"` owner type and an arbitrary ID (`999`). It asserts that the resulting formatted text includes both the identifier and a human-readable date string (`"2024-01-01"`), confirming that the Retriever extracts and formats the database fields as expected.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock database result
        from datetime import datetime

        result_mock = MagicMock()
        result_mock.fetchone.return_value = (
            "evtx_sysmon_1",
            datetime(2024, 1, 1, 12, 0),
            '{"Image": "cmd.exe"}',
        )
        db.execute.return_value = result_mock

        text = await retriever._fetch_text("tool", 999)

        assert "evtx_sysmon_1" in text
        assert "2024-01-01" in text

    async def test_fetch_text_not_found(self):
        """
        Test that the private `_fetch_text` method correctly returns `None` when the database query yields no matching record. The test sets up an asynchronous mock database where `execute` returns a result whose `fetchone` method returns `None`, then asserts that calling `_fetch_text` with a non-existent owner ID results in `None` being returned.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock empty result
        result_mock = MagicMock()
        result_mock.fetchone.return_value = None
        db.execute.return_value = result_mock

        text = await retriever._fetch_text("chat", 999)

        assert text is None

    async def test_fetch_text_unknown_type(self):
        """
        Test that retrieving text for an unsupported owner type returns `None` without raising errors. The mock database is not used because the method should short-circuit on the unknown type, ensuring graceful handling of unexpected input.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        text = await retriever._fetch_text("unknown_type", 123)

        assert text is None

    async def test_fetch_text_handles_exception(self):
        """
        Test that the private _fetch_text method returns `None` when a database exception occurs, ensuring the retriever handles errors gracefully without propagating them. The test sets up an AsyncMock database, configures its execute method to raise an Exception, invokes _fetch_text with sample parameters, and asserts that the result is `None`.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock database error
        db.execute.side_effect = Exception("Database error")

        text = await retriever._fetch_text("chat", 123)

        # Should return None instead of raising
        assert text is None


@pytest.mark.unit
class TestRetrieverLoadTexts:
    """Test _load_texts method."""

    async def test_load_texts_success(self):
        """
        Test that the private `_load_texts` coroutine correctly retrieves and scores text chunks for multiple candidates.

        The test creates an `AsyncMock` database instance and a `Retriever` object, then defines two candidate tuples containing an identifier, owner type, reference ID, and distance value. By patching the retriever’s internal `_fetch_text` method to return predefined strings, the coroutine is invoked with the candidate list.

        Assertions verify that:
        - The returned collection contains one chunk per candidate.
        - Each chunk’s `text` attribute matches the mocked fetch result.
        - Each chunk’s `score` attribute is computed as `1.0 - distance`, resulting in scores of 0.9 and 0.8 for the provided distances.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        candidates = [(1, "chat", 100, 0.1), (2, "timeline", 200, 0.2)]

        with patch.object(retriever, "_fetch_text", side_effect=["Text 1", "Text 2"]):
            with patch.object(retriever, "_fetch_event_data", return_value=None):
                chunks = await retriever._load_texts_with_events(candidates)

                assert len(chunks) == 2
                assert chunks[0].text == "Text 1"
                assert chunks[0].score == 0.9  # 1.0 - 0.1
                assert chunks[1].text == "Text 2"
                assert chunks[1].score == 0.8  # 1.0 - 0.2

    async def test_load_texts_skips_failed(self):
        """
        Test that the Retriever skips any candidate whose text fetch returns `None`. The test creates a mock database and a Retriever instance, defines three candidate tuples, and patches the private `_fetch_text` method to return a valid string for the first and third candidates while returning `None` for the second. It then calls `_load_texts` with the candidates and asserts that only two chunks are returned, containing the texts from the successful fetches.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        candidates = [(1, "chat", 100, 0.1), (2, "timeline", 200, 0.2), (3, "note", 300, 0.3)]

        # Second fetch returns None (not found)
        with patch.object(retriever, "_fetch_text", side_effect=["Text 1", None, "Text 3"]):
            with patch.object(retriever, "_fetch_event_data", return_value=None):
                chunks = await retriever._load_texts_with_events(candidates)

                # Should skip the one that returned None
                assert len(chunks) == 2
                assert chunks[0].text == "Text 1"
                assert chunks[1].text == "Text 3"

    async def test_load_texts_stops_on_transaction_abort(self):
        """
        Test that the Retriever stops loading text chunks when a transaction abort error is raised during fetching.

        The test creates an async mock database and a Retriever instance, then defines candidate tuples representing different owner types. It patches the private `_fetch_text` method to raise an exception for a specific owner ID (simulating a transaction abort). The test invokes the internal `_load_texts` coroutine with the candidates and asserts that processing halts after the first successful fetch, resulting in exactly one chunk whose text matches the expected value for the first candidate.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        candidates = [(1, "chat", 100, 0.1), (2, "timeline", 200, 0.2), (3, "note", 300, 0.3)]

        # Second fetch raises transaction abort error
        def fetch_side_effect(owner_type, owner_id):
            """
            Fetches text for a given owner, simulating database behavior.

            Parameters
            ----------
            owner_type : Any
                Identifier of the type of owner (e.g., user, organization). The value is not used in this mock implementation but is kept for signature compatibility.
            owner_id : int
                Unique identifier of the owner whose associated text should be retrieved. If `owner_id` equals `200`, an exception is raised to simulate a transaction abort.

            Returns
            -------
            str
                A formatted string containing the placeholder text for the provided `owner_id`.

            Raises
            ------
            Exception
                If `owner_id` is `200`, indicating that the simulated database transaction was aborted.
            """
            if owner_id == 200:
                raise Exception("transaction is aborted")
            return f"Text for {owner_id}"

        with patch.object(retriever, "_fetch_text", side_effect=fetch_side_effect):
            with patch.object(retriever, "_fetch_event_data", return_value=None):
                chunks = await retriever._load_texts_with_events(candidates)

                # Should only have first chunk, then stop
                assert len(chunks) == 1
                assert chunks[0].text == "Text for 100"


@pytest.mark.unit
class TestRetrieverVectorSearch:
    """Test _vector_search method."""

    async def test_vector_search_success(self):
        """
        Test that the private `_vector_search` method correctly performs a vector similarity query and returns the expected rows.

        The test sets up an asynchronous mock database connection and configures its `execute` coroutine to return:
        * A count result whose `scalar()` call yields `100`, simulating the total number of matching vectors.
        * A search result whose `fetchall()` call yields two sample rows, each consisting of `(owner_id, owner_type, document_id, score)`.

        A dummy NumPy query vector is supplied along with an investigation identifier. The method is invoked with no owner type filter and a limit of five results.

        Assertions verify that:
        * Exactly two result tuples are returned.
        * Each tuple matches the mocked data in order, confirming that the method forwards the database response unchanged.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock count query
        count_result = MagicMock()
        count_result.scalar.return_value = 100

        # Mock search results
        search_result = MagicMock()
        search_result.fetchall.return_value = [(1, "chat", 100, 0.1), (2, "timeline", 200, 0.2)]

        db.execute.side_effect = [count_result, search_result]

        query_vec = np.array([0.1, 0.2, 0.3])

        results = await retriever._vector_search(
            query_vec=query_vec, investigation_id="test-uuid", owner_types=None, limit=5
        )

        assert len(results) == 2
        assert results[0] == (1, "chat", 100, 0.1)
        assert results[1] == (2, "timeline", 200, 0.2)

    async def test_vector_search_with_owner_types(self):
        """
        Test vector search with owner type filter.

        This test verifies that the private `_vector_search` method of :class:`Retriever` correctly applies an owner type filter when performing a similarity search. It sets up a mocked asynchronous database connection, configures expected query results for both the total count and the fetched rows, and asserts that the returned result list matches the mocked data.

        The test performs the following steps:
        - Creates an `AsyncMock` instance to simulate the database.
        - Instantiates a :class:`Retriever` with the mocked database.
        - Mocks the scalar result of a count query to return `50`.
        - Mocks the fetchall result of the vector search query to return a single row `(1, "chat", 100, 0.1)`.
        - Configures the mock `execute` method to yield the count result first and then the search result.
        - Constructs a sample query vector using NumPy.
        - Calls `retriever._vector_search` with the query vector, an investigation ID, a list of owner types (`["chat", "timeline"]`), and a limit of `5`.
        - Awaits the coroutine and asserts that exactly one result is returned.

        No exceptions are expected; any unexpected behavior will cause the test to fail.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        count_result = MagicMock()
        count_result.scalar.return_value = 50

        search_result = MagicMock()
        search_result.fetchall.return_value = [(1, "chat", 100, 0.1)]

        db.execute.side_effect = [count_result, search_result]

        query_vec = np.array([0.1, 0.2, 0.3])

        results = await retriever._vector_search(
            query_vec=query_vec,
            investigation_id="test-uuid",
            owner_types=["chat", "timeline"],
            limit=5,
        )

        assert len(results) == 1

    async def test_vector_search_handles_exception(self):
        """
        Test that the private `_vector_search` method propagates exceptions raised by the database layer.

        The test sets up an `AsyncMock` database where `execute` raises a generic `Exception` with the message "Database error". It then calls `_vector_search` with a sample query vector, investigation ID, no owner type filtering, and a limit of 5. The `pytest.raises` context asserts that the same exception is re-raised, confirming that the method does not silently swallow errors from the underlying database execution.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        db.execute.side_effect = Exception("Database error")

        query_vec = np.array([0.1, 0.2, 0.3])

        with pytest.raises(Exception, match="Database error"):
            await retriever._vector_search(
                query_vec=query_vec, investigation_id="test-uuid", owner_types=None, limit=5
            )


@pytest.mark.unit
class TestRetrieverFetchEventData:
    """Test _fetch_event_data method."""

    async def test_fetch_event_data_success(self):
        """
        Test that _fetch_event_data correctly retrieves and formats event data.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock database result
        from datetime import datetime
        
        result_mock = MagicMock()
        result_mock.fetchone.return_value = (
            123,  # event_id
            "evtx_security_4624",  # event_type
            datetime(2024, 1, 1, 12, 0),  # event_ts
            {"LogonType": 3, "TargetUserName": "admin"},  # payload as dict (PostgreSQL jsonb)
            5,  # artifact_id
        )
        db.execute.return_value = result_mock

        event_data = await retriever._fetch_event_data(123)

        assert event_data is not None
        assert event_data["event_id"] == 123
        assert event_data["event_type"] == "evtx_security_4624"
        assert event_data["artifact_id"] == 5
        assert "LogonType" in event_data["payload"]
        assert event_data["payload"]["LogonType"] == 3

    async def test_fetch_event_data_not_found(self):
        """
        Test that _fetch_event_data returns None when event doesn't exist.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock empty result
        result_mock = MagicMock()
        result_mock.fetchone.return_value = None
        db.execute.return_value = result_mock

        event_data = await retriever._fetch_event_data(999)

        assert event_data is None

    async def test_fetch_event_data_handles_exception(self):
        """
        Test that _fetch_event_data returns None on database errors.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock database error
        db.execute.side_effect = Exception("Database error")

        event_data = await retriever._fetch_event_data(123)

        # Should return None instead of raising
        assert event_data is None

    async def test_fetch_event_data_with_dict_payload(self):
        """
        Test that _fetch_event_data handles payloads that are already dicts.
        """
        db = AsyncMock()
        retriever = Retriever(db)

        # Mock database result with dict payload (not JSON string)
        from datetime import datetime
        
        result_mock = MagicMock()
        result_mock.fetchone.return_value = (
            456,  # event_id
            "mft_file_created",  # event_type
            datetime(2024, 1, 2, 10, 30),  # event_ts
            {"FileName": "malware.exe", "FileSize": 1024},  # payload as dict
            10,  # artifact_id
        )
        db.execute.return_value = result_mock

        event_data = await retriever._fetch_event_data(456)

        assert event_data is not None
        assert event_data["event_id"] == 456
        assert event_data["event_type"] == "mft_file_created"
        assert event_data["payload"]["FileName"] == "malware.exe"
