import time
import pytest
from app.auth import hash_password, verify_password


@pytest.mark.unit
class TestPasswordHashing:
    """Test password hashing functions."""

    def test_hash_password_basic(self):
        """
        Test basic password hashing using Argon2.

        This test verifies that `hash_password` returns a non-null string representation of the hashed password, that the result differs from the original plaintext password, and that it follows the expected Argon2 hash format (i.e., starts with `$argon2`).
        """
        password = "MySecurePassword123"
        hashed = hash_password(password)

        assert hashed is not None
        assert isinstance(hashed, str)
        assert hashed != password
        assert hashed.startswith("$argon2")

    def test_verify_correct_password(self):
        """
        Test that verifying the correct password against its Argon2 hash returns `True`.
        """
        password = "MySecurePassword123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_incorrect_password(self):
        """
        Test that password verification correctly fails when an incorrect password is provided.

        The test hashes a known valid password using :func:`hash_password` and then attempts to verify a different,
        incorrect password against the generated hash. It asserts that :func:`verify_password` returns `False`,
        confirming that mismatched credentials are not accepted.
        """
        password = "MySecurePassword123"
        wrong_password = "WrongPassword456"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_hash_produces_different_salts(self):
        """
        Test that hashing the same password twice generates distinct salted hashes and that each hash correctly verifies the original password.
        """
        password = "TestPassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_hash_empty_password(self):
        """
        Test that hashing an empty password produces a valid Argon2 hash and that verification succeeds only with the exact empty string.

        The test:
        - Calls :func:`hash_password` with `""` and stores the resulting hash.
        - Asserts that :func:`verify_password` returns `True` when both the original empty password and the generated hash are provided.
        - Asserts that verification fails (returns `False`) when a different password (e.g., `"a"`) is checked against the same hash.
        """
        hashed = hash_password("")

        assert verify_password("", hashed)
        assert not verify_password("a", hashed)

    def test_hash_unicode_password(self):
        """
        Test that hashing and verification work correctly with a Unicode password string.

        - Creates a password containing Japanese characters and digits.
        - Generates a hash using `hash_password`.
        - Asserts that the original password verifies successfully against the generated hash.
        - Asserts that a slightly altered password (different trailing digit) fails verification.
        """
        password = "パスワード123"
        hashed = hash_password(password)

        assert verify_password(password, hashed)
        assert not verify_password("パスワード124", hashed)

    def test_hash_long_password(self):
        """
        Test that a very long password can be hashed and subsequently verified.

        The test creates a password consisting of 1000 repeated `'a'` characters, hashes it using :func:`hash_password`, and then asserts that :func:`verify_password` returns `True` when checking the original password against the generated hash.
        """
        long_password = "a" * 1000
        hashed = hash_password(long_password)

        assert verify_password(long_password, hashed)

    def test_hash_special_characters(self):
        """
        Test hashing a password containing special characters and verify it matches the generated hash.
        """
        password = "P@ssw0rd!#$%^&*()"
        hashed = hash_password(password)

        assert verify_password(password, hashed)

    def test_verify_case_sensitive(self):
        """
        Test that password verification respects case sensitivity: the original password verifies successfully, while any variation with different capitalization fails.
        """
        password = "MyPassword"
        hashed = hash_password(password)

        assert verify_password(password, hashed)
        assert not verify_password("mypassword", hashed)
        assert not verify_password("MYPASSWORD", hashed)

    def test_verify_whitespace_sensitive(self):
        """
        Test that whitespace characters are significant when verifying passwords: verifies a correctly hashed password succeeds, while passwords with leading or trailing spaces fail verification.
        """
        password = "password"
        hashed = hash_password(password)

        assert verify_password(password, hashed)
        assert not verify_password("password ", hashed)
        assert not verify_password(" password", hashed)

    def test_verify_invalid_hash_format(self):
        """
        Test that verifying a password against an improperly formatted hash raises an exception, confirming the function correctly handles unrecognizable hash strings.
        """
        password = "test123"
        invalid_hash = "not-a-valid-hash"

        # passlib raises exception for unrecognized hash format
        with pytest.raises(Exception):
            verify_password(password, invalid_hash)

    def test_verify_bcrypt_hash_fails(self):
        """
        Test that attempting to verify a password against an unsupported bcrypt hash raises an exception, confirming that only Argon2 hashes are accepted by the verification function.
        """
        password = "test123"
        bcrypt_hash = "$2b$12$KIXqRw8N7FfqKJ.V6xGxLOXxQq9Y6Y0YqVqVqVqVqVqVqVqVqVqVq"

        # passlib raises exception for unsupported hash schemes
        with pytest.raises(Exception):
            verify_password(password, bcrypt_hash)

    def test_hash_with_null_bytes(self):
        """
        Test that hashing and verifying a password containing null byte characters works correctly. The function creates a password string with an embedded null byte, hashes it using `hash_password`, then verifies the hash with `verify_password` to ensure the process succeeds despite the presence of null bytes.
        """
        password = "test\x00password"
        hashed = hash_password(password)

        assert verify_password(password, hashed)

    def test_hash_numeric_string(self):
        """
        Test hashing a numeric string password and verify correct matching and mismatch.

        This test creates a password consisting solely of digits, hashes it using `hash_password`, and asserts that:
        - The original numeric password successfully verifies against the generated hash.
        - A similar but different numeric password (missing the last digit) fails verification.
        """
        password = "123456789"
        hashed = hash_password(password)

        assert verify_password(password, hashed)
        assert not verify_password("12345678", hashed)

    def test_hash_spaces_only(self):
        """
        Test that hashing and verification work correctly when the password consists solely of space characters.

        The test hashes a password containing five spaces, verifies that the original password matches the generated hash, and confirms that a different string with four spaces does not verify against the same hash. This ensures that whitespace-only passwords are handled distinctly and that the length of the input is taken into account during verification.
        """
        password = "     "
        hashed = hash_password(password)

        assert verify_password(password, hashed)
        assert not verify_password("    ", hashed)


@pytest.mark.unit
class TestPasswordHashingPerformance:
    """Test password hashing performance."""

    def test_hash_reasonable_time(self):
        """
        Test that hashing completes in reasonable time.

        The test measures the elapsed time taken by `hash_password` when processing a typical password string and asserts that the operation finishes in under one second. This ensures that the Argon2 implementation remains performant for standard use cases.
        """
        password = "TestPassword123"
        start = time.time()
        hash_password(password)
        elapsed = time.time() - start

        # Should complete in less than 1 second
        assert elapsed < 1.0

    def test_verify_reasonable_time(self):
        """
        Test that password verification completes within an acceptable duration.

        This test hashes a sample password using :func:`hash_password`, measures the time taken by
        :func:`verify_password` to confirm the same password against the generated hash, and asserts
        that the elapsed time is less than one second, ensuring that verification remains performant.
        """
        password = "TestPassword123"
        hashed = hash_password(password)

        start = time.time()
        verify_password(password, hashed)
        elapsed = time.time() - start

        # Verification should be fast
        assert elapsed < 1.0
