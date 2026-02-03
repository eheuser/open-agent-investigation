import pytest
from httpx import AsyncClient
import json


@pytest.mark.integration
class TestRoutePolicyEndpoint:
    """Test POST /api/v1/agents/{investigation_id}/route endpoint."""

    async def test_route_policy_missing_question(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the routing endpoint validates the request payload and returns a 422 status code when the required `question` field is missing.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for testing the API.
            test_investigation: A fixture providing an investigation object with an `investigation_id` attribute used to construct the endpoint URL.
            auth_headers: Dictionary containing authentication headers required by the endpoint.
        """
        payload = {"effort": "medium"}

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/route",
            headers=auth_headers,
            json=payload,
        )

        # Should fail validation
        assert response.status_code == 422

    async def test_route_policy_empty_question(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test routing with empty question.

        Send a POST request to the `/api/v1/agents/{investigation_id}/route` endpoint using an empty `question` field and a valid `effort` value. The request includes authentication headers and targets the investigation identified by `test_investigation.investigation_id`.

        The test asserts that the response status code indicates a client-side validation error (HTTP 400 Bad Request or HTTP 422 Unprocessable Entity).

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTPX client fixture configured for the application.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute used in the request URL.
        auth_headers : dict
            Dictionary containing authentication headers required by the endpoint.

        Returns
        -------
        None
            The test performs assertions internally and does not return a value.
        """
        payload = {"question": "", "effort": "medium"}

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/route",
            headers=auth_headers,
            json=payload,
        )

        # May fail validation or return error
        assert response.status_code in [400, 422]

    async def test_route_policy_with_question(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that routing a valid question with a specified effort level succeeds or triggers a clarification request.

        Parameters:
            self: Test class instance.
            async_client (AsyncClient): Asynchronous HTTP client used to send requests to the API.
            test_investigation: Fixture providing an investigation object containing `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized access.

        The test sends a POST request to `/api/v1/agents/{investigation_id}/route` with a payload containing a question and effort level, then asserts that the response status code indicates success (200 or 201) or a clarification flow.
        """
        payload = {"question": "What suspicious activity occurred?", "effort": "medium"}

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/route",
            headers=auth_headers,
            json=payload,
        )

        # Should succeed or return clarification request
        assert response.status_code in [200, 201]

    async def test_route_policy_low_effort(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test routing with low effort level.

        This integration test verifies that the `/route` endpoint correctly processes a request
        with an `effort` value of `"low"` for a given investigation. It sends a POST request
        containing a question and the specified effort level, then asserts that the response
        status code indicates success (HTTP 200 or 201).

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to make requests against the API.
        test_investigation : Any
            A fixture providing an investigation object with an `investigation_id` attribute
            used to construct the request URL.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        Raises
        ------
        AssertionError
            If the response status code is not 200 or 201, indicating that routing failed
            for low effort requests.
        """
        payload = {"question": "Analyze the timeline", "effort": "low"}

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/route",
            headers=auth_headers,
            json=payload,
        )

        assert response.status_code in [200, 201]

    async def test_route_policy_high_effort(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that routing an investigation with a high effort level returns a successful HTTP status code (200 or 201) when called with valid authentication headers and a minimal payload containing a question and the `"high"` effort specification. The test sends a POST request to the `/route` endpoint for the given investigation ID and asserts that the response indicates success.
        """
        payload = {"question": "Perform deep analysis", "effort": "high"}

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/route",
            headers=auth_headers,
            json=payload,
        )

        assert response.status_code in [200, 201]

    async def test_route_policy_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that the routing endpoint returns an unauthorized (401) response when called without authentication.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client fixture configured for asynchronous requests to the API.
        test_investigation : Any
            Fixture providing an investigation object with a valid `investigation_id` used to construct the request URL.
        """
        payload = {"question": "Test question", "effort": "medium"}

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/route", json=payload
        )

        assert response.status_code == 401

    async def test_route_policy_invalid_investigation(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that routing a request to a non-existent investigation ID results in an error response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test constructs a payload containing a question and an effort level, generates a random UUID that does not correspond to any existing investigation, and sends a POST request to `/api/v1/agents/{uuid}/route`. It asserts that the response status code indicates failure (either 404 Not Found or 403 Forbidden), confirming that the router correctly handles invalid investigation identifiers.
        """
        from uuid import uuid4

        payload = {"question": "Test question", "effort": "medium"}

        response = await async_client.post(
            f"/api/v1/agents/{uuid4()}/route", headers=auth_headers, json=payload
        )

        # Should fail - investigation not found
        assert response.status_code in [404, 403]


@pytest.mark.integration
class TestProvideClarificationEndpoint:
    """Test POST /api/v1/agents/{investigation_id}/clarify endpoint."""

    async def test_provide_clarification_missing_fields(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the clarification endpoint returns a validation error when required fields are missing.

        This asynchronous integration test sends an empty JSON payload to the `/api/v1/agents/{investigation_id}/clarify` endpoint using an authenticated client. It verifies that the server responds with HTTP status code 422, indicating that request validation has failed due to the absence of mandatory fields.
        """
        payload = {}

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/clarify",
            headers=auth_headers,
            json=payload,
        )

        # Should fail validation
        assert response.status_code == 422

    async def test_provide_clarification_with_policy_id(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the `/clarify` endpoint correctly processes a request containing a `policy_id` and associated rule values.\n\nThe test sends a POST request to `/api/v1/agents/{investigation_id}/clarify` using the provided asynchronous HTTP client, authentication headers, and a payload with:\n- `policy_id`: identifier of the policy to apply (e.g., `\"test_policy\"`).\n- `rule_values`: dictionary of rule parameters such as `target_user` and `timeframe`.\n\nThe response status code is asserted to be one of the expected outcomes:\n- `200` or `201` if the clarification succeeds,\n- `400` if the request is malformed or fails validation,\n- `404` if the specified policy does not exist.\n\nParameters\n----------\nself : object\n    Instance of the test class containing shared fixtures.\nasync_client : AsyncClient\n    Asynchronous HTTP client fixture used to perform the request.\ntest_investigation : Any\n    Fixture providing an investigation object with an `investigation_id` attribute.\nauth_headers : dict\n    Dictionary of authentication headers required by the API.
        """
        payload = {
            "policy_id": "test_policy",
            "rule_values": {"target_user": "admin", "timeframe": "24h"},
        }

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/clarify",
            headers=auth_headers,
            json=payload,
        )

        # May succeed or fail depending on policy existence
        assert response.status_code in [200, 201, 400, 404]

    async def test_provide_clarification_empty_rule_values(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the `/clarify` endpoint correctly handles a request with an empty `rule_values` dictionary.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client fixture for making asynchronous requests to the API.
        test_investigation : Any
            Fixture providing an investigation object containing the `investigation_id` used in the request URL.
        auth_headers : dict
            Dictionary of authentication headers required by the endpoint.

        The test sends a POST request to `/api/v1/agents/{investigation_id}/clarify` with a payload that includes a valid `policy_id` and an empty `rule_values`. It asserts that the response status code is one of the expected outcomes (200, 201, 400, or 404), indicating that the endpoint gracefully handles empty rule values without raising unexpected errors.
        """
        payload = {"policy_id": "test_policy", "rule_values": {}}

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/clarify",
            headers=auth_headers,
            json=payload,
        )

        # Should handle empty rule values
        assert response.status_code in [200, 201, 400, 404]

    async def test_provide_clarification_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that the `/clarify` endpoint rejects requests lacking authentication.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the test server.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id` for constructing the request URL.
        """
        payload = {"policy_id": "test_policy", "rule_values": {"key": "value"}}

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/clarify", json=payload
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestAgentsEdgeCases:
    """Test edge cases and error handling."""

    async def test_route_policy_very_long_question(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the `/route` endpoint correctly handles a question payload exceeding typical length limits.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client configured for asynchronous requests against the API.
        test_investigation : Any
            Fixture providing an investigation context with an `investigation_id` attribute used to construct the request URL.
        auth_headers : dict
            Authentication headers required by the endpoint.

        The test sends a POST request with a 10 KB `question` string and a medium effort level, then asserts that the response status code is one of the expected outcomes:
        - **200** or **201**: successful routing despite the long input,
        - **400**, **413**, or **422**: appropriate client-error responses indicating rejection or validation failure.
        """
        payload = {"question": "A" * 10000, "effort": "medium"}  # 10KB question

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/route",
            headers=auth_headers,
            json=payload,
        )

        # Should handle or reject long input
        assert response.status_code in [200, 201, 400, 413, 422]

    async def test_route_policy_special_characters(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the routing endpoint safely processes a question containing special characters such as HTML tags.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture for making requests to the API.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute used in the request URL.
        auth_headers : dict
            Dictionary of authentication headers required by the endpoint.

        The test sends a POST request to `/api/v1/agents/<investigation_id>/route` with a payload that includes a question containing potentially unsafe characters (e.g., `<script>` tags). It asserts that the response status code indicates success (200 or 201), confirming that the endpoint handles special characters without error or injection.
        """
        payload = {
            "question": "What about <script>alert('xss')</script> attacks?",
            "effort": "medium",
        }

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/route",
            headers=auth_headers,
            json=payload,
        )

        # Should handle special characters safely
        assert response.status_code in [200, 201]

    async def test_route_policy_unicode_question(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test routing with Unicode characters.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            Asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation object containing the `investigation_id` used in the request URL.
        auth_headers : dict
            Dictionary of authentication headers required for authorized access.

        The test sends a POST request to the `/api/v1/agents/{investigation_id}/route` endpoint with a payload that includes a Unicode question and a medium effort level. It asserts that the response status code indicates success (200 or 201), verifying that the endpoint correctly handles Unicode characters in the request body.
        """
        payload = {"question": "分析可疑活动 🔍", "effort": "medium"}

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/route",
            headers=auth_headers,
            json=payload,
        )

        # Should handle Unicode
        assert response.status_code in [200, 201]

    async def test_route_policy_invalid_effort_level(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that routing fails with a 422 status code when an invalid effort level is provided.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for the application.
            test_investigation: Fixture providing an investigation object containing `investigation_id` used to build the request URL.
            auth_headers: Dictionary of authentication headers required for authorized access.
        """
        payload = {"question": "Test question", "effort": "invalid"}

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/route",
            headers=auth_headers,
            json=payload,
        )

        # Should fail validation
        assert response.status_code == 422

    async def test_provide_clarification_invalid_policy_id(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that providing a clarification request with a policy_id that does not exist results in an error response.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture supplying an investigation object containing at least an `investigation_id` attribute.
            auth_headers: Dictionary of authentication headers required for authorized access to the endpoint.

        The test sends a POST request to `/api/v1/agents/{investigation_id}/clarify` with a payload referencing a non-existent policy. It asserts that the response status code indicates failure (HTTP 400 or 404), confirming proper validation and error handling for invalid policy identifiers.
        """
        payload = {"policy_id": "non_existent_policy_12345", "rule_values": {"key": "value"}}

        response = await async_client.post(
            f"/api/v1/agents/{test_investigation.investigation_id}/clarify",
            headers=auth_headers,
            json=payload,
        )

        # Should fail - policy not found
        assert response.status_code in [400, 404]
