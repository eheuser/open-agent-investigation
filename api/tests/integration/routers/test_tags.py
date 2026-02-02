import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestDeprecatedTagsEndpoints:
    """Test deprecated tags endpoints return 410."""

    async def test_add_node_tags_deprecated(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the deprecated `add_node_tags` endpoint returns HTTP 410 Gone with a deprecation notice.

        The test performs an asynchronous POST request to `/api/v1/tags/nodes/{investigation_id}/1` using the provided `async_client` and authentication headers, sending a JSON payload of tag names. It then asserts that:

        * The response status code is **410**.
        * The response body contains the word “deprecated” (case-insensitive) in the `detail` field.
        """
        response = await async_client.post(
            f"/api/v1/tags/nodes/{test_investigation.investigation_id}/1",
            headers=auth_headers,
            json=["tag1", "tag2"],
        )

        assert response.status_code == 410
        assert "deprecated" in response.json()["detail"].lower()

    async def test_remove_node_tags_deprecated(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that deleting node tags via the deprecated endpoint returns HTTP 410 Gone and includes a deprecation notice in the response payload. The test sends a DELETE request to `/api/v1/tags/nodes/{investigation_id}/1` with an example tag list, then asserts that the status code is 410 and that the JSON `detail` field contains the word “deprecated”.
        """
        response = await async_client.delete(
            f"/api/v1/tags/nodes/{test_investigation.investigation_id}/1",
            headers=auth_headers,
            json=["tag1"],
        )

        assert response.status_code == 410
        assert "deprecated" in response.json()["detail"].lower()

    async def test_add_edge_tags_deprecated(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that adding tags to an edge using the deprecated `/api/v1/tags/edges` endpoint returns HTTP 410 Gone and includes a deprecation notice in the response body.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to make requests against the API.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute used to construct the request URL.
        auth_headers : dict
            Dictionary containing authentication headers required for the request.

        Raises
        ------
        AssertionError
            If the response status code is not 410 or if the response body does not contain a deprecation notice.
        """
        response = await async_client.post(
            f"/api/v1/tags/edges/{test_investigation.investigation_id}/1",
            headers=auth_headers,
            json=["tag1", "tag2"],
        )

        assert response.status_code == 410
        assert "deprecated" in response.json()["detail"].lower()

    async def test_remove_edge_tags_deprecated(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test the deprecated `remove_edge_tags` endpoint to ensure it consistently returns an HTTP 410 Gone status with a deprecation notice.\n\nParameters\n----------\nself : object\n    The test case instance.\nasync_client : AsyncClient\n    An asynchronous HTTP client fixture used to make requests against the API.\ntest_investigation : Any\n    A fixture providing an investigation object containing `investigation_id` used in the request URL.\nauth_headers : dict\n    Authentication headers required for authorized access to the endpoint.\n\nThe test sends a DELETE request to `/api/v1/tags/edges/{investigation_id}/1` with a JSON payload of tag identifiers and asserts that:\n\n* The response status code is 410, indicating the resource is gone.\n* The response body contains a `detail` field whose text includes the word \"deprecated\" (case-insensitive).
        """
        response = await async_client.delete(
            f"/api/v1/tags/edges/{test_investigation.investigation_id}/1",
            headers=auth_headers,
            json=["tag1"],
        )

        assert response.status_code == 410
        assert "deprecated" in response.json()["detail"].lower()
