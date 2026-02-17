from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
import aiohttp
import asyncio

from ..deps import get_db, get_current_user
from typing import cast
from ..models.user import User
from ..utils.security import validate_url_safe
from ..models.llm_config import LLMProviderConfig
from ..schemas.llm_config import (
    LLMConfigCreate,
    LLMConfigUpdate,
    LLMConfigRead,
    LLMConfigReadMasked,
)
from ..crud import llm_config as crud


router = APIRouter()


# Test request schemas
class LLMTestRequest(BaseModel):
    """Schema for testing LLM configuration."""
    provider_name: str
    api_endpoint: str
    api_key: Optional[str] = None
    model_name: str
    max_context_length: int = 8192
    temperature: float = 0.7
    timeout: int = 30


class EmbeddingTestRequest(BaseModel):
    """Schema for testing embedding configuration."""
    embedding_provider: str
    embedding_api_url: str
    embedding_api_key: Optional[str] = None
    embedding_model_name: str


def _to_masked_response(config: LLMProviderConfig) -> LLMConfigReadMasked:
    """
    Convert an :class:`LLMProviderConfig` ORM instance into a masked read-only response model.

    Parameters
    ----------
    config: LLMProviderConfig
        The SQLAlchemy-mapped configuration object to be transformed.

    Returns
    -------
    LLMConfigReadMasked
        A data transfer object containing the same field values as *config*, with numeric fields explicitly cast to `float` and optional fields set to `None` when absent. The function uses :func:`getattr` to safely access attributes on mapped objects, avoiding type-checking issues.
    """
    return LLMConfigReadMasked(
        config_id=getattr(config, "config_id"),
        user_id=getattr(config, "user_id"),
        provider_name=getattr(config, "provider_name"),
        api_endpoint=getattr(config, "api_endpoint"),
        model_name=getattr(config, "model_name"),
        max_context_length=getattr(config, "max_context_length"),
        temperature=float(getattr(config, "temperature")),
        top_p=float(getattr(config, "top_p")) if getattr(config, "top_p") is not None else None,
        top_k=getattr(config, "top_k"),
        min_p=float(getattr(config, "min_p")) if getattr(config, "min_p") is not None else None,
        timeout=getattr(config, "timeout"),
        is_active=getattr(config, "is_active"),
        allow_concurrent_llm_calls=getattr(config, "allow_concurrent_llm_calls", False),
        # Embedding configuration
        embedding_provider=getattr(config, "embedding_provider", None),
        embedding_api_url=getattr(config, "embedding_api_url", None),
        embedding_model_name=getattr(config, "embedding_model_name", None),
        embedding_max_context_length=getattr(config, "embedding_max_context_length", None),
        reranker_model_name=getattr(config, "reranker_model_name", None),
        reranker_max_context_length=getattr(config, "reranker_max_context_length", None),
        allow_concurrent_embedding_calls=getattr(config, "allow_concurrent_embedding_calls", False),
        created_at=getattr(config, "created_at"),
        updated_at=getattr(config, "updated_at"),
    )


@router.post("/", response_model=LLMConfigReadMasked, status_code=status.HTTP_201_CREATED)
async def create_config(
    payload: LLMConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new LLM provider configuration for the authenticated user.

    Parameters
    ----------
    payload: LLMConfigCreate
        The request body containing all required fields for the configuration,
        including provider details, API credentials, model settings, and optional
        embedding parameters.
    db: AsyncSession, optional
        Database session injected by FastAPI's dependency system. Used to perform
        persistence operations.
    current_user: User, optional
        The authenticated user obtained via dependency injection. The new
        configuration will be associated with this user's identifier.

    Returns
    -------
    MaskedLLMConfigResponse
        A masked representation of the created LLM provider configuration,
        suitable for returning to clients (sensitive fields such as API keys are
        omitted or redacted).

    Raises
    ------
    HTTPException
        If the creation fails due to validation errors, duplicate configurations,
        or database issues. The exception will contain an appropriate HTTP status
        code and detail message.
    """

    config = await crud.create_llm_config(
        db=db,
        user_id=current_user.user_id,
        provider_name=payload.provider_name,
        api_endpoint=payload.api_endpoint,
        api_key=payload.api_key,
        model_name=payload.model_name,
        max_context_length=payload.max_context_length,
        temperature=payload.temperature,
        top_p=payload.top_p,
        top_k=payload.top_k,
        min_p=payload.min_p,
        timeout=payload.timeout,
        is_active=payload.is_active,
        allow_concurrent_llm_calls=payload.allow_concurrent_llm_calls,
        # Embedding configuration
        embedding_provider=payload.embedding_provider,
        embedding_api_url=payload.embedding_api_url,
        embedding_api_key=payload.embedding_api_key,
        embedding_model_name=payload.embedding_model_name,
        embedding_max_context_length=payload.embedding_max_context_length,
        reranker_model_name=payload.reranker_model_name,
        reranker_max_context_length=payload.reranker_max_context_length,
        allow_concurrent_embedding_calls=payload.allow_concurrent_embedding_calls,
    )

    return _to_masked_response(config)


@router.get("/", response_model=List[LLMConfigReadMasked])
async def list_configs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all masked LLM provider configurations owned by the authenticated user.\n\nParameters\n----------\ndb : AsyncSession\n    Database session injected via FastAPI's dependency system.\ncurrent_user : User\n    The currently authenticated user, provided by `get_current_user`.\n\nReturns\n-------\nlist[MaskedLLMConfigResponse]\n    A list of masked configuration objects suitable for API response. Each item is the result of converting a stored LLM configuration to its masked representation.\n\nRaises\n------\nHTTPException\n    Propagated from underlying CRUD operations if database access fails or the user is unauthorized.
    """

    configs = await crud.list_llm_configs(db, current_user.user_id)
    return [_to_masked_response(c) for c in configs]


@router.get("/active", response_model=LLMConfigReadMasked)
async def get_active_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve the active LLM configuration associated with the authenticated user.\n\nParameters\n----------\ndb : AsyncSession\n    Database session provided by FastAPI's dependency injection.\ncurrent_user : User\n    The currently authenticated user, obtained via the `get_current_user` dependency.\n\nReturns\n-------\nMaskedLLMConfigResponse\n    A masked representation of the active LLM configuration suitable for client consumption.\n\nRaises\n------\nHTTPException\n    If no active LLM configuration exists for the user, a 404 Not Found error is raised with a descriptive message.
    """

    config = await crud.get_active_llm_config(db, current_user.user_id)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active LLM configuration found. Please create one.",
        )

    return _to_masked_response(config)


@router.get("/{config_id}", response_model=LLMConfigReadMasked)
async def get_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve a specific masked LLM provider configuration by its database identifier.

    Args:
        config_id (int): The unique identifier of the LLM configuration to retrieve.
        db (AsyncSession, optional): An asynchronous SQLAlchemy session provided via FastAPI dependency injection.
        current_user (User, optional): The authenticated user object obtained from the security dependency.

    Returns:
        MaskedLLMConfigResponse: A Pydantic model representing the requested configuration with sensitive fields masked.

    Raises:
        HTTPException:
            - 404 NOT FOUND if no configuration exists with the given `config_id`.
            - 403 FORBIDDEN if the authenticated user is neither the owner of the configuration nor an administrator (role != 1).
    """

    config = await crud.get_llm_config_by_id(db, config_id)

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM configuration not found",
        )

    # Verify ownership
    if (
        getattr(config, "user_id") != getattr(current_user, "user_id")
        and getattr(current_user, "role") != 1
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this configuration",
        )

    return _to_masked_response(config)


@router.patch("/{config_id}", response_model=LLMConfigReadMasked)
async def update_config(
    config_id: int,
    payload: LLMConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update an existing LLM configuration after verifying ownership and permissions.

    Args:
        config_id: The unique identifier of the LLM configuration to update.
        payload: An instance of `LLMConfigUpdate` containing the fields to be modified. Only set fields are applied.
        db: An asynchronous SQLAlchemy session provided by FastAPI's dependency injection.
        current_user: The authenticated user object obtained from the request context.

    Returns:
        A masked representation of the updated LLM configuration, suitable for returning to the client.

    Raises:
        HTTPException:
            - 404 NOT FOUND if no configuration with `config_id` exists.
            - 403 FORBIDDEN if the current user does not own the configuration and is not an admin (role != 1).
            - 500 INTERNAL SERVER ERROR if the update operation fails unexpectedly.
    """

    # Verify ownership
    existing = await crud.get_llm_config_by_id(db, config_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM configuration not found",
        )

    if (
        getattr(existing, "user_id") != getattr(current_user, "user_id")
        and getattr(current_user, "role") != 1
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this configuration",
        )

    updated_config = await crud.update_llm_config(
        db=db,
        config_id=config_id,
        **payload.model_dump(exclude_unset=True),
    )

    if not updated_config:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update configuration",
        )

    return _to_masked_response(updated_config)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a masked LLM provider configuration.

    Parameters
    ----------
    config_id: int
        The unique identifier of the configuration to delete.
    db: AsyncSession, optional
        Asynchronous SQLAlchemy session provided by FastAPI's dependency injection.
    current_user: User, optional
        Authenticated user object obtained from the request context.

    Raises
    ------
    HTTPException
        - 404 NOT FOUND if no configuration with `config_id` exists.
        - 403 FORBIDDEN if the authenticated user is neither the owner of the configuration nor an admin (role != 1).
    """

    # Verify ownership
    existing = await crud.get_llm_config_by_id(db, config_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM configuration not found",
        )

    if (
        getattr(existing, "user_id") != getattr(current_user, "user_id")
        and getattr(current_user, "role") != 1
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this configuration",
        )

    await crud.delete_llm_config(db, config_id)


@router.post("/test")
async def test_llm_config(
    payload: LLMTestRequest,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Test an LLM configuration by sending a minimal test query.
    
    This endpoint validates that the LLM provider is accessible and responding correctly
    without saving the configuration to the database.
    
    Args:
        payload: LLM configuration to test
        current_user: Authenticated user (required for authorization)
    
    Returns:
        Dict with 'success' boolean, 'message' string, and optional 'error' string
    """
    # Validate URL to prevent SSRF attacks
    try:
        validate_url_safe(payload.api_endpoint)
    except HTTPException as e:
        return {
            "success": False,
            "error": f"Invalid API endpoint: {e.detail}"
        }
    
    try:
        # Prepare minimal test request
        headers = {
            "Content-Type": "application/json",
        }
        
        # Add API key to headers if provided
        if payload.api_key:
            if "anthropic" in payload.api_endpoint.lower():
                headers["x-api-key"] = payload.api_key
                headers["anthropic-version"] = "2023-06-01"
            elif "openai" in payload.api_endpoint.lower() or "openrouter" in payload.api_endpoint.lower():
                headers["Authorization"] = f"Bearer {payload.api_key}"
            elif "generativelanguage" in payload.api_endpoint.lower():
                # Google uses API key in URL
                pass
        
        # Minimal test message
        test_messages = [{"role": "user", "content": "Say 'OK'"}]
        
        # Build request body based on provider
        if "anthropic" in payload.api_endpoint.lower():
            request_body = {
                "model": payload.model_name,
                "messages": test_messages,
                "max_tokens": 10,
                "temperature": payload.temperature,
            }
        else:
            # OpenAI-compatible format
            request_body = {
                "model": payload.model_name,
                "messages": test_messages,
                "max_tokens": 10,
                "temperature": payload.temperature,
            }
        
        # Send test request
        timeout = aiohttp.ClientTimeout(total=payload.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                payload.api_endpoint,
                json=request_body,
                headers=headers,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "message": f"LLM test successful! Model: {payload.model_name}"
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"LLM test failed (HTTP {response.status}): {error_text[:200]}"
                    }
    
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": f"LLM test timed out after {payload.timeout} seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"LLM test failed: {str(e)[:200]}"
        }


@router.post("/test-embedding")
async def test_embedding_config(
    payload: EmbeddingTestRequest,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Test an embedding configuration by generating a test embedding.
    
    This endpoint validates that the embedding provider is accessible and responding correctly
    without saving the configuration to the database.
    
    Args:
        payload: Embedding configuration to test
        current_user: Authenticated user (required for authorization)
    
    Returns:
        Dict with 'success' boolean, 'message' string, and optional 'error' string
    """
    # Validate URL to prevent SSRF attacks
    if payload.embedding_api_url and payload.embedding_api_url.strip():
        try:
            validate_url_safe(payload.embedding_api_url)
        except HTTPException as e:
            return {
                "success": False,
                "error": f"Invalid embedding API URL: {e.detail}"
            }
    
    # Check if provider is None/empty
    if not payload.embedding_provider or payload.embedding_provider.strip() == '':
        return {
            "success": False,
            "error": "Embedding provider is set to 'None'. RAG functionality will be disabled. To enable RAG, select a provider (openai, cohere, or ollama) and configure all required fields."
        }
    
    # Check if required fields are missing
    missing_fields = []
    if not payload.embedding_api_url or payload.embedding_api_url.strip() == '':
        missing_fields.append('Embedding API URL')
    if not payload.embedding_model_name or payload.embedding_model_name.strip() == '':
        missing_fields.append('Embedding Model Name')
    
    if missing_fields:
        return {
            "success": False,
            "error": f"Missing required fields: {', '.join(missing_fields)}. Please complete the embedding configuration."
        }
    
    try:
        # Prepare minimal test request
        headers = {
            "Content-Type": "application/json",
        }
        
        # Add API key to headers if provided
        if payload.embedding_api_key:
            if "cohere" in payload.embedding_api_url.lower():
                headers["Authorization"] = f"Bearer {payload.embedding_api_key}"
            elif "openai" in payload.embedding_api_url.lower() or "openrouter" in payload.embedding_api_url.lower():
                headers["Authorization"] = f"Bearer {payload.embedding_api_key}"
        
        # Minimal test text
        test_text = "test"
        
        # Build request body based on provider
        if payload.embedding_provider == "cohere":
            request_body = {
                "texts": [test_text],
                "model": payload.embedding_model_name,
                "input_type": "search_document",
            }
        else:
            # OpenAI-compatible format
            request_body = {
                "input": test_text,
                "model": payload.embedding_model_name,
            }
        
        # Send test request
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                payload.embedding_api_url,
                json=request_body,
                headers=headers,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "message": f"Embedding test successful! Model: {payload.embedding_model_name}"
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Embedding test failed (HTTP {response.status}): {error_text[:200]}"
                    }
    
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Embedding test timed out after 30 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Embedding test failed: {str(e)[:200]}"
        }


__all__ = ["router"]
