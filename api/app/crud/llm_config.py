from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from ..models.llm_config import LLMProviderConfig


async def create_llm_config(
    db: AsyncSession,
    user_id: int,
    provider_name: str,
    api_endpoint: str,
    api_key: Optional[str],
    model_name: str,
    max_context_length: int,
    temperature: float,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    min_p: Optional[float] = None,
    timeout: int = 300,
    is_active: bool = True,
    allow_concurrent_llm_calls: bool = False,
    # Embedding configuration (optional)
    embedding_provider: Optional[str] = None,
    embedding_api_url: Optional[str] = None,
    embedding_api_key: Optional[str] = None,
    embedding_model_name: Optional[str] = None,
    embedding_max_context_length: Optional[int] = 8192,
    reranker_model_name: Optional[str] = None,
    reranker_max_context_length: Optional[int] = 8192,
    allow_concurrent_embedding_calls: bool = False,
) -> LLMProviderConfig:
    """
    Create and persist a new LLM provider configuration for a given user.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used to add and commit the configuration.
    user_id : int
        Identifier of the user that owns the configuration.
    provider_name : str
        Human-readable name of the LLM provider (e.g., `openai`, `anthropic`).
    api_endpoint : str
        Base URL or endpoint for the provider's API.
    api_key : Optional[str]
        Secret key used to authenticate requests to the provider. May be `None` if the provider does not require a key; note that the value should be encrypted before storage.
    model_name : str
        Name of the model to use with this provider (e.g., `gpt-4o`).
    max_context_length : int
        Maximum number of tokens the model can process in a single request.
    temperature : float
        Sampling temperature controlling randomness; typical range is 0.0-2.0.
    top_p : Optional[float], default=None
        Nucleus sampling parameter; if provided, limits token selection to the smallest set with cumulative probability >= `top_p`.
    top_k : Optional[int], default=None
        Top-k sampling parameter; if provided, restricts token selection to the `top_k` most probable tokens.
    min_p : Optional[float], default=None
        Minimum probability threshold for token inclusion during sampling.
    timeout : int, default=300
        Maximum number of seconds to wait for a response from the provider before aborting.
    is_active : bool, default=True
        Indicates whether this configuration should be considered active for routing requests.
    embedding_provider : Optional[str], default=None
        Name of an optional embedding service associated with this LLM configuration.
    embedding_api_url : Optional[str], default=None
        API endpoint for the embedding provider, if applicable.
    embedding_api_key : Optional[str], default=None
        Secret key for the embedding provider; also should be encrypted before storage.
    embedding_model_name : Optional[str], default=None
        Model name to use for embeddings when an embedding provider is specified.

    Returns
    -------
    LLMProviderConfig
        The newly created and persisted `LLMProviderConfig` instance, refreshed from the database.
    """

    config = LLMProviderConfig(
        user_id=user_id,
        provider_name=provider_name,
        api_endpoint=api_endpoint,
        api_key=api_key,
        model_name=model_name,
        max_context_length=max_context_length,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        min_p=min_p,
        timeout=timeout,
        is_active=is_active,
        allow_concurrent_llm_calls=allow_concurrent_llm_calls,
        # Embedding configuration
        embedding_provider=embedding_provider,
        embedding_api_url=embedding_api_url,
        embedding_api_key=embedding_api_key,
        embedding_model_name=embedding_model_name,
        embedding_max_context_length=embedding_max_context_length,
        reranker_model_name=reranker_model_name,
        reranker_max_context_length=reranker_max_context_length,
        allow_concurrent_embedding_calls=allow_concurrent_embedding_calls,
    )

    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def get_llm_config_by_id(
    db: AsyncSession,
    config_id: int,
) -> Optional[LLMProviderConfig]:
    """
    Retrieve a single LLM provider configuration identified by its primary key.

    Args:
        db: An active `AsyncSession` used for executing database queries.
        config_id: The integer primary-key of the desired `LLMProviderConfig`.

    Returns:
        The matching `LLMProviderConfig` instance, or `None` if no record with the given ID exists.
    """

    result = await db.execute(
        select(LLMProviderConfig).where(LLMProviderConfig.config_id == config_id)
    )
    return result.scalar_one_or_none()


async def get_active_llm_config(
    db: AsyncSession,
    user_id: int,
) -> Optional[LLMProviderConfig]:
    """
    Retrieve the active LLM provider configuration for a given user.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used to execute the query.
    user_id : int
        Identifier of the user whose active configuration is requested.

    Returns
    -------
    Optional[LLMProviderConfig]
        The active `LLMProviderConfig` instance if one exists, otherwise `None`.
    """

    result = await db.execute(
        select(LLMProviderConfig)
        .where(LLMProviderConfig.user_id == user_id)
        .where(LLMProviderConfig.is_active == True)
    )
    return result.scalar_one_or_none()


async def list_llm_configs(
    db: AsyncSession,
    user_id: int,
) -> List[LLMProviderConfig]:
    """
    List all LLM provider configurations for a given user.

    Parameters
    ----------
    db: AsyncSession
        The asynchronous SQLAlchemy session used to execute the query.
    user_id: int
        Identifier of the user whose configurations are being retrieved.

    Returns
    -------
    List[LLMProviderConfig]
        A list of `LLMProviderConfig` objects belonging to the specified user,
        ordered by `created_at` in descending order (newest first).
    """

    result = await db.execute(
        select(LLMProviderConfig)
        .where(LLMProviderConfig.user_id == user_id)
        .order_by(LLMProviderConfig.created_at.desc())
    )
    return list(result.scalars().all())


async def update_llm_config(
    db: AsyncSession,
    config_id: int,
    **kwargs,
) -> Optional[LLMProviderConfig]:
    """
    Update an LLM provider configuration in the database.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used for executing the query.
        config_id: The primary key of the :class:`LLMProviderConfig` record to update.
        **kwargs: Arbitrary keyword arguments representing fields of `LLMProviderConfig` to be updated. Keys with a value of `None` are ignored.

    Returns:
        An instance of :class:`LLMProviderConfig` reflecting the updated row, or `None` if no matching configuration exists. If no update data is provided, the existing configuration is retrieved and returned unchanged.

    Raises:
        Any exception raised by SQLAlchemy during execution (e.g., connection errors) will propagate to the caller.
    """

    # Remove None values
    update_data = {k: v for k, v in kwargs.items() if v is not None}

    if not update_data:
        return await get_llm_config_by_id(db, config_id)

    stmt = (
        update(LLMProviderConfig)
        .where(LLMProviderConfig.config_id == config_id)
        .values(**update_data)
        .returning(LLMProviderConfig)
    )

    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one_or_none()


async def delete_llm_config(
    db: AsyncSession,
    config_id: int,
) -> bool:
    """
    Delete an LLM provider configuration.\n\nParameters\n----------\ndb : AsyncSession\n    Asynchronous SQLAlchemy session used to execute the delete operation.\nconfig_id : int\n    Identifier of the LLMProviderConfig record to be removed.\n\nReturns\n-------\nbool\n    `True` if a row was deleted, otherwise `False`.
    """

    stmt = delete(LLMProviderConfig).where(LLMProviderConfig.config_id == config_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0


__all__ = [
    "create_llm_config",
    "get_llm_config_by_id",
    "get_active_llm_config",
    "list_llm_configs",
    "update_llm_config",
    "delete_llm_config",
]
