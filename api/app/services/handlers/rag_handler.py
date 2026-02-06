from typing import Dict, Any, AsyncIterator, List
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from ..rag.embedding import Embedder
from ..rag.retriever import Retriever, EmbeddingChunk
from ...crud.llm_config import get_active_llm_config
from ...crud.investigation import get_investigation
from ...models.tool_execution import ToolExecution
from ..llm_service import LLMService, LLMConfig
from ..context_manager import RAGContextManager

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


async def _expand_query_with_llm(
    user_query: str,
    llm_config: Any,
) -> List[str]:
    """
    Use an LLM to generate specific forensic search terms that expand a user’s query.

    The function creates an LLM service from the supplied configuration, builds a prompt that asks the model to produce 5-7 concrete terms (process names, file paths, registry keys, event IDs, techniques, tool names) relevant to Windows forensic artifacts, and then parses the comma-separated response into a list.

    Parameters
    ----------
    user_query: str
        The original query supplied by the user.
    llm_config: Any
        Configuration object used to instantiate `LLMConfig` and subsequently an `LLMService`.

    Returns
    -------
    list[str]
        A list containing up to seven expanded search terms. Returns an empty list if the LLM call fails or yields no usable output.

    Raises
    ------
    None directly; any exception raised during processing is caught, logged as a warning, and results in an empty list being returned.
    """
    # Create LLM service from config
    config = LLMConfig.from_db_config(llm_config)
    llm_service = LLMService(config)

    # Build expansion prompt
    expansion_prompt = f"""You are a digital forensics expert. Generate 5-7 specific search terms that would help find relevant evidence for this query in Windows forensic artifacts (EVTX logs, registry, MFT, prefetch, etc.).

User Query: {user_query}

Generate specific terms like:
- Process names (e.g., lsass.exe, powershell.exe)
- File paths (e.g., C:\\Windows\\System32\\)
- Registry keys (e.g., HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run)
- Event IDs (e.g., 4624, 4688)
- Attack techniques (e.g., credential dumping, lateral movement)
- Tool names (e.g., mimikatz, psexec)

Respond with ONLY a comma-separated list of terms, no explanations."""

    try:
        # Call LLM via centralized service
        data = await llm_service.call_llm(
            messages=[{"role": "user", "content": expansion_prompt}],
            max_tokens=4096,
            temperature=0.3,  # Lower temp for focused expansion
            enforce_context_limit=False,
        )

        # Extract response text
        expanded_text = await llm_service.extract_text_response(data)

        if not expanded_text:
            return []

        # Parse comma-separated terms
        terms = [term.strip() for term in expanded_text.split(",") if term.strip()]
        return terms[:7]  # Limit to 7 terms max

    except Exception as e:
        logger.warning(f"Query expansion error: {e}")
        return []  # Return empty list on error, continue with original query


def _deduplicate_and_rerank(chunks: List[EmbeddingChunk], top_k: int = 50) -> List[EmbeddingChunk]:
    """
    Deduplicate a list of embedding chunks and return the highest-scoring unique entries.

    This function removes duplicate chunks that share the same `owner_type` and `owner_id` pair,
    keeping only the instance with the greatest `score` value. After deduplication, the remaining
    chunks are sorted in descending order by their scores and the top *k* results are returned.

    Args:
        chunks (List[EmbeddingChunk]): A collection of embedding chunk objects that may contain
            duplicates. Each chunk is expected to have the attributes `owner_type`, `owner_id`,
            and `score`.
        top_k (int, optional): The maximum number of chunks to include in the returned list.
            Defaults to 50. If fewer unique chunks are available, all will be returned.

    Returns:
        List[EmbeddingChunk]: A list containing up to *top_k* deduplicated chunks, ordered from
        highest to lowest score.
    """
    # Deduplicate by (owner_type, owner_id), keeping highest score
    seen = {}
    for chunk in chunks:
        key = (chunk.owner_type, chunk.owner_id)
        if key not in seen or chunk.score > seen[key].score:
            seen[key] = chunk

    # Sort by score (descending) and take top_k
    unique_chunks = list(seen.values())
    unique_chunks.sort(key=lambda c: c.score, reverse=True)

    return unique_chunks[:top_k]


async def handle_rag_query(
    db: AsyncSession,
    investigation_id: UUID,
    user_query: str,
    user_id: int,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Handle a Retrieval-Augmented Generation (RAG) query by expanding the user’s question, retrieving relevant document chunks, and synthesizing an answer with context.

    The function performs the following steps:
    1. Retrieves the active LLM configuration for the given user.
    2. Validates that embedding settings are present; otherwise yields an error message.
    3. Expands the original query into additional search terms using a language model.
    4. Creates an embedder based on the configured provider and generates embeddings for the original query plus the expanded terms.
    5. Retrieves document chunks for each embedding vector, merges them, deduplicates, and re-ranks the results.
    6. Constructs a context string from the top chunks and prepares system/user prompts via `RAGContextManager`.
    7. Calls the LLM service to generate an answer, extracts the textual response, and yields it as the final chunk.
    8. Packages metadata about sources, expanded terms, and a placeholder event sequence for later persistence.

    If any step fails (missing configuration, embedding generation error, retrieval failure, or LLM synthesis issue), an error payload is yielded and the database transaction is rolled back.

    Args:
        db: An asynchronous SQLAlchemy session used for all database interactions.
        investigation_id: The UUID of the investigation whose documents are searched.
        user_query: The raw question submitted by the user.
        user_id: Identifier of the user, used to look up their LLM configuration.

    Yields:
        A dictionary representing a stream chunk. The `type` key indicates the kind of payload
        (e.g., `error`, `answer_chunk`). For successful processing an `answer_chunk` with
        `is_final=True` is yielded, containing the generated answer and a `metadata` field
        that includes source counts, event-sequence placeholders, retrieved chunk data,
        expanded terms, original query, and basic statistics.

    Raises:
        No exceptions are propagated; all errors are captured, logged, and emitted as error
        stream chunks. The function ensures the database session is either committed on success
        or rolled back on failure.
    """
    try:
        # Get user's LLM configuration
        llm_config = await get_active_llm_config(db, user_id)
        if not llm_config:
            yield {
                "type": "error",
                "content": "No active LLM configuration found. Please configure your LLM settings.",
                "is_final": True,
            }
            return

        # Extract config values (SQLAlchemy returns actual values at runtime)
        # Use getattr to safely extract values and satisfy type checker
        embedding_provider_val = getattr(llm_config, "embedding_provider", None)
        if not embedding_provider_val:
            yield {
                "type": "error",
                "content": "RAG requires embedding configuration. Please configure an embedding provider (OpenAI, Cohere, or Ollama) in LLM settings.",
                "is_final": True,
            }
            return
        embedding_provider = str(embedding_provider_val)

        embedding_api_url_val = getattr(llm_config, "embedding_api_url", None)
        if not embedding_api_url_val:
            yield {
                "type": "error",
                "content": "RAG requires embedding API URL. Please configure the embedding API endpoint in LLM settings.",
                "is_final": True,
            }
            return
        embedding_api_url = str(embedding_api_url_val)

        embedding_api_key_val = getattr(llm_config, "embedding_api_key", None)
        embedding_api_key = (
            str(embedding_api_key_val) if embedding_api_key_val is not None else None
        )

        embedding_model_name_val = getattr(llm_config, "embedding_model_name", None)
        if not embedding_model_name_val:
            yield {
                "type": "error",
                "content": "RAG requires embedding model name. Please configure the embedding model in LLM settings.",
                "is_final": True,
            }
            return
        embedding_model_name = str(embedding_model_name_val)

        # Get embedding max context length
        embedding_max_context_val = getattr(llm_config, "embedding_max_context_length", None)
        embedding_max_context_length = int(embedding_max_context_val) if embedding_max_context_val else 8192

        # Get reranker model (optional, falls back to embedding model)
        reranker_model_name_val = getattr(llm_config, "reranker_model_name", None)
        reranker_model_name = (
            str(reranker_model_name_val) if reranker_model_name_val else embedding_model_name
        )

        # Get reranker max context length
        reranker_max_context_val = getattr(llm_config, "reranker_max_context_length", None)
        reranker_max_context_length = int(reranker_max_context_val) if reranker_max_context_val else 8192

        # Get concurrent calls flag
        allow_concurrent_val = getattr(llm_config, "allow_concurrent_embedding_calls", None)
        allow_concurrent_embedding_calls = bool(allow_concurrent_val) if allow_concurrent_val is not None else False

        # Step 1: Use LLM to expand query with contextual search terms
        logger.debug(f"Expanding query: {user_query[:100]}")
        expanded_terms = await _expand_query_with_llm(
            user_query=user_query,
            llm_config=llm_config,
        )
        logger.debug(f"Expanded query terms: {expanded_terms}")

        # Step 2: Initialize embedder with reranker support
        embedder = Embedder(
            provider=embedding_provider,
            api_url=embedding_api_url,
            api_key=embedding_api_key,
            model_name=embedding_model_name,
            embedding_max_context_length=embedding_max_context_length,
            reranker_model_name=reranker_model_name,
            reranker_max_context_length=reranker_max_context_length,
            allow_concurrent_calls=allow_concurrent_embedding_calls,
        )

        # Step 3: Generate embeddings for original query + expanded terms
        all_queries = [user_query] + expanded_terms
        logger.debug(f"Generating embeddings for {len(all_queries):,} queries")
        query_vecs = await embedder.embed(all_queries)

        if len(query_vecs) == 0:
            yield {
                "type": "error",
                "content": "Failed to generate query embeddings",
                "is_final": True,
            }
            return

        # Step 4: Retrieve chunks for each query and merge results
        retriever = Retriever(db)
        all_chunks = []

        query_k = 50
        if len(query_vecs) > 20:
            query_k = 10
        elif len(query_vecs) > 15:
            query_k = 20
        elif len(query_vecs) > 10:
            query_k = 30
        elif len(query_vecs) > 5:
            query_k = 40
        
        try:
            for i, query_vec in enumerate(query_vecs):
                query_text = all_queries[i][:50]
                logger.debug(f"Searching with query {i+1}/{len(query_vecs):,}: {query_text}...")

                chunks = await retriever.retrieve(
                    query_vec=query_vec,
                    investigation_id=str(investigation_id),
                    owner_types=["chat", "timeline", "note", "tool"],
                    k=query_k,
                )
                all_chunks.extend(chunks)

            logger.debug(f"Retrieved {len(all_chunks):,} total chunks from {len(query_vecs):,} queries")
        except Exception as retrieval_error:
            logger.error(f"Retrieval error: {retrieval_error}", exc_info=True)
            # Rollback the transaction to clean up state
            await db.rollback()
            yield {
                "type": "error",
                "content": f"Failed to retrieve context: {str(retrieval_error)}",
                "is_final": True,
            }
            return

        # Step 5: Deduplicate chunks first
        chunks = _deduplicate_and_rerank(all_chunks, top_k=200)  # Get more candidates for reranking
        logger.debug(f"After deduplication: {len(chunks):,} chunks")

        # Step 6: Use reranker model for better relevance scoring (only if explicitly configured)
        # Reranker only runs if reranker_model_name is set AND different from embedding_model_name
        if reranker_model_name_val and reranker_model_name != embedding_model_name:
            try:
                logger.debug(f"Reranking {len(chunks):,} chunks with model: {reranker_model_name}")
                
                # Prepare documents for reranking
                documents = [chunk.text for chunk in chunks]
                
                # Call reranker
                reranked_results = await embedder.rerank(
                    query=user_query,
                    documents=documents,
                    top_k=50,  # Final top-k after reranking
                )
                
                # Map reranked results back to chunks
                reranked_chunks = []
                for result in reranked_results:
                    idx = result.get("index", result.get("document_index", 0))
                    score = result.get("score", result.get("relevance_score", 0.0))
                    
                    # Update chunk with new reranker score
                    chunk = chunks[idx]
                    chunk.score = score
                    reranked_chunks.append(chunk)
                
                chunks = reranked_chunks
                logger.debug(f"After reranking: {len(chunks):,} chunks (using {reranker_model_name})")
            except Exception as rerank_error:
                logger.warning(f"Reranking failed, falling back to vector similarity: {rerank_error}")
                # Fall back to original deduplication/ranking
                chunks = _deduplicate_and_rerank(all_chunks, top_k=50)
        else:
            # No reranker configured, use vector similarity only
            chunks = chunks[:50]  # Take top 50 from deduplicated results
            logger.debug(f"No reranker configured, using vector similarity only: {len(chunks):,} chunks")

        # Build context from chunks
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            context_parts.append(f"[Source {i} - {chunk.owner_type}]")
            context_parts.append(chunk.text)
            context_parts.append("")  # Blank line

        context_text = "\n".join(context_parts)

        # Get investigation metadata (wrap in try/except in case of transaction issues)
        try:
            investigation = await get_investigation(db, investigation_id)
            investigation_title = investigation.title if investigation else "Unknown"
        except Exception as inv_error:
            logger.warning(f"Failed to get investigation metadata: {inv_error}")
            investigation_title = "Unknown"

        # Prepare context using context manager
        system_prompt, prepared_query = RAGContextManager.prepare_context(
            investigation_title=investigation_title,
            user_query=user_query,
            retrieved_chunks=[{"owner_type": c.owner_type, "text": c.text} for c in chunks],
            max_tokens=16000,
        )

        # Create LLM service from config
        config = LLMConfig.from_db_config(llm_config)
        llm_service = LLMService(config)

        # Call LLM with context
        try:
            data = await llm_service.call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prepared_query},
                ],
                max_tokens=4096,
                temperature=0.7,
                enforce_context_limit=True,  # Enforce limit (context manager already trimmed if needed)
            )

            # Extract answer
            answer = await llm_service.extract_text_response(data)

            if not answer:
                yield {
                    "type": "error",
                    "content": "No response from LLM",
                    "is_final": True,
                }
                return
        except Exception as llm_error:
            logger.error(f"LLM synthesis failed: {llm_error}", exc_info=True)
            yield {
                "type": "error",
                "content": f"LLM synthesis failed: {str(llm_error)}",
                "is_final": True,
            }
            return

        # Serialize chunk data and expanded terms for later persistence
        chunks_data = []
        events_with_data = 0
        for chunk in chunks:
            chunk_dict = {
                "id": chunk.id,
                "owner_type": chunk.owner_type,
                "owner_id": chunk.owner_id,
                "text": chunk.text,
                "score": chunk.score,
            }
            # Include full event data for tool-type sources
            if chunk.event_data:
                chunk_dict["event_data"] = chunk.event_data
                events_with_data += 1
            chunks_data.append(chunk_dict)
        
        logger.info(f"Serialized {len(chunks_data)} chunks, {events_with_data} with event_data")

        # Build event_sequence placeholders (actual tool executions will be persisted later)
        event_sequence = []
        sequence_num = 0

        # Add query expansion placeholder
        if expanded_terms:
            event_sequence.append(
                {
                    "type": "tool_execution",
                    "sequence": sequence_num,
                    "tool_name": "expand_query",
                    "display_name": "Query Expansion",
                    "status": "completed",
                }
            )
            sequence_num += 1

        # Add single aggregated sources retrieval placeholder
        if chunks:
            event_sequence.append(
                {
                    "type": "tool_execution",
                    "sequence": sequence_num,
                    "tool_name": "retrieve_sources",
                    "display_name": f"Retrieved Sources ({len(chunks):,} results)",
                    "status": "completed",
                }
            )
            sequence_num += 1

        # Add thinking/answer after sources
        event_sequence.append(
            {
                "type": "thinking",
                "sequence": sequence_num,
                "content": answer,
            }
        )

        # Get embedding provider for metadata
        embedding_provider = str(getattr(llm_config, "embedding_provider", "unknown"))

        yield {
            "type": "answer_chunk",
            "content": answer,
            "is_final": True,
            "metadata": {
                "sources_count": len(chunks),
                "handler": "rag",
                "event_sequence": event_sequence,
                "chunks_data": chunks_data,
                "expanded_terms": expanded_terms,
                "original_query": user_query,
                "stats": {
                    "sources_retrieved": len(chunks),
                    "expansion_terms": len(expanded_terms),
                },
                "routing_metadata": {
                    "handler_type": "rag",
                    "handler_display_name": "Augmented Chat (RAG)",
                    "sources_retrieved": len(chunks),
                    "expansion_terms": len(expanded_terms),
                    "embedding_provider": embedding_provider,
                    "total_candidates": len(all_chunks),
                },
            },
        }

        # Commit the transaction to finalize read operations
        # This ensures the session is in a clean state for subsequent operations
        try:
            await db.commit()
        except Exception as commit_error:
            logger.warning(f"Failed to commit after RAG query: {commit_error}")
            await db.rollback()

    except Exception as e:
        logger.error(f"Error in RAG handler: {e}", exc_info=True)
        # Rollback transaction on any error
        try:
            await db.rollback()
        except:
            pass
        yield {
            "type": "error",
            "content": f"RAG query failed: {str(e)}",
            "is_final": True,
        }


async def persist_rag_tool_executions(
    db: AsyncSession,
    message_id: int,
    event_sequence: List[Dict[str, Any]],
    expanded_terms: List[str],
    chunks_data: List[Dict[str, Any]],
) -> List[int]:
    """
    Persist RAG tool execution records in the database.

    This coroutine creates and stores `ToolExecution` entries corresponding to the
    steps performed during a Retrieval-Augmented Generation (RAG) workflow:

    1. **Query expansion** - recorded when `expanded_terms` is non-empty.
    2. **Source retrieval** - a single aggregated entry that captures all retrieved
       document chunks.

    The function also returns the primary keys of the created records so callers can
    reference them later.

    Parameters
    ----------
    db: AsyncSession
        An active asynchronous SQLAlchemy session used to add and flush new rows.
    message_id: int
        The identifier of the chat message with which the tool executions should be
        associated.
    event_sequence: List[Dict[str, Any]]
        A list describing the sequence of events emitted by the RAG handler.  It is
        included for completeness but not directly used in this implementation.
    expanded_terms: List[str]
        The list of terms generated by the query-expansion step.  If empty, no
        expansion tool execution will be created.
    chunks_data: List[Dict[str, Any]]
        A collection of dictionaries representing retrieved document chunks.  Each
        dictionary must contain at least `owner_type`, `owner_id`, `score` and
        `text` keys.

    Returns
    -------
    List[int]
        The primary-key identifiers (`execution_id`) of the persisted
        `ToolExecution` rows, in the order they were created.

    Raises
    ------
    Exception
        Propagates any exception raised during database interaction after logging an
        error message.
    """
    execution_ids = []

    try:
        total_tools = (1 if chunks_data else 0) + (1 if expanded_terms else 0)
        current_tool = 0

        # Create query expansion tool execution
        if expanded_terms:
            current_tool += 1
            expansion_tool = ToolExecution(
                chat_message_id=message_id,
                tool_name="expand_query",
                display_name="Query Expansion",
                arguments={},
                result={"expanded_terms": expanded_terms},
                result_summary=f"Generated {len(expanded_terms):,} search terms: {', '.join(expanded_terms[:3])}{'...' if len(expanded_terms) > 3 else ''}",
                status="completed",
                execution_number=current_tool,
                max_tools=total_tools,
                finished_at=datetime.utcnow(),
            )
            db.add(expansion_tool)
            await db.flush()
            execution_ids.append(expansion_tool.execution_id)

        # Create single aggregated tool execution for all retrieved sources
        if chunks_data:
            current_tool += 1

            # Build a summary of sources by type
            sources_by_type = {}
            for chunk in chunks_data:
                owner_type = chunk["owner_type"]
                sources_by_type[owner_type] = sources_by_type.get(owner_type, 0) + 1

            type_summary = ", ".join([f"{count} {type}" for type, count in sources_by_type.items()])

            # Create result with all chunk data for expandable view
            sources_tool = ToolExecution(
                chat_message_id=message_id,
                tool_name="retrieve_sources",
                display_name=f"Retrieved Sources ({len(chunks_data):,} results)",
                arguments={
                    "total_sources": len(chunks_data),
                    "sources_by_type": sources_by_type,
                },
                result={
                    "sources": [
                        {
                            "index": i + 1,
                            "owner_type": chunk["owner_type"],
                            "owner_id": chunk["owner_id"],
                            "score": chunk["score"],
                            "text_preview": chunk["text"][:200]
                            + ("..." if len(chunk["text"]) > 200 else ""),
                            "text_full": chunk["text"],
                            "event": chunk.get("event_data"),  # Include full event object if available
                        }
                        for i, chunk in enumerate(chunks_data)
                    ]
                },
                result_summary=f"Retrieved {len(chunks_data):,} sources ({type_summary})",
                status="completed",
                execution_number=current_tool,
                max_tools=total_tools,
                finished_at=datetime.utcnow(),
            )
            db.add(sources_tool)
            await db.flush()
            execution_ids.append(sources_tool.execution_id)

        logger.debug(f"Persisted {len(execution_ids):,} RAG tool executions for message {message_id}")
        return execution_ids

    except Exception as e:
        logger.error(f"Failed to persist RAG tool executions: {e}", exc_info=True)
        raise


__all__ = ["handle_rag_query", "persist_rag_tool_executions"]
