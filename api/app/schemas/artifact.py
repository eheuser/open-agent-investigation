from pydantic import BaseModel, Field, ConfigDict, model_validator
from datetime import datetime
from uuid import UUID
from typing import Optional, List, Any


class ArtifactMetadata(BaseModel):
    """Schema for artifact metadata (response)."""

    artifact_id: int
    investigation_id: UUID
    sha256: str  # hex string representation
    filename: str
    classification: int
    upload_ts: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def convert_sha256_to_hex(cls, data: Any) -> Any:
        """
        Convert SHA-256 values from binary form to a hexadecimal string prior to validation.

        Parameters
        ----------
        cls : type
            The Pydantic model class invoking this validator (unused but required by the signature).
        data : Any
            The input data to be validated, which may be a dictionary, an object with a `sha256` attribute,
            or any other type. If `data` contains a `sha256` field/value that is a `bytes`,
            `bytearray` or `memoryview` instance, it will be replaced with its hexadecimal string
            representation.

        Returns
        -------
        Any
            The original `data` with any binary `sha256` fields converted to hex strings. If the input
            does not contain a convertible `sha256` field, the data is returned unchanged.
        """
        if isinstance(data, dict):
            if "sha256" in data and isinstance(data["sha256"], (bytes, bytearray, memoryview)):
                data["sha256"] = bytes(data["sha256"]).hex()
        elif hasattr(data, "sha256") and isinstance(data.sha256, (bytes, bytearray, memoryview)):
            # Handle SQLAlchemy model objects
            data = {**data.__dict__}
            data["sha256"] = bytes(data["sha256"]).hex()
        return data


class ArtifactUploadResponse(BaseModel):
    """Schema for artifact upload response."""

    artifact: ArtifactMetadata
    artifact_id: int
    job_id: int
    message: str = "Uploaded successfully"


class ArtifactListResponse(BaseModel):
    """Schema for listing artifacts."""

    artifacts: List[ArtifactMetadata]
    total: int


__all__ = ["ArtifactMetadata", "ArtifactUploadResponse", "ArtifactListResponse"]
