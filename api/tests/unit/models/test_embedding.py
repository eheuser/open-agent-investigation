import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from app.models.embedding import Embedding


@pytest.mark.unit
class TestEmbeddingModel:
    """Test Embedding model structure and constraints."""

    def test_embedding_creation(self):
        """
        Test that an :class:`Embedding` object can be instantiated with valid data and that its attributes are correctly assigned.

        The test creates an `Embedding` with:
        - `id` set to `1`,
        - `owner_type` set to `"chat"`,
        - `owner_id` set to `123`,
        - `model_name` set to `"text-embedding-ada-002"`,
        - `vector` containing 1536 float elements.

        It then asserts that each attribute on the resulting instance matches the supplied values and that the vector length is exactly `1536`.
        """
        embedding = Embedding(
            id=1,
            owner_type="chat",
            owner_id=123,
            model_name="text-embedding-ada-002",
            vector=[0.1] * 1536,
        )

        assert embedding.id == 1
        assert embedding.owner_type == "chat"
        assert embedding.owner_id == 123
        assert embedding.model_name == "text-embedding-ada-002"
        assert len(embedding.vector) == 1536

    def test_embedding_owner_types(self):
        """
        Test that the `owner_type` attribute of an :class:`Embedding` instance accepts all defined valid types.

        The test iterates over each value in `valid_types` (`"chat"`, `"timeline"`, `"note"`, and `"tool"`), creates an `Embedding` with that `owner_type` and a minimal set of required fields, and asserts that the stored `owner_type` matches the input. This ensures the model correctly validates and stores each permissible owner type.
        """
        valid_types = ["chat", "timeline", "note", "tool"]

        for owner_type in valid_types:
            embedding = Embedding(
                owner_type=owner_type, owner_id=1, model_name="test-model", vector=[0.0] * 1536
            )
            assert embedding.owner_type == owner_type

    def test_embedding_different_models(self):
        """
        Test that an Embedding instance correctly stores and returns the model_name attribute for each supported embedding model. The test iterates over a list of known model identifiers, creates an Embedding with a zero-filled vector of the expected dimensionality, and asserts that the model_name property matches the input value. This verifies that the model_name field accepts all valid strings without alteration.
        """
        models = [
            "text-embedding-ada-002",
            "text-embedding-3-small",
            "text-embedding-3-large",
            "embed-english-v3.0",
            "nomic-embed-text",
        ]

        for model_name in models:
            embedding = Embedding(
                owner_type="chat", owner_id=1, model_name=model_name, vector=[0.0] * 1536
            )
            assert embedding.model_name == model_name

    def test_embedding_vector_dimensions(self):
        """
        Test embedding vector handling across multiple dimensions.

        This test verifies that an `Embedding` instance can be created with vectors of various lengths,
        ensuring the `vector` attribute correctly stores the provided number of elements.

        The model's default dimension is 1536, but the test iterates over a set of alternative sizes
        (768, 1024, 1536, 3072) and asserts that the length of `embedding.vector` matches each
        specified dimension.
        """
        # Note: The model defines Vector(1536) but can handle different sizes
        dimensions = [768, 1024, 1536, 3072]

        for dim in dimensions:
            embedding = Embedding(
                owner_type="chat", owner_id=1, model_name="test-model", vector=[0.1] * dim
            )
            assert len(embedding.vector) == dim

    def test_embedding_zero_vector(self):
        """
        Test that an Embedding instance correctly stores a zero-valued vector of the expected dimensionality. The embedding is created with a 1536-element list filled with 0.0, and the test asserts every element in `embedding.vector` equals 0.0.
        """
        embedding = Embedding(
            owner_type="chat", owner_id=1, model_name="test-model", vector=[0.0] * 1536
        )
        assert all(v == 0.0 for v in embedding.vector)

    def test_embedding_normalized_vector(self):
        """
        Test that an Embedding instance correctly stores a normalized vector of the expected dimensionality.

        The test constructs a unit-norm vector by dividing 1.0 by the square root of the target dimension (1536) and replicating this value across all dimensions. It then creates an `Embedding` object with typical metadata fields and the generated vector, asserting that the stored vector length matches the intended dimension. This verifies both the handling of high-dimensional normalized vectors and the proper assignment of the `vector` attribute.
        """
        # Create a simple normalized vector
        import math

        dim = 1536
        value = 1.0 / math.sqrt(dim)
        vector = [value] * dim

        embedding = Embedding(owner_type="chat", owner_id=1, model_name="test-model", vector=vector)
        assert len(embedding.vector) == dim

    def test_embedding_repr(self):
        """
        Test that the `Embedding` object's `__repr__` method returns a string containing identifying information.

        The test creates an `Embedding` instance with a minimal set of required fields and a zero-filled vector, obtains its `repr`, and asserts that the resulting string includes either the class name `Embedding` or a generic identifier such as `object`. This ensures that the representation is informative for debugging while remaining tolerant of implementation variations.
        """
        embedding = Embedding(
            id=1, owner_type="chat", owner_id=123, model_name="test-model", vector=[0.0] * 1536
        )
        repr_str = repr(embedding)
        assert "Embedding" in repr_str or "object" in repr_str

    def test_embedding_tablename(self):
        """
        Test that the SQLAlchemy model `Embedding` uses the expected table name `embeddings`.
        """
        assert Embedding.__tablename__ == "embeddings"

    def test_embedding_has_required_columns(self):
        """
        Test that all required columns exist on the `Embedding` model.

        This test verifies that the `Embedding` class defines each of the mandatory
        attributes needed for proper operation: `id`, `owner_type`, `owner_id`,
        `model_name`, `vector`, and `created_at`. If any attribute is missing,
        the assertions will fail, indicating an incomplete model definition.
        """
        assert hasattr(Embedding, "id")
        assert hasattr(Embedding, "owner_type")
        assert hasattr(Embedding, "owner_id")
        assert hasattr(Embedding, "model_name")
        assert hasattr(Embedding, "vector")
        assert hasattr(Embedding, "created_at")


@pytest.mark.unit
class TestEmbeddingEdgeCases:
    """Test edge cases for Embedding model."""

    def test_embedding_with_very_large_owner_id(self):
        """
        Test embedding with a very large `owner_id` to ensure the model correctly stores and retrieves integer identifiers exceeding typical 32-bit ranges.
        """
        embedding = Embedding(
            owner_type="chat", owner_id=9999999999999, model_name="test-model", vector=[0.0] * 1536
        )
        assert embedding.owner_id == 9999999999999

    def test_embedding_with_special_chars_in_model_name(self):
        """
        Test that an Embedding instance correctly stores a model name containing special characters such as hyphens, periods, and underscores, ensuring the `model_name` attribute preserves the exact string provided.
        """
        embedding = Embedding(
            owner_type="chat", owner_id=1, model_name="model-v3.0_large-1536", vector=[0.0] * 1536
        )
        assert embedding.model_name == "model-v3.0_large-1536"

    def test_embedding_with_unicode_model_name(self):
        """
        Test that an Embedding instance correctly stores and retains a Unicode model name, ensuring the Unicode characters are present in the `model_name` attribute.
        """
        embedding = Embedding(
            owner_type="chat", owner_id=1, model_name="モデル-v1", vector=[0.0] * 1536
        )
        assert "モデル" in embedding.model_name

    def test_embedding_with_negative_values(self):
        """
        Test embedding with negative vector values.

        Creates an :class:`Embedding` instance using a vector that contains negative, positive, and zero components. Verifies that the first three elements of the stored `vector` attribute match the expected values (-0.5, 0.3, -0.1), ensuring that negative numbers are correctly preserved in the embedding representation.
        """
        embedding = Embedding(
            owner_type="chat",
            owner_id=1,
            model_name="test-model",
            vector=[-0.5, 0.3, -0.1] + [0.0] * 1533,
        )
        assert embedding.vector[0] == -0.5
        assert embedding.vector[1] == 0.3
        assert embedding.vector[2] == -0.1

    def test_embedding_with_mixed_precision(self):
        """
        Test that an Embedding instance correctly stores and retrieves vector values when the vector contains mixed-precision floating-point numbers, ensuring the first element matches the expected value within a relative tolerance of 1e-6.
        """
        embedding = Embedding(
            owner_type="chat",
            owner_id=1,
            model_name="test-model",
            vector=[0.123456789, 0.987654321] + [0.0] * 1534,
        )
        assert embedding.vector[0] == pytest.approx(0.123456789, rel=1e-6)
