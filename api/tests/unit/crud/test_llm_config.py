"""
Unit tests for LLM config CRUD operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.crud.llm_config import (
    create_llm_config,
    get_llm_config_by_id,
    get_active_llm_config,
    list_llm_configs,
    update_llm_config,
    delete_llm_config,
)
from app.models.llm_config import LLMProviderConfig


@pytest.mark.unit
class TestCreateLLMConfig:
    """Test create_llm_config function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure a mocked asynchronous database session.

        This helper constructs an :class:`unittest.mock.AsyncMock` instance that mimics a typical SQLAlchemy async session used in the tests. The mock provides:

        * `add` - a synchronous :class:`unittest.mock.MagicMock` for adding objects to the session.
        * `commit` - an asynchronous mock representing the commit operation.
        * `refresh` - an asynchronous mock used to refresh instances after persistence.

        The returned object can be injected into code under test to simulate database interactions without requiring a real database connection.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_create_llm_config_minimal(self, mock_db):
        """
        Test creating an LLM provider configuration with only the required fields.

        The test sets up minimal valid input values for a new configuration, calls `create_llm_config` with those arguments (leaving optional fields such as `api_key` unset), and then verifies that:

        * The database session's `add`, `commit` and `refresh` methods are each called exactly once.
        * The object passed to `db.add` is an instance of :class:`LLMProviderConfig`.
        * All supplied attributes (`user_id`, `provider_name`, `api_endpoint`, `model_name`, `max_context_length` and `temperature`) are correctly stored on the created configuration.
        * Default values are applied for fields not provided: `is_active` is `True` and `timeout` defaults to `300`.
        """
        user_id = 1
        provider_name = "openai"
        api_endpoint = "https://api.openai.com/v1/chat/completions"
        model_name = "gpt-4"
        max_context_length = 8192
        temperature = 0.7

        result = await create_llm_config(
            db=mock_db,
            user_id=user_id,
            provider_name=provider_name,
            api_endpoint=api_endpoint,
            api_key=None,
            model_name=model_name,
            max_context_length=max_context_length,
            temperature=temperature,
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify config object
        added_config = mock_db.add.call_args[0][0]
        assert isinstance(added_config, LLMProviderConfig)
        assert added_config.user_id == user_id
        assert added_config.provider_name == provider_name
        assert added_config.api_endpoint == api_endpoint
        assert added_config.model_name == model_name
        assert added_config.max_context_length == max_context_length
        assert added_config.temperature == temperature
        assert added_config.is_active is True  # Default
        assert added_config.timeout == 300  # Default

    async def test_create_llm_config_full(self, mock_db):
        """
        Test that creating an LLM configuration with all possible fields correctly passes the provided values to the database layer.

        The test invokes `create_llm_config` with a full set of arguments, including standard LLM settings (provider name, API endpoint, key, model name, context length, temperature, top-p, top-k, min-p, timeout, active flag) and embedding configuration (provider, API URL, key, model name). After awaiting the creation call, it inspects the object that was added to the mocked database via `mock_db.add` and asserts that each attribute on the stored configuration matches the corresponding input value. This ensures that the function correctly maps all supplied parameters to the persisted LLM config record.
        """
        result = await create_llm_config(
            db=mock_db,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            api_key="sk-test123",
            model_name="gpt-4",
            max_context_length=8192,
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            min_p=0.05,
            timeout=600,
            is_active=True,
            embedding_provider="openai",
            embedding_api_url="https://api.openai.com/v1/embeddings",
            embedding_api_key="sk-embed123",
            embedding_model_name="text-embedding-ada-002",
        )

        added_config = mock_db.add.call_args[0][0]
        assert added_config.api_key == "sk-test123"
        assert added_config.top_p == 0.9
        assert added_config.top_k == 40
        assert added_config.min_p == 0.05
        assert added_config.timeout == 600
        assert added_config.embedding_provider == "openai"
        assert added_config.embedding_api_url == "https://api.openai.com/v1/embeddings"
        assert added_config.embedding_api_key == "sk-embed123"
        assert added_config.embedding_model_name == "text-embedding-ada-002"

    async def test_create_llm_config_with_concurrent_and_reranker(self, mock_db):
        """
        Test creating an LLM config with concurrent calls and reranker settings.
        """
        result = await create_llm_config(
            db=mock_db,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            api_key="sk-test123",
            model_name="gpt-4",
            max_context_length=128000,
            temperature=0.7,
            allow_concurrent_llm_calls=True,
            embedding_provider="openai",
            embedding_api_url="https://api.openai.com/v1/embeddings",
            embedding_api_key="sk-embed123",
            embedding_model_name="text-embedding-3-small",
            embedding_max_context_length=8192,
            reranker_model_name="text-embedding-3-large",
            reranker_max_context_length=8192,
            allow_concurrent_embedding_calls=True,
        )

        added_config = mock_db.add.call_args[0][0]
        assert added_config.allow_concurrent_llm_calls is True
        assert added_config.embedding_max_context_length == 8192
        assert added_config.reranker_model_name == "text-embedding-3-large"
        assert added_config.reranker_max_context_length == 8192
        assert added_config.allow_concurrent_embedding_calls is True

    async def test_create_llm_config_new_fields_defaults(self, mock_db):
        """
        Test that new fields have correct defaults when not provided.
        """
        result = await create_llm_config(
            db=mock_db,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            api_key="sk-test123",
            model_name="gpt-4",
            max_context_length=8192,
            temperature=0.7,
            # Don't provide new fields
        )

        added_config = mock_db.add.call_args[0][0]
        assert added_config.allow_concurrent_llm_calls is False
        assert added_config.allow_concurrent_embedding_calls is False
        assert added_config.embedding_max_context_length == 8192
        assert added_config.reranker_max_context_length == 8192

    async def test_create_llm_config_inactive(self, mock_db):
        """
        Test that creating an LLM configuration with `is_active=False` correctly stores the inactive flag.

        The test invokes :func:`create_llm_config` with typical parameters for an Ollama provider, explicitly passing `is_active=False`. After awaiting the creation call, it inspects the object passed to the mocked database's `add` method and asserts that its `is_active` attribute is `False`, confirming that inactive configurations are persisted as such.
        """
        result = await create_llm_config(
            db=mock_db,
            user_id=1,
            provider_name="ollama",
            api_endpoint="http://localhost:11434/v1/chat/completions",
            api_key=None,
            model_name="llama2",
            max_context_length=4096,
            temperature=0.5,
            is_active=False,
        )

        added_config = mock_db.add.call_args[0][0]
        assert added_config.is_active is False


@pytest.mark.unit
class TestGetLLMConfigByID:
    """Test get_llm_config_by_id function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return an `AsyncMock` instance that simulates an asynchronous database session for use in unit tests. The returned object mimics the interface of a real async DB session, allowing coroutine methods to be awaited without performing actual I/O.
        """
        db = AsyncMock()
        return db

    async def test_get_llm_config_found(self, mock_db):
        """
        Test that retrieving an existing LLM provider configuration by its identifier returns the correct object.

        The test sets up a mock database session that returns a predefined `LLMProviderConfig` instance when `scalar_one_or_none` is called, invokes `get_llm_config_by_id` with the mock session and the target ID, and then asserts that:

        * The returned value matches the expected configuration.
        * The database `execute` method was called exactly once.
        """
        config_id = 1
        expected_config = LLMProviderConfig(
            config_id=config_id,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            model_name="gpt-4",
            max_context_length=8192,
            temperature=0.7,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_config
        mock_db.execute.return_value = mock_result

        result = await get_llm_config_by_id(mock_db, config_id)

        assert result == expected_config
        mock_db.execute.assert_called_once()

    async def test_get_llm_config_not_found(self, mock_db):
        """
        Test that retrieving a LLM provider configuration by an identifier that does not exist returns `None` and that the database execute method is called exactly once.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate the query execution.

        Returns:
            None - this test asserts behavior rather than returning a value.
        """
        config_id = 999

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_llm_config_by_id(mock_db, config_id)

        assert result is None
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestGetActiveLLMConfig:
    """Test get_active_llm_config function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mock asynchronous database session used in unit tests.

        The returned object is an instance of :class:`unittest.mock.AsyncMock` that mimics the behavior of an async DB session, allowing test code to configure expected method calls and return values without requiring a real database connection.
        """
        db = AsyncMock()
        return db

    async def test_get_active_llm_config_found(self, mock_db):
        """
        Test that get_active_llm_config correctly retrieves an active LLM provider configuration for a given user when it exists in the database.

        Args:
            self: TestCase instance.
            mock_db: A mocked asynchronous database session used to simulate the execute call.

        Returns:
            None; asserts are performed within the test to verify that the returned configuration matches the expected LLMProviderConfig and that the database execute method was called exactly once.
        """
        user_id = 1
        expected_config = LLMProviderConfig(
            config_id=1,
            user_id=user_id,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            model_name="gpt-4",
            max_context_length=8192,
            temperature=0.7,
            is_active=True,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_config
        mock_db.execute.return_value = mock_result

        result = await get_active_llm_config(mock_db, user_id)

        assert result == expected_config
        mock_db.execute.assert_called_once()

    async def test_get_active_llm_config_not_found(self, mock_db):
        """
        Test that get_active_llm_config returns `None` when the specified user has no active configuration in the database. The mock database is set up so that `scalar_one_or_none` yields `None`, and the test asserts the function result is `None` while also verifying that `execute` was called exactly once.
        """
        user_id = 999

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_active_llm_config(mock_db, user_id)

        assert result is None
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestListLLMConfigs:
    """Test list_llm_configs function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mock asynchronous database session for use in tests.

        This helper constructs an :class:`unittest.mock.AsyncMock` instance that mimics the
        behaviour of an async database connection/session. The returned mock can be
        configured with expected return values or side effects to simulate various
        database interactions without requiring a real database backend.
        """
        db = AsyncMock()
        return db

    async def test_list_llm_configs_with_results(self, mock_db):
        """
        Test that `list_llm_configs` returns all LLM provider configurations belonging to a given user.\n\nThe test sets up a mock database session that, when `execute` is called, yields a result whose `scalars().all()` method returns a predefined list of two :class:`LLMProviderConfig` instances. It then invokes `list_llm_configs` with the mocked session and the target `user_id`.\n\nAssertions verify that:\n- The returned collection contains exactly two items.\n- The returned collection matches the expected configuration objects.\n- The database session's `execute` method was called exactly once.\n\nParameters\n----------\nself: object\n    The test case instance (provided by the unittest framework).\nmock_db: MagicMock\n    A mock representing an asynchronous SQLAlchemy session used to simulate database interactions.\"""
        """
        user_id = 1
        configs = [
            LLMProviderConfig(
                config_id=1,
                user_id=user_id,
                provider_name="openai",
                api_endpoint="https://api.openai.com/v1/chat/completions",
                model_name="gpt-4",
                max_context_length=8192,
                temperature=0.7,
                is_active=True,
            ),
            LLMProviderConfig(
                config_id=2,
                user_id=user_id,
                provider_name="ollama",
                api_endpoint="http://localhost:11434/v1/chat/completions",
                model_name="llama2",
                max_context_length=4096,
                temperature=0.5,
                is_active=False,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = configs
        mock_db.execute.return_value = mock_result

        result = await list_llm_configs(mock_db, user_id)

        assert len(result) == 2
        assert result == configs
        mock_db.execute.assert_called_once()

    async def test_list_llm_configs_empty(self, mock_db):
        """
        Test that listing LLM configurations returns an empty list when no configurations exist for the specified user.

        The test mocks the database's `execute` method to return a result whose `scalars().all()` call yields an empty list, simulating the absence of any stored configurations. It then calls :func:`list_llm_configs` with the mocked database and verifies that the function returns an empty list. Additionally, it asserts that the database `execute` method was invoked exactly once.
        """
        user_id = 999

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await list_llm_configs(mock_db, user_id)

        assert result == []
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestUpdateLLMConfig:
    """Test update_llm_config function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mock asynchronous database session with an async `commit` method for use in unit tests. The returned object mimics the interface of an async SQLAlchemy session, allowing test code to call `await db.commit()` without performing any real database operations.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    async def test_update_llm_config_single_field(self, mock_db):
        """
        Test that updating a single field of an LLM provider configuration works correctly.\n\nThe test creates a mock database session and configures it to return a predefined `LLMProviderConfig` instance when the update query is executed. It then calls :func:`update_llm_config` with only the `model_name` argument changed, asserts that the returned object matches the expected updated configuration, and verifies that the database `execute` and `commit` methods were each called exactly once.\n\nArgs:\n    self: The test case instance (provided by the unittest framework).\n    mock_db: A mocked asynchronous database session injected via a fixture, used to simulate query execution and transaction commit.\n\nThe function does not return a value; it uses assertions to validate behavior.
        """
        config_id = 1
        updated_config = LLMProviderConfig(
            config_id=config_id,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            model_name="gpt-4-turbo",  # Updated
            max_context_length=8192,
            temperature=0.7,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = updated_config
        mock_db.execute.return_value = mock_result

        result = await update_llm_config(
            db=mock_db,
            config_id=config_id,
            model_name="gpt-4-turbo",
        )

        assert result == updated_config
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_update_llm_config_multiple_fields(self, mock_db):
        """
        Test updating multiple fields of an LLM provider configuration.\n\nThis asynchronous unit test verifies that `update_llm_config` correctly updates several fields-specifically `model_name`, `max_context_length` and `temperature`-for a given configuration ID. It uses a mocked database session to simulate the execution of the update query and returns a pre-constructed `LLMProviderConfig` instance representing the updated record.\n\nThe test performs the following steps:\n1. Defines the target `config_id` and creates an `updated_config` object with the expected values after the update.\n2. Configures the mock database's `execute` method to return a `MagicMock` whose `scalar_one_or_none` method yields `updated_config`.\n3. Calls `update_llm_config` with the mock database and the new field values.\n4. Asserts that the function returns the exact `updated_config` instance, confirming that the update logic correctly interacts with the database layer and propagates the updated configuration.\n\nNo explicit arguments are passed to this test method beyond the fixture-provided `mock_db`; the function under test receives `db`, `config_id` and the fields to be updated. The expected return value is an instance of `LLMProviderConfig` reflecting the applied changes.
        """
        config_id = 1
        updated_config = LLMProviderConfig(
            config_id=config_id,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            model_name="gpt-4-turbo",
            max_context_length=128000,
            temperature=0.8,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = updated_config
        mock_db.execute.return_value = mock_result

        result = await update_llm_config(
            db=mock_db,
            config_id=config_id,
            model_name="gpt-4-turbo",
            max_context_length=128000,
            temperature=0.8,
        )

        assert result == updated_config

    async def test_update_llm_config_no_changes(self, mock_db):
        """
        Test that updating an LLM provider configuration with no changes (all optional parameters omitted) returns the original configuration unchanged and does not trigger any database update operations. The test mocks the retrieval of the existing configuration, invokes `update_llm_config` without modification arguments, asserts that the returned object matches the original, and verifies that `mock_db.execute` was never called.
        """
        config_id = 1
        existing_config = LLMProviderConfig(
            config_id=config_id,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            model_name="gpt-4",
            max_context_length=8192,
            temperature=0.7,
        )

        # Mock get_llm_config_by_id
        with patch("app.crud.llm_config.get_llm_config_by_id", return_value=existing_config):
            result = await update_llm_config(
                db=mock_db,
                config_id=config_id,
            )

        # Should return existing config without executing update
        assert result == existing_config
        mock_db.execute.assert_not_called()

    async def test_update_llm_config_not_found(self, mock_db):
        """
        Test that updating an LLM provider configuration with an ID that does not exist in the database returns `None`. The test mocks the database execution to yield a result whose `scalar_one_or_none` method returns `None`, simulating a missing record. It then calls `update_llm_config` with the mock DB, a non-existent `config_id` and a new `model_name`. Finally, it asserts that the function under test returns `None` to indicate that no configuration was found to update.
        """
        config_id = 999

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await update_llm_config(
            db=mock_db,
            config_id=config_id,
            model_name="gpt-4",
        )

        assert result is None


@pytest.mark.unit
class TestDeleteLLMConfig:
    """Test delete_llm_config function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure a mock asynchronous database session for use in tests.

        The returned object mimics an async SQLAlchemy session:
        * It is an instance of :class:`unittest.mock.AsyncMock`.
        * Its `commit` attribute is also an :class:`AsyncMock`, allowing calls such as `await db.commit()` without side effects.

        Returns
        -------
        AsyncMock
            A mock database session with a mocked `commit` coroutine.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    async def test_delete_llm_config_success(self, mock_db):
        """
        Test that deleting an existing LLM provider configuration succeeds.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate the delete operation.

        Returns:
            None - assertions are made within the test to verify behavior.
        """
        config_id = 1

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await delete_llm_config(mock_db, config_id)

        assert result is True
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_delete_llm_config_not_found(self, mock_db):
        """
        Test that attempting to delete a non-existent LLM provider configuration returns `False` and triggers the expected database calls.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate the execution and commit operations.

        The test sets up `mock_db.execute` to return a result with `rowcount` equal to `0`, indicating that no rows were affected. It then calls :func:`delete_llm_config` with a configuration ID that does not exist, asserts that the function returns `False`, and verifies that both `execute` and `commit` were invoked exactly once.
        """
        config_id = 999

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await delete_llm_config(mock_db, config_id)

        assert result is False
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()


@pytest.mark.unit
class TestLLMConfigCRUDEdgeCases:
    """Test edge cases for LLM config CRUD operations."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure a mocked asynchronous database session.

        This helper constructs an `AsyncMock` instance that mimics the essential
        behaviour of an async SQLAlchemy session used in the tests.  The returned
        object provides:

        * `add` - a synchronous `MagicMock` for adding objects to the session.
        * `commit` - an `AsyncMock` representing the asynchronous commit call.
        * `refresh` - an `AsyncMock` for refreshing instances after commit.

        The mock is intended for use in unit tests where database interactions
        are simulated rather than performed against a real database.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_create_llm_config_with_very_high_temperature(self, mock_db):
        """
        Test that creating an LLM configuration with the maximum allowed temperature (2.0) correctly stores the value in the database mock.

        The test invokes `create_llm_config` with:
        - `user_id` set to `1`,
        - `provider_name` as `"openai"`,
        - `api_endpoint` pointing to OpenAI's chat completions endpoint,
        - `api_key` left as `None` (to verify handling of missing keys),
        - `model_name` set to `"gpt-4"`,
        - `max_context_length` of `8192`, and
        - `temperature` at the upper bound of `2.0`.

        After awaiting the creation call, the test extracts the configuration object passed to `mock_db.add` and asserts that its `temperature` attribute equals `2.0`. This ensures that the function accepts and persists the highest valid temperature value without alteration.
        """
        result = await create_llm_config(
            db=mock_db,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            api_key=None,
            model_name="gpt-4",
            max_context_length=8192,
            temperature=2.0,  # Max value
        )

        added_config = mock_db.add.call_args[0][0]
        assert added_config.temperature == 2.0

    async def test_create_llm_config_with_zero_temperature(self, mock_db):
        """
        Test that creating an LLM configuration with a temperature of 0.0 stores the deterministic value correctly in the database mock. The test invokes `create_llm_config` with `temperature=0.0` and asserts that the `temperature` attribute of the added configuration object equals 0.0.
        """
        result = await create_llm_config(
            db=mock_db,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            api_key=None,
            model_name="gpt-4",
            max_context_length=8192,
            temperature=0.0,  # Deterministic
        )

        added_config = mock_db.add.call_args[0][0]
        assert added_config.temperature == 0.0

    async def test_create_llm_config_with_very_large_context(self, mock_db):
        """
        Test that creating an LLM provider configuration with an exceptionally large `max_context_length` correctly stores the specified value in the database mock.

        Args:
            self: The test case instance.
            mock_db: A mocked database session providing `add` and other ORM methods used by `create_llm_config`.

        The test invokes :func:`create_llm_config` with a `max_context_length` of 200,000 and then verifies that the configuration object passed to `mock_db.add` has its `max_context_length` attribute set to this value. No explicit return value is expected; assertions validate behavior.
        """
        result = await create_llm_config(
            db=mock_db,
            user_id=1,
            provider_name="anthropic",
            api_endpoint="https://api.anthropic.com/v1/messages",
            api_key=None,
            model_name="claude-3-opus",
            max_context_length=200000,  # Very large
            temperature=0.7,
        )

        added_config = mock_db.add.call_args[0][0]
        assert added_config.max_context_length == 200000

    async def test_create_llm_config_with_unicode_provider_name(self, mock_db):
        """
        Test creating an LLM provider configuration using a Unicode string for the provider name.

        This test verifies that:
        - The `create_llm_config` coroutine can handle non-ASCII characters in the `provider_name` argument.
        - The resulting configuration object stored via the mocked database has its `provider_name` attribute set to the exact Unicode value provided.
        """
        result = await create_llm_config(
            db=mock_db,
            user_id=1,
            provider_name="自定义提供商",
            api_endpoint="https://example.com/api",
            api_key=None,
            model_name="model-1",
            max_context_length=4096,
            temperature=0.7,
        )

        added_config = mock_db.add.call_args[0][0]
        assert added_config.provider_name == "自定义提供商"

    async def test_create_llm_config_with_very_long_api_key(self, mock_db):
        """
        Test that creating an LLM configuration with an excessively long API key succeeds and stores the exact key.

        The test constructs a 1002-character API key (prefix `sk-` followed by 1000 `x` characters) and calls :func:`create_llm_config` with typical parameters. After awaiting the coroutine, it inspects the object passed to the mocked database's `add` method and asserts that its `api_key` attribute matches the long value, verifying that no truncation or validation error occurs for unusually long keys.
        """
        long_api_key = "sk-" + ("x" * 1000)

        result = await create_llm_config(
            db=mock_db,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            api_key=long_api_key,
            model_name="gpt-4",
            max_context_length=8192,
            temperature=0.7,
        )

        added_config = mock_db.add.call_args[0][0]
        assert added_config.api_key == long_api_key

    async def test_update_llm_config_filters_none_values(self, mock_db):
        """
        Test that `update_llm_config` correctly filters out arguments whose value is `None` so that only provided fields are included in the update operation.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate `execute` calls.

        The test creates a sample `LLMProviderConfig` instance representing the expected updated configuration, configures the mock to return this object from `scalar_one_or_none`, and then calls `update_llm_config` with `temperature` set to a new value while passing `None` for `model_name` and `api_key`.

        The test asserts that the result returned by `update_llm_config` matches the expected configuration, confirming that only the non-`None` field (`temperature`) was applied.
        """
        config_id = 1
        updated_config = LLMProviderConfig(
            config_id=config_id,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            model_name="gpt-4",
            max_context_length=8192,
            temperature=0.8,  # Updated
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = updated_config
        mock_db.execute.return_value = mock_result

        # Pass None for some fields
        result = await update_llm_config(
            db=mock_db,
            config_id=config_id,
            temperature=0.8,
            model_name=None,  # Should be filtered out
            api_key=None,  # Should be filtered out
        )

        # Only temperature should be updated
        assert result == updated_config

    async def test_update_llm_config_concurrent_flags(self, mock_db):
        """
        Test updating concurrent call flags.
        """
        config_id = 1
        updated_config = LLMProviderConfig(
            config_id=config_id,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            model_name="gpt-4",
            max_context_length=8192,
            temperature=0.7,
            allow_concurrent_llm_calls=True,
            allow_concurrent_embedding_calls=True,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = updated_config
        mock_db.execute.return_value = mock_result

        result = await update_llm_config(
            db=mock_db,
            config_id=config_id,
            allow_concurrent_llm_calls=True,
            allow_concurrent_embedding_calls=True,
        )

        assert result.allow_concurrent_llm_calls is True
        assert result.allow_concurrent_embedding_calls is True

    async def test_update_llm_config_reranker_settings(self, mock_db):
        """
        Test updating reranker model and token limits.
        """
        config_id = 1
        updated_config = LLMProviderConfig(
            config_id=config_id,
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1/chat/completions",
            model_name="gpt-4",
            max_context_length=8192,
            temperature=0.7,
            reranker_model_name="text-embedding-3-large",
            reranker_max_context_length=16384,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = updated_config
        mock_db.execute.return_value = mock_result

        result = await update_llm_config(
            db=mock_db,
            config_id=config_id,
            reranker_model_name="text-embedding-3-large",
            reranker_max_context_length=16384,
        )

        assert result.reranker_model_name == "text-embedding-3-large"
        assert result.reranker_max_context_length == 16384
