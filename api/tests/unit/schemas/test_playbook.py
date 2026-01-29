# api/tests/unit/schemas/test_playbook.py
import pytest
from datetime import datetime
from pydantic import ValidationError

from app.schemas.playbook import (
    PlaybookBase,
    PlaybookCreate,
    PlaybookUpdate,
    PlaybookResponse,
    BasePlaybookResponse,
    PlaybookListResponse,
    InvestigationPlaybookCreate,
    InvestigationPlaybookResponse,
)


def test_playbook_base_valid():
    """Test valid PlaybookBase schema."""
    data = {
        "name": "test_playbook",
        "description": "Test description",
        "playbook": "## Test Playbook\n\n### Steps\n1. Step 1",
    }
    
    playbook = PlaybookBase(**data)
    
    assert playbook.name == "test_playbook"
    assert playbook.description == "Test description"
    assert "## Test Playbook" in playbook.playbook


def test_playbook_base_empty_name():
    """Test that empty name is rejected."""
    data = {
        "name": "",
        "description": "Test description",
        "playbook": "Content",
    }
    
    with pytest.raises(ValidationError) as exc_info:
        PlaybookBase(**data)
    
    errors = exc_info.value.errors()
    assert any("name" in str(e["loc"]) for e in errors)


def test_playbook_base_empty_description():
    """Test that empty description is rejected."""
    data = {
        "name": "test",
        "description": "",
        "playbook": "Content",
    }
    
    with pytest.raises(ValidationError) as exc_info:
        PlaybookBase(**data)
    
    errors = exc_info.value.errors()
    assert any("description" in str(e["loc"]) for e in errors)


def test_playbook_base_empty_playbook():
    """Test that empty playbook content is rejected."""
    data = {
        "name": "test",
        "description": "Test description",
        "playbook": "",
    }
    
    with pytest.raises(ValidationError) as exc_info:
        PlaybookBase(**data)
    
    errors = exc_info.value.errors()
    assert any("playbook" in str(e["loc"]) for e in errors)


def test_playbook_create_defaults():
    """Test PlaybookCreate with default values."""
    data = {
        "name": "test",
        "description": "Test description",
        "playbook": "Content",
    }
    
    playbook = PlaybookCreate(**data)
    
    assert playbook.is_enabled == True  # Default value


def test_playbook_create_custom_enabled():
    """Test PlaybookCreate with custom is_enabled value."""
    data = {
        "name": "test",
        "description": "Test description",
        "playbook": "Content",
        "is_enabled": False,
    }
    
    playbook = PlaybookCreate(**data)
    
    assert playbook.is_enabled == False


def test_playbook_update_partial():
    """Test PlaybookUpdate with partial data."""
    data = {
        "description": "Updated description",
    }
    
    playbook = PlaybookUpdate(**data)
    
    assert playbook.description == "Updated description"
    assert playbook.name is None
    assert playbook.playbook is None
    assert playbook.is_enabled is None


def test_playbook_update_all_fields():
    """Test PlaybookUpdate with all fields."""
    data = {
        "name": "updated_name",
        "description": "Updated description",
        "playbook": "Updated content",
        "is_enabled": False,
    }
    
    playbook = PlaybookUpdate(**data)
    
    assert playbook.name == "updated_name"
    assert playbook.description == "Updated description"
    assert playbook.playbook == "Updated content"
    assert playbook.is_enabled == False


def test_playbook_response():
    """Test PlaybookResponse schema."""
    data = {
        "playbook_id": 1,
        "user_id": 1,
        "name": "test",
        "description": "Test description",
        "playbook": "Content",
        "is_enabled": True,
        "is_base": False,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    
    playbook = PlaybookResponse(**data)
    
    assert playbook.playbook_id == 1
    assert playbook.is_base == False


def test_base_playbook_response():
    """Test BasePlaybookResponse schema."""
    data = {
        "name": "lateral_movement",
        "description": "Lateral movement detection",
        "playbook": "## Playbook\n\nContent",
    }
    
    playbook = BasePlaybookResponse(**data)
    
    assert playbook.name == "lateral_movement"
    assert playbook.is_base == True  # Default value


def test_playbook_list_response():
    """Test PlaybookListResponse schema."""
    data = {
        "base_playbooks": [
            {
                "name": "base1",
                "description": "Base playbook 1",
                "playbook": "Content 1",
                "is_base": True,
            }
        ],
        "user_playbooks": [
            {
                "playbook_id": 1,
                "user_id": 1,
                "name": "user1",
                "description": "User playbook 1",
                "playbook": "Content 1",
                "is_enabled": True,
                "is_base": False,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
        ],
        "total": 2,
    }
    
    response = PlaybookListResponse(**data)
    
    assert len(response.base_playbooks) == 1
    assert len(response.user_playbooks) == 1
    assert response.total == 2


def test_investigation_playbook_create():
    """Test InvestigationPlaybookCreate schema."""
    data = {
        "playbook_id": 1,
        "is_enabled": True,
    }
    
    inv_playbook = InvestigationPlaybookCreate(**data)
    
    assert inv_playbook.playbook_id == 1
    assert inv_playbook.is_enabled is True


def test_investigation_playbook_create_default():
    """Test InvestigationPlaybookCreate with default is_enabled."""
    data = {
        "playbook_id": 1,
    }
    
    inv_playbook = InvestigationPlaybookCreate(**data)
    
    assert inv_playbook.is_enabled == True  # Default


def test_investigation_playbook_response():
    """Test InvestigationPlaybookResponse schema."""
    data = {
        "id": 1,
        "investigation_id": "123e4567-e89b-12d3-a456-426614174000",
        "playbook_id": 1,
        "is_enabled": True,
        "enabled_at": datetime.now(),
        "playbook": {
            "playbook_id": 1,
            "user_id": 1,
            "name": "test",
            "description": "Test",
            "playbook": "Content",
            "is_enabled": True,
            "is_base": False,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        },
    }
    
    response = InvestigationPlaybookResponse(**data)
    
    assert response.id == 1
    assert response.investigation_id == "123e4567-e89b-12d3-a456-426614174000"
    assert response.playbook.name == "test"


def test_playbook_name_max_length():
    """Test that playbook name respects max length."""
    data = {
        "name": "a" * 201,  # Over 200 character limit
        "description": "Test",
        "playbook": "Content",
    }
    
    with pytest.raises(ValidationError) as exc_info:
        PlaybookBase(**data)
    
    errors = exc_info.value.errors()
    assert any("name" in str(e["loc"]) for e in errors)


def test_playbook_description_max_length():
    """Test that playbook description respects max length."""
    data = {
        "name": "test",
        "description": "a" * 1001,  # Over 1000 character limit
        "playbook": "Content",
    }
    
    with pytest.raises(ValidationError) as exc_info:
        PlaybookBase(**data)
    
    errors = exc_info.value.errors()
    assert any("description" in str(e["loc"]) for e in errors)
