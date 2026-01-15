"""
Integration tests for investigation choices router.
Tests choice creation, retrieval, and updates during agent execution.
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.integration
class TestInvestigationChoicesRouter:
    """Test investigation choices endpoints."""

    async def test_create_choice_success(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
        db_session,
    ):
        """
        Test creating a new investigation choice via the API.

        This integration test verifies that:
        - An `AgentJob` can be created and persisted.
        - A POST request to the `/choices` endpoint with a valid payload returns HTTP 201.
        - The response body contains the correct `agent_job_id` and reflects the submitted `choice_json`.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for testing the API.
            test_investigation: A fixture providing an investigation object with a populated `investigation_id`.
            auth_headers: Authentication headers required by the endpoint.
            db_session: Asynchronous SQLAlchemy session used to add and flush the `AgentJob` record.
        """
        from app.models.job_agent import AgentJob, JobStatus

        # Create an agent job first
        job = AgentJob(
            investigation_id=test_investigation.investigation_id,
            user_id=1,
            policy_id="test_policy.yaml",
            seed_instructions="Test instructions",
            status=JobStatus.PENDING,
        )
        db_session.add(job)
        await db_session.flush()

        response = await async_client.post(
            f"/api/v1/investigations/{test_investigation.investigation_id}/choices",
            json={
                "agent_job_id": job.job_id,
                "choice_json": {
                    "action": "search_timeline",
                    "reasoning": "Need to find events",
                    "confidence": 0.85,
                },
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["agent_job_id"] == job.job_id
        assert data["choice_json"]["action"] == "search_timeline"

    async def test_list_choices_by_investigation(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
        db_session,
    ):
        """
        Test that listing choices for a given investigation returns a successful response containing at least the two choices created during the test.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to make requests against the API.
        test_investigation : Investigation
            A fixture providing an investigation model with a valid `investigation_id`.
        auth_headers : dict
            Authentication headers required for authorized API access.
        db_session : AsyncSession
            The database session used to insert test data and flush changes.

        The test creates an agent job and two associated `InvestigationChoice` records, then sends a GET request to the `/api/v1/investigations/{investigation_id}/choices` endpoint. It asserts that the response status code is 200 and that the returned JSON array contains at least two items.
        """
        from app.models.job_agent import AgentJob, JobStatus
        from app.models.investigation_choice import InvestigationChoice

        # Create agent job
        job = AgentJob(
            investigation_id=test_investigation.investigation_id,
            user_id=1,
            policy_id="test_policy.yaml",
            seed_instructions="Test",
            status=JobStatus.PENDING,
        )
        db_session.add(job)
        await db_session.flush()

        # Create choices
        choice1 = InvestigationChoice(
            investigation_id=test_investigation.investigation_id,
            agent_job_id=job.job_id,
            choice_json={"action": "choice1"},
        )
        choice2 = InvestigationChoice(
            investigation_id=test_investigation.investigation_id,
            agent_job_id=job.job_id,
            choice_json={"action": "choice2"},
        )
        db_session.add(choice1)
        db_session.add(choice2)
        await db_session.flush()

        response = await async_client.get(
            f"/api/v1/investigations/{test_investigation.investigation_id}/choices",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2

    async def test_get_choice_by_id(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
        db_session,
    ):
        """
        Test retrieving a specific investigation choice by its identifier.

        Args:
            self: Test class instance.
            async_client (AsyncClient): HTTP client for making asynchronous requests to the API.
            test_investigation: Fixture providing an investigation object with a valid `investigation_id`.
            auth_headers (dict): Authorization headers required to authenticate the request.
            db_session: Database session fixture used to insert temporary `AgentJob` and `InvestigationChoice` records.

        The test creates a pending `AgentJob` linked to the given investigation, then adds an `InvestigationChoice` associated with that job. It issues a GET request to the `/api/v1/investigations/{investigation_id}/choices/{choice_id}` endpoint using the provided authentication headers.

        Asserts:
            - The response status code is 200 (OK).
            - The returned JSON contains the expected `choice_id`.
            - The `choice_json` field includes the correct `"action"` value as stored in the database.
        """
        from app.models.job_agent import AgentJob, JobStatus
        from app.models.investigation_choice import InvestigationChoice

        job = AgentJob(
            investigation_id=test_investigation.investigation_id,
            user_id=1,
            policy_id="test_policy.yaml",
            seed_instructions="Test",
            status=JobStatus.PENDING,
        )
        db_session.add(job)
        await db_session.flush()

        choice = InvestigationChoice(
            investigation_id=test_investigation.investigation_id,
            agent_job_id=job.job_id,
            choice_json={"action": "test_action", "confidence": 0.9},
        )
        db_session.add(choice)
        await db_session.flush()

        response = await async_client.get(
            f"/api/v1/investigations/{test_investigation.investigation_id}/choices/{choice.choice_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["choice_id"] == choice.choice_id
        assert data["choice_json"]["action"] == "test_action"

    async def test_get_choice_not_found(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that retrieving a choice with an ID that does not exist returns a 404 response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client configured for asynchronous requests against the API.
        test_investigation : Any
            Fixture providing an investigation context, including its `investigation_id`.
        auth_headers : dict
            Authentication headers required to authorize the request.

        The test sends a GET request to the `/api/v1/investigations/<investigation_id>/choices/999999` endpoint and asserts that the response status code is 404, indicating that the requested choice was not found.
        """
        response = await async_client.get(
            f"/api/v1/investigations/{test_investigation.investigation_id}/choices/999999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_list_choices_empty(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that listing choices for an investigation returns an empty list when no choices have been created.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture used to make API requests.
            test_investigation: Fixture providing a populated investigation object with an `investigation_id` attribute.
            auth_headers (dict): Authentication headers required for authorized API access.

        Raises:
            AssertionError: If the response status code is not 200 or if the returned JSON payload is not a list.
        """
        response = await async_client.get(
            f"/api/v1/investigations/{test_investigation.investigation_id}/choices",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_create_choice_unauthenticated(
        self,
        async_client: AsyncClient,
        test_investigation,
    ):
        """
        Test that creating a choice without authentication returns a 401 Unauthorized response. The request posts a simple JSON payload containing an `agent_job_id` and a `choice_json` to the choices endpoint of a specific investigation, and asserts that the HTTP status code is 401.
        """
        response = await async_client.post(
            f"/api/v1/investigations/{test_investigation.investigation_id}/choices",
            json={
                "agent_job_id": 1,
                "choice_json": {"action": "test"},
            },
        )

        assert response.status_code == 401

    async def test_create_choice_complex_json(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
        db_session,
    ):
        """
        Test creating a choice with a complex nested JSON payload.

        This integration test verifies that the `POST /api/v1/investigations/{investigation_id}/choices` endpoint correctly processes a request containing a richly structured `choice_json` object. The test performs the following steps:

        * Creates an `AgentJob` instance linked to the supplied `test_investigation` and persists it to the database.
        * Constructs a `complex_choice` dictionary that includes nested parameters, filters, reasoning, confidence scores, and alternative actions.
        * Sends an asynchronous HTTP `POST` request with the job identifier and the complex choice payload using the provided `async_client` and authentication headers.
        * Asserts that the response status code is `201 Created`.
        * Parses the JSON response and validates that:
          * The `categories` filter list matches the expected values `["auth", "process"]`.
          * Exactly two alternative actions are present in the returned `choice_json`.

        Args:
            self: Test class instance (provided by the test framework).
            async_client (AsyncClient): Asynchronous HTTP client used to issue requests against the API.
            test_investigation: Fixture representing an existing investigation; provides `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized API access.
            db_session: Database session fixture for persisting and flushing ORM objects.

        Raises:
            AssertionError: If any of the response assertions fail, indicating incorrect handling of complex JSON payloads.
        """
        from app.models.job_agent import AgentJob, JobStatus

        job = AgentJob(
            investigation_id=test_investigation.investigation_id,
            user_id=1,
            policy_id="test_policy.yaml",
            seed_instructions="Test",
            status=JobStatus.PENDING,
        )
        db_session.add(job)
        await db_session.flush()

        complex_choice = {
            "action": "execute_query",
            "parameters": {
                "query": "SELECT * FROM events",
                "filters": {
                    "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                    "categories": ["auth", "process"],
                },
            },
            "reasoning": "Analyzing high-severity events",
            "confidence": 0.92,
            "alternatives": [
                {"action": "search_timeline", "confidence": 0.75},
                {"action": "analyze_artifacts", "confidence": 0.65},
            ],
        }

        response = await async_client.post(
            f"/api/v1/investigations/{test_investigation.investigation_id}/choices",
            json={
                "agent_job_id": job.job_id,
                "choice_json": complex_choice,
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["choice_json"]["parameters"]["filters"]["categories"] == ["auth", "process"]
        assert len(data["choice_json"]["alternatives"]) == 2
