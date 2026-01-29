from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.utils.log_setup import get_logger

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
        logger.info("Retriever initialized (re-ranking disabled)")

    async def retrieve(
        self,
        query_vec: np.ndarray,
        investigation_id: str,
        owner_types: Optional[List[str]] = None,
        k: int = 5,
    ) -> List[EmbeddingChunk]:
        """
        Retrieve relevant embedding chunks for a given investigation using PGVector similarity search.

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

        Returns
        -------
        list[EmbeddingChunk]
            Up to *k* `EmbeddingChunk` objects ordered by decreasing similarity. Each chunk includes its vector metadata and the associated text loaded from the underlying tables. An empty list is returned if no candidates are found.
        """
        # Vector search with PGVector
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
        chunks_with_text = await self._load_texts(candidates)

        return chunks_with_text[:k]

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
            logger.info(f"Total embeddings in database: {total_embeddings}")

            result = await self.db.execute(text(sql), params)
            rows = result.fetchall()

            logger.info(
                f"Vector search returned {len(rows):,} candidates (out of {total_embeddings} total embeddings)"
            )

            # Log first result for debugging
            if rows:
                logger.debug(
                    f"First result: id={rows[0][0]}, owner_type={rows[0][1]}, owner_id={rows[0][2]}, distance={rows[0][3]}"
                )

            return [(row[0], row[1], row[2], row[3]) for row in rows]

        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            # Don't rollback here - let the caller handle it
            # Re-raising will propagate the error up to the handler
            raise

    async def _load_texts(
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
                if text:
                    chunks.append(
                        EmbeddingChunk(
                            id=emb_id,
                            owner_type=owner_type,
                            owner_id=owner_id,
                            text=text,
                            score=1.0 - distance,  # Convert distance to similarity score
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
                        logger.info("Transaction rolled back successfully")
                    except Exception as rb_error:
                        logger.error(f"Rollback failed: {rb_error}")
                    # Stop processing remaining candidates
                    break
                # For other errors, continue to next candidate
                continue

        logger.info(f"Loaded {len(chunks):,} chunks from {len(candidates):,} candidates")
        return chunks

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
                        "SELECT title || ': ' || COALESCE(description, '') FROM timeline_entries WHERE entry_id = :id"
                    ),
                    {"id": owner_id},
                )
                row = result.fetchone()
                return row[0] if row else None

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
                payload_str = str(payload)[:500] if payload else "No details"
                text_result = f"{event_type} at {timestamp_str}: {payload_str}"
                logger.debug(
                    f"Successfully fetched event {owner_id}, text length: {len(text_result):,}"
                )
                return text_result

            return None

        except Exception as e:
            logger.warning(f"Failed to fetch text for {owner_type}/{owner_id}: {e}")
            # Don't rollback here - just return None and let the chunk be skipped
            return None


__all__ = ["Retriever", "EmbeddingChunk"]
