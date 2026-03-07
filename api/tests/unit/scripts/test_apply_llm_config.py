"""
Unit tests for apply_llm_config.py script.

Tests the LLM configuration file parsing and application logic.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import sys

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "scripts"))

from apply_llm_config import (
    parse_bool,
    parse_int,
    parse_float,
    load_llm_config,
)


class TestParseBool:
    """Test boolean parsing from string."""
    
    def test_parse_true_values(self):
        """Test various true values."""
        assert parse_bool("true") is True
        assert parse_bool("TRUE") is True
        assert parse_bool("yes") is True
        assert parse_bool("YES") is True
        assert parse_bool("1") is True
        assert parse_bool("on") is True
        assert parse_bool("ON") is True
    
    def test_parse_false_values(self):
        """Test various false values."""
        assert parse_bool("false") is False
        assert parse_bool("FALSE") is False
        assert parse_bool("no") is False
        assert parse_bool("NO") is False
        assert parse_bool("0") is False
        assert parse_bool("off") is False
        assert parse_bool("OFF") is False
    
    def test_parse_empty_value(self):
        """Test empty value returns default."""
        assert parse_bool("", default=False) is False
        assert parse_bool("", default=True) is True
        assert parse_bool(None, default=True) is True
    
    def test_parse_invalid_value(self):
        """Test invalid value returns default."""
        assert parse_bool("invalid", default=False) is False


class TestParseInt:
    """Test integer parsing from string."""
    
    def test_parse_valid_int(self):
        """Test valid integer values."""
        assert parse_int("42") == 42
        assert parse_int("0") == 0
        assert parse_int("-10") == -10
        assert parse_int("8192") == 8192
    
    def test_parse_empty_value(self):
        """Test empty value returns default."""
        assert parse_int("", default=100) == 100
        assert parse_int(None, default=200) == 200
    
    def test_parse_invalid_value(self):
        """Test invalid value returns default."""
        assert parse_int("not_a_number", default=50) == 50
        assert parse_int("3.14", default=10) == 10


class TestParseFloat:
    """Test float parsing from string."""
    
    def test_parse_valid_float(self):
        """Test valid float values."""
        assert parse_float("0.7") == 0.7
        assert parse_float("1.5") == 1.5
        assert parse_float("0.0") == 0.0
        assert parse_float("2.0") == 2.0
    
    def test_parse_empty_value(self):
        """Test empty value returns default."""
        assert parse_float("", default=0.5) == 0.5
        assert parse_float(None, default=1.0) == 1.0
    
    def test_parse_invalid_value(self):
        """Test invalid value returns default."""
        assert parse_float("not_a_number", default=0.7) == 0.7


class TestLoadLLMConfig:
    """Test LLM configuration file loading."""
    
    def test_load_valid_config(self, tmp_path):
        """Test loading a valid configuration file."""
        config_file = tmp_path / ".llm_config.env"
        config_file.write_text("""
# Test configuration
LLM_PROVIDER_NAME=openai
LLM_API_ENDPOINT=https://api.openai.com/v1/chat/completions
LLM_API_KEY=sk-test-key
LLM_MODEL_NAME=gpt-4o-mini
LLM_MAX_CONTEXT_LENGTH=128000
LLM_TEMPERATURE=0.70

# Embedding configuration
EMBEDDING_PROVIDER=openai
EMBEDDING_API_URL=https://api.openai.com/v1/embeddings
EMBEDDING_API_KEY=sk-test-key
EMBEDDING_MODEL_NAME=text-embedding-3-small
""")
        
        config = load_llm_config(config_file)
        
        assert config is not None
        assert config["provider_name"] == "openai"
        assert config["api_endpoint"] == "https://api.openai.com/v1/chat/completions"
        assert config["api_key"] == "sk-test-key"
        assert config["model_name"] == "gpt-4o-mini"
        assert config["max_context_length"] == 128000
        assert config["temperature"] == 0.70
        assert config["embedding_provider"] == "openai"
        assert config["embedding_model_name"] == "text-embedding-3-small"
    
    def test_load_config_with_quotes(self, tmp_path):
        """Test loading configuration with quoted values."""
        config_file = tmp_path / ".llm_config.env"
        config_file.write_text("""
LLM_PROVIDER_NAME="openai"
LLM_API_ENDPOINT='https://api.openai.com/v1/chat/completions'
LLM_MODEL_NAME=gpt-4o-mini
""")
        
        config = load_llm_config(config_file)
        
        assert config is not None
        assert config["provider_name"] == "openai"
        assert config["api_endpoint"] == "https://api.openai.com/v1/chat/completions"
    
    def test_load_config_missing_required_field(self, tmp_path):
        """Test loading configuration with missing required field."""
        config_file = tmp_path / ".llm_config.env"
        config_file.write_text("""
LLM_PROVIDER_NAME=openai
LLM_API_KEY=sk-test-key
# Missing LLM_API_ENDPOINT and LLM_MODEL_NAME
""")
        
        config = load_llm_config(config_file)
        
        # Should return None due to missing required fields
        assert config is None
    
    def test_load_config_with_defaults(self, tmp_path):
        """Test loading configuration with default values."""
        config_file = tmp_path / ".llm_config.env"
        config_file.write_text("""
LLM_PROVIDER_NAME=ollama
LLM_API_ENDPOINT=http://localhost:11434/v1/chat/completions
LLM_MODEL_NAME=llama3.1:70b
# No API key, context length, or temperature (should use defaults)
""")
        
        config = load_llm_config(config_file)
        
        assert config is not None
        assert config["api_key"] is None  # Default for local Ollama
        assert config["max_context_length"] == 8192  # Default
        assert config["temperature"] == 0.70  # Default
    
    def test_load_config_file_not_found(self, tmp_path):
        """Test loading non-existent configuration file."""
        config_file = tmp_path / "nonexistent.env"
        
        config = load_llm_config(config_file)
        
        assert config is None
    
    def test_load_config_with_comments(self, tmp_path):
        """Test loading configuration with comments and empty lines."""
        config_file = tmp_path / ".llm_config.env"
        config_file.write_text("""
# This is a comment
LLM_PROVIDER_NAME=openai

# Another comment
LLM_API_ENDPOINT=https://api.openai.com/v1/chat/completions

LLM_MODEL_NAME=gpt-4o-mini
""")
        
        config = load_llm_config(config_file)
        
        assert config is not None
        assert config["provider_name"] == "openai"
    
    def test_load_config_with_advanced_params(self, tmp_path):
        """Test loading configuration with advanced parameters."""
        config_file = tmp_path / ".llm_config.env"
        config_file.write_text("""
LLM_PROVIDER_NAME=openai
LLM_API_ENDPOINT=https://api.openai.com/v1/chat/completions
LLM_MODEL_NAME=gpt-4o-mini
LLM_TOP_P=0.95
LLM_TOP_K=50
LLM_MIN_P=0.05
LLM_TIMEOUT=600
LLM_ALLOW_CONCURRENT=true
""")
        
        config = load_llm_config(config_file)
        
        assert config is not None
        assert config["top_p"] == 0.95
        assert config["top_k"] == 50
        assert config["min_p"] == 0.05
        assert config["timeout"] == 600
        assert config["allow_concurrent_llm_calls"] is True


@pytest.mark.asyncio
class TestApplyConfig:
    """Test configuration application to database."""
    
    # Note: Full integration tests would require database setup
    # These tests would mock the database interactions
    
    async def test_apply_config_creates_new(self):
        """Test applying configuration when none exists."""
        # This would require mocking AsyncSession and CRUD functions
        # Implementation depends on test infrastructure
        pass
    
    async def test_apply_config_updates_existing(self):
        """Test applying configuration when one exists."""
        # This would require mocking AsyncSession and CRUD functions
        # Implementation depends on test infrastructure
        pass
