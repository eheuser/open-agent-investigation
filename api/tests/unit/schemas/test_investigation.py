"""
Unit tests for Investigation Pydantic schemas.
"""

import pytest
from pydantic import ValidationError
from datetime import datetime
import uuid

from app.schemas.investigation import InvestigationCreate, InvestigationRead, InvestigationUpdate


@pytest.mark.unit
class TestInvestigationCreateSchema:
    """Test InvestigationCreate schema validation."""

    def test_valid_investigation_create(self):
        """
        Test creating an investigation with valid data.

        Ensures that the `InvestigationCreate` Pydantic model can be instantiated using a dictionary containing a `title` field, and verifies that the resulting object's `title` attribute matches the provided value.
        """
        data = {"title": "Test Investigation"}
        schema = InvestigationCreate(**data)

        assert schema.title == "Test Investigation"

    def test_investigation_create_min_length(self):
        """
        Test that the `title` field enforces a minimum length constraint.\n\nThe test attempts to create an `InvestigationCreate` instance with an empty string for `title`. It expects Pydantic to raise a `ValidationError` and verifies that the error message includes \"String should have at least 1 character\". This ensures that the schema correctly validates the minimum length requirement for the title field.
        """
        # Empty string should fail
        with pytest.raises(ValidationError) as exc_info:
            InvestigationCreate(title="")

        assert "String should have at least 1 character" in str(exc_info.value)

    def test_investigation_create_max_length(self):
        """
        Test that creating an Investigation with a title longer than the allowed maximum raises a ValidationError and includes the appropriate length constraint message.
        """
        # 201 characters should fail
        long_title = "A" * 201

        with pytest.raises(ValidationError) as exc_info:
            InvestigationCreate(title=long_title)

        assert "String should have at most 200 characters" in str(exc_info.value)

    def test_investigation_create_exactly_max_length(self):
        """
        Test that the `title` field accepts a string whose length is exactly the maximum allowed (200 characters), ensuring the boundary condition is handled correctly. The test creates an `InvestigationCreate` instance with a 200-character title and asserts that the stored title length matches the expected value.
        """
        max_title = "A" * 200
        schema = InvestigationCreate(title=max_title)

        assert len(schema.title) == 200

    def test_investigation_create_special_characters(self):
        """
        Test that InvestigationCreate.title correctly accepts a variety of special characters, including punctuation, symbols, HTML tags, and Unicode text. The test iterates over several example titles containing these characters, creates an InvestigationCreate instance for each, and asserts that the stored title matches the input value. This ensures that no validation errors are raised for allowed special characters.
        """
        special_titles = [
            "Investigation: Case #123",
            "Malware Analysis (2024-01-15)",
            "User@domain.com - Suspicious Activity",
            "Test <script>alert('xss')</script>",
            "Unicode: 日本語 中文 한글",
        ]

        for title in special_titles:
            schema = InvestigationCreate(title=title)
            assert schema.title == title

    def test_investigation_create_missing_title(self):
        """
        Test that creating an InvestigationCreate instance without a title raises a validation error.

        The test invokes `InvestigationCreate()` inside a `pytest.raises(ValidationError)` context manager and asserts that the resulting exception message contains the phrase "Field required", confirming that the `title` field is mandatory.
        """
        with pytest.raises(ValidationError) as exc_info:
            InvestigationCreate()

        assert "Field required" in str(exc_info.value)

    def test_investigation_create_extra_fields_ignored(self):
        """
        Tests that when creating an InvestigationCreate schema with additional unexpected fields, those fields are ignored: verifies the title is set correctly and the extra field does not become an attribute of the resulting model.
        """
        data = {"title": "Test", "extra_field": "should be ignored"}
        schema = InvestigationCreate(**data)

        assert schema.title == "Test"
        assert not hasattr(schema, "extra_field")


@pytest.mark.unit
class TestInvestigationReadSchema:
    """Test InvestigationRead schema validation."""

    def test_valid_investigation_read(self):
        """
        Test that an InvestigationRead instance correctly populates all fields when provided with valid data.

        The test creates a UUID and a UTC timestamp, assembles a dictionary containing every required attribute of the investigation schema, instantiates `InvestigationRead` with this data, and asserts that each model attribute matches the original input values. This ensures proper field mapping, type handling, and default behavior for a fully populated read schema.
        """
        inv_id = uuid.uuid4()
        created = datetime.utcnow()

        data = {
            "investigation_id": inv_id,
            "title": "Test Investigation",
            "owner_user_id": 1,
            "parsing_locked": False,
            "created_at": created,
        }
        schema = InvestigationRead(**data)

        assert schema.investigation_id == inv_id
        assert schema.title == "Test Investigation"
        assert schema.owner_user_id == 1
        assert schema.parsing_locked is False
        assert schema.created_at == created

    def test_investigation_read_nullable_owner(self):
        """
        Test that the `owner_user_id` field of an `InvestigationRead` instance can be set to `None` and is retained as `None` after model initialization. This verifies that the schema correctly handles nullable owner identifiers.
        """
        data = {
            "investigation_id": uuid.uuid4(),
            "title": "Orphaned Investigation",
            "owner_user_id": None,
            "created_at": datetime.utcnow(),
        }
        schema = InvestigationRead(**data)

        assert schema.owner_user_id is None

    def test_investigation_read_default_parsing_locked(self):
        """
        Test that the `parsing_locked` field defaults to `False` when an `InvestigationRead` instance is created without explicitly providing this value.
        """
        data = {"investigation_id": uuid.uuid4(), "title": "Test", "created_at": datetime.utcnow()}
        schema = InvestigationRead(**data)

        assert schema.parsing_locked is False

    def test_investigation_read_uuid_validation(self):
        """
        Test that the `InvestigationRead` schema enforces UUID validation on the `investigation_id` field. The test supplies a non-UUID string, expects a :class:`pydantic.ValidationError` to be raised, and verifies that the error message mentions “UUID”. This ensures that invalid identifiers are correctly rejected during model instantiation.
        """
        data = {"investigation_id": "not-a-uuid", "title": "Test", "created_at": datetime.utcnow()}

        with pytest.raises(ValidationError) as exc_info:
            InvestigationRead(**data)

        assert "UUID" in str(exc_info.value) or "uuid" in str(exc_info.value).lower()

    def test_investigation_read_datetime_validation(self):
        """
        Test that the `created_at` field of :class:`InvestigationRead` enforces proper datetime validation.

        The test constructs a payload with an invalid `created_at` string and attempts to instantiate the schema.
        It expects a :class:`pydantic.ValidationError` to be raised, confirming that non-datetime values are rejected.
        The assertion checks that the error message mentions a datetime issue (e.g., contains "datetime" or the generic Pydantic phrase "Input should be").
        """
        data = {"investigation_id": uuid.uuid4(), "title": "Test", "created_at": "not-a-datetime"}

        with pytest.raises(ValidationError) as exc_info:
            InvestigationRead(**data)

        assert "datetime" in str(exc_info.value).lower() or "Input should be" in str(exc_info.value)

    def test_investigation_read_from_orm(self):
        """
        Test that a Pydantic InvestigationRead schema can be instantiated from an ORM model instance using model_validate with from_attributes enabled, verifying that all fields (investigation_id, title, owner_user_id, parsing_locked) are correctly transferred.
        """
        from app.models.investigation import Investigation

        # Create ORM model with all required fields
        inv_id = uuid.uuid4()
        orm_model = Investigation(
            investigation_id=inv_id,
            title="ORM Test",
            owner_user_id=1,
            parsing_locked=False,
            created_at=datetime.utcnow(),
        )

        # Convert to schema using from_attributes
        schema = InvestigationRead.model_validate(orm_model, from_attributes=True)

        assert schema.investigation_id == inv_id
        assert schema.title == "ORM Test"
        assert schema.owner_user_id == 1
        assert schema.parsing_locked is False


@pytest.mark.unit
class TestInvestigationUpdateSchema:
    """Test InvestigationUpdate schema validation."""

    def test_valid_investigation_update(self):
        """
        Test that `InvestigationUpdate` correctly assigns a new title when provided.\n\nThis test creates an `InvestigationUpdate` instance with a `title` value of\n\"Updated Title\" and asserts that the resulting object's `title` attribute matches\nthe input, verifying that the schema validates and stores the updated title field.
        """
        data = {"title": "Updated Title"}
        schema = InvestigationUpdate(**data)

        assert schema.title == "Updated Title"

    def test_investigation_update_optional_title(self):
        """
        Test that the `title` field is optional for update operations, confirming that a newly instantiated `InvestigationUpdate` schema has its `title` attribute set to `None`.
        """
        schema = InvestigationUpdate()

        assert schema.title is None

    def test_investigation_update_min_length(self):
        """
        Test that providing an empty string for the optional `title` field raises a validation error indicating the minimum length requirement. The test ensures the schema enforces that, if supplied, `title` must contain at least one character.
        """
        with pytest.raises(ValidationError) as exc_info:
            InvestigationUpdate(title="")

        assert "String should have at least 1 character" in str(exc_info.value)

    def test_investigation_update_max_length(self):
        """
        Test that providing a title longer than the allowed maximum raises a ValidationError with an appropriate message indicating the length constraint.
        """
        long_title = "A" * 201

        with pytest.raises(ValidationError) as exc_info:
            InvestigationUpdate(title=long_title)

        assert "String should have at most 200 characters" in str(exc_info.value)

    def test_investigation_update_partial(self):
        """
        Test that partial updates only set provided fields and leave unspecified fields as None. This verifies that an InvestigationUpdate instance initialized with a subset of attributes (e.g., title) correctly reflects those values while all other attributes remain unset (None), and that creating an empty InvestigationUpdate results in all fields being None.
        """
        schema = InvestigationUpdate(title="New Title")

        # Only title should be set
        assert schema.title == "New Title"

        # Create empty update
        empty_schema = InvestigationUpdate()
        assert empty_schema.title is None


@pytest.mark.unit
class TestInvestigationSchemaEdgeCases:
    """Test edge cases for investigation schemas."""

    def test_unicode_in_title(self):
        """
        Test that Unicode characters are correctly handled in the title field of investigation schemas.

        This test iterates over a collection of titles containing various non-ASCII scripts and emojis. For each title it:
        - Instantiates an `InvestigationCreate` schema with the given title and asserts that the stored `title` matches the input.
        - Instantiates an `InvestigationUpdate` schema with the same title and asserts that its `title` also matches the input.

        The purpose is to verify that the Pydantic models accept and preserve Unicode characters without alteration.
        """
        unicode_titles = [
            "日本語のタイトル",
            "中文标题",
            "한국어 제목",
            "Русский заголовок",
            "العنوان العربي",
            "🔍 Investigation with emoji 🚨",
        ]

        for title in unicode_titles:
            create_schema = InvestigationCreate(title=title)
            assert create_schema.title == title

            update_schema = InvestigationUpdate(title=title)
            assert update_schema.title == title

    def test_whitespace_in_title(self):
        """
        Test handling of whitespace characters in investigation titles.

        This test verifies that the `InvestigationCreate` schema preserves leading and trailing spaces, as well as newline (`\n`) and tab (`\t`) characters within the provided title string. It ensures that no automatic stripping or normalization occurs during model instantiation.
        """
        # Leading/trailing whitespace
        schema = InvestigationCreate(title="  Whitespace Test  ")
        assert schema.title == "  Whitespace Test  "

        # Newlines and tabs
        schema = InvestigationCreate(title="Title\nWith\tWhitespace")
        assert schema.title == "Title\nWith\tWhitespace"

    def test_serialization(self):
        """
        Test that InvestigationRead schema instances serialize correctly to dictionary and JSON formats, verifying type correctness and inclusion of key fields.
        """
        inv_id = uuid.uuid4()
        created = datetime.utcnow()

        schema = InvestigationRead(
            investigation_id=inv_id, title="Test", owner_user_id=1, created_at=created
        )

        # Serialize to dict
        data = schema.model_dump()
        assert isinstance(data, dict)
        assert data["investigation_id"] == inv_id
        assert data["title"] == "Test"

        # Serialize to JSON
        json_str = schema.model_dump_json()
        assert isinstance(json_str, str)
        assert "Test" in json_str
