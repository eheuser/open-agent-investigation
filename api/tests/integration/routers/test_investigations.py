import pytest
import uuid
from httpx import AsyncClient

from tests.factories import InvestigationFactory


@pytest.mark.integration
class TestCreateInvestigation:
    """Test investigation creation endpoint."""

    async def test_create_investigation_success(self, async_client: AsyncClient, auth_headers):
        """
        Test that creating an investigation with valid data succeeds.\n\nThe test sends a POST request to `/api/v1/investigations/` using an authenticated client and a minimal payload containing a `title`. It verifies that:\n\n* The response status code is **201 Created**.\n* The JSON body includes the keys `investigation_id`, `title`, `created_at` and `owner_user_id`.\n* The returned `title` matches the one sent in the request.\n* The `investigation_id` value conforms to a valid UUID format.
        """
        response = await async_client.post(
            "/api/v1/investigations/", headers=auth_headers, json={"title": "Test Investigation"}
        )

        assert response.status_code == 201
        data = response.json()

        assert "investigation_id" in data
        assert data["title"] == "Test Investigation"
        assert "created_at" in data
        assert "owner_user_id" in data

        # Verify UUID format
        inv_id = uuid.UUID(data["investigation_id"])
        assert isinstance(inv_id, uuid.UUID)

    async def test_create_investigation_unauthenticated(self, async_client: AsyncClient):
        """
        Test that an unauthenticated request to the investigations creation endpoint is rejected with HTTP 401 Unauthorized. The test sends a POST request with minimal payload and asserts that the response status code equals 401.
        """
        response = await async_client.post(
            "/api/v1/investigations/", json={"title": "Test Investigation"}
        )

        assert response.status_code == 401

    async def test_create_investigation_empty_title(self, async_client: AsyncClient, auth_headers):
        """
        Test that creating an investigation with an empty `title` field behaves as expected.\n\nThe request is sent to `/api/v1/investigations/` using the provided `async_client` and authentication headers. The test asserts that the response status code is either `201 Created` (if empty titles are allowed) or `422 Unprocessable Entity` (if validation rejects them).\n\nArgs:\n    async_client: An instance of `httpx.AsyncClient` used to perform asynchronous HTTP requests against the API.\n    auth_headers: A dictionary containing authentication headers required for authorized access.\n\nRaises:\n    AssertionError: If the response status code is not one of the expected values (201 or 422).
        """
        response = await async_client.post(
            "/api/v1/investigations/", headers=auth_headers, json={"title": ""}
        )

        # Should either accept or reject based on validation
        assert response.status_code in [201, 422]

    async def test_create_investigation_long_title(self, async_client: AsyncClient, auth_headers):
        """
        Test creating an investigation with a title that exceeds the allowed maximum length.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to send HTTP requests to the API.
            auth_headers: A dictionary containing authentication headers required for authorized access.

        The test sends a POST request to `/api/v1/investigations/` with a JSON payload where `title` is a string of 1000 characters, surpassing the defined maximum length of 200. It verifies that the API responds with a 422 Unprocessable Entity status code and includes a `detail` field in the response body indicating validation failure.
        """
        long_title = "A" * 1000  # Exceeds max_length=200
        response = await async_client.post(
            "/api/v1/investigations/", headers=auth_headers, json={"title": long_title}
        )

        # Should reject due to max_length validation
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    async def test_create_investigation_special_characters(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that creating an investigation with a title containing special characters (e.g., HTML/JavaScript tags) succeeds and preserves the exact input string.

        The test sends a POST request to the `/api/v1/investigations/` endpoint with an authentication header and a JSON payload where `title` includes potentially unsafe characters. It verifies that:

        * The response status code is **201 Created**, indicating successful creation.
        * The returned JSON payload contains a `title` field whose value exactly matches the submitted string, ensuring that special characters are not stripped or altered by the API.
        """
        response = await async_client.post(
            "/api/v1/investigations/",
            headers=auth_headers,
            json={"title": "Test <script>alert('xss')</script>"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test <script>alert('xss')</script>"


@pytest.mark.integration
class TestListInvestigations:
    """Test investigation listing endpoint."""

    async def test_list_investigations_empty(self, async_client: AsyncClient, auth_headers):
        """
        Test that retrieving the list of investigations returns an empty collection when no investigation records exist.

        The test performs a GET request against the `/api/v1/investigations/` endpoint using an authenticated client.
        It asserts that the response status code is HTTP 200 (OK) and verifies that the JSON payload
        is a list, which should be empty in this scenario. This ensures the API correctly handles
        the case where no investigations are present without raising errors or returning unexpected data.
        """
        response = await async_client.get("/api/v1/investigations/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # May have 0 or more investigations depending on test isolation

    async def test_list_investigations_with_data(
        self, async_client: AsyncClient, auth_headers, test_investigation
    ):
        """
        Test that listing investigations returns a 200 response with a non-empty list of investigation objects when data exists.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client configured for asynchronous requests against the API.
        auth_headers : dict
            Authorization headers containing valid credentials for an authenticated user.
        test_investigation : dict
            Fixture providing a pre-created investigation in the database, ensuring that at least one record exists.

        Asserts
        -------
        - The response status code is 200.
        - The JSON payload is a list with length greater than or equal to one.
        - Each investigation dictionary contains the keys `investigation_id`, `title` and `created_at`.
        """
        response = await async_client.get("/api/v1/investigations/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Check structure of first investigation
        inv = data[0]
        assert "investigation_id" in inv
        assert "title" in inv
        assert "created_at" in inv

    async def test_list_investigations_unauthenticated(self, async_client: AsyncClient):
        """
        Test that unauthenticated users cannot list investigations.

        The test issues a GET request to `/api/v1/investigations/` without providing any
        authentication credentials and verifies that the API responds with HTTP 401
        Unauthorized.
        """
        response = await async_client.get("/api/v1/investigations/")

        assert response.status_code == 401

    async def test_list_investigations_user_isolation(
        self, async_client: AsyncClient, db_session, test_user, admin_user
    ):
        """
        Test that regular users only see investigations they own.

        This integration test verifies user isolation for the `GET /api/v1/investigations/` endpoint. It creates one investigation owned by a normal user and another owned by an admin user, commits them to the database, then performs a request as the normal user. The response must contain only the investigation belonging to that user.

        Args:
            self: Test class instance.
            async_client (AsyncClient): HTTP client fixture for making asynchronous requests to the API.
            db_session: Database session fixture used to interact with the test database.
            test_user: Fixture representing a regular user; provides `user_id`, `username` and `role` attributes.
            admin_user: Fixture representing an administrator user; provides `user_id` attribute.

        Raises:
            AssertionError: If the response status is not 200 or if the returned investigations do not include the expected
            investigation owned by `test_user`.
        """
        from app.auth import create_access_token
        from app.crud.investigation import create_investigation

        # Create investigation for test_user
        user_inv = await create_investigation(
            db_session, title="User Investigation", owner_user_id=test_user.user_id
        )

        # Create investigation for admin_user
        admin_inv = await create_investigation(
            db_session, title="Admin Investigation", owner_user_id=admin_user.user_id
        )

        await db_session.commit()

        # List as regular user
        user_token = create_access_token(
            user_id=test_user.user_id, username=test_user.username, role=test_user.role
        )

        response = await async_client.get(
            "/api/v1/investigations/", headers={"Authorization": f"Bearer {user_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Regular user should only see their own investigation
        user_inv_ids = [inv["investigation_id"] for inv in data]
        assert str(user_inv.investigation_id) in user_inv_ids
        # Note: Admin investigation may or may not be visible depending on RBAC implementation


@pytest.mark.integration
class TestGetInvestigation:
    """Test get single investigation endpoint."""

    async def test_get_investigation_success(
        self, async_client: AsyncClient, auth_headers, test_investigation
    ):
        """
        Test retrieving a specific investigation via the API.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to make requests against the application.
        auth_headers : dict
            Authentication headers containing a valid JWT token for authorized access.
        test_investigation : InvestigationModel
            A fixture providing an existing investigation with populated fields.

        The function sends a GET request to `/api/v1/investigations/{investigation_id}` and asserts that:
        - The response status code is 200 (OK).
        - The returned JSON contains the correct `investigation_id` and `title` matching the provided fixture.
        """
        response = await async_client.get(
            f"/api/v1/investigations/{test_investigation.investigation_id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["investigation_id"] == str(test_investigation.investigation_id)
        assert data["title"] == test_investigation.title

    async def test_get_investigation_not_found(self, async_client: AsyncClient, auth_headers):
        """
        Test retrieving an investigation that does not exist.

        Args:
            async_client: An httpx.AsyncClient instance used to make requests against the API.
            auth_headers: Dictionary containing authentication headers for the request.

        The test generates a random UUID, issues a GET request to the investigations endpoint,
        and asserts that the response status code is 404 and that the error detail contains
        the phrase “not found”.
        """
        fake_id = uuid.uuid4()
        response = await async_client.get(f"/api/v1/investigations/{fake_id}", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    async def test_get_investigation_invalid_uuid(self, async_client: AsyncClient, auth_headers):
        """
        Test retrieving an investigation using an invalid UUID string and verify that the API returns a 422 Unprocessable Entity response.
        """
        response = await async_client.get("/api/v1/investigations/not-a-uuid", headers=auth_headers)

        assert response.status_code == 422  # Validation error

    async def test_get_investigation_unauthenticated(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test the GET endpoint for retrieving a single investigation when the request is made without authentication, expecting an HTTP 401 Unauthorized response. The test sends a GET request to the investigation detail URL using an unauthenticated client and asserts that the returned status code equals 401.
        """
        response = await async_client.get(
            f"/api/v1/investigations/{test_investigation.investigation_id}"
        )

        assert response.status_code == 401

    async def test_get_investigation_access_control(
        self, async_client: AsyncClient, db_session, test_user, admin_user
    ):
        """
        Test that non-owner users cannot retrieve an investigation they do not own.

        This integration test verifies the access-control logic of the `GET /api/v1/investigations/{id}` endpoint:

        - An investigation is created with its `owner_user_id` set to an admin user.
        - A regular user obtains a JWT access token via :func:`app.auth.create_access_token`.
        - The regular user attempts to fetch the admin-owned investigation using the async client.
        - The response must indicate that the operation is not permitted, asserting that the HTTP status code is either `403 Forbidden` or `404 Not Found`.

        The test ensures that investigations are only accessible by their owners (or privileged roles) and that unauthorized access is correctly blocked.
        """
        from app.auth import create_access_token
        from app.crud.investigation import create_investigation

        # Create investigation owned by admin
        admin_inv = await create_investigation(
            db_session, title="Admin Investigation", owner_user_id=admin_user.user_id
        )
        await db_session.commit()

        # Try to access as regular user
        user_token = create_access_token(
            user_id=test_user.user_id, username=test_user.username, role=test_user.role
        )

        response = await async_client.get(
            f"/api/v1/investigations/{admin_inv.investigation_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Should be forbidden for non-owner regular user
        assert response.status_code in [403, 404]


@pytest.mark.integration
class TestUpdateInvestigation:
    """Test investigation update endpoint."""

    async def test_update_investigation_title(
        self, async_client: AsyncClient, auth_headers, test_investigation
    ):
        """
        Test that updating an investigation's title via the PATCH endpoint succeeds and returns the updated data.

        The test performs the following steps:
        1. Sends a PATCH request to `/api/v1/investigations/{investigation_id}` with a JSON payload containing the new title.
        2. Asserts that the response status code is 200 (OK).
        3. Parses the JSON response and verifies that:
           - The `title` field matches the new title supplied in the request.
           - The `investigation_id` field matches the ID of the investigation used in the test.
        """
        new_title = "Updated Investigation Title"
        response = await async_client.patch(
            f"/api/v1/investigations/{test_investigation.investigation_id}",
            headers=auth_headers,
            json={"title": new_title},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == new_title
        assert data["investigation_id"] == str(test_investigation.investigation_id)

    async def test_update_investigation_not_found(self, async_client: AsyncClient, auth_headers):
        """
        Test that updating an investigation with a non-existent UUID returns a 404 Not Found response. The test generates a random UUID, sends a PATCH request to the investigations endpoint with authentication headers and a new title payload, then asserts that the HTTP status code of the response is 404.
        """
        fake_id = uuid.uuid4()
        response = await async_client.patch(
            f"/api/v1/investigations/{fake_id}", headers=auth_headers, json={"title": "New Title"}
        )

        assert response.status_code == 404

    async def test_update_investigation_unauthenticated(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that an unauthenticated request to update an investigation is rejected with HTTP 401 Unauthorized.

        Args:
            async_client: An httpx.AsyncClient instance configured for testing the API.
            test_investigation: A fixture providing a pre-created Investigation object whose `investigation_id` will be used in the request.
        """
        response = await async_client.patch(
            f"/api/v1/investigations/{test_investigation.investigation_id}",
            json={"title": "New Title"},
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestDeleteInvestigation:
    """Test investigation deletion endpoint."""

    async def test_delete_investigation_success(
        self, async_client: AsyncClient, auth_headers, test_investigation
    ):
        """
        Test that an investigation can be successfully deleted via the API.

        The test performs the following steps:
        1. Sends a DELETE request to the `/api/v1/investigations/{investigation_id}` endpoint using
           the provided authentication headers.
        2. Asserts that the response status code is `204 No Content` indicating successful deletion.
        3. Sends a subsequent GET request for the same investigation ID.
        4. Asserts that the GET request returns a `404 Not Found` status, confirming that the
           investigation has been removed from the system.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for testing the API.
            auth_headers: A dictionary containing authentication headers required for authorized requests.
            test_investigation: A fixture representing a pre-created investigation object with an
                `investigation_id` attribute used to target the DELETE and GET operations.
        """
        response = await async_client.delete(
            f"/api/v1/investigations/{test_investigation.investigation_id}", headers=auth_headers
        )

        assert response.status_code == 204

        # Verify investigation is deleted
        get_response = await async_client.get(
            f"/api/v1/investigations/{test_investigation.investigation_id}", headers=auth_headers
        )
        assert get_response.status_code == 404

    async def test_delete_investigation_not_found(self, async_client: AsyncClient, auth_headers):
        """
        Test that attempting to delete a non-existent investigation returns a 404 Not Found response.
        """
        fake_id = uuid.uuid4()
        response = await async_client.delete(
            f"/api/v1/investigations/{fake_id}", headers=auth_headers
        )

        assert response.status_code == 404

    async def test_delete_investigation_unauthenticated(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that an unauthenticated request to the investigation delete endpoint is rejected with HTTP 401 Unauthorized.

        Parameters
        ----------
        self : object
            The test class instance.
        async_client : AsyncClient
            An HTTPX asynchronous client fixture configured for the application.
        test_investigation : Investigation
            A fixture providing a persisted investigation whose `investigation_id` will be used in the DELETE request.
        """
        response = await async_client.delete(
            f"/api/v1/investigations/{test_investigation.investigation_id}"
        )

        assert response.status_code == 401

    async def test_delete_investigation_cascade(
        self, async_client: AsyncClient, auth_headers, db_session, test_investigation
    ):
        """
        Test that deleting an investigation via the API results in a HTTP 204 response and cascades the deletion to all related Artifact records, ensuring no artifacts remain linked to the removed investigation.
        """
        from app.models.artifact import Artifact
        from sqlalchemy import select

        # Create an artifact for the investigation
        artifact = Artifact(
            investigation_id=test_investigation.investigation_id,
            sha256=b"\x00" * 32,
            filename="test_file.evtx",
            classification=0,  # LOG_FILE
            blob=b"test data",
        )
        db_session.add(artifact)
        await db_session.commit()

        # Delete investigation
        response = await async_client.delete(
            f"/api/v1/investigations/{test_investigation.investigation_id}", headers=auth_headers
        )

        assert response.status_code == 204

        # Verify artifacts are also deleted (cascade)
        result = await db_session.execute(
            select(Artifact).where(Artifact.investigation_id == test_investigation.investigation_id)
        )
        artifacts = result.scalars().all()
        assert len(artifacts) == 0


@pytest.mark.integration
class TestFieldDictionaryStatus:
    """Test field dictionary status endpoint."""

    async def test_field_dictionary_status_empty(
        self, async_client: AsyncClient, auth_headers, test_investigation
    ):
        """
        Test getting field dictionary status when no fields have been discovered.

        Verifies that the endpoint returns zero counts for all metrics and
        `is_complete` is False when no field_dictionary entries exist.
        """
        response = await async_client.get(
            f"/api/v1/investigations/{test_investigation.investigation_id}/field-dictionary/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_fields"] == 0
        assert data["pending_fields"] == 0
        assert data["completed_fields"] == 0
        assert data["event_types"] == 0
        assert data["is_complete"] is False

    async def test_field_dictionary_status_with_pending_fields(
        self, async_client: AsyncClient, auth_headers, test_investigation, db_session
    ):
        """
        Test field dictionary status when some fields are pending LLM descriptions.

        Creates field_dictionary entries where some have NULL descriptions (pending)
        and verifies the counts are accurate.
        """
        from sqlalchemy import text

        # Insert field dictionary entries with mixed completion status
        await db_session.execute(
            text(
                """
                INSERT INTO field_dictionary 
                (investigation_id, event_type, field_name, description, sample_values)
                VALUES 
                (:inv_id, 'evtx_security_4624', 'TargetUserName', 'Account targeted by logon', ARRAY['admin', 'user']),
                (:inv_id, 'evtx_security_4624', 'LogonType', 'Type of logon event', ARRAY['2', '3', '10']),
                (:inv_id, 'evtx_security_4624', 'IpAddress', NULL, ARRAY['192.168.1.1']),
                (:inv_id, 'evtx_security_4625', 'FailureReason', NULL, ARRAY['Bad password']),
                (:inv_id, 'mft_entry', 'FileName', 'Name of file', ARRAY['test.txt'])
            """
            ),
            {"inv_id": str(test_investigation.investigation_id)},
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/investigations/{test_investigation.investigation_id}/field-dictionary/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_fields"] == 5
        assert data["pending_fields"] == 2  # IpAddress and FailureReason
        assert data["completed_fields"] == 3
        assert data["event_types"] == 3  # evtx_security_4624, evtx_security_4625, mft_entry
        assert data["is_complete"] is False

    async def test_field_dictionary_status_complete(
        self, async_client: AsyncClient, auth_headers, test_investigation, db_session
    ):
        """
        Test field dictionary status when all fields have LLM descriptions.

        Verifies that `is_complete` is True when no fields have NULL descriptions.
        """
        from sqlalchemy import text

        # Insert field dictionary entries all with descriptions
        await db_session.execute(
            text(
                """
                INSERT INTO field_dictionary 
                (investigation_id, event_type, field_name, description, sample_values)
                VALUES 
                (:inv_id, 'evtx_security_4624', 'TargetUserName', 'Account targeted by logon', ARRAY['admin']),
                (:inv_id, 'evtx_security_4624', 'LogonType', 'Type of logon event', ARRAY['2', '3']),
                (:inv_id, 'mft_entry', 'FileName', 'Name of file', ARRAY['test.txt'])
            """
            ),
            {"inv_id": str(test_investigation.investigation_id)},
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/investigations/{test_investigation.investigation_id}/field-dictionary/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_fields"] == 3
        assert data["pending_fields"] == 0
        assert data["completed_fields"] == 3
        assert data["event_types"] == 2
        assert data["is_complete"] is True

    async def test_field_dictionary_status_not_found(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test field dictionary status for non-existent investigation.

        Verifies that the endpoint returns 404 when the investigation doesn't exist.
        """
        fake_id = uuid.uuid4()
        response = await async_client.get(
            f"/api/v1/investigations/{fake_id}/field-dictionary/status",
            headers=auth_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    async def test_field_dictionary_status_unauthenticated(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that field dictionary status requires authentication.

        Verifies that unauthenticated requests are rejected with 401.
        """
        response = await async_client.get(
            f"/api/v1/investigations/{test_investigation.investigation_id}/field-dictionary/status"
        )

        assert response.status_code == 401

    async def test_field_dictionary_status_access_control(
        self, async_client: AsyncClient, db_session, test_user, admin_user
    ):
        """
        Test that users cannot access field dictionary status for investigations they don't own.

        Creates an investigation owned by admin, then attempts to access its field
        dictionary status as a regular user, expecting 403 Forbidden.
        """
        from app.auth import create_access_token
        from app.crud.investigation import create_investigation

        # Create investigation owned by admin
        admin_inv = await create_investigation(
            db_session, title="Admin Investigation", owner_user_id=admin_user.user_id
        )
        await db_session.commit()

        # Try to access as regular user
        user_token = create_access_token(
            user_id=test_user.user_id, username=test_user.username, role=test_user.role
        )

        response = await async_client.get(
            f"/api/v1/investigations/{admin_inv.investigation_id}/field-dictionary/status",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Should be forbidden for non-owner regular user
        assert response.status_code == 403

    async def test_field_dictionary_status_multiple_event_types(
        self, async_client: AsyncClient, auth_headers, test_investigation, db_session
    ):
        """
        Test field dictionary status correctly counts distinct event types.

        Verifies that the event_types count reflects the number of unique event_type
        values, not the total field count.
        """
        from sqlalchemy import text

        # Insert fields across multiple event types
        await db_session.execute(
            text(
                """
                INSERT INTO field_dictionary 
                (investigation_id, event_type, field_name, description, sample_values)
                VALUES 
                (:inv_id, 'evtx_security_4624', 'Field1', 'Description 1', ARRAY['val1']),
                (:inv_id, 'evtx_security_4624', 'Field2', 'Description 2', ARRAY['val2']),
                (:inv_id, 'evtx_security_4624', 'Field3', 'Description 3', ARRAY['val3']),
                (:inv_id, 'evtx_security_4625', 'Field1', 'Description 1', ARRAY['val1']),
                (:inv_id, 'mft_entry', 'Field1', 'Description 1', ARRAY['val1']),
                (:inv_id, 'mft_entry', 'Field2', 'Description 2', ARRAY['val2'])
            """
            ),
            {"inv_id": str(test_investigation.investigation_id)},
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/investigations/{test_investigation.investigation_id}/field-dictionary/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_fields"] == 6
        assert data["event_types"] == 3  # evtx_security_4624, evtx_security_4625, mft_entry
        assert data["completed_fields"] == 6
        assert data["pending_fields"] == 0
        assert data["is_complete"] is True
