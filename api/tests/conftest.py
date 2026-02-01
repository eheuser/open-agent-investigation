import os
import pytest
import uuid
from typing import AsyncGenerator, Generator
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Import app components - WeasyPrint is now optional
from app.main import app
from app.core.database import Base, get_db

from app.models.user import User
from app.models.investigation import Investigation
from app.auth import create_access_token, hash_password
from app.models.user import UserRole


from app.utils.log_setup import get_logger

logger = get_logger(__name__)

# Use a separate test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:example@localhost:5432/open_agent_inv_test"
)


@pytest.fixture(scope="function")
async def test_engine():
    """
    Create and configure an asynchronous SQLAlchemy engine for testing.

    The fixture builds a fresh test database engine using the `TEST_DATABASE_URL` with a `NullPool` to prevent connection pooling side-effects during tests. It ensures the required `pgvector` extension is present (ignoring any errors) and recreates all tables before each test, guaranteeing an isolated schema state. After yielding the engine to the test function, it drops all tables again and disposes of the engine to clean up resources.

    Yielded value
        An instance of :class:`sqlalchemy.ext.asyncio.AsyncEngine` connected to the test database.

    Notes
        * The fixture is scoped to each test function to avoid event-loop conflicts with `pytest-asyncio`.
        * Set `echo=True` in the engine creation call for detailed SQL debugging output.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,  # Set to True for SQL debugging
    )

    # Create pgvector extension first (idempotent)
    async with engine.begin() as conn:
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception as e:
            logger.warning(f"Could not create vector extension: {e}")

    # Create all tables (drop first to ensure clean state)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        
        # Create field_dictionary table (not in ORM models)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS field_dictionary (
                field_id BIGSERIAL PRIMARY KEY,
                investigation_id UUID NOT NULL,
                event_type TEXT NOT NULL,
                field_name TEXT NOT NULL,
                description TEXT,
                sample_values TEXT[],
                cached_markdown TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(investigation_id, event_type, field_name)
            )
        """))
        
        # Create indexes for field_dictionary
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_field_dict_investigation 
            ON field_dictionary(investigation_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_field_dict_event_type 
            ON field_dictionary(investigation_id, event_type)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_field_dict_pending 
            ON field_dictionary(investigation_id) WHERE description IS NULL
        """))

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create and yield an asynchronous SQLAlchemy session bound to the provided test engine.

    Args:
        test_engine: An `AsyncEngine` fixture scoped to the test session. It is responsible for creating and dropping tables before each test function, eliminating the need for explicit transaction rollbacks.

    Yields:
        AsyncSession: A new `AsyncSession` instance that can be used within a test to interact with the database. The session is automatically closed when exiting the context manager.
    """
    # Create a session factory
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        # Session will be automatically closed
        # Tables will be dropped by test_engine cleanup


@pytest.fixture(scope="function")
def override_get_db(db_session: AsyncSession):
    """
    Override the FastAPI `get_db` dependency with a provided asynchronous session for testing.

    Parameters
    ----------
    db_session: AsyncSession
        The database session that should be yielded by the overridden dependency.

    Yields
    -----
    None
        The function yields control back to the caller after setting the override; once execution resumes, the dependency overrides are cleared.
    """

    async def _override_get_db():
        """
        Override the default database dependency used by FastAPI routes during tests.

        This asynchronous generator yields a SQLAlchemy session (`db_session`) that points to the test
        database, allowing test code to interact with an isolated in-memory or temporary database.
        The yielded session is automatically closed after the request finishes.
        """
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def client(override_get_db) -> Generator[TestClient, None, None]:
    """
    Create a synchronous FastAPI test client.

    Parameters
    ----------
    override_get_db : Any
        Fixture that overrides the database dependency for testing purposes.

    Yields
    ------
    TestClient
        An instance of `TestClient` bound to the application, usable within a `with` block or as a generator fixture.
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
async def async_client(override_get_db) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an asynchronous HTTP client configured for testing the FastAPI application.

    Parameters
    ----------
    override_get_db : Any
        Fixture or callable used to override the database dependency during tests.

    Yields
    ------
    AsyncClient
        An instance of `httpx.AsyncClient` with the test application's ASGI app and a base URL of `http://test`. The client is automatically closed when exiting the context.
    """
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> User:
    """
    Create and persist a test user in the database.

    Parameters
    ----------
    db_session: AsyncSession
        An asynchronous SQLAlchemy session used to add and commit the new user record.

    Returns
    -------
    User
        The newly created `User` instance, refreshed from the database with its generated primary key.
    """
    user = User(
        username="testuser",
        password_hash=hash_password("testpass123"),
        role=0,  # Regular user
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
async def admin_user(db_session: AsyncSession) -> User:
    """
    Create an admin user in the database.

    Args:
        db_session: An asynchronous SQLAlchemy session used to add and commit the new user.

    Returns:
        The newly created `User` instance refreshed from the database.

    Raises:
        Any exception raised by the database operations (e.g., integrity errors) will propagate.
    """
    user = User(
        username="adminuser",
        password_hash=hash_password("adminpass123"),
        role=1,  # Admin
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def test_token(test_user: User) -> str:
    """
    Generate a JWT access token for a given test user.

    Parameters
    ----------
    test_user : User
        The user instance containing the identifier, username, and role to embed in the token.

    Returns
    -------
    str
        A signed JWT string that can be used for authenticating requests in tests.
    """
    return create_access_token(
        user_id=test_user.user_id, username=test_user.username, role=test_user.role
    )


@pytest.fixture(scope="function")
def admin_token(admin_user: User) -> str:
    """
    Generate a JSON Web Token (JWT) for an administrative user.

    Parameters
    ----------
    admin_user : User
        The user instance representing the administrator. Must contain `user_id`, `username` and `role` attributes required for token creation.

    Returns
    -------
    str
        A JWT string encoding the provided user's identity and role, suitable for authenticating admin-level requests.
    """
    return create_access_token(
        user_id=admin_user.user_id, username=admin_user.username, role=admin_user.role
    )


@pytest.fixture(scope="function")
def auth_headers(test_token: str) -> dict:
    """
    Create HTTP authorization headers for a test user.

    Parameters
    ----------
    test_token: str
        The JWT or token string representing the test user's authentication credentials.

    Returns
    -------
    dict
        A dictionary containing the `Authorization` header with the value formatted as `Bearer <test_token>`.
    """
    return {"Authorization": f"Bearer {test_token}"}


@pytest.fixture(scope="function")
def admin_headers(admin_token: str) -> dict:
    """
    Create HTTP authorization headers for an admin user.

    Parameters
    ----------
    admin_token: str
        The JWT token representing the admin's authentication credentials.

    Returns
    -------
    dict
        A dictionary containing the "Authorization" header with the bearer token formatted as `Bearer <admin_token>`.
    """
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="function")
async def test_investigation(db_session: AsyncSession, test_user: User) -> Investigation:
    """
    Create and persist a test Investigation record in the database.

    Parameters
    ----------
    db_session: AsyncSession
        The asynchronous SQLAlchemy session used to add and flush the new record.
    test_user: User
        The user who will be set as the owner of the investigation.

    Returns
    -------
    Investigation
        The newly created Investigation instance, refreshed from the database with its generated primary key.
    """
    investigation = Investigation(
        investigation_id=uuid.uuid4(),
        title="Test Investigation",
        owner_user_id=test_user.user_id,
        created_at=datetime.utcnow(),
    )
    db_session.add(investigation)
    await db_session.flush()  # Flush instead of commit to stay in same transaction
    await db_session.refresh(investigation)
    return investigation


class MockLLMClient:
    """
    Mock LLM client for testing without external API calls.
    Returns deterministic responses based on input.
    """

    def __init__(self, responses: dict | None = None):
        """
        Initializes the mock response handler.

        Args:
            responses (dict | None): Optional mapping of request identifiers to predefined responses. If omitted or None, an empty dictionary is used.

        Attributes set:
            responses (dict): Stores the provided or default response mappings.
            call_count (int): Counter tracking how many times a mocked request has been made.
            last_request: Holds the most recent request object received; initially None.
        """
        self.responses = responses or {}
        self.call_count = 0
        self.last_request = None

    async def chat_completion(
        self,
        messages: list,
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> dict:
        """
        Mock implementation of a chat completion endpoint.

        Parameters
        ----------
        messages : list
            A list of message dictionaries representing the conversation history.
            Each dictionary should contain at least `"role"` (e.g., "user", "assistant")
            and `"content"` keys.
        model : str, optional
            The identifier of the language model to emulate. Defaults to `"gpt-4"`.
        temperature : float, optional
            Sampling temperature that influences randomness of the response.
            This value is recorded but not used in the mock logic. Default is `0.7`.
        max_tokens : int, optional
            Maximum number of tokens the mock should pretend to generate.
            This parameter is stored for inspection only. Default is `1000`.

        Returns
        -------
        dict
            A dictionary mimicking the structure returned by OpenAI's chat completion API.
            If the user message matches a key in `self.responses`, the corresponding
            pre-configured response is returned; otherwise a default mock payload is
            generated, containing an incremental `id` (e.g., `"mock-1"`), model name,
            fixed timestamps, a single choice with a generic assistant reply, and token usage
            statistics.

        Notes
        -----
        The method updates `self.call_count` and `self.last_request` to allow test code
        to verify how many times the endpoint was invoked and with what arguments. The mock does not perform any real language model inference.
        """
        self.call_count += 1
        self.last_request = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Extract user message for response matching
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")

        # Return pre-configured response or default
        if user_msg in self.responses:
            return self.responses[user_msg]

        # Default response
        return {
            "id": f"mock-{self.call_count}",
            "object": "chat.completion",
            "created": 1234567890,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Mock LLM response",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }


@pytest.fixture(scope="function")
def mock_llm_client() -> MockLLMClient:
    """
    Provides a mock implementation of an LLM client for use in tests.

    Returns
    -------
    MockLLMClient
        An instance of :class:`MockLLMClient` that mimics the behavior of the real language-model client without making external API calls. This object can be configured within test cases to return predefined responses, track usage, and simulate error conditions as needed.
    """
    return MockLLMClient()


@pytest.fixture(scope="function")
def mock_intent_classifier(mock_llm_client: MockLLMClient) -> MockLLMClient:
    """
    Configure a mock LLM client with predefined responses for intent classification.

    Parameters
    ----------
    mock_llm_client: MockLLMClient
        An instance of the mock LLM client whose `responses` attribute will be populated.

    Returns
    -------
    MockLLMClient
        The same mock LLM client instance, now configured with canned responses mapping specific user prompts to JSON-encoded intent payloads. These payloads include an `intent` string, a confidence score, and a reasoning description, enabling deterministic testing of the application's intent handling logic.
    """
    mock_llm_client.responses = {
        "Show me timeline entries": {
            "choices": [
                {
                    "message": {
                        "content": '{"intent": "timeline_query", "confidence": 0.95, "reasoning": "User wants to view timeline"}'
                    }
                }
            ]
        },
        "Find failed logon attempts": {
            "choices": [
                {
                    "message": {
                        "content": '{"intent": "execute_agent_policy", "confidence": 0.9, "reasoning": "Requires event search"}'
                    }
                }
            ]
        },
        "What is this investigation about?": {
            "choices": [
                {
                    "message": {
                        "content": '{"intent": "general_chat", "confidence": 0.85, "reasoning": "Metadata question"}'
                    }
                }
            ]
        },
        "Is there evidence of credential access?": {
            "choices": [
                {
                    "message": {
                        "content": '{"intent": "augmented_chat", "confidence": 0.88, "reasoning": "Semantic search query"}'
                    }
                }
            ]
        },
    }
    return mock_llm_client


class MockEmbeddingService:
    """
    Mock embedding service for RAG tests.
    Returns deterministic vectors based on text input.
    """

    def __init__(self, dimension: int = 1536):
        """
        Initializes the object with a specified embedding dimension.

        Args:
            dimension (int, optional): The size of the vector space for embeddings. Defaults to 1536.

        Attributes:
            dimension (int): Stores the configured embedding dimensionality.
            call_count (int): Counter tracking how many times the object's primary method has been invoked; initialized to zero.
        """
        self.dimension = dimension
        self.call_count = 0

    async def generate_embedding(self, text: str) -> list[float]:
        """
        Generate a deterministic embedding vector for the given text.\n\nParameters\n----------\ntext: str\n    The input string to be embedded.\n\nReturns\n-------\nlist[float]\n    A list of floats representing the embedding vector, deterministically derived from the hash of `text`. The length of the list equals the instance's `dimension` attribute.\n\nNotes\n-----\nThe method increments `self.call_count` each time it is invoked and uses a simple deterministic algorithm based on Python's built-in `hash` function to ensure reproducible results across calls with the same input.\"""
        """
        self.call_count += 1

        # Simple deterministic vector based on text hash
        text_hash = hash(text)
        vector = [(text_hash % (i + 1)) / (i + 1) / 1000.0 for i in range(self.dimension)]
        return vector

    async def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.

        Parameters
        ----------
        texts: list[str]
            A sequence of text strings for which embeddings should be computed.

        Returns
        -------
        list[list[float]]
            A list where each element is the embedding vector (a list of floats) corresponding to the input text at the same position.

        Notes
        -----
        This coroutine internally calls :meth:`generate_embedding` for each text, preserving order. It runs sequentially; consider parallelizing if performance is a concern.
        """
        return [await self.generate_embedding(text) for text in texts]


@pytest.fixture(scope="function")
def mock_embedding_service() -> MockEmbeddingService:
    """
    Provides a mock implementation of the embedding service used in tests.

    Returns
    -------
    MockEmbeddingService
        An instance of `MockEmbeddingService` that mimics the behavior of the real embedding service for testing purposes.
    """
    return MockEmbeddingService()


class DeterministicUUID:
    """
    Generate deterministic UUIDs for testing.
    """

    def __init__(self, start: int = 1):
        """
        Initializes a new counter instance.

        Parameters
        ----------
        start: int, optional
            The starting value for the counter. Defaults to `1`.
        """
        self.counter = start

    def __call__(self) -> uuid.UUID:
        """
        Generate the next deterministic UUID in the sequence.

        Returns
        -------
        uuid.UUID
            A UUID object constructed from a zero-filled prefix and the current counter value,
            formatted as `00000000-0000-0000-0000-{counter:012d}`. The internal counter is
            incremented after each call.
        """
        uuid_str = f"00000000-0000-0000-0000-{self.counter:012d}"
        self.counter += 1
        return uuid.UUID(uuid_str)


@pytest.fixture(scope="function")
def deterministic_uuid() -> DeterministicUUID:
    """
    Creates and returns a :class:`DeterministicUUID` instance that generates UUIDs in a reproducible,
    predictable sequence. This is useful for tests where consistent identifiers are required.

    Returns
    -------
    DeterministicUUID
        A deterministic UUID generator instance.
    """
    return DeterministicUUID()


def pytest_configure(config):
    """
    Configure pytest by adding custom markers for categorizing tests.

    Adds the following markers:
    - `unit`: Unit tests that don't require a database or external services.
    - `integration`: Integration tests that require a database.
    - `e2e`: End-to-end tests that require the full stack.
    - `slow`: Tests that take longer than one second.
    """
    config.addinivalue_line(
        "markers", "unit: Unit tests that don't require database or external services"
    )
    config.addinivalue_line("markers", "integration: Integration tests that require database")
    config.addinivalue_line("markers", "e2e: End-to-end tests that require full stack")
    config.addinivalue_line("markers", "slow: Tests that take longer than 1 second")
