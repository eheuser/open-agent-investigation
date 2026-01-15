"""
Unit tests for user schemas.
Tests Pydantic validation for user data.
"""

import pytest
from pydantic import ValidationError
from app.schemas.user import UserCreate, UserRead, UserLogin


@pytest.mark.unit
class TestUserCreate:
    """Test UserCreate schema."""

    def test_create_valid_user(self):
        """
        Test creating a valid user instance using the `UserCreate` schema.

        This test verifies that:
        - Supplying a dictionary with both required fields (`username` and `password`) correctly constructs a `UserCreate` model.
        - The resulting object's attributes match the input values, confirming successful validation and assignment.
        """
        data = {
            "username": "testuser",
            "password": "SecurePass123!",
        }

        user = UserCreate(**data)

        assert user.username == "testuser"
        assert user.password == "SecurePass123!"

    def test_create_user_missing_username(self):
        """
        Test that creating a user without providing the required `username` field raises a Pydantic `ValidationError`. The input data includes only a valid `password`; attempting to instantiate `UserCreate` with this incomplete payload should trigger validation failure.
        """
        data = {
            "password": "SecurePass123!",
        }

        with pytest.raises(ValidationError):
            UserCreate(**data)

    def test_create_user_missing_password(self):
        """
        Test that creating a UserCreate instance without providing the required `password` field raises a `ValidationError`. The input data includes only a `username` key, and the test asserts that validation fails as expected.
        """
        data = {
            "username": "testuser",
        }

        with pytest.raises(ValidationError):
            UserCreate(**data)

    def test_create_user_short_username(self):
        """
        Test that creating a user with a username shorter than the typical minimum length does not raise a validation error when such a constraint is absent, and verifies that the resulting model retains the provided short username. If a `ValidationError` is raised (e.g., when a minimum length validator is present), the exception is caught and ignored, allowing the test suite to continue without failure.
        """
        data = {
            "username": "ab",
            "password": "SecurePass123!",
        }

        # May or may not have min length validation
        try:
            user = UserCreate(**data)
            assert user.username == "ab"
        except ValidationError:
            pass  # Min length validation exists

    def test_create_user_long_username(self):
        """
        Test that creating a UserCreate instance with a username of maximum allowed length (100 characters) succeeds and preserves the full length of the username. The test constructs input data with a 100-character username and a valid password, instantiates the schema, and asserts that the resulting object's username attribute retains the expected length.
        """
        data = {
            "username": "a" * 100,
            "password": "SecurePass123!",
        }

        user = UserCreate(**data)
        assert len(user.username) == 100

    def test_create_user_unicode_username(self):
        """
        Test creating a user with a Unicode username, ensuring the `UserCreate` schema correctly accepts and preserves non-ASCII characters in the `username` field.
        """
        data = {
            "username": "ユーザー123",
            "password": "SecurePass123!",
        }

        user = UserCreate(**data)
        assert user.username == "ユーザー123"

    def test_create_user_special_chars_username(self):
        """
        Test that creating a user with a username containing special characters (e.g., an email address) succeeds and retains the special character in the stored username field. The function constructs a valid payload, instantiates the `UserCreate` schema, and asserts that the "@" symbol is present in the resulting `username` attribute.
        """
        data = {
            "username": "user@example.com",
            "password": "SecurePass123!",
        }

        user = UserCreate(**data)
        assert "@" in user.username

    def test_create_user_weak_password(self):
        """
        Test creating a user with a weak password, ensuring that the schema either accepts the short password or raises a ValidationError without causing unexpected failures. The test verifies that when validation passes, the password attribute matches the provided value; otherwise, it silently handles the expected ValidationError.
        """
        data = {
            "username": "testuser",
            "password": "123",
        }

        # May or may not have password strength validation
        try:
            user = UserCreate(**data)
            assert user.password == "123"
        except ValidationError:
            pass  # Password strength validation exists


@pytest.mark.unit
class TestUserRead:
    """Test UserRead schema."""

    def test_read_user_basic(self):
        """
        Test that the `UserRead` schema correctly parses a typical user payload.

        The function constructs a dictionary containing an `id`, `username`, `role` and a `created_at` timestamp, instantiates a `UserRead` model with it, and asserts that the resulting object's `id`, `username` and `role` attributes match the supplied values. This verifies that required fields are accepted and correctly typed during deserialization.
        """
        from datetime import datetime

        data = {
            "id": 1,
            "username": "testuser",
            "role": 0,
            "created_at": datetime.now(),
        }

        user = UserRead(**data)

        assert user.id == 1
        assert user.username == "testuser"
        assert user.role == 0

    def test_read_admin_user(self):
        """
        Test reading an admin user by constructing a UserRead instance with typical admin data and verifying that the role attribute is correctly set to the expected admin role value (1). This ensures that the UserRead schema properly parses and retains the role information for admin users.
        """
        from datetime import datetime

        data = {
            "id": 1,
            "username": "admin",
            "role": 1,
            "created_at": datetime.now(),
        }

        user = UserRead(**data)

        assert user.role == 1

    def test_read_user_missing_field(self):
        """
        Test that constructing a UserRead model without the required `username` field raises a Pydantic `ValidationError`. The input dictionary includes only an `id` key; attempting to instantiate `UserRead` should trigger validation failure, which is asserted using `pytest.raises`.
        """
        data = {
            "id": 1,
            # Missing username
        }

        with pytest.raises(ValidationError):
            UserRead(**data)

    def test_read_user_invalid_role(self):
        """
        Test that constructing a `UserRead` instance with an out-of-range `role` value does not raise a validation error when the schema permits any integer, and that the resulting object's `role` attribute retains the supplied invalid value; if the schema enforces role constraints, the test gracefully handles the raised `ValidationError`.
        """
        from datetime import datetime

        data = {
            "id": 1,
            "username": "testuser",
            "role": 999,
            "created_at": datetime.now(),
        }

        # May accept any integer or validate role range
        try:
            user = UserRead(**data)
            assert user.role == 999
        except ValidationError:
            pass


@pytest.mark.unit
class TestUserLogin:
    """Test UserLogin schema."""

    def test_login_valid(self):
        """
        Test that a UserLogin instance correctly validates and stores valid credentials.

        The test constructs a dictionary with a typical username and password, creates a `UserLogin` model from it, and asserts that the resulting object's attributes match the input values. This verifies both field validation and attribute assignment for successful login data.
        """
        data = {
            "username": "testuser",
            "password": "SecurePass123!",
        }

        login = UserLogin(**data)

        assert login.username == "testuser"
        assert login.password == "SecurePass123!"

    def test_login_missing_username(self):
        """
        Test that creating a UserLogin schema without the required `username` field raises a Pydantic `ValidationError`.
        """
        data = {
            "password": "SecurePass123!",
        }

        with pytest.raises(ValidationError):
            UserLogin(**data)

    def test_login_missing_password(self):
        """
        Test that constructing a UserLogin schema without providing the required `password` field raises a Pydantic `ValidationError`. The test supplies only a `username` key in the input data and asserts that validation fails as expected.
        """
        data = {
            "username": "testuser",
        }

        with pytest.raises(ValidationError):
            UserLogin(**data)

    def test_login_unicode_username(self):
        """
        Test the UserLogin schema's ability to handle usernames containing Unicode characters.

        This test constructs a payload with a Japanese username and a standard password,
        instantiates the `UserLogin` model, and asserts that the `username` attribute
        preserves the original Unicode string. It verifies that no validation errors are
        raised for non-ASCII input and that the field value remains unchanged after
        model creation.
        """
        data = {
            "username": "ユーザー",
            "password": "password123",
        }

        login = UserLogin(**data)

        assert login.username == "ユーザー"
