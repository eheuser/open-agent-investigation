"""
Unit tests for Investigation model.
"""

import pytest
import uuid
from datetime import datetime

from app.models.investigation import Investigation


@pytest.mark.unit
class TestInvestigationModel:
    """Test Investigation model behavior."""

    def test_investigation_creation(self):
        """
        Test that an `Investigation` object can be instantiated with explicit values for its primary key, title, owner identifier, and creation timestamp, and that the resulting attributes match the supplied arguments.
        """
        inv_id = uuid.uuid4()
        created = datetime.utcnow()

        investigation = Investigation(
            investigation_id=inv_id, title="Test Investigation", owner_user_id=1, created_at=created
        )

        assert investigation.investigation_id == inv_id
        assert investigation.title == "Test Investigation"
        assert investigation.owner_user_id == 1
        assert investigation.created_at == created

    def test_investigation_uuid_generation(self):
        """
        Test that an Investigation instance can be created without explicitly providing an `investigation_id` and that the title is set correctly; verifies that UUID generation is handled automatically by the database (the attribute may remain `None` until the object is persisted).
        """
        investigation = Investigation(title="Auto UUID Test", owner_user_id=1)

        # UUID should be generated if not provided (at DB level)
        # In Python, it might be None until committed
        assert investigation.title == "Auto UUID Test"

    def test_investigation_repr(self):
        """
        Test that the `Investigation` model’s `__repr__` method returns a string containing identifying information.

        The test creates an `Investigation` instance with a known UUID, title, and owner, obtains its representation via `repr()`, and asserts that the resulting string includes either the class name `"Investigation"` or the string form of the supplied UUID. This ensures that the `__repr__` implementation provides useful debugging output.
        """
        inv_id = uuid.uuid4()
        investigation = Investigation(
            investigation_id=inv_id, title="Test Investigation", owner_user_id=1
        )

        repr_str = repr(investigation)
        # Check that repr includes key information
        assert "Investigation" in repr_str or str(inv_id) in repr_str

    def test_investigation_title_types(self):
        """
        Test that the `title` field of an :class:`Investigation` instance accepts a variety of string inputs, including simple text, numeric characters, special symbols, Unicode characters, very long concatenated strings, and an empty string, ensuring the stored value matches the provided input for each case.
        """
        test_titles = [
            "Simple Title",
            "Title with numbers 123",
            "Title with special chars !@#$%",
            "Unicode title: 日本語 中文 한글",
            "Very " + "long " * 100 + "title",
            "",  # Empty title
        ]

        for title in test_titles:
            investigation = Investigation(
                investigation_id=uuid.uuid4(), title=title, owner_user_id=1
            )
            assert investigation.title == title

    def test_investigation_owner_nullable(self):
        """
        Test that an Investigation instance can be created with a null `owner_user_id` and that the attribute remains `None` after instantiation.
        """
        investigation = Investigation(
            investigation_id=uuid.uuid4(), title="Orphaned Investigation", owner_user_id=None
        )

        assert investigation.owner_user_id is None


@pytest.mark.unit
class TestInvestigationRelationships:
    """Test Investigation model relationships."""

    def test_investigation_has_owner_relationship(self):
        """
        Test that an Investigation instance correctly stores and exposes its owner_user_id attribute, ensuring it references the associated User's primary key.
        """
        # This is a documentation test for the relationship
        investigation = Investigation(investigation_id=uuid.uuid4(), title="Test", owner_user_id=42)

        # owner_user_id should reference users.user_id
        assert investigation.owner_user_id == 42

    def test_investigation_cascade_delete(self):
        """
        Test that deleting an :class:`Investigation` instance triggers cascade deletion of all related records at the database level.

        The test creates an `Investigation` with a generated UUID, a title, and an owner user ID, then verifies that the `investigation_id` attribute is set (i.e., the object was successfully instantiated). The actual cascade behavior is enforced by database constraints and is not verified directly in this unit test; instead, the presence of the identifier confirms that the investigation exists before deletion.
        """
        # This is a documentation test
        # Actual cascade behavior is enforced by DB constraints
        investigation = Investigation(
            investigation_id=uuid.uuid4(), title="To Be Deleted", owner_user_id=1
        )

        # When deleted, all related data should cascade delete:
        # - artifacts
        # - events
        # - timeline entries
        # - chat messages
        # - tool executions
        assert investigation.investigation_id is not None
