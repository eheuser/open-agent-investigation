import asyncio
import json
from typing import Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


async def discover_and_populate_fields(
    db: AsyncSession,
    investigation_id: str,
) -> Dict[str, int]:
    """
    Discover all JSONB fields from events and populate field_dictionary (without descriptions).

    This runs ONCE after parsing completes, replacing the per-row trigger approach.
    Much faster for bulk inserts.

    Args:
        db: AsyncSession for database operations
        investigation_id: UUID of the investigation

    Returns:
        Dict with statistics:
        - fields_discovered: Number of unique fields found
        - event_types_scanned: Number of event types scanned
    """
    try:
        # Discover all unique (event_type, field_name) pairs from events
        # Sample up to 5 values per field for context
        result = await db.execute(
            text(
                """
                WITH field_samples AS (
                    SELECT 
                        investigation_id,
                        event_type,
                        jsonb_object_keys(payload) AS field_name,
                        payload,
                        ROW_NUMBER() OVER (
                            PARTITION BY investigation_id, event_type, jsonb_object_keys(payload) 
                            ORDER BY event_ts DESC
                        ) AS rn
                    FROM events
                    WHERE investigation_id = :investigation_id
                )
                SELECT 
                    event_type,
                    field_name,
                    array_agg(DISTINCT LEFT(payload->>field_name, 200)) AS sample_values
                FROM field_samples
                WHERE rn <= 5
                GROUP BY event_type, field_name
                ORDER BY event_type, field_name
            """
            ),
            {"investigation_id": investigation_id},
        )

        discovered_fields = result.fetchall()

        if not discovered_fields:
            logger.info(f"No fields discovered for investigation {investigation_id}")
            return {"fields_discovered": 0, "event_types_scanned": 0}

        # Bulk insert all discovered fields
        fields_inserted = 0
        event_types = set()

        for event_type, field_name, sample_values in discovered_fields:
            event_types.add(event_type)

            await db.execute(
                text(
                    """
                    INSERT INTO field_dictionary (
                        investigation_id,
                        event_type,
                        field_name,
                        sample_values,
                        description,
                        cached_markdown
                    )
                    VALUES (
                        :investigation_id,
                        :event_type,
                        :field_name,
                        :sample_values,
                        NULL,
                        NULL
                    )
                    ON CONFLICT (investigation_id, event_type, field_name) DO NOTHING
                """
                ),
                {
                    "investigation_id": investigation_id,
                    "event_type": event_type,
                    "field_name": field_name,
                    "sample_values": sample_values or [],
                },
            )
            fields_inserted += 1

        await db.commit()

        logger.info(
            f"Field discovery complete: {fields_inserted:,} fields discovered "
            f"across {len(event_types):,} event types"
        )

        return {
            "fields_discovered": fields_inserted,
            "event_types_scanned": len(event_types),
        }

    except Exception as e:
        logger.error(f"Failed to discover fields: {e}", exc_info=True)
        return {"fields_discovered": 0, "event_types_scanned": 0}


async def finalize_field_dictionary(
    db: AsyncSession,
    investigation_id: str,
    llm_client,
    max_output_tokens: int = 16384,
    allow_concurrent_calls: bool = False,
    max_concurrent_batches: int = 4,
) -> Dict[str, int]:
    """
    Discover fields and generate LLM descriptions after parsing.

    This function:
    1. Discovers all JSONB fields from events (batch operation)
    2. Finds fields needing LLM descriptions (NULL description)
    3. Batches them efficiently for LLM processing
    4. Generates concise forensic descriptions using the LLM
    5. Updates field_dictionary with descriptions and cached markdown
    6. Returns statistics about fields processed

    Args:
        db: AsyncSession for database operations
        investigation_id: UUID of the investigation
        llm_client: LLM client for generating descriptions
        max_output_tokens: Maximum tokens for LLM output (default 16384)
        allow_concurrent_calls: Enable parallel LLM calls (default False)
        max_concurrent_batches: Maximum concurrent batches (default 4)

    Returns:
        Dict with statistics:
        - fields_discovered: Number of fields discovered
        - fields_pending: Number of fields needing descriptions
        - fields_processed: Number of fields successfully described
        - event_types_processed: Number of event types processed
    """
    try:
        # Step 1: Discover all fields from events (batch operation)
        discovery_stats = await discover_and_populate_fields(db, investigation_id)

        # Step 2: Find pending fields (NULL description)
        result = await db.execute(
            text(
                """
                SELECT event_type, field_name, sample_values
                FROM field_dictionary
                WHERE investigation_id = :investigation_id
                  AND description IS NULL
                ORDER BY event_type, field_name
            """
            ),
            {"investigation_id": investigation_id},
        )

        pending_rows = result.fetchall()

        if not pending_rows:
            logger.info(f"No pending fields for investigation {investigation_id}")
            return {
                "fields_pending": 0,
                "fields_processed": 0,
                "event_types_processed": 0,
            }

        # Organize by event type
        fields_by_type: Dict[str, List[tuple]] = {}
        for event_type, field_name, sample_values in pending_rows:
            fields_by_type.setdefault(event_type, []).append((field_name, sample_values or []))

        total_pending = len(pending_rows)
        logger.info(
            f"Finalizing field dictionary: {total_pending:,} pending fields "
            f"across {len(fields_by_type):,} event types"
        )

        # Reduce batch size to prevent JSON parsing errors (was 200-1000, now 100-250)
        batch_size = min(250, max(100, int(max_output_tokens / 30)))

        # Process in batches
        event_types_list = list(fields_by_type.items())
        current_batch = []
        current_field_count = 0
        fields_processed = 0

        # Build all batches first
        all_batches = []
        for event_type, field_list in event_types_list:
            # Check if adding this event type would exceed batch size
            if current_field_count + len(field_list) > batch_size and current_batch:
                all_batches.append(current_batch)
                current_batch = []
                current_field_count = 0

            # Add to current batch
            current_batch.append((event_type, field_list))
            current_field_count += len(field_list)

        # Add remaining batch
        if current_batch:
            all_batches.append(current_batch)
        
        # Process batches (concurrent or sequential)
        if allow_concurrent_calls and len(all_batches) > 1:
            logger.info(
                f"Concurrent LLM calls enabled: processing {len(all_batches):,} batches in parallel "
                f"(up to {max_concurrent_batches} concurrent)"
            )
            
            # Import here to avoid circular dependency
            from app.core.config import settings
            
            # Create separate database engine for concurrent operations
            # This prevents "another operation is in progress" errors
            concurrent_engine = create_async_engine(
                settings.database_url,
                echo=False,
                pool_pre_ping=True,
                pool_size=max_concurrent_batches + 2,  # One per concurrent task + buffer
            )
            
            ConcurrentSessionLocal = async_sessionmaker(
                concurrent_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            
            batch_results = []
            
            try:
                # Process in chunks of max_concurrent_batches
                for i in range(0, len(all_batches), max_concurrent_batches):
                    batch_chunk = all_batches[i:i + max_concurrent_batches]
                    
                    # Create tasks for this chunk - each with its own DB session
                    tasks = []
                    for batch in batch_chunk:
                        tasks.append(
                            _process_field_batch_with_session(
                                ConcurrentSessionLocal,
                                investigation_id,
                                llm_client,
                                batch,
                                max_output_tokens,
                            )
                        )
                    
                    # Wait for all tasks in this chunk
                    chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Handle results and errors
                    for batch_idx, result in enumerate(chunk_results):
                        global_batch_idx = i + batch_idx
                        if isinstance(result, BaseException):
                            logger.error(
                                f"Batch {global_batch_idx + 1}/{len(all_batches)} failed: {result}",
                                exc_info=result,
                            )
                            batch_results.append(0)
                        else:
                            batch_results.append(result)
                            fields_processed += result
                
                logger.info(
                    f"Concurrent processing complete: {len(all_batches):,} batches, "
                    f"{fields_processed:,} fields processed"
                )
            finally:
                # Clean up concurrent engine
                await concurrent_engine.dispose()
        else:
            # Sequential processing (default)
            for batch in all_batches:
                count = await _process_field_batch(
                    db,
                    investigation_id,
                    llm_client,
                    batch,
                    max_output_tokens,
                )
                fields_processed += count

        logger.info(
            f"Field dictionary finalized: {fields_processed:,}/{total_pending:,} fields processed"
        )

        return {
            "fields_discovered": discovery_stats.get("fields_discovered", 0),
            "fields_pending": total_pending,
            "fields_processed": fields_processed,
            "event_types_processed": len(fields_by_type),
        }

    except Exception as e:
        logger.error(f"Failed to finalize field dictionary: {e}", exc_info=True)
        return {
            "fields_discovered": 0,
            "fields_pending": 0,
            "fields_processed": 0,
            "event_types_processed": 0,
        }


async def _process_field_batch_with_session(
    session_factory,
    investigation_id: str,
    llm_client,
    batch: List[tuple],
    max_output_tokens: int = 16384,
) -> int:
    """
    Process a batch with its own database session (for concurrent execution).
    
    Args:
        session_factory: AsyncSessionmaker to create a new session
        investigation_id: UUID of the investigation
        llm_client: LLM client for generating descriptions
        batch: List of (event_type, [(field_name, sample_values), ...]) tuples
        max_output_tokens: Maximum tokens for LLM output
    
    Returns:
        Number of fields successfully processed
    """
    async with session_factory() as db:
        return await _process_field_batch(
            db,
            investigation_id,
            llm_client,
            batch,
            max_output_tokens,
        )


async def _process_field_batch(
    db: AsyncSession,
    investigation_id: str,
    llm_client,
    batch: List[tuple],
    max_output_tokens: int = 16384,
) -> int:
    """
    Process a batch of event types and generate field descriptions via LLM.

    Args:
        db: AsyncSession for database operations
        investigation_id: UUID of the investigation
        llm_client: LLM client for generating descriptions
        batch: List of (event_type, [(field_name, sample_values), ...]) tuples
        max_output_tokens: Maximum tokens for LLM output

    Returns:
        Number of fields successfully processed
    """
    # Calculate total fields in batch for better error handling
    total_fields = sum(len(field_list) for _, field_list in batch)
    
    # Build comprehensive prompt for all event types in batch
    event_type_sections = []

    for event_type, field_list in batch:
        # Build section for this event type
        section = f"\n{event_type}:\n"

        # Show sample values for first 3 fields (reduced to keep prompt smaller)
        samples_shown = 0
        for field_name, sample_values in field_list[:3]:
            if sample_values and samples_shown < 3:
                # Truncate samples for prompt efficiency
                samples_str = ", ".join(str(v)[:40] for v in sample_values[:2])
                section += f"  - {field_name}: [{samples_str}]\n"
                samples_shown += 1

        # List all field names
        all_fields = [fn for fn, _ in field_list]
        section += f"  All fields ({len(all_fields)}): {', '.join(all_fields)}\n"

        event_type_sections.append(section)

    # Build single prompt for entire batch
    prompt = f"""Generate brief forensic descriptions (5-10 words each) for JSONB fields from multiple event types.

Event Types and Fields:
{''.join(event_type_sections)}

CRITICAL: Return ONLY valid JSON. No markdown, no code blocks, no explanatory text.

JSON structure:
{{
  "event_type": {{
    "field_name": "Brief description (5-10 words)",
    ...
  }},
  ...
}}

Examples:
- "TargetUserName": "Account targeted by operation"
- "IpAddress": "Source IP of connection"
- "ProcessId": "Process identifier (PID)"
- "EventRecordID": "Unique event log record number"

Generate descriptions for ALL {total_fields} fields listed above.
"""

    try:
        messages = [
            {
                "role": "system", 
                "content": "You are a forensic analyst. Output ONLY valid JSON with no additional text, markdown formatting, or code blocks."
            },
            {"role": "user", "content": prompt},
        ]

        # Call LLM once for entire batch
        stream = llm_client.stream_chat(
            messages=messages,
            temperature=0.3,
            max_tokens=max_output_tokens,
        )

        response_msg = await llm_client.parse_stream_to_message(stream)
        content = response_msg.content or "{}"

        # More aggressive JSON extraction
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        # Remove any leading/trailing non-JSON text
        # Find first { and last }
        start_idx = content.find('{')
        end_idx = content.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            content = content[start_idx:end_idx + 1]
        
        # Try to parse JSON
        try:
            batch_descriptions = json.loads(content)
        except json.JSONDecodeError as json_err:
            logger.error(
                f"JSON parsing failed: {json_err}. "
                f"Content preview: {content[:500]}... (total {len(content):,} chars)"
            )
            # Log full content for debugging
            logger.debug(f"Full LLM response:\n{content}")
            logger.warning(
                f"Skipping batch due to malformed JSON. "
                f"Batch had {total_fields:,} fields across {len(batch):,} event types."
            )
            return 0

        # Store all descriptions in database with cached markdown
        stored_count = 0
        for event_type, field_descriptions in batch_descriptions.items():
            for field_name, description in field_descriptions.items():
                # Generate cached markdown for this field
                cached_markdown = f"- `{field_name}` - {description}\n"

                await db.execute(
                    text(
                        """
                        UPDATE field_dictionary
                        SET description = :description,
                            cached_markdown = :cached_markdown,
                            updated_at = NOW()
                        WHERE investigation_id = :investigation_id
                          AND event_type = :event_type
                          AND field_name = :field_name
                    """
                    ),
                    {
                        "investigation_id": investigation_id,
                        "event_type": event_type,
                        "field_name": field_name,
                        "description": description,
                        "cached_markdown": cached_markdown,
                    },
                )
                stored_count += 1

        await db.commit()
        logger.info(
            f"Batch: Stored {stored_count:,} descriptions for {len(batch_descriptions):,} event types "
            f"({total_fields:,} total fields)"
        )

        return stored_count

    except Exception as e:
        logger.warning(
            f"Batch LLM call failed ({total_fields:,} fields, {len(batch):,} event types): {e}", 
            exc_info=True
        )
        try:
            await db.rollback()  # Rollback on error
        except:
            pass  # Ignore rollback errors
        return 0


async def get_cached_field_dictionary_markdown(
    db: AsyncSession,
    investigation_id: str,
    max_fields_per_type: int = 30,
) -> str:
    """
    Retrieve pre-generated cached markdown for field dictionary.

    This is much faster than regenerating markdown every agent iteration.

    Args:
        db: AsyncSession for database operations
        investigation_id: UUID of the investigation
        max_fields_per_type: Maximum fields to show per event type (default 30)

    Returns:
        Markdown-formatted field dictionary string
    """
    try:
        # Get all event types for this investigation
        result = await db.execute(
            text(
                """
                SELECT DISTINCT event_type
                FROM field_dictionary
                WHERE investigation_id = :investigation_id
                ORDER BY event_type
            """
            ),
            {"investigation_id": investigation_id},
        )

        event_types = [row[0] for row in result.fetchall()]

        if not event_types:
            return "**No fields available yet** - Upload and parse artifacts first.\n"

        # Build markdown from cached entries
        dict_parts = ["\n### Field Dictionary\n\n"]
        dict_parts.append(
            "**Available JSONB fields** (use exact names with `query_jsonb_field` or `aggregate_jsonb_field`):\n\n"
        )

        for event_type in event_types:
            # Get cached markdown for this event type (limit per type)
            result = await db.execute(
                text(
                    """
                    SELECT cached_markdown, field_name
                    FROM field_dictionary
                    WHERE investigation_id = :investigation_id
                      AND event_type = :event_type
                    ORDER BY field_name
                    LIMIT :limit
                """
                ),
                {
                    "investigation_id": investigation_id,
                    "event_type": event_type,
                    "limit": max_fields_per_type,
                },
            )

            rows = result.fetchall()

            if rows:
                dict_parts.append(f"\n**{event_type}**:\n")

                for cached_markdown, field_name in rows:
                    if cached_markdown:
                        # Use pre-generated markdown
                        dict_parts.append(cached_markdown)
                    else:
                        # Fallback for fields without description yet
                        dict_parts.append(f"- `{field_name}`\n")

                # Check if there are more fields
                count_result = await db.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM field_dictionary
                        WHERE investigation_id = :investigation_id
                          AND event_type = :event_type
                    """
                    ),
                    {
                        "investigation_id": investigation_id,
                        "event_type": event_type,
                    },
                )
                total_count = count_result.scalar()

                if total_count is not None and total_count > max_fields_per_type:
                    dict_parts.append(
                        f"  *(+{total_count - max_fields_per_type:,} more fields)*\n"
                    )

        formatted_dict = "".join(dict_parts)
        logger.debug(
            f"Retrieved cached field dictionary: {len(event_types):,} event types, "
            f"{len(formatted_dict):,} chars"
        )

        return formatted_dict

    except Exception as e:
        logger.error(f"Failed to retrieve cached field dictionary: {e}", exc_info=True)
        return "**Error retrieving field dictionary**\n"


__all__ = [
    "discover_and_populate_fields",
    "finalize_field_dictionary",
    "get_cached_field_dictionary_markdown",
]
