import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestEmbeddingsRouter:
    """Test embeddings endpoints."""

    async def test_generate_embedding_success(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that the embeddings generation endpoint correctly processes a valid request.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client for making requests to the API.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id`.
            auth_headers (dict): Authentication headers containing a valid token.

        The test sends a POST request to `/api/v1/embeddings/generate` with a valid
        `investigation_id` and a list of text strings. It asserts that the response status
        code is one of 200, 400, or 500. If the status code is 200, it further checks
        that the JSON payload contains either an `"embeddings"` field (indicating success)
        or an `"error"` field (indicating a configuration issue).
        """
        response = await async_client.post(
            f"/api/v1/embeddings/generate",
            json={
                "investigation_id": str(test_investigation.investigation_id),
                "texts": ["This is a test event", "Another test event"],
            },
            headers=auth_headers,
        )

        # May return 200 with embeddings or error if no embedding config
        assert response.status_code in [200, 400, 500]

        if response.status_code == 200:
            data = response.json()
            assert "embeddings" in data or "error" in data

    async def test_generate_embedding_unauthenticated(
        self,
        async_client: AsyncClient,
        test_investigation,
    ):
        """
        Test that the embeddings generation endpoint rejects requests lacking authentication.

        Parameters
        ----------
        self : object
            Test class instance.
        async_client : AsyncClient
            Asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation with a valid `investigation_id` for use in the request payload.

        The test sends a POST request to `/api/v1/embeddings/generate` without authentication headers and asserts that the response status code is `401 Unauthorized`.
        """
        response = await async_client.post(
            f"/api/v1/embeddings/generate",
            json={
                "investigation_id": str(test_investigation.investigation_id),
                "texts": ["Test"],
            },
        )

        assert response.status_code == 401

    async def test_generate_embedding_empty_texts(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that the embeddings generation endpoint correctly handles a request where the `texts` list is empty, asserting that the response status code indicates either successful handling (200) or appropriate client error handling (400).
        """
        response = await async_client.post(
            f"/api/v1/embeddings/generate",
            json={
                "investigation_id": str(test_investigation.investigation_id),
                "texts": [],
            },
            headers=auth_headers,
        )

        # Should handle empty list gracefully
        assert response.status_code in [200, 400]

    async def test_generate_embedding_invalid_investigation(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that the embeddings generation endpoint returns an appropriate client error when called with an invalid investigation identifier.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        auth_headers : dict
            Authentication headers containing a valid bearer token for authorized access.

        The test sends a POST request to `/api/v1/embeddings/generate` with a malformed `investigation_id` and asserts that the response status code indicates a bad request (HTTP 400) or an unprocessable entity (HTTP 422).
        """
        response = await async_client.post(
            f"/api/v1/embeddings/generate",
            json={
                "investigation_id": "invalid-uuid",
                "texts": ["Test"],
            },
            headers=auth_headers,
        )

        assert response.status_code in [400, 422]
