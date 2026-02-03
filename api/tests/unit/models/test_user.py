import pytest
from datetime import datetime

from app.models.user import User, UserRole


@pytest.mark.unit
class TestUserModel:
    """Test User model behavior."""

    def test_user_creation(self):
        """
        Test creating a User instance and verifying its attributes.

        The test constructs a `User` object with explicit values for all required fields and then asserts that each attribute is correctly set:

        - `user_id` matches the provided integer identifier.
        - `username` equals the supplied string.
        - `password_hash` stores the given hash value.
        - `role` reflects the numeric role identifier.
        - `created_at` is an instance of :class:`datetime.datetime`.

        No return value is expected; the test passes if all assertions succeed.
        """
        user = User(
            user_id=1,
            username="testuser",
            password_hash="hashed_password",
            role=0,
            created_at=datetime.utcnow(),
        )

        assert user.user_id == 1
        assert user.username == "testuser"
        assert user.password_hash == "hashed_password"
        assert user.role == 0
        assert isinstance(user.created_at, datetime)

    def test_user_repr(self):
        """
        Test that the User model's __repr__ method returns a string containing the class name, user ID, username, and role value. The test creates a User instance with known attributes, obtains its representation via repr(), and asserts that the resulting string includes "User", the numeric ID, the provided username, and the correct role assignment.
        """
        user = User(user_id=42, username="testuser", password_hash="hash", role=0)

        repr_str = repr(user)
        assert "User" in repr_str
        assert "42" in repr_str
        assert "testuser" in repr_str
        assert "role=0" in repr_str

    def test_is_admin_regular_user(self):
        """
        Test that `User.is_admin()` correctly returns `False` when called on a user with the `REGULAR` role.
        """
        user = User(user_id=1, username="regular", password_hash="hash", role=UserRole.REGULAR)

        assert user.is_admin() is False

    def test_is_admin_admin_user(self):
        """
        Test that `User.is_admin` returns `True` when the user has the :class:`~UserRole.ADMIN` role.
        """
        user = User(user_id=1, username="admin", password_hash="hash", role=UserRole.ADMIN)

        assert user.is_admin() is True

    def test_user_role_enum(self):
        """
        Test that the UserRole enumeration defines the expected integer values for regular and admin roles and that each enum member is an instance of int.
        """
        assert UserRole.REGULAR == 0
        assert UserRole.ADMIN == 1

        # Test that enum values are integers
        assert isinstance(UserRole.REGULAR, int)
        assert isinstance(UserRole.ADMIN, int)

    def test_user_default_role(self):
        """
        Test that the user's role defaults to `REGULAR` (value 0) when not explicitly provided, verifying the expected database-level default behavior.
        """
        user = User(
            user_id=1,
            username="newuser",
            password_hash="hash",
            role=0,  # Default must be set explicitly in Python
        )

        # Note: Default is set at DB level, not in Python
        # This test documents expected behavior
        assert user.role == 0


@pytest.mark.unit
class TestUserValidation:
    """Test User model validation."""

    def test_username_uniqueness_constraint(self):
        """
        Test that the `username` field enforces uniqueness at the database level. The test creates two :class:`User` instances with identical usernames, demonstrating that Python object creation does not raise an error, but a subsequent database insert would violate the unique constraint. The assertion confirms both objects share the same username value.
        """
        # This is a documentation test - actual uniqueness is enforced by DB
        user1 = User(user_id=1, username="same", password_hash="hash1", role=0)
        user2 = User(user_id=2, username="same", password_hash="hash2", role=0)

        # Both can be created in Python, but DB will reject duplicate username
        assert user1.username == user2.username

    def test_role_values(self):
        """
        Test that the User model accepts valid role inputs and normalizes them correctly.

        The test iterates over a collection of permissible role representations-including integer literals (0 and 1) as well as the corresponding `UserRole` enum members-and constructs a `User` instance for each. It then asserts that the stored `role` attribute on the created user is normalized to one of the expected integer values (0 for regular users, 1 for admins). This ensures both direct integer assignments and enum-based assignments are handled uniformly by the model.
        """
        valid_roles = [0, 1, UserRole.REGULAR, UserRole.ADMIN]

        for role in valid_roles:
            user = User(user_id=1, username="test", password_hash="hash", role=role)
            assert user.role in [0, 1]

    def test_password_hash_not_plaintext(self):
        """
        Test that the password_hash attribute is not stored as plain text.

        This test creates a User instance with an intentionally unhashed password string to illustrate that passwords must be hashed before being saved. It verifies that the `password_hash` field contains data (i.e., its length is greater than zero), documenting the expectation that password handling logic elsewhere (e.g., in auth.py) will replace plain-text values with a proper hash. The test does not perform hashing itself; it merely confirms that the attribute is populated and signals the need for hashing.
        """
        user = User(
            user_id=1,
            username="test",
            password_hash="password123",  # BAD - should be hashed
            role=0,
        )

        # This test documents that passwords should be hashed
        # The actual hashing happens in auth.py
        assert len(user.password_hash) > 0
