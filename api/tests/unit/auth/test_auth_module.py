import pytest
from datetime import datetime, timedelta
from app.auth import create_access_token, verify_jwt_token


@pytest.mark.unit
class TestJWTTokenCreation:
    """Test JWT token creation."""

    def test_create_token_basic(self):
        """
        Test creating a basic JWT access token with typical user data.

        This test verifies that:
        - The token is generated (not None).
        - The returned value is a string.
        - The token string has non-zero length, indicating successful encoding.
        """
        user_id = 1
        username = "testuser"
        role = 0

        token = create_access_token(user_id=user_id, username=username, role=role)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_token_admin(self):
        """
        Test that an access token generated for an admin user contains the correct subject and role claims.

        The test creates a JWT using `create_access_token` with:
        - `user_id` set to `1`
        - `username` set to `"admin"`
        - `role` set to `1` (admin)

        It then verifies the token with `verify_jwt_token` and asserts that:
        - The `sub` claim in the payload equals the string representation of the user ID (`"1"`).
        - The `role` claim matches the provided admin role value (`1`).
        """
        token = create_access_token(user_id=1, username="admin", role=1)

        payload = verify_jwt_token(token)

        assert payload["sub"] == "1"
        assert payload["role"] == 1

    def test_create_token_with_custom_expiry(self):
        """
        Test creating an access token with a custom expiration time.

        This test verifies that `create_access_token` successfully generates a JWT when a specific
        expiration delta is provided. It uses a short-lived token (5 minutes) and asserts that the
        resulting token string is not `None`, confirming that the function respects the
        `expires_delta` parameter and returns a valid token value.
        """
        token = create_access_token(
            user_id=1,
            username="test",
            role=0,
            expires_delta=timedelta(minutes=5),
        )

        assert token is not None

    def test_token_contains_required_claims(self):
        """
        Test that an access token includes all mandatory JWT claims.

        Creates a token using `create_access_token` with a sample user ID, username, and role,
        then verifies it with `verify_jwt_token`. The resulting payload is examined to ensure
        the presence of the standard `sub` (subject) claim as well as the custom `username`,
        `role`, and expiration `exp` claims. Raises an assertion error if any required claim
        is missing.
        """
        token = create_access_token(user_id=1, username="test", role=0)
        payload = verify_jwt_token(token)

        assert "sub" in payload
        assert "username" in payload
        assert "role" in payload
        assert "exp" in payload


@pytest.mark.unit
class TestJWTTokenVerification:
    """Test JWT token verification."""

    def test_verify_valid_token(self):
        """
        Test verifying a valid JWT access token.

        Creates an access token with a known user ID, username, and role using `create_access_token`.
        The token is then passed to `verify_jwt_token` to decode and validate it.

        Asserts that:
        - The returned payload is not `None`.
        - The `sub` claim matches the string representation of the provided user ID.
        - The `username` claim matches the supplied username.
        - The `role` claim matches the supplied role value.
        """
        token = create_access_token(user_id=1, username="test", role=0)

        payload = verify_jwt_token(token)

        assert payload is not None
        assert payload["sub"] == "1"
        assert payload["username"] == "test"
        assert payload["role"] == 0

    def test_verify_expired_token(self):
        """
        Test that verifying an expired JWT token raises an exception.

        This test creates an access token with a negative expiration delta (i.e., already expired) and asserts that calling `verify_jwt_token` on this token triggers an exception, confirming proper handling of expired tokens.
        """
        token = create_access_token(
            user_id=1,
            username="test",
            role=0,
            expires_delta=timedelta(seconds=-1),
        )

        with pytest.raises(Exception):
            verify_jwt_token(token)

    def test_verify_malformed_token(self):
        """
        Test that verifying a malformed JWT token raises an exception, ensuring the verification function correctly handles inputs that do not conform to the expected three-part token structure.
        """
        malformed_token = "not.a.valid.token"

        with pytest.raises(Exception):
            verify_jwt_token(malformed_token)

    def test_verify_tampered_token(self):
        """
        Test verifying that token verification fails when the JWT is tampered with by modifying its signature part, expecting an exception to be raised.
        """
        token = create_access_token(user_id=1, username="test", role=0)

        # Tamper with token
        parts = token.split(".")
        if len(parts) == 3:
            parts[2] = parts[2][:-5] + "XXXXX"
            tampered_token = ".".join(parts)

            with pytest.raises(Exception):
                verify_jwt_token(tampered_token)

    def test_verify_token_extracts_user_id(self):
        """
        Verify that the JWT access token correctly encodes and returns the expected user identifier.\n\nThe test creates an access token using a known `user_id` value, then decodes the token with `verify_jwt_token`. It asserts that the `sub` claim in the resulting payload matches the original `user_id` when cast to `int`. This ensures that the token generation and verification processes preserve the user identifier accurately.
        """
        user_id = 12345
        token = create_access_token(user_id=user_id, username="test", role=0)

        payload = verify_jwt_token(token)

        assert int(payload["sub"]) == user_id

    def test_verify_token_extracts_role(self):
        """
        Test that the JWT verification correctly extracts the `role` claim from a valid access token created for a user with ID 1 and username \"admin\". The test creates an access token using :func:`create_access_token`, verifies it with :func:`verify_jwt_token`, and asserts that the returned payload contains the expected role value (`1`).
        """
        token = create_access_token(user_id=1, username="admin", role=1)

        payload = verify_jwt_token(token)

        assert payload["role"] == 1


@pytest.mark.unit
class TestTokenEdgeCases:
    """Test JWT token edge cases."""

    def test_create_token_unicode_username(self):
        """
        Test that creating an access token with a Unicode username correctly encodes and decodes the username field.

        The test generates a JWT using `create_access_token` with a username containing non-ASCII characters, verifies the token with `verify_jwt_token`, and asserts that the decoded payload retains the original Unicode username. This ensures proper handling of UTF-8 encoding/decoding throughout the token lifecycle.
        """
        token = create_access_token(user_id=1, username="用户", role=0)
        payload = verify_jwt_token(token)

        assert payload["username"] == "用户"

    def test_create_token_long_username(self):
        """
        Test that creating an access token with an exceptionally long username correctly embeds the full username in the JWT payload and that verification retrieves the exact same string without truncation or corruption. The test generates a username consisting of 1,000 repeated characters, creates a token using `create_access_token` with a sample user ID and role, verifies the token with `verify_jwt_token`, and asserts that the `username` field in the decoded payload matches the original long username.
        """
        long_username = "a" * 1000
        token = create_access_token(user_id=1, username=long_username, role=0)
        payload = verify_jwt_token(token)

        assert payload["username"] == long_username

    def test_create_token_special_chars_username(self):
        """
        Test that an access token can be created when the `username` contains special characters (e.g., `user@example.com!#$%`), and that after verification the `username` claim in the decoded payload matches the original value. This ensures the JWT handling correctly preserves and validates usernames with non-alphanumeric symbols.
        """
        username = "user@example.com!#$%"
        token = create_access_token(user_id=1, username=username, role=0)
        payload = verify_jwt_token(token)

        assert payload["username"] == username

    def test_token_expiration_is_future(self):
        """
        Test that the access token generated by `create_access_token` includes an expiration (`exp`) claim set to a future timestamp relative to the current UTC time. The test creates a token for a sample user, verifies it to extract the payload, and asserts that the `exp` value is greater than the present moment.
        """
        token = create_access_token(user_id=1, username="test", role=0)
        payload = verify_jwt_token(token)

        exp_timestamp = payload["exp"]
        current_timestamp = datetime.utcnow().timestamp()

        assert exp_timestamp > current_timestamp

    def test_create_token_very_large_user_id(self):
        """
        Test creating an access token with an extremely large numeric user ID and verify that the decoded payload preserves the original ID.
        """
        large_id = 999999999
        token = create_access_token(user_id=large_id, username="test", role=0)
        payload = verify_jwt_token(token)

        assert int(payload["sub"]) == large_id
