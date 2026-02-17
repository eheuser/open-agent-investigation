from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message

logger = get_logger(__name__)


@dataclass
class EmbeddingChunk:
    """Represents a retrieved chunk with metadata."""

    id: int
    owner_type: str
    owner_id: int
    text: str
    score: float
    metadata: Optional[Dict[str, Any]] = None
    event_data: Optional[Dict[str, Any]] = None  # Full event object for tool-type sources


class Retriever:
    """
    Retriever for RAG using PGVector similarity search.

    Re-ranking is disabled to avoid heavy dependencies.
    Uses PGVector IVFFLAT index for fast approximate nearest neighbor search.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize an asynchronous PGVector retriever with a database session.

        Args:
            db (AsyncSession): An active SQLAlchemy async session used for executing queries throughout the retriever's lifecycle.

        Sets:
            self.db: Stores the provided database session for later use in retrieval operations.
            logger.info: Emits a log entry indicating that the retriever has been initialized with re-ranking disabled.
        """
        self.db = db
        logger.debug("Retriever initialized (re-ranking disabled)")

    async def retrieve(
        self,
        query_vec: np.ndarray,
        investigation_id: str,
        owner_types: Optional[List[str]] = None,
        k: int = 5,
        query_text: Optional[str] = None,
        bm25_weight: float = 0.3,
    ) -> List[EmbeddingChunk]:
        """
        Retrieve relevant embedding chunks using hybrid BM25 + vector search.

        Parameters
        ----------
        query_vec : numpy.ndarray
            The embedding vector representing the query.
        investigation_id : str
            UUID of the investigation to which the search is scoped.
        owner_types : list[str] or None, optional
            A list of owner type identifiers (e.g., `["chat", "timeline"]`) used to filter results. If `None`, no owner-type filtering is applied.
        k : int, default 5
            Maximum number of chunks to return.
        query_text : str or None, optional
            The original text query for BM25 full-text search. If None, only vector search is performed.
        bm25_weight : float, default 0.3
            Weight for BM25 scores (0.0-1.0). Vector weight is (1.0 - bm25_weight).

        Returns
        -------
        list[EmbeddingChunk]
            Up to *k* `EmbeddingChunk` objects ordered by decreasing combined score. Each chunk includes its vector metadata and the associated text loaded from the underlying tables. An empty list is returned if no candidates are found.
        """
        # If query_text provided, perform hybrid BM25 + vector search
        if query_text:
            return await self._hybrid_retrieve(
                query_vec=query_vec,
                query_text=query_text,
                investigation_id=investigation_id,
                owner_types=owner_types,
                k=k,
                bm25_weight=bm25_weight,
            )

        # Fallback to vector-only search
        candidates = await self._vector_search(
            query_vec=query_vec,
            investigation_id=investigation_id,
            owner_types=owner_types,
            limit=k,
        )

        if not candidates:
            logger.info("No candidates found in vector search")
            return []

        # Load text content for candidates
        chunks_with_text = await self._load_texts_with_events(candidates)

        return chunks_with_text[:k]

    async def _hybrid_retrieve(
        self,
        query_vec: np.ndarray,
        query_text: str,
        investigation_id: str,
        owner_types: Optional[List[str]],
        k: int,
        bm25_weight: float,
    ) -> List[EmbeddingChunk]:
        """
        Perform hybrid BM25 + vector search and merge results.

        Args:
            query_vec: Query embedding vector
            query_text: Original text query for BM25 search
            investigation_id: Investigation UUID
            owner_types: Optional list of owner types to filter
            k: Maximum number of results to return
            bm25_weight: Weight for BM25 scores (0.0-1.0)

        Returns:
            List of EmbeddingChunk objects with combined scores
        """
        vector_weight = 1.0 - bm25_weight

        # Get candidates from both methods (fetch more to allow for merging)
        fetch_k = min(k * 3, 150)  # Fetch 3x desired results, capped at 150

        # Perform BM25 search
        bm25_candidates = await self._bm25_search(
            query_text=query_text,
            investigation_id=investigation_id,
            owner_types=owner_types,
            limit=fetch_k,
        )

        # Perform vector search
        vector_candidates = await self._vector_search(
            query_vec=query_vec,
            investigation_id=investigation_id,
            owner_types=owner_types,
            limit=fetch_k,
        )

        logger.debug(
            f"Hybrid search: {len(bm25_candidates)} BM25 candidates, {len(vector_candidates)} vector candidates"
        )

        # Build score maps
        bm25_scores = {
            (emb_id, owner_type, owner_id): score
            for emb_id, owner_type, owner_id, score in bm25_candidates
        }
        vector_scores = {
            (emb_id, owner_type, owner_id): score
            for emb_id, owner_type, owner_id, score in vector_candidates
        }

        # Normalize scores to [0, 1]
        max_bm25 = max((s for s in bm25_scores.values()), default=1.0)
        max_vector = max((s for s in vector_scores.values()), default=1.0)

        # Combine all candidates
        all_keys = set(bm25_scores.keys()) | set(vector_scores.keys())

        combined = []
        for key in all_keys:
            emb_id, owner_type, owner_id = key

            # Normalize and combine scores
            norm_bm25 = (bm25_scores.get(key, 0.0) / max_bm25) if max_bm25 > 0 else 0.0
            norm_vector = (vector_scores.get(key, 0.0) / max_vector) if max_vector > 0 else 0.0

            final_score = (bm25_weight * norm_bm25) + (vector_weight * norm_vector)

            combined.append((emb_id, owner_type, owner_id, final_score))

        # Sort by combined score and take top k
        combined.sort(key=lambda x: x[3], reverse=True)
        top_candidates = combined[:k]

        logger.debug(
            f"Hybrid merge: {len(combined)} unique candidates, returning top {len(top_candidates)}"
        )

        # Load text content
        chunks = await self._load_texts_with_events(top_candidates)

        return chunks

    async def _bm25_search(
        self,
        query_text: str,
        investigation_id: str,
        owner_types: Optional[List[str]],
        limit: int,
    ) -> List[Tuple[int, str, int, float]]:
        """
        Perform BM25 full-text search on embedded content.

        Args:
            query_text: Text query for full-text search
            investigation_id: Investigation UUID
            owner_types: Optional list of owner types to filter
            limit: Maximum number of results

        Returns:
            List of tuples: (embedding_id, owner_type, owner_id, bm25_score)
        """
        try:
            # Build SQL query with full-text search
            # We search the original text content that was embedded
            sql = """
            SELECT DISTINCT ON (e.id) 
                e.id, 
                e.owner_type, 
                e.owner_id,
                ts_rank_cd(
                    to_tsvector('english', 
                        CASE e.owner_type
                            WHEN 'chat' THEN (SELECT content FROM chat_messages WHERE message_id = e.owner_id)
                            WHEN 'timeline' THEN (SELECT title || ' ' || COALESCE(description, '') FROM timeline_entries WHERE entry_id = e.owner_id)
                            WHEN 'note' THEN (SELECT content FROM investigation_notes WHERE note_id = e.owner_id)
                            WHEN 'tool' THEN (SELECT event_type || ' ' || COALESCE(payload::text, '') FROM events WHERE event_id = e.owner_id)
                            ELSE ''
                        END
                    ),
                    plainto_tsquery('english', :query)
                ) AS bm25_score
            FROM embeddings e
            WHERE EXISTS (
                SELECT 1 FROM (
                    SELECT investigation_id FROM chat_messages WHERE message_id = e.owner_id AND e.owner_type = 'chat'
                    UNION ALL
                    SELECT investigation_id FROM timeline_entries WHERE entry_id = e.owner_id AND e.owner_type = 'timeline'
                    UNION ALL
                    SELECT investigation_id FROM investigation_notes WHERE note_id = e.owner_id AND e.owner_type = 'note'
                    UNION ALL
                    SELECT investigation_id FROM events WHERE event_id = e.owner_id AND e.owner_type = 'tool'
                ) AS owners
                WHERE owners.investigation_id = :inv_id
            )
            AND to_tsvector('english', 
                CASE e.owner_type
                    WHEN 'chat' THEN (SELECT content FROM chat_messages WHERE message_id = e.owner_id)
                    WHEN 'timeline' THEN (SELECT title || ' ' || COALESCE(description, '') FROM timeline_entries WHERE entry_id = e.owner_id)
                    WHEN 'note' THEN (SELECT content FROM investigation_notes WHERE note_id = e.owner_id)
                    WHEN 'tool' THEN (SELECT event_type || ' ' || COALESCE(payload::text, '') FROM events WHERE event_id = e.owner_id)
                    ELSE ''
                END
            ) @@ plainto_tsquery('english', :query)
            """

            if owner_types:
                sql += " AND e.owner_type = ANY(:owner_types)"

            sql += " ORDER BY e.id, bm25_score DESC LIMIT :limit"

            params = {
                "query": query_text,
                "inv_id": investigation_id,
                "limit": limit,
            }

            if owner_types:
                params["owner_types"] = owner_types

            result = await self.db.execute(text(sql), params)
            rows = result.fetchall()

            logger.debug(
                f"BM25 search returned {len(rows)} results for query: {query_text[:50]}..."
            )

            return [(row[0], row[1], row[2], float(row[3])) for row in rows]

        except Exception as e:
            logger.error(f"BM25 search failed: {sanitize_log_message(str(e))}", exc_info=True)
            raise

    async def _vector_search(
        self,
        query_vec: np.ndarray,
        investigation_id: str,
        owner_types: Optional[List[str]],
        limit: int,
    ) -> List[Tuple[int, str, int, float]]:
        """
        Perform a vector similarity search against the PostgreSQL PGVector embeddings table, scoped to a specific investigation and optional owner type filters.

        Args:
            query_vec (np.ndarray): The embedding vector representing the query. It will be converted to the PGVector literal format for SQL execution.
            investigation_id (str): Identifier of the investigation whose related owners should be considered. Only embeddings whose owning record belongs to this investigation are returned.
            owner_types (Optional[List[str]]): A list of owner type strings to restrict results to (e.g., `["chat", "timeline"]`). If `None`, no additional owner-type filtering is applied.
            limit (int): Maximum number of result rows to return.

        Returns:
            List[Tuple[int, str, int, float]]: A list of tuples containing:
                - id (int): Primary key of the embedding row.
                - owner_type (str): Type of the owning entity (e.g., `"chat"`, `"timeline"`, `"note"`, `"tool"`).
                - owner_id (int): Identifier of the owning record in its respective table.
                - distance (float): Euclidean (or L2) distance between `query_vec` and the stored embedding, as computed by PGVector's `<=>` operator.

        Raises:
            Exception: Propagates any exception raised during query construction, execution, or result processing after logging the error. The caller is responsible for handling transaction roll-back if required.
        """
        try:
            # Convert numpy array to PostgreSQL vector format string: '[x,y,z]'
            query_list = query_vec.tolist()
            query_vec_str = "[" + ",".join(map(str, query_list)) + "]"
            logger.debug(
                f"Query vector length: {len(query_list):,}, investigation_id: {investigation_id}"
            )

            # Build SQL query
            sql = """
            SELECT e.id, e.owner_type, e.owner_id, 
                   (e.vector <=> CAST(:query_vec AS vector)) AS distance
            FROM embeddings e
            WHERE EXISTS (
                SELECT 1 FROM (
                    SELECT investigation_id FROM chat_messages WHERE message_id = e.owner_id AND e.owner_type = 'chat'
                    UNION ALL
                    SELECT investigation_id FROM timeline_entries WHERE entry_id = e.owner_id AND e.owner_type = 'timeline'
                    UNION ALL
                    SELECT investigation_id FROM investigation_notes WHERE note_id = e.owner_id AND e.owner_type = 'note'
                    UNION ALL
                    SELECT investigation_id FROM tool_results WHERE result_id = e.owner_id AND e.owner_type = 'tool'
                    UNION ALL
                    SELECT investigation_id FROM events WHERE event_id = e.owner_id AND e.owner_type = 'tool'
                ) AS owners
                WHERE owners.investigation_id = :inv_id
            )
            """

            if owner_types:
                sql += " AND e.owner_type = ANY(:owner_types)"

            sql += " ORDER BY distance ASC LIMIT :limit"

            params = {
                "query_vec": query_vec_str,
                "inv_id": investigation_id,
                "limit": limit,
            }

            if owner_types:
                params["owner_types"] = owner_types

            # First check if any embeddings exist at all
            count_result = await self.db.execute(text("SELECT COUNT(*) FROM embeddings"))
            total_embeddings = count_result.scalar()
            logger.debug(f"Total embeddings in database: {total_embeddings}")

            result = await self.db.execute(text(sql), params)
            rows = result.fetchall()

            logger.debug(
                f"Vector search returned {len(rows):,} candidates (out of {total_embeddings} total embeddings)"
            )

            # Log first result for debugging
            if rows:
                logger.debug(
                    f"First result: id={rows[0][0]}, owner_type={rows[0][1]}, owner_id={rows[0][2]}, distance={rows[0][3]}"
                )

            return [(row[0], row[1], row[2], row[3]) for row in rows]

        except Exception as e:
            logger.error(f"Vector search failed: {sanitize_log_message(str(e))}", exc_info=True)
            # Don't rollback here - let the caller handle it
            # Re-raising will propagate the error up to the handler
            raise

    async def _load_texts_with_events(
        self, candidates: List[Tuple[int, str, int, float]]
    ) -> List[EmbeddingChunk]:
        """
        Load text content for embedding candidates.

        This coroutine iterates over a list of candidate embeddings, fetches the associated
        text from the appropriate source table based on `owner_type` and `owner_id`,
        and builds a list of :class:`EmbeddingChunk` objects containing the retrieved
        text and a similarity score derived from the supplied distance.

        The function is tolerant of individual retrieval failures: errors are logged,
        the offending candidate is skipped, and processing continues unless the error
        indicates that the database transaction has been aborted. In that case the
        transaction is rolled back, an appropriate warning is logged, and the loop is
        terminated early.

        Parameters
        ----------
        candidates : List[Tuple[int, str, int, float]]
            A list of tuples where each tuple contains:
            * `embedding_id` (int): Identifier of the embedding record.
            * `owner_type` (str): The type of entity that owns the text (e.g., "note",
              "report").
            * `owner_id` (int): Primary-key identifier of the owning entity.
            * `distance` (float): Cosine distance (or other metric) between the query
              embedding and this candidate; will be converted to a similarity score.

        Returns
        -------
        List[EmbeddingChunk]
            A list of populated :class:`EmbeddingChunk` objects for which text could be
            successfully retrieved. The length may be smaller than `len(candidates)`
            when some candidates fail to load or when processing stops due to a aborted
            transaction.

        Notes
        -----
        * The similarity score is computed as `1.0 - distance`; callers should ensure
          that the distance metric lies in the range `[0, 1]` for meaningful scores.
        * Errors related to a failed database transaction trigger an explicit rollback via
          `await self.db.rollback()` and cause early termination of the loop. Other
          exceptions are caught, logged, and the function proceeds with the next candidate.
        """
        chunks = []

        for i, (emb_id, owner_type, owner_id, distance) in enumerate(candidates):
            try:
                text = await self._fetch_text(owner_type, owner_id)
                # Fetch full event data for tool-type sources and timeline entries with linked events
                event_data = None
                if owner_type == "tool" and text:
                    event_data = await self._fetch_event_data(owner_id)
                    if event_data:
                        logger.debug(
                            f"Fetched event data for event {owner_id}: {event_data.get('event_type')}"
                        )
                    else:
                        logger.warning(f"Failed to fetch event data for event {owner_id}")
                elif owner_type == "timeline" and text:
                    # Check if timeline entry has a linked event
                    event_id = await self._get_timeline_event_id(owner_id)
                    if event_id:
                        event_data = await self._fetch_event_data(event_id)
                        if event_data:
                            logger.debug(
                                f"Fetched linked event data for timeline {owner_id}: {event_data.get('event_type')}"
                            )
                        else:
                            logger.warning(
                                f"Failed to fetch linked event data for timeline {owner_id}"
                            )
                if text:
                    chunks.append(
                        EmbeddingChunk(
                            id=emb_id,
                            owner_type=owner_type,
                            owner_id=owner_id,
                            text=text,
                            score=1.0 - distance,  # Convert distance to similarity score
                            event_data=event_data,  # Include full event object for tool-type and linked timeline sources
                        )
                    )
                    logger.debug(
                        f"Successfully loaded text for {owner_type}/{owner_id} ({i+1}/{len(candidates):,})"
                    )
            except Exception as e:
                error_msg = str(e)
                logger.error(
                    f"Error loading text for {owner_type}/{owner_id} ({i+1}/{len(candidates):,}): {error_msg}"
                )

                # If transaction is aborted, rollback and stop processing
                if (
                    "transaction is aborted" in error_msg
                    or "InFailedSQLTransactionError" in error_msg
                ):
                    logger.warning(
                        f"Transaction aborted at candidate {i+1}/{len(candidates):,}, rolling back and stopping"
                    )
                    try:
                        await self.db.rollback()
                        logger.debug("Transaction rolled back successfully")
                    except Exception as rb_error:
                        logger.error(f"Rollback failed: {sanitize_log_message(str(rb_error))}")
                    # Stop processing remaining candidates
                    break
                # For other errors, continue to next candidate
                continue

        logger.debug(f"Loaded {len(chunks):,} chunks from {len(candidates):,} candidates")
        return chunks

    async def _get_timeline_event_id(self, timeline_entry_id: int) -> Optional[int]:
        """
        Get the linked event_id for a timeline entry.

        Args:
            timeline_entry_id: Timeline entry ID

        Returns:
            Event ID if the timeline entry has a linked event, None otherwise
        """
        try:
            result = await self.db.execute(
                text(
                    """
                    SELECT event_id
                    FROM timeline_entries 
                    WHERE entry_id = :id
                """
                ),
                {"id": timeline_entry_id},
            )
            row = result.fetchone()

            if not row or row[0] is None:
                return None

            return row[0]
        except Exception as e:
            logger.warning(f"Failed to get event_id for timeline entry {timeline_entry_id}: {sanitize_log_message(str(e))}")
            return None

    async def _fetch_event_data(self, event_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch full event object for UI display.

        Args:
            event_id: Event ID

        Returns:
            Event object with event_id, event_type, timestamp, artifact_id, payload
        """
        try:
            result = await self.db.execute(
                text(
                    """
                    SELECT event_id, event_type, event_ts, payload, artifact_id
                    FROM events 
                    WHERE event_id = :id
                """
                ),
                {"id": event_id},
            )
            row = result.fetchone()

            if not row:
                return None

            event_id_val, event_type, event_ts, payload, artifact_id = row

            event_obj = {
                "event_id": event_id_val,
                "event_type": event_type,
                "timestamp": str(event_ts) if event_ts else "unknown time",
                "artifact_id": artifact_id,
                "payload": payload,
            }

            logger.debug(f"Built event object for event {event_id_val}: type={event_type}")
            return event_obj
        except Exception as e:
            logger.warning(f"Failed to fetch event data for event {event_id}: {sanitize_log_message(str(e))}")
            return None

    async def _fetch_text(self, owner_type: str, owner_id: int) -> Optional[str]:
        """
        Fetches textual content associated with a given owner type and identifier.\n\nParameters\n----------\nowner_type: str\n    The category of the owner; one of `\"chat\"`, `\"timeline\"`, `\"note\"` or `\"tool\"`.\nowner_id: int\n    Primary-key identifier for the specific record within the chosen owner type's table.\n\nReturns\n-------\nOptional[str]\n    The retrieved text if a matching row is found; otherwise `None`. For `\"tool\"` entries the returned string is formatted as `\"{event_type} at {timestamp}: {payload}\"` with the payload truncated to 500 characters.\n\nNotes\n-----\n* This method does **not** perform any transaction rollback on failure; it merely logs a warning and returns `None`.\n* Callers are responsible for managing database transaction state and handling `None` results appropriately.
        """
        try:
            if owner_type == "chat":
                result = await self.db.execute(
                    text("SELECT content FROM chat_messages WHERE message_id = :id"),
                    {"id": owner_id},
                )
                row = result.fetchone()
                return row[0] if row else None

            elif owner_type == "timeline":
                result = await self.db.execute(
                    text(
                        "SELECT title || ': ' || COALESCE(description, ''), event_id FROM timeline_entries WHERE entry_id = :id"
                    ),
                    {"id": owner_id},
                )
                row = result.fetchone()
                if not row:
                    return None
                # Store event_id in a temporary attribute for later fetching
                # We'll fetch the event data in _load_texts_with_events
                return row[0]

            elif owner_type == "note":
                result = await self.db.execute(
                    text("SELECT content FROM investigation_notes WHERE note_id = :id"),
                    {"id": owner_id},
                )
                row = result.fetchone()
                return row[0] if row else None

            elif owner_type == "tool":
                # For tool type, the owner_id points to events table
                # Embeddings were created with owner_type='tool', owner_id=event_id
                logger.debug(f"Fetching event {owner_id} from events table")

                # Query the correct column names: event_ts and payload (not event_timestamp and event_data)
                result = await self.db.execute(
                    text(
                        """
                        SELECT event_type, event_ts, payload
                        FROM events 
                        WHERE event_id = :id
                    """
                    ),
                    {"id": owner_id},
                )
                row = result.fetchone()

                if not row:
                    logger.warning(f"Event {owner_id} not found in events table")
                    return None

                event_type, event_ts, payload = row
                # Format in Python instead of SQL to avoid casting issues
                timestamp_str = str(event_ts) if event_ts else "unknown time"
                # Truncate payload to avoid huge strings
                payload_str = str(payload)[:4096] if payload else "No details"
                text_result = f"{event_type} at {timestamp_str}: {payload_str}"
                logger.debug(
                    f"Successfully fetched event {owner_id}, text length: {len(text_result):,}"
                )
                return text_result

            return None

        except Exception as e:
            logger.warning(f"Failed to fetch text for {owner_type}/{owner_id}: {sanitize_log_message(str(e))}")
            # Don't rollback here - just return None and let the chunk be skipped
            return None


__all__ = ["Retriever", "EmbeddingChunk"]
