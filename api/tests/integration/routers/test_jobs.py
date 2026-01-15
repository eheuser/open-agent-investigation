"""
Integration tests for jobs endpoints.
Tests parsing and agent job status queries.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.job_parsing import ParsingJob, JobStatus
from app.models.job_agent import AgentJob
from app.models.artifact import Artifact


@pytest.mark.integration
class TestParsingJobStatus:
    """Test parsing job status endpoint."""

    async def test_get_parsing_job_success(
        self, async_client: AsyncClient, auth_headers, test_investigation, db_session
    ):
        """
        Test that a parsing job can be retrieved successfully via the API.

        The test performs the following steps:
        - Creates an `Artifact` linked to a provided investigation and persists it.
        - Creates a `ParsingJob` associated with the artifact, sets its status to `PENDING`, and saves it.
        - Sends an authenticated GET request to `/api/v1/jobs/parsing/{job_id}`.
        - Asserts that the response has HTTP 200 OK.
        - Verifies that the returned JSON contains the expected `job_id`, `investigation_id` (as a string), `artifact_id`, and a status of `"pending"`.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client configured for asynchronous requests against the application.
        auth_headers : dict
            Authentication headers required by the endpoint.
        test_investigation : Investigation
            A fixture providing an investigation to associate with the artifact and job.
        db_session : AsyncSession
            Database session used to add and commit test records.
        """
        # Create artifact
        artifact = Artifact(
            investigation_id=test_investigation.investigation_id,
            sha256=b"\x00" * 32,
            filename="test.evtx",
            classification=0,
            blob=b"test data",
        )
        db_session.add(artifact)
        await db_session.flush()

        # Create parsing job
        job = ParsingJob(
            investigation_id=test_investigation.investigation_id,
            artifact_id=artifact.artifact_id,
            status=JobStatus.PENDING,
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        response = await async_client.get(
            f"/api/v1/jobs/parsing/{job.job_id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job.job_id
        assert data["investigation_id"] == str(test_investigation.investigation_id)
        assert data["artifact_id"] == artifact.artifact_id
        assert data["status"] == "pending"

    async def test_get_parsing_job_not_found(self, async_client: AsyncClient, auth_headers):
        """
        Test that retrieving a parsing job with an ID that does not exist returns a 404 Not Found response.
        """
        response = await async_client.get("/api/v1/jobs/parsing/999999", headers=auth_headers)

        assert response.status_code == 404

    async def test_get_parsing_job_unauthenticated(
        self, async_client: AsyncClient, test_investigation, db_session
    ):
        """
        Test that an unauthenticated request to retrieve a specific parsing job returns HTTP 401 Unauthorized.

        The test creates an artifact and an associated parsing job in the database, then performs a GET request to the `/api/v1/jobs/parsing/{job_id}` endpoint without providing authentication credentials. It asserts that the response status code is 401, confirming that access to job details is correctly restricted for unauthenticated users.
        """
        # Create artifact and job
        artifact = Artifact(
            investigation_id=test_investigation.investigation_id,
            sha256=b"\x00" * 32,
            filename="test.evtx",
            classification=0,
            blob=b"test data",
        )
        db_session.add(artifact)
        await db_session.flush()

        job = ParsingJob(
            investigation_id=test_investigation.investigation_id,
            artifact_id=artifact.artifact_id,
            status=JobStatus.PENDING,
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        response = await async_client.get(f"/api/v1/jobs/parsing/{job.job_id}")

        assert response.status_code == 401


@pytest.mark.integration
class TestListParsingJobs:
    """Test listing parsing jobs for investigation."""

    async def test_list_parsing_jobs_empty(
        self, async_client: AsyncClient, auth_headers, test_investigation
    ):
        """
        Test that listing parsing jobs for an investigation returns an empty result set when no jobs exist.

        The test sends a GET request to the `/api/v1/jobs/parsing/investigation/{investigation_id}` endpoint using an authenticated client. It verifies that:
        - The response status code is 200 (OK).
        - The JSON payload contains a `jobs` key whose value is an empty list.
        - The `total` field in the response equals `0`, indicating no jobs are present.
        """
        response = await async_client.get(
            f"/api/v1/jobs/parsing/investigation/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert isinstance(data["jobs"], list)
        assert data["total"] == 0

    async def test_list_parsing_jobs_with_data(
        self, async_client: AsyncClient, auth_headers, test_investigation, db_session
    ):
        """
        Test that listing parsing jobs for an investigation returns existing jobs.

        Args:
            self: Test case instance.
            async_client (AsyncClient): HTTP client used to make asynchronous requests to the API.
            auth_headers (dict): Authentication headers required by the endpoint.
            test_investigation: Fixture providing a populated Investigation model with a valid ID.
            db_session: Asynchronous SQLAlchemy session fixture for database operations.

        The test creates an Artifact and a corresponding completed ParsingJob in the database, then queries the `/api/v1/jobs/parsing/investigation/{investigation_id}` endpoint. It asserts that:
        * The response status code is 200 (OK).
        * The JSON payload contains a non-empty `jobs` list.
        * The `total` count reflects at least one job.
        * The first returned job has its `status` field set to `"completed"`.
        """
        # Create artifact and job
        artifact = Artifact(
            investigation_id=test_investigation.investigation_id,
            sha256=b"\x00" * 32,
            filename="test.evtx",
            classification=0,
            blob=b"test data",
        )
        db_session.add(artifact)
        await db_session.flush()

        job = ParsingJob(
            investigation_id=test_investigation.investigation_id,
            artifact_id=artifact.artifact_id,
            status=JobStatus.COMPLETED,
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/jobs/parsing/investigation/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) >= 1
        assert data["total"] >= 1
        assert data["jobs"][0]["status"] == "completed"

    async def test_list_parsing_jobs_pagination(
        self, async_client: AsyncClient, auth_headers, test_investigation, db_session
    ):
        """
        Test that pagination query parameters are correctly applied when listing parsing jobs for a specific investigation.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.
        test_investigation : Investigation
            A fixture providing an investigation object whose ID is used in the request URL.
        db_session : Session
            Database session fixture (unused directly in this test but provided for consistency).

        The test sends a GET request with `limit=10` and `offset=0` query parameters, asserts that the response status code is 200, and verifies that the returned JSON payload contains matching `limit` and `offset` values.
        """
        response = await async_client.get(
            f"/api/v1/jobs/parsing/investigation/{test_investigation.investigation_id}?limit=10&offset=0",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 0

    async def test_list_parsing_jobs_unauthenticated(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that an unauthenticated request to the parsing-jobs list endpoint returns HTTP 401 Unauthorized, confirming that authentication is required for job listing.
        """
        response = await async_client.get(
            f"/api/v1/jobs/parsing/investigation/{test_investigation.investigation_id}"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestAgentJobStatus:
    """Test agent job status endpoint."""

    async def test_get_agent_job_success(
        self, async_client: AsyncClient, auth_headers, test_investigation, test_user, db_session
    ):
        """
        Test that retrieving an existing agent job returns a successful response with correct data.

        Parameters:
            self: Test class instance.
            async_client (AsyncClient): HTTP client for making asynchronous requests to the API.
            auth_headers (dict): Authentication headers containing a valid token.
            test_investigation: Fixture providing an investigation object used to associate the job.
            test_user: Fixture providing a user object that owns the job.
            db_session: Database session fixture for persisting and querying objects.

        The test creates an AgentJob with status PENDING, commits it to the database, then performs a GET request to `/api/v1/jobs/agent/{job_id}`. It asserts that the response status code is 200 and that the returned JSON contains the correct `job_id`, `investigation_id`, `user_id`, and a stringified `status` of "pending".
        """
        # Create agent job
        job = AgentJob(
            investigation_id=test_investigation.investigation_id,
            user_id=test_user.user_id,
            policy_id="test_policy.yaml",
            seed_instructions="Test agent instructions",
            status=JobStatus.PENDING,
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        response = await async_client.get(f"/api/v1/jobs/agent/{job.job_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job.job_id
        assert data["investigation_id"] == str(test_investigation.investigation_id)
        assert data["user_id"] == test_user.user_id
        assert data["status"] == "pending"

    async def test_get_agent_job_not_found(self, async_client: AsyncClient, auth_headers):
        """
        Test that requesting an agent job with an ID that does not exist returns a 404 Not Found response.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured to call the test server.
            auth_headers: A dictionary containing authentication headers required for the request.

        The test performs a GET request against `/api/v1/jobs/agent/999999` and asserts that the HTTP status code in the response is 404, confirming proper handling of missing agent jobs.
        """
        response = await async_client.get("/api/v1/jobs/agent/999999", headers=auth_headers)

        assert response.status_code == 404

    async def test_get_agent_job_unauthenticated(
        self, async_client: AsyncClient, test_investigation, test_user, db_session
    ):
        """
        Test that an unauthenticated request to retrieve a specific agent job returns HTTP 401 Unauthorized.

        The test creates an `AgentJob` linked to a test investigation and user, persists it to the database, and then attempts to fetch the job status via the `/api/v1/jobs/agent/{job_id}` endpoint without providing authentication credentials. It asserts that the response status code is 401, confirming that unauthenticated users are prohibited from accessing agent job details.
        """
        job = AgentJob(
            investigation_id=test_investigation.investigation_id,
            user_id=test_user.user_id,
            policy_id="test_policy.yaml",
            seed_instructions="Test agent instructions",
            status=JobStatus.PENDING,
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        response = await async_client.get(f"/api/v1/jobs/agent/{job.job_id}")

        assert response.status_code == 401


@pytest.mark.integration
class TestListAgentJobs:
    """Test listing agent jobs for investigation."""

    async def test_list_agent_jobs_empty(
        self, async_client: AsyncClient, auth_headers, test_investigation
    ):
        """
        Test that retrieving the list of agent jobs for a specific investigation returns an empty result set when no jobs have been created.

        The request is sent to the `/api/v1/jobs/agent/investigation/{investigation_id}` endpoint using the provided authentication headers. The test asserts that:

        * The HTTP status code is 200 (OK).
        * The JSON payload contains a `jobs` key whose value is an empty list.
        * The `total` field in the response equals `0`, indicating no jobs are present.
        """
        response = await async_client.get(
            f"/api/v1/jobs/agent/investigation/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert isinstance(data["jobs"], list)
        assert data["total"] == 0

    async def test_list_agent_jobs_with_data(
        self, async_client: AsyncClient, auth_headers, test_investigation, test_user, db_session
    ):
        """
        Test that the endpoint for listing agent jobs returns the correct data when jobs exist.

        The test creates an `AgentJob` linked to a specific investigation and user, commits it to the database, and then performs a GET request to the `/api/v1/jobs/agent/investigation/{investigation_id}` endpoint using valid authentication headers.

        It verifies that:
        - The response status code is 200 (OK).
        - The JSON payload contains a non-empty `jobs` list.
        - The `total` count reflects at least one job.
        - The first job in the list has its `status` field set to `"running"`, matching the created job's state.
        """
        job = AgentJob(
            investigation_id=test_investigation.investigation_id,
            user_id=test_user.user_id,
            policy_id="test_policy.yaml",
            seed_instructions="Test agent instructions",
            status=JobStatus.RUNNING,
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/jobs/agent/investigation/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) >= 1
        assert data["total"] >= 1
        assert data["jobs"][0]["status"] == "running"

    async def test_list_agent_jobs_unauthenticated(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that unauthenticated users cannot list agent jobs for a given investigation, expecting an HTTP 401 Unauthorized response.
        """
        response = await async_client.get(
            f"/api/v1/jobs/agent/investigation/{test_investigation.investigation_id}"
        )

        assert response.status_code == 401
