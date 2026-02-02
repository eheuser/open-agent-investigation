import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from uuid import uuid4
import yaml

from app.services.policy_router import (
    extract_policy_name,
    load_policy,
    VALID_POLICIES,
)


@pytest.mark.unit
class TestExtractPolicyName:
    """Test extract_policy_name function."""

    def test_exact_match(self):
        """
        Test that `extract_policy_name` correctly returns the exact policy name when the response string matches a known policy identifier.
        """
        response = "event_search"

        result = extract_policy_name(response)

        assert result == "event_search"

    def test_exact_match_with_whitespace(self):
        """
        Test that `extract_policy_name` correctly trims leading and trailing whitespace from a response string and returns the exact policy name without surrounding spaces.
        """
        response = "  event_search  "

        result = extract_policy_name(response)

        assert result == "event_search"

    def test_policy_name_at_start(self):
        """
        Test that `extract_policy_name` correctly identifies and returns the policy name when it appears at the very beginning of the response string. The test supplies a sample response where the policy name is the first word followed by additional text, invokes the function, and asserts that the returned value matches the expected policy identifier.
        """
        response = "event_search is the best policy for this question"

        result = extract_policy_name(response)

        assert result == "event_search"

    def test_policy_name_in_middle(self):
        """
        Test that extract_policy_name correctly identifies a policy name appearing in the middle of a response string, ensuring it returns the expected policy identifier.
        """
        response = "I recommend using event_search for this analysis"

        result = extract_policy_name(response)

        assert result == "event_search"

    def test_empty_response(self):
        """
        Test that an empty LLM response defaults to the first valid policy name. The function extracts the policy name from an empty string and asserts that the result is one of the allowed policies, effectively verifying fallback to a default policy.
        """
        response = ""

        result = extract_policy_name(response)

        # Should return default policy (first in VALID_POLICIES)
        assert result in VALID_POLICIES

    def test_none_response(self):
        """
        Test that `extract_policy_name` correctly handles a `None` response by returning one of the allowed default policies defined in `VALID_POLICIES`.
        """
        response = None

        result = extract_policy_name(response)

        # Should return default policy
        assert result in VALID_POLICIES

    def test_invalid_policy_name(self):
        """
        Test that when the LLM response contains an invalid or non-existent policy name, :func:`extract_policy_name` falls back to a default policy by returning a value present in `VALID_POLICIES`. This ensures graceful handling of unexpected policy identifiers without raising errors.
        """
        response = "invalid_policy_that_does_not_exist"

        result = extract_policy_name(response)

        # Should return default policy
        assert result in VALID_POLICIES

    def test_case_insensitive_matching(self):
        """
        Test that policy name extraction is case-insensitive.

        The test provides an uppercase response string `"EVENT_SEARCH"`, calls :func:`extract_policy_name`, and asserts that the returned value is the lowercase policy identifier `"event_search"`. This ensures the extraction function normalises policy names regardless of input casing.
        """
        response = "EVENT_SEARCH"

        result = extract_policy_name(response)

        assert result == "event_search"


@pytest.mark.unit
class TestLoadPolicy:
    """Test load_policy function."""

    def test_load_existing_policy(self):
        """
        Test that loading an existing policy file returns the correct parsed content.

        The test creates a mock YAML policy definition containing a title, description, rules, and seed instructions. It patches `open` to supply this content and patches `Path.is_file` to indicate the file exists. After calling :func:`load_policy` with the policy name `"event_search"`, it asserts that:

        - The returned dictionary contains the expected `title` value.
        - A `rules` key is present in the result.
        - A `seed_instructions` key is present in the result.

        This verifies that a valid policy file is read, parsed, and its essential fields are correctly extracted.
        """
        policy_content = """
title: Event Search Policy
description: Search for events
rules:
  timeframe:
    type: string
    default: "24h"
seed_instructions: "Search for {question}"
"""

        with patch("builtins.open", mock_open(read_data=policy_content)):
            with patch("pathlib.Path.is_file", return_value=True):
                policy = load_policy("event_search")

                assert policy["title"] == "Event Search Policy"
                assert "rules" in policy
                assert "seed_instructions" in policy

    def test_load_nonexistent_policy(self):
        """
        Test that loading a policy with a name that does not correspond to an existing file raises a FileNotFoundError by mocking pathlib.Path.is_file to return False.
        """
        with patch("pathlib.Path.is_file", return_value=False):
            with pytest.raises(FileNotFoundError):
                load_policy("nonexistent_policy")

    def test_load_policy_with_complex_rules(self):
        """
        Test that loading a policy file containing complex rule definitions correctly parses each rule's attributes, such as type, options, and default values, ensuring the resulting policy dictionary reflects the expected structure for both select-type and numeric rules.
        """
        policy_content = """
title: Complex Policy
rules:
  severity:
    type: select
    options: [low, medium, high]
    default: medium
  max_events:
    type: number
    default: 100
seed_instructions: "Analyze with severity={severity}"
"""

        with patch("builtins.open", mock_open(read_data=policy_content)):
            with patch("pathlib.Path.is_file", return_value=True):
                policy = load_policy("complex_policy")

                assert policy["rules"]["severity"]["type"] == "select"
                assert policy["rules"]["severity"]["default"] == "medium"
                assert policy["rules"]["max_events"]["default"] == 100


@pytest.mark.unit
class TestCallLLMBackend:
    """Test call_llm_backend function."""

    async def test_no_llm_config(self):
        """
        Test that the LLM backend correctly falls back to a default policy when no active LLM configuration is found.

        The test creates an asynchronous mock database connection and a sample user identifier, then patches `get_active_llm_config` to return `None`. It invokes `call_llm_backend` with a simple prompt and verifies that the returned dictionary contains a `policy` key whose value belongs to the predefined set of valid policies (`VALID_POLICIES`). This ensures graceful handling of missing LLM configuration without raising errors.
        """
        from app.services.policy_router import call_llm_backend

        db = AsyncMock()
        user_id = 1

        with patch("app.services.policy_router.get_active_llm_config", return_value=None):
            result = await call_llm_backend(db, user_id, "test prompt")

            # Should return default policy
            assert "policy" in result
            assert result["policy"] in VALID_POLICIES

    async def test_llm_returns_valid_policy(self):
        """
        Test that the LLM backend call returns a valid policy name and raw response when the external API responds with a successful 200 status and a JSON payload containing the expected policy identifier. The test mocks the active LLM configuration, HTTP client session, and response to isolate the behavior of `call_llm_backend` without making real network requests. It verifies that the returned dictionary includes both the extracted `policy` value and the original `raw_response` string.
        """
        from app.services.policy_router import call_llm_backend

        db = AsyncMock()
        user_id = 1

        # Mock LLM config
        mock_config = MagicMock()
        mock_config.api_endpoint = "https://api.example.com/v1/chat/completions"
        mock_config.api_key = "test-key"
        mock_config.model_name = "gpt-4"
        mock_config.temperature = 0.0
        mock_config.top_p = None
        mock_config.top_k = None
        mock_config.min_p = None

        # Mock HTTP response
        mock_response = {"choices": [{"message": {"content": "event_search"}}]}

        with patch("app.services.policy_router.get_active_llm_config", return_value=mock_config):
            with patch("aiohttp.ClientSession") as mock_session:
                mock_post = AsyncMock()
                mock_post.__aenter__.return_value.status = 200
                mock_post.__aenter__.return_value.json = AsyncMock(return_value=mock_response)
                mock_session.return_value.__aenter__.return_value.post = MagicMock(
                    return_value=mock_post
                )

                result = await call_llm_backend(db, user_id, "test prompt")

                assert result["policy"] == "event_search"
                assert result["raw_response"] == "event_search"

    async def test_llm_error_returns_default(self):
        """
        Test that when the LLM backend encounters an HTTP error (e.g., status 500), the function falls back to returning the default policy.

        The test patches the active LLM configuration and mocks an aiohttp.ClientSession to simulate a failed request, then asserts that the result contains a "policy" key whose value is one of the predefined VALID_POLICIES. No exceptions should be raised during execution.
        """
        from app.services.policy_router import call_llm_backend

        db = AsyncMock()
        user_id = 1

        mock_config = MagicMock()
        mock_config.api_endpoint = "https://api.example.com/v1/chat/completions"
        mock_config.api_key = "test-key"
        mock_config.model_name = "gpt-4"
        mock_config.temperature = 0.0
        mock_config.top_p = None
        mock_config.top_k = None
        mock_config.min_p = None

        with patch("app.services.policy_router.get_active_llm_config", return_value=mock_config):
            with patch("aiohttp.ClientSession") as mock_session:
                # Simulate HTTP error
                mock_post = AsyncMock()
                mock_post.__aenter__.return_value.status = 500
                mock_post.__aenter__.return_value.text = AsyncMock(
                    return_value="Internal Server Error"
                )
                mock_session.return_value.__aenter__.return_value.post = MagicMock(
                    return_value=mock_post
                )

                result = await call_llm_backend(db, user_id, "test prompt")

                # Should return default policy on error
                assert "policy" in result
                assert result["policy"] in VALID_POLICIES


@pytest.mark.unit
class TestRouteQuestion:
    """Test route_question function."""

    async def test_route_with_explicit_policy(self):
        """
        Test that routing a question with an explicitly supplied policy identifier correctly loads the specified policy file, enqueues a job via `enqueue_agent_job`, and returns a response indicating the job was queued.

        Parameters
        ----------
        self : object
            The test case instance.
        db : AsyncMock
            Mocked asynchronous database session passed to `route_question`.
        investigation_id : uuid.UUID
            Unique identifier for the investigation context.
        user_id : int
            Identifier of the user making the request.
        question : str
            The question string that will be routed.
        policy_id : str
            Explicit policy name (e.g., `"event_search"`) to be used by the router.

        Returns
        -------
        dict
            A dictionary with keys:
                * `type` - should be `"job_queued"`,
                * `job_id` - the UUID of the mocked job returned by `enqueue_agent_job`,
                * `policy_id` - echoing the provided policy identifier.

        Raises
        ------
        AssertionError
            If any of the expected response fields are missing or contain incorrect values.
        """
        from app.services.policy_router import route_question

        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        # Mock policy file
        policy_content = """
title: Test Policy
rules: {}
seed_instructions: "Test {question}"
"""

        # Mock job creation
        mock_job = MagicMock()
        mock_job.job_id = uuid4()

        with patch("builtins.open", mock_open(read_data=policy_content)):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("app.services.policy_router.get_active_parsing_jobs", return_value=[]):
                    with patch("app.services.policy_router.enqueue_agent_job", return_value=mock_job):
                        result = await route_question(
                            db=db,
                            investigation_id=investigation_id,
                            question="Test question",
                            user_id=user_id,
                            policy_id="event_search",
                        )

                        assert result["type"] == "job_queued"
                        assert result["job_id"] == mock_job.job_id
                        assert result["policy_id"] == "event_search"

    async def test_route_with_missing_rules(self):
        """
        Test routing behavior when the selected policy defines required rules that are not provided in the request.

        This asynchronous unit test verifies that:
        - The `route_question` service loads a policy file containing rule definitions.
        - When the incoming question does not supply values for those required rules, the service returns a clarification request instead of proceeding with routing.
        - The returned payload includes:
          * `"type"` set to `"clarification_request"`.
          * `"policy_id"` matching the requested policy identifier.
          * A `"missing_rules"` list whose length corresponds to the number of undefined mandatory rules (two in this test case).
        """
        from app.services.policy_router import route_question

        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        # Mock policy with required rules
        policy_content = """
title: Test Policy
rules:
  timeframe:
    type: string
    description: "Time range to search"
  severity:
    type: select
    description: "Severity level"
    options: [low, medium, high]
seed_instructions: "Test {question}"
"""

        with patch("builtins.open", mock_open(read_data=policy_content)):
            with patch("pathlib.Path.is_file", return_value=True):
                result = await route_question(
                    db=db,
                    investigation_id=investigation_id,
                    question="Test question",
                    user_id=user_id,
                    policy_id="event_search",
                )

                # Should request clarification
                assert result["type"] == "clarification_request"
                assert result["policy_id"] == "event_search"
                assert len(result["missing_rules"]) == 2

    async def test_route_with_default_rules(self):
        """
        Test routing when rules have default values.

        This test verifies that `route_question` correctly handles policies containing rule definitions with default values. It mocks a policy file specifying a `timeframe` rule of type `string` with a default of `"24h"`, and ensures that the resulting job is queued using these defaults when no explicit value is provided in the request.

        Args:
            self: The test case instance (inherited from `unittest.IsolatedAsyncioTestCase` or similar).

        The function performs the following steps:
        - Imports the `route_question` function from `app.services.policy_router`.
        - Sets up mock objects for the database connection, investigation ID, and user ID.
        - Creates a temporary policy definition with default rule values.
        - Mocks file I/O to return the policy content and patches path checks to indicate the policy file exists.
        - Patches `enqueue_agent_job` to return a mocked job object.
        - Calls `route_question` with the mock dependencies and asserts that the result indicates a queued job (`result["type"] == "job_queued"`).
        """
        from app.services.policy_router import route_question

        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        # Mock policy with default rules
        policy_content = """
title: Test Policy
rules:
  timeframe:
    type: string
    default: "24h"
seed_instructions: "Search for {question} in {timeframe}"
"""

        mock_job = MagicMock()
        mock_job.job_id = uuid4()

        with patch("builtins.open", mock_open(read_data=policy_content)):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("app.services.policy_router.get_active_parsing_jobs", return_value=[]):
                    with patch("app.services.policy_router.enqueue_agent_job", return_value=mock_job):
                        result = await route_question(
                            db=db,
                            investigation_id=investigation_id,
                            question="Test question",
                            user_id=user_id,
                            policy_id="event_search",
                        )

                        # Should create job with default values
                        assert result["type"] == "job_queued"

    async def test_route_with_nonexistent_policy(self):
        """
        Test that routing a question with a policy identifier that does not correspond to an existing policy file results in an error response.

        The test patches `Path.is_file` to simulate the absence of the specified policy file, then calls `route_question` with a non-existent `policy_id`. It asserts that the returned dictionary has a `type` key equal to `"error"` and that its `message` contains the phrase “not found”, confirming proper error handling for missing policies.
        """
        from app.services.policy_router import route_question

        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        with patch("pathlib.Path.is_file", return_value=False):
            result = await route_question(
                db=db,
                investigation_id=investigation_id,
                question="Test question",
                user_id=user_id,
                policy_id="nonexistent_policy",
            )

            # Should return error
            assert result["type"] == "error"
            assert "not found" in result["message"]
