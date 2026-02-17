from typing import Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rag.embedding import Embedder
from app.crud.llm_config import get_active_llm_config

from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message

logger = get_logger(__name__)


async def hybrid_search(
    db: AsyncSession,
    investigation_id: str,
    query: str,
    bm25_weight: float = 0.5,
    limit: int = 50,
    offset: int = 0,
    user_id: Optional[int] = None,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Hybrid search that combines BM25 full-text ranking with vector similarity and returns paginated results.

    The function first validates and normalises input parameters, then attempts to obtain an embedding model for the given `user_id`. If embeddings are available, it performs a BM25 search over the JSONB `payload` column and an approximate nearest-neighbor (ANN) vector search using the generated query embedding. Scores from both modalities are normalised to the range [0, 1], weighted according to `bm25_weight` (the complementary weight is applied to the vector score), merged, de-duplicated by `event_id`, and re-ranked to produce a final relevance score.

    If no embedding model can be initialised or the user has no configuration, the function falls back to a pure BM25 search via `_bm25_only_search` and returns that result set.

    The combined result set is then paginated according to `limit` and `offset`, event details are fetched, and a structured response containing pagination metadata, score breakdowns, and method information is returned.

    Args:
        db: Async SQLAlchemy session used for all database queries.
        investigation_id: UUID string identifying the investigation whose events are searched.
        query: Free-text search string supplied by the caller.
        bm25_weight: Float in the interval [0.0, 1.0] indicating the relative importance of the BM25 score; the vector weight is `1.0 - bm25_weight`. Defaults to 0.5.
        limit: Maximum number of events to return (capped at 100). Default is 50.
        offset: Number of results to skip for pagination. Default is 0.
        user_id: Optional identifier of the user whose embedding configuration should be used. If `None` or if embedding initialisation fails, a BM25-only search is performed.
        stats: Optional mutable dictionary that will be updated with statistics such as the number of events analysed.

    Returns:
        dict containing:
            * `count` - Number of events in the current page.
            * `total_count` - Total number of unique events found before pagination.
            * `current_page` - 1-based index of the returned page.
            * `total_pages` - Total number of pages available given `limit`.
            * `events` - List of event dictionaries, each with keys `event_id`, `event_ts`, `event_type`, `artifact_id`, `payload` and a nested `score` dict holding `final`, `bm25`, `vector`, `norm_bm25` and `norm_vector` values.
            * `has_more` - Boolean indicating whether additional pages exist beyond the current one.
            * `limit` and `offset` - Echoed pagination parameters.
            * `search_method` - String literal `"hybrid"` (or `"bm25"`, when falling back).
            * `bm25_weight` and `vector_weight` - The weights used for score fusion.
            * `bm25_results` - Number of events returned by the BM25 sub-query.
            * `vector_results` - Number of events returned by the vector similarity sub-query.

    Raises:
        Any exception raised while querying the database or generating embeddings propagates to the caller; embedding initialisation failures are caught and cause a graceful fallback to BM25-only search.
    """
    # Validate parameters
    limit = min(int(limit) if limit else 50, 100)
    offset = int(offset) if offset else 0
    bm25_weight = max(0.0, min(1.0, float(bm25_weight)))
    vector_weight = 1.0 - bm25_weight

    logger.debug(
        f"Hybrid search: query='{sanitize_log_message(query[:50])}...', "
        f"bm25_weight={bm25_weight:.2f}, limit={limit}, offset={offset}"
    )

    # Check if embeddings are available
    embedding_available = False
    embedder = None
    query_embedding = None

    if user_id:
        try:
            llm_config = await get_active_llm_config(db, user_id)
            if llm_config:
                embedding_provider = getattr(llm_config, "embedding_provider", None)
                if embedding_provider:
                    embedding_api_url = str(getattr(llm_config, "embedding_api_url", ""))
                    embedding_api_key_val = getattr(llm_config, "embedding_api_key", None)
                    embedding_api_key = (
                        str(embedding_api_key_val) if embedding_api_key_val else None
                    )
                    embedding_model_name = str(
                        getattr(llm_config, "embedding_model_name", "text-embedding-ada-002")
                    )

                    if embedding_api_url:
                        embedder = Embedder(
                            provider=embedding_provider,
                            api_url=embedding_api_url,
                            api_key=embedding_api_key,
                            model_name=embedding_model_name,
                        )

                        # Generate query embedding
                        embeddings = await embedder.embed([query])
                        if len(embeddings) > 0:
                            query_embedding = embeddings[0]
                            embedding_available = True
                            logger.debug("Vector search enabled for hybrid search")
        except Exception as e:
            logger.warning(f"Failed to initialize embedder for hybrid search: {sanitize_log_message(str(e))}")

    # If embeddings not available, fall back to BM25-only
    if not embedding_available:
        logger.debug("Embeddings not available, falling back to BM25-only search")
        return await _bm25_only_search(
            db=db,
            investigation_id=investigation_id,
            query=query,
            limit=limit,
            offset=offset,
            stats=stats,
        )

    # === Step 1: BM25 Full-Text Search ===
    # Create tsvector from payload and rank using ts_rank_cd
    bm25_query = f"""
        WITH bm25_results AS (
            SELECT 
                event_id,
                ts_rank_cd(
                    to_tsvector('english', payload::text),
                    plainto_tsquery('english', :query)
                ) AS bm25_score
            FROM events
            WHERE investigation_id = :investigation_id
              AND to_tsvector('english', payload::text) @@ plainto_tsquery('english', :query)
        )
        SELECT event_id, bm25_score
        FROM bm25_results
        ORDER BY bm25_score DESC
        LIMIT 100  -- Get top 100 for merging
    """

    bm25_result = await db.execute(
        text(bm25_query), {"investigation_id": investigation_id, "query": query}
    )
    bm25_rows = bm25_result.fetchall()
    bm25_scores = {row[0]: float(row[1]) for row in bm25_rows}

    logger.debug(f"BM25 search returned {len(bm25_scores)} results")

    # === Step 2: Vector Similarity Search ===
    # Convert query embedding to PostgreSQL vector format
    if query_embedding is None:
        # This should never happen due to earlier check, but satisfy type checker
        logger.error("Query embedding is None after availability check")
        return await _bm25_only_search(
            db=db,
            investigation_id=investigation_id,
            query=query,
            limit=limit,
            offset=offset,
            stats=stats,
        )

    vec_list = query_embedding.tolist()
    vec_str = "[" + ",".join(map(str, vec_list)) + "]"

    vector_query = f"""
        WITH vector_results AS (
            SELECT 
                e.event_id,
                1 - (emb.vector <=> CAST(:query_vector AS vector)) AS similarity_score
            FROM embeddings emb
            INNER JOIN timeline_entries te ON emb.owner_type = 'timeline' AND emb.owner_id = te.entry_id
            INNER JOIN events e ON te.event_id = e.event_id
            WHERE e.investigation_id = :investigation_id
              AND emb.owner_type = 'timeline'
            ORDER BY emb.vector <=> CAST(:query_vector AS vector)
            LIMIT 100  -- Get top 100 for merging
        )
        SELECT event_id, similarity_score
        FROM vector_results
    """

    vector_result = await db.execute(
        text(vector_query), {"investigation_id": investigation_id, "query_vector": vec_str}
    )
    vector_rows = vector_result.fetchall()
    vector_scores = {row[0]: float(row[1]) for row in vector_rows}

    logger.debug(f"Vector search returned {len(vector_scores)} results")

    # === Step 3: Merge and Re-rank ===
    # Normalize scores to [0, 1] range
    max_bm25 = max(bm25_scores.values()) if bm25_scores else 1.0
    max_vector = max(vector_scores.values()) if vector_scores else 1.0

    # Combine results with weighted fusion
    combined_scores = {}
    all_event_ids = set(bm25_scores.keys()) | set(vector_scores.keys())

    for event_id in all_event_ids:
        norm_bm25 = (bm25_scores.get(event_id, 0.0) / max_bm25) if max_bm25 > 0 else 0.0
        norm_vector = (vector_scores.get(event_id, 0.0) / max_vector) if max_vector > 0 else 0.0

        final_score = (bm25_weight * norm_bm25) + (vector_weight * norm_vector)
        combined_scores[event_id] = {
            "final_score": final_score,
            "bm25_score": bm25_scores.get(event_id, 0.0),
            "vector_score": vector_scores.get(event_id, 0.0),
            "norm_bm25": norm_bm25,
            "norm_vector": norm_vector,
        }

    # Sort by final score
    sorted_event_ids = sorted(
        combined_scores.keys(), key=lambda eid: combined_scores[eid]["final_score"], reverse=True
    )

    logger.debug(f"Merged {len(combined_scores)} unique results")

    # === Step 4: Pagination ===
    total_count = len(sorted_event_ids)
    paginated_event_ids = sorted_event_ids[offset : offset + limit]

    # === Step 5: Fetch Event Details ===
    if not paginated_event_ids:
        return {
            "count": 0,
            "total_count": total_count,
            "current_page": (offset // limit) + 1 if limit > 0 else 1,
            "total_pages": (total_count + limit - 1) // limit if limit > 0 else 1,
            "events": [],
            "has_more": False,
            "limit": limit,
            "offset": offset,
            "search_method": "hybrid",
            "bm25_weight": bm25_weight,
            "vector_weight": vector_weight,
        }

    # Fetch event details with scores
    events_query = f"""
        SELECT event_id, event_ts, event_type, artifact_id, payload
        FROM events
        WHERE event_id = ANY(:event_ids)
        ORDER BY 
            CASE event_id
                {' '.join(f"WHEN {eid} THEN {idx}" for idx, eid in enumerate(paginated_event_ids))}
            END
    """

    events_result = await db.execute(text(events_query), {"event_ids": paginated_event_ids})
    events_rows = events_result.fetchall()

    events = []
    for row in events_rows:
        event_id = row[0]
        score_info = combined_scores.get(event_id, {})

        events.append(
            {
                "event_id": event_id,
                "event_ts": row[1].isoformat() if row[1] else None,
                "event_type": row[2],
                "artifact_id": row[3],
                "payload": row[4],
                "score": {
                    "final": score_info.get("final_score", 0.0),
                    "bm25": score_info.get("bm25_score", 0.0),
                    "vector": score_info.get("vector_score", 0.0),
                    "norm_bm25": score_info.get("norm_bm25", 0.0),
                    "norm_vector": score_info.get("norm_vector", 0.0),
                },
            }
        )

    if stats is not None:
        stats["events_analyzed"] = stats.get("events_analyzed", 0) + len(events)

    # Calculate pagination info
    current_page = (offset // limit) + 1 if limit > 0 else 1
    total_pages = (total_count + limit - 1) // limit if limit > 0 else 1

    logger.debug(
        f"Hybrid search returned {len(events)} events, "
        f"page {current_page}/{total_pages}, total={total_count}"
    )

    return {
        "count": len(events),
        "total_count": total_count,
        "current_page": current_page,
        "total_pages": total_pages,
        "events": events,
        "has_more": len(events) == limit,
        "limit": limit,
        "offset": offset,
        "search_method": "hybrid",
        "bm25_weight": bm25_weight,
        "vector_weight": vector_weight,
        "bm25_results": len(bm25_scores),
        "vector_results": len(vector_scores),
    }


async def _bm25_only_search(
    db: AsyncSession,
    investigation_id: str,
    query: str,
    limit: int,
    offset: int,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Implements a fallback BM25-only search when vector embeddings are unavailable.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous SQLAlchemy session used to execute the queries.
    investigation_id: str
        Identifier of the investigation whose events are being searched.
    query: str
        Full-text query string supplied by the user. It is processed with PostgreSQL's
        `plainto_tsquery` using the English text search configuration.
    limit: int
        Maximum number of events to return for the current page. Must be greater than
        zero; a non-positive value will be treated as no limit.
    offset: int
        Number of events to skip before returning results, used for pagination.
    stats: Optional[Dict[str, Any]], optional
        Mutable mapping that, if provided, is updated with statistics about the search
        (e.g., number of events analyzed). The function adds or increments the
        `events_analyzed` key.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing pagination metadata and the list of matching events.
        Keys include:

        - `count`: Number of events returned in this response.
        - `total_count`: Total number of events that match the query across all pages.
        - `current_page`: 1-based index of the current page derived from *offset* and *limit*.
        - `total_pages`: Total number of pages available given *total_count* and *limit*.
        - `events`: List of event dictionaries, each with keys `event_id`, `event_ts`,
          `event_type`, `artifact_id`, `payload` and a nested `score` mapping
          containing `final`, `bm25`, `vector`, `norm_bm25` and `norm_vector`.
        - `has_more`: Boolean indicating whether additional pages are available.
        - `limit` and `offset`: Echo the pagination parameters received.
        - `search_method`: Fixed string `"bm25_only"` identifying the fallback mode.
        - `bm25_weight`: Weight applied to BM25 scores (always `1.0` in this mode).
        - `vector_weight`: Weight for vector similarity (always `0.0` in this mode).

    Notes
    -----
    * The function logs a summary of the request and the pagination outcome at INFO level.
    * If *limit* is zero or negative, pagination calculations default to page 1 with a single total page.
    * Vector-related score components are populated with neutral values (zero or one) because no embedding comparison is performed.
    """
    logger.debug(f"BM25-only search: query='{sanitize_log_message(query[:50])}...', limit={limit}, offset={offset}")

    # BM25 search with pagination
    bm25_query = f"""
        WITH ranked_events AS (
            SELECT 
                event_id,
                event_ts,
                event_type,
                artifact_id,
                payload,
                ts_rank_cd(
                    to_tsvector('english', payload::text),
                    plainto_tsquery('english', :query)
                ) AS bm25_score
            FROM events
            WHERE investigation_id = :investigation_id
              AND to_tsvector('english', payload::text) @@ plainto_tsquery('english', :query)
        )
        SELECT event_id, event_ts, event_type, artifact_id, payload, bm25_score
        FROM ranked_events
        ORDER BY bm25_score DESC
        LIMIT :limit OFFSET :offset
    """

    result = await db.execute(
        text(bm25_query),
        {"investigation_id": investigation_id, "query": query, "limit": limit, "offset": offset},
    )
    rows = result.fetchall()

    events = [
        {
            "event_id": row[0],
            "event_ts": row[1].isoformat() if row[1] else None,
            "event_type": row[2],
            "artifact_id": row[3],
            "payload": row[4],
            "score": {
                "final": float(row[5]),
                "bm25": float(row[5]),
                "vector": 0.0,
                "norm_bm25": 1.0,
                "norm_vector": 0.0,
            },
        }
        for row in rows
    ]

    # Get total count
    count_query = f"""
        SELECT COUNT(*)
        FROM events
        WHERE investigation_id = :investigation_id
          AND to_tsvector('english', payload::text) @@ plainto_tsquery('english', :query)
    """

    count_result = await db.execute(
        text(count_query), {"investigation_id": investigation_id, "query": query}
    )
    total_count = count_result.scalar() or 0

    if stats is not None:
        stats["events_analyzed"] = stats.get("events_analyzed", 0) + len(events)

    current_page = (offset // limit) + 1 if limit > 0 else 1
    total_pages = (total_count + limit - 1) // limit if limit > 0 else 1

    logger.debug(
        f"BM25-only search returned {len(events)} events, "
        f"page {current_page}/{total_pages}, total={total_count}"
    )

    return {
        "count": len(events),
        "total_count": total_count,
        "current_page": current_page,
        "total_pages": total_pages,
        "events": events,
        "has_more": len(events) == limit,
        "limit": limit,
        "offset": offset,
        "search_method": "bm25_only",
        "bm25_weight": 1.0,
        "vector_weight": 0.0,
    }


__all__ = ["hybrid_search"]
