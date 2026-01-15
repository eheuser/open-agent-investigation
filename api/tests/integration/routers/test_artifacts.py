"""
Integration tests for artifacts endpoints.
Tests artifact upload, listing, and retrieval.
"""

import pytest
import io
from httpx import AsyncClient
from sqlalchemy import select

from app.models.artifact import Artifact


@pytest.mark.integration
class TestUploadArtifact:
    """Test artifact upload endpoint."""

    async def test_upload_artifact_success(
        self, async_client: AsyncClient, auth_headers, test_investigation
    ):
        """
        Test that uploading a valid artifact file succeeds and returns the expected response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to send requests to the API.
        auth_headers : dict
            Dictionary containing authentication headers (e.g., `Authorization`) required for the request.
        test_investigation : Any
            Fixture representing an existing investigation; its `investigation_id` attribute is used in the payload.

        The test constructs a multipart/form-data request with a small text file, includes the required `investigation_id` and a classification code, sends a POST request to `/api/v1/artifacts/`, and asserts that:

        * The response status code is **201 Created**.
        * The JSON body contains the keys `artifact_id`, `job_id`, and `message`.
        """
        file_content = b"test file content"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
        data = {
            "investigation_id": str(test_investigation.investigation_id),
            "classification": "3",  # OTHER
        }

        response = await async_client.post(
            "/api/v1/artifacts/", headers=auth_headers, files=files, data=data
        )

        assert response.status_code == 201
        result = response.json()

        assert "artifact_id" in result
        assert "job_id" in result
        assert "message" in result

    async def test_upload_artifact_evtx_file(
        self, async_client: AsyncClient, auth_headers, test_investigation
    ):
        """
        Test uploading an EVTX file as an artifact.

        This integration test verifies that a valid EVTX file can be uploaded to the `/api/v1/artifacts/` endpoint with proper authentication and metadata. It constructs a multipart request containing:

        - A binary payload representing a fake EVTX file named `Security.evtx`.
        - Form data specifying the target investigation ID and the classification code for log files.

        The test asserts that the response status code is `201 Created`, indicating successful artifact creation. The function expects the following fixtures to be provided by the test suite:

        - **async_client**: An instance of `httpx.AsyncClient` configured for the application.
        - **auth_headers**: A dictionary containing authentication headers required by the API.
        - **test_investigation**: An object exposing an `investigation_id` attribute representing a pre-created investigation.
        """
        file_content = b"fake evtx content"
        files = {"file": ("Security.evtx", io.BytesIO(file_content), "application/octet-stream")}
        data = {
            "investigation_id": str(test_investigation.investigation_id),
            "classification": "0",  # LOG_FILE
        }

        response = await async_client.post(
            "/api/v1/artifacts/", headers=auth_headers, files=files, data=data
        )

        assert response.status_code == 201

    async def test_upload_artifact_unauthenticated(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that an unauthenticated request to the artifact upload endpoint is rejected with a 401 status code. The test constructs a simple text file payload and associated form data (including investigation ID and classification), sends it via an asynchronous POST request, and asserts that the response indicates unauthorized access.
        """
        file_content = b"test content"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
        data = {
            "investigation_id": str(test_investigation.investigation_id),
            "classification": "3",
        }

        response = await async_client.post("/api/v1/artifacts/", files=files, data=data)

        assert response.status_code == 401

    async def test_upload_artifact_invalid_investigation(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that uploading an artifact with an investigation ID that does not exist returns a 404 response.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture for making requests to the API.
            auth_headers (dict): Authentication headers containing valid credentials for the request.

        The test generates a random UUID to simulate a non-existent investigation, constructs a simple text file payload, and sends a POST request to the `/api/v1/artifacts/` endpoint with the fake investigation ID. It asserts that the response status code is 404, indicating proper handling of invalid investigation references.
        """
        import uuid

        fake_id = uuid.uuid4()
        file_content = b"test content"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
        data = {
            "investigation_id": str(fake_id),
            "classification": "3",
        }

        response = await async_client.post(
            "/api/v1/artifacts/", headers=auth_headers, files=files, data=data
        )

        assert response.status_code == 404

    async def test_upload_artifact_no_file(
        self, async_client: AsyncClient, auth_headers, test_investigation
    ):
        """
        Test that uploading an artifact without providing a file results in a validation error.\n\nParameters:\n    async_client (AsyncClient): The asynchronous HTTP client used to make requests against the API.\n    auth_headers (dict): Authentication headers containing valid credentials for the request.\n    test_investigation (object): A fixture representing an existing investigation; its `investigation_id` is used in the payload.\n\nThe test sends a POST request to the `/api/v1/artifacts/` endpoint with only the `investigation_id` and `classification` fields, omitting the required file upload. It asserts that the response status code is `422`, indicating that the server correctly rejects the request due to missing file data.
        """
        data = {
            "investigation_id": str(test_investigation.investigation_id),
            "classification": "3",
        }

        response = await async_client.post("/api/v1/artifacts/", headers=auth_headers, data=data)

        assert response.status_code == 422  # Missing required file


@pytest.mark.integration
class TestListArtifacts:
    """Test artifact listing endpoint."""

    async def test_list_artifacts_empty(
        self, async_client: AsyncClient, auth_headers, test_investigation
    ):
        """
        Test that listing artifacts for a given investigation returns an empty list when no artifacts have been uploaded.

        This test sends a GET request to the `/api/v1/artifacts/investigation/{investigation_id}` endpoint using the provided asynchronous client and authentication headers. It asserts that:

        * The response status code is 200 (OK).
        * The response body is a JSON-encoded list.
        * The list is empty, indicating no artifacts are associated with the specified investigation.
        """
        response = await async_client.get(
            f"/api/v1/artifacts/investigation/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    async def test_list_artifacts_with_data(
        self, async_client: AsyncClient, auth_headers, test_investigation, db_session
    ):
        """
        Test that listing artifacts for an investigation returns the expected data when artifacts exist.

        Parameters:
            self: The test case instance.
            async_client (AsyncClient): HTTP client used to make asynchronous requests against the API.
            auth_headers (dict): Dictionary containing authentication headers required by the endpoint.
            test_investigation: Fixture providing a populated Investigation object with a valid investigation_id.
            db_session: Asynchronous SQLAlchemy session fixture used to insert test data into the database.

        The test creates an Artifact linked to the provided investigation, commits it to the database, and then performs a GET request to the `/api/v1/artifacts/investigation/{investigation_id}` endpoint. It asserts that:
        - The response status code is 200.
        - The response body is a JSON list containing at least one artifact entry.
        - Each artifact entry includes an `artifact_id` and `filename`.
        - The filename of the first returned artifact matches the expected value ("test.evtx").
        """
        # Create an artifact
        artifact = Artifact(
            investigation_id=test_investigation.investigation_id,
            sha256=b"\x00" * 32,
            filename="test.evtx",
            classification=0,
            blob=b"test data",
        )
        db_session.add(artifact)
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/artifacts/investigation/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Check structure
        artifact_data = data[0]
        assert "artifact_id" in artifact_data
        assert "filename" in artifact_data
        assert artifact_data["filename"] == "test.evtx"

    async def test_list_artifacts_unauthenticated(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that unauthenticated users cannot list artifacts.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client used to make requests against the API.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id` for constructing the request URL.
        """
        response = await async_client.get(
            f"/api/v1/artifacts/investigation/{test_investigation.investigation_id}"
        )

        assert response.status_code == 401

    async def test_list_artifacts_invalid_investigation(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that requesting the list of artifacts for an investigation ID that does not exist returns a 404 Not Found response. The test generates a random UUID, performs a GET request to the `/api/v1/artifacts/investigation/{id}` endpoint with valid authentication headers, and asserts that the HTTP status code is 404.
        """
        import uuid

        fake_id = uuid.uuid4()
        response = await async_client.get(
            f"/api/v1/artifacts/investigation/{fake_id}", headers=auth_headers
        )

        assert response.status_code == 404


@pytest.mark.integration
class TestDownloadArtifact:
    """Test artifact download endpoint."""

    async def test_download_artifact_success(
        self, async_client: AsyncClient, auth_headers, test_investigation, db_session
    ):
        """
        Test that downloading an artifact returns the correct binary blob with appropriate headers.

        The test creates an `Artifact` record in the database with known content, commits it, and then issues a GET request to the artifact download endpoint using authenticated headers. It asserts that:
        - The response status code is 200 (OK).
        - The response body matches the original blob content.
        - The `Content-Disposition` header contains the string “attachment”, indicating a file download.
        """
        blob_content = b"test file blob content"
        artifact = Artifact(
            investigation_id=test_investigation.investigation_id,
            sha256=b"\x00" * 32,
            filename="test.txt",
            classification=3,  # OTHER
            blob=blob_content,
        )
        db_session.add(artifact)
        await db_session.commit()
        await db_session.refresh(artifact)

        response = await async_client.get(
            f"/api/v1/artifacts/{artifact.artifact_id}", headers=auth_headers
        )

        assert response.status_code == 200
        assert response.content == blob_content
        assert "attachment" in response.headers.get("content-disposition", "")

    async def test_download_artifact_not_found(self, async_client: AsyncClient, auth_headers):
        """
        Test that attempting to download an artifact with an ID that does not exist returns a 404 Not Found response. The test sends a GET request for a fabricated artifact identifier and asserts that the HTTP status code of the response is 404.
        """
        fake_id = 999999
        response = await async_client.get(f"/api/v1/artifacts/{fake_id}", headers=auth_headers)

        assert response.status_code == 404

    async def test_download_artifact_unauthenticated(
        self, async_client: AsyncClient, db_session, test_investigation
    ):
        """
        Test that an unauthenticated request to the artifact download endpoint is rejected with a 401 status code. The test creates an artifact in the database, commits it, then performs a GET request without authentication and asserts that the response indicates unauthorized access.
        """
        artifact = Artifact(
            investigation_id=test_investigation.investigation_id,
            sha256=b"\x00" * 32,
            filename="test.txt",
            classification=3,
            blob=b"test data",
        )
        db_session.add(artifact)
        await db_session.commit()
        await db_session.refresh(artifact)

        response = await async_client.get(f"/api/v1/artifacts/{artifact.artifact_id}")

        assert response.status_code == 401
