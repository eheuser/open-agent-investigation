import pytest
from datetime import timedelta
from fastapi import HTTPException

from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    verify_jwt_token,
)
from app.core.security import get_token


@pytest.mark.unit
class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password_returns_string(self):
        """
        Test that `hash_password` returns a non-empty string distinct from the original password. The test hashes a sample password, verifies the result is an instance of `str`, checks its length is greater than zero, and confirms it does not equal the input password.
        """
        password = "testpassword123"
        hashed = hash_password(password)

        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != password  # Should not be plaintext

    def test_hash_password_is_deterministic(self):
        """
        Ensures that hashing the identical plaintext password twice yields distinct hash values, confirming that a random salt is applied during each invocation of `hash_password`. This validates the nondeterministic nature of the Argon2 hashing algorithm used for secure password storage.
        """
        password = "testpassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Argon2 uses random salt, so hashes should differ
        assert hash1 != hash2

    def test_verify_password_correct(self):
        """
        Test that :func:`verify_password` returns `True` when provided with the original password and its correctly generated hash.
        """
        password = "testpassword123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """
        Test that `verify_password` returns `False` when given an incorrect password, ensuring it does not mistakenly validate mismatched credentials.
        """
        password = "testpassword123"
        wrong_password = "wrongpassword"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_empty_string(self):
        """
        Test that `verify_password` returns `False` when given an empty password string, ensuring it does not mistakenly validate against a valid hash.
        """
        password = "testpassword123"
        hashed = hash_password(password)

        assert verify_password("", hashed) is False

    def test_hash_empty_password(self):
        """
        Test hashing and verification of an empty password.

        Ensures that `hash_password` returns a string when given an empty string and that `verify_password` correctly validates the empty password against its hash.
        """
        hashed = hash_password("")
        assert isinstance(hashed, str)
        assert verify_password("", hashed) is True


@pytest.mark.unit
class TestJWTTokens:
    """Test JWT token creation and verification."""

    def test_create_access_token_returns_string(self):
        """
        Test that `create_access_token` generates a non-empty JWT string containing exactly two period characters. The token is created with a sample user ID, username, and role, then the test asserts the result is an instance of `str`, has length greater than zero, and includes two dot separators separating header, payload, and signature.
        """
        token = create_access_token(user_id=1, username="testuser", role=0)

        assert isinstance(token, str)
        assert len(token) > 0
        assert token.count(".") == 2  # JWT has 3 parts separated by dots

    def test_verify_jwt_token_valid(self):
        """
        Test that `verify_jwt_token` correctly decodes a valid JWT and returns the expected payload fields.

        The test creates an access token with known `user_id`, `username` and `role` values using :func:`create_access_token`. It then passes this token to :func:`verify_jwt_token` and asserts that:

        * The `sub` claim matches the string representation of the original `user_id`.
        * The `username` claim equals the original username.
        * The `role` claim equals the original role value.
        * An expiration claim (`exp`) is present in the decoded payload.
        """
        user_id = 42
        username = "testuser"
        role = 1

        token = create_access_token(user_id=user_id, username=username, role=role)

        payload = verify_jwt_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["username"] == username
        assert payload["role"] == role
        assert "exp" in payload

    def test_verify_jwt_token_expired(self):
        """
        Test that `verify_jwt_token` raises an :class:`~fastapi.HTTPException` with status code 401 when provided with an expired JWT. The test creates an access token whose expiration time is set to one second in the past, invokes `verify_jwt_token` with this token, and asserts that the exception’s detail contains the word “expired”.
        """
        token = create_access_token(
            user_id=1,
            username="testuser",
            role=0,
            expires_delta=timedelta(seconds=-1),  # Expired 1 second ago
        )

        with pytest.raises(HTTPException) as exc_info:
            verify_jwt_token(token)

        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_verify_jwt_token_invalid(self):
        """
        Test that verify_jwt_token raises an HTTPException with status code 401 when provided with a malformed JWT string.
        """
        invalid_token = "not.a.valid.jwt.token"

        with pytest.raises(HTTPException) as exc_info:
            verify_jwt_token(invalid_token)

        assert exc_info.value.status_code == 401

    def test_verify_jwt_token_malformed(self):
        """
        Test that `verify_jwt_token` raises an :class:`~fastapi.HTTPException` with status code 401 when given a malformed JWT string. The test supplies the literal string `"malformed"`, invokes `verify_jwt_token` inside a `pytest.raises` context, and asserts that the caught exception's `status_code` attribute equals 401. This ensures the function correctly identifies and rejects tokens that cannot be parsed as valid JWTs.
        """
        malformed_token = "malformed"

        with pytest.raises(HTTPException) as exc_info:
            verify_jwt_token(malformed_token)

        assert exc_info.value.status_code == 401

    def test_create_access_token_custom_expiry(self):
        """
        Test that a custom expiration timedelta is correctly applied when creating an access token, then verify the resulting JWT contains an expiration claim and the expected subject identifier.
        """
        custom_delta = timedelta(hours=24)
        token = create_access_token(
            user_id=1, username="testuser", role=0, expires_delta=custom_delta
        )

        payload = verify_jwt_token(token)

        # Token should be valid
        assert "exp" in payload
        assert payload["sub"] == "1"

    def test_token_contains_all_claims(self):
        """
        Test that the generated JWT access token includes all required claims and that each claim contains the expected value.

        The test creates an access token using `create_access_token` with a specific user identifier, username, and role. It then verifies the token via `verify_jwt_token` to obtain its payload. The assertions confirm:

        * Presence of the standard `sub` (subject) claim as well as custom `username`, `role`, and expiration `exp` claims.
        * Correctness of the claim values: `sub` matches the stringified user ID, `username` matches the supplied username, and `role` matches the provided role.
        """
        user_id = 99
        username = "adminuser"
        role = 1

        token = create_access_token(user_id=user_id, username=username, role=role)

        payload = verify_jwt_token(token)

        # Check all claims are present
        assert "sub" in payload
        assert "username" in payload
        assert "role" in payload
        assert "exp" in payload

        # Check values
        assert payload["sub"] == str(user_id)
        assert payload["username"] == username
        assert payload["role"] == role


@pytest.mark.unit
class TestPasswordHashingEdgeCases:
    """Test edge cases for password hashing."""

    def test_hash_very_long_password(self):
        """
        Test hashing a very long password.

        This test verifies that the password-hashing utilities correctly handle passwords near the maximum size supported by Argon2 (4096 bytes). It creates a 4000-character password string-just under the limit-hashes it using :func:`hash_password`, and asserts that:

        * The returned hash is a string.
        * :func:`verify_password` confirms the original password matches the generated hash.
        """
        # Argon2 has a max password size of 4096 bytes
        password = "a" * 4000  # Just under the limit
        hashed = hash_password(password)

        assert isinstance(hashed, str)
        assert verify_password(password, hashed) is True

    def test_hash_special_characters(self):
        """
        Test that hashing and verification work correctly when the password contains a wide range of special characters, ensuring the functions handle all printable symbols without error.
        """
        password = "p@ssw0rd!#$%^&*()_+-=[]{}|;:',.<>?/~`"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_hash_unicode_password(self):
        """
        Test hashing of a password containing Unicode characters, ensuring that `hash_password` correctly processes multibyte input and that `verify_password` successfully validates the original Unicode string against the generated hash.
        """
        password = "пароль密码🔒"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_hash_newline_in_password(self):
        """
        Test that a password containing newline characters (both LF and CRLF) can be hashed and subsequently verified successfully. This ensures the hashing and verification functions correctly handle passwords with embedded line breaks.
        """
        password = "pass\nword\r\n123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True


@pytest.mark.unit
class TestGetToken:
    """Test get_token dependency."""

    async def test_get_token_with_credentials(self):
        """
        Test that `get_token` correctly extracts the token string from an `HTTPAuthorizationCredentials` instance when credentials are provided.

        The function creates a `HTTPAuthorizationCredentials` object with scheme `Bearer` and a sample token, invokes `get_token` asynchronously, and asserts that the returned value matches the original token. This verifies the normal extraction path of the utility.
        """
        from fastapi.security import HTTPAuthorizationCredentials

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-token-123")

        token = await get_token(credentials)

        assert token == "test-token-123"

    async def test_get_token_without_credentials(self):
        """
        Test the get_token utility when called with a None credential, verifying that it returns `None` indicating no token could be retrieved.
        """
        token = await get_token(None)

        assert token is None

    async def test_get_token_empty_credentials(self):
        """Test get_token with empty string credentials."""
        from fastapi.security import HTTPAuthorizationCredentials

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="")
        token = await get_token(credentials)
        assert token == ""

    async def test_get_token_various_schemes(self):
        """Test get_token works regardless of auth scheme."""
        from fastapi.security import HTTPAuthorizationCredentials

        # Test with different schemes
        for scheme in ["Bearer", "bearer", "Token", "JWT"]:
            credentials = HTTPAuthorizationCredentials(scheme=scheme, credentials="my-token")
            token = await get_token(credentials)
            assert token == "my-token"
