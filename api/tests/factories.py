import factory  # type: ignore[import]
from factory import fuzzy  # type: ignore[import]
from datetime import datetime, timedelta
import uuid
import json

from app.models.user import User
from app.models.investigation import Investigation
from app.models.artifact import Artifact, ArtifactClassification
from app.models.llm_config import LLMProviderConfig
from app.models.chat_history import ChatMessage
from app.auth import hash_password


class UserFactory(factory.Factory):
    """Factory for creating User instances."""
    
    class Meta:
        model = User
    
    user_id = factory.Sequence(lambda n: n + 1)
    username = factory.Sequence(lambda n: f"user{n}")
    password_hash = factory.LazyFunction(lambda: hash_password("password123"))
    role = 0  # Regular user
    created_at = factory.LazyFunction(datetime.utcnow)


class AdminUserFactory(UserFactory):
    """Factory for creating admin User instances."""
    
    username = factory.Sequence(lambda n: f"admin{n}")
    role = 1  # Admin


class InvestigationFactory(factory.Factory):
    """Factory for creating Investigation instances."""
    
    class Meta:
        model = Investigation
    
    investigation_id = factory.LazyFunction(uuid.uuid4)
    title = factory.Faker("sentence", nb_words=4)
    owner_user_id = None  # Must be set explicitly
    created_at = factory.LazyFunction(datetime.utcnow)


class ArtifactFactory(factory.Factory):
    """Factory for creating Artifact instances."""
    
    class Meta:
        model = Artifact
    
    artifact_id = factory.Sequence(lambda n: n + 1)
    investigation_id = None  # Must be set explicitly
    sha256 = factory.LazyFunction(lambda: b'\x00' * 32)  # Dummy SHA-256
    filename = factory.Faker("file_name")
    classification = ArtifactClassification.LOG_FILE
    blob = b"dummy artifact content"
    upload_ts = factory.LazyFunction(datetime.utcnow)


class EVTXArtifactFactory(ArtifactFactory):
    """Factory for EVTX artifact instances."""
    
    filename = factory.Sequence(lambda n: f"Security_{n}.evtx")
    classification = ArtifactClassification.LOG_FILE


class RegistryArtifactFactory(ArtifactFactory):
    """Factory for Registry hive artifact instances."""
    
    filename = factory.Sequence(lambda n: f"SYSTEM_{n}")
    classification = ArtifactClassification.SYSTEM_HIVE


class MFTArtifactFactory(ArtifactFactory):
    """Factory for MFT artifact instances."""
    
    filename = "$MFT"
    classification = ArtifactClassification.BINARY


class LLMConfigFactory(factory.Factory):
    """Factory for creating LLMProviderConfig instances."""
    
    class Meta:
        model = LLMProviderConfig
    
    config_id = factory.Sequence(lambda n: n + 1)
    user_id = None  # Must be set explicitly
    provider_name = "openai"
    api_endpoint = "https://api.openai.com/v1/chat/completions"
    api_key = "sk-test-key-1234567890"
    model_name = "gpt-4"
    max_context_length = 8192
    temperature = 0.7
    is_active = True
    created_at = factory.LazyFunction(datetime.utcnow)
    updated_at = factory.LazyFunction(datetime.utcnow)


class OllamaConfigFactory(LLMConfigFactory):
    """Factory for Ollama LLM configuration."""
    
    provider_name = "ollama"
    api_endpoint = "http://localhost:11434/v1/chat/completions"
    api_key = None
    model_name = "llama3"
    max_context_length = 4096


class ChatMessageFactory(factory.Factory):
    """Factory for creating ChatMessage instances."""
    
    class Meta:
        model = ChatMessage
    
    message_id = factory.Sequence(lambda n: n + 1)
    investigation_id = None  # Must be set explicitly
    user_id = None  # Must be set explicitly
    role = "user"
    content = factory.Faker("sentence")
    name = None
    tool_calls = None
    tool_call_id = None
    metadata = factory.LazyFunction(lambda: {})
    include_in_llm_context = True
    visible_in_ui = True
    created_at = factory.LazyFunction(datetime.utcnow)


class UserMessageFactory(ChatMessageFactory):
    """Factory for user chat messages."""
    
    role = "user"
    content = factory.Faker("sentence", nb_words=10)


class AssistantMessageFactory(ChatMessageFactory):
    """Factory for assistant chat messages."""
    
    role = "assistant"
    content = factory.Faker("paragraph")
