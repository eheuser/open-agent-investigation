import json
import logging
from typing import Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def generate_field_dictionary(
    db: AsyncSession,
    investigation_id: str,
    llm_client,
    max_fields_per_type: int = 30,
    llm_max_context: int = 32768,
) -> str:
    """
    Generate a markdown-formatted dictionary of JSONB field names and short descriptions for all event types in the specified investigation.

    The function samples recent events per type, extracts distinct payload keys, checks which fields already have stored descriptions, uses the provided LLM client to generate missing descriptions in optimal batches, caches those results in the `field_dictionary` table, and finally assembles a human-readable markdown string grouped by event type.

    Args:
        db: An active `AsyncSession` used for all database queries and inserts.
        investigation_id: The UUID of the investigation whose events are being inspected.
        llm_client: A client capable of generating field descriptions; required only for fields without existing entries.
        max_fields_per_type: Maximum number of fields to display per event type in the output (default 30).
        llm_max_context: The maximum token context size supported by the LLM model (default 32768).

    Returns:
        A markdown string containing a “Field Dictionary” section. Each event type is listed with its fields; known fields include a short description, while newly discovered fields are shown without one until they are processed.

    Raises:
        Any exception raised during database access or LLM interaction is caught internally; the function logs the error and returns a markdown error message instead of propagating the exception.
    """
    try:
        # Get all event types and their fields from this investigation
        result = await db.execute(
            text(
                """
                WITH sampled_events AS (
                    SELECT event_type, payload
                    FROM (
                        SELECT event_type, payload,
                               ROW_NUMBER() OVER (PARTITION BY event_type ORDER BY event_ts DESC) as rn
                        FROM events
                        WHERE investigation_id = :investigation_id
                    ) AS ranked
                    WHERE rn <= 5
                )
                SELECT DISTINCT event_type, jsonb_object_keys(payload) as field_name
                FROM sampled_events
                ORDER BY event_type, field_name
            """
            ),
            {"investigation_id": investigation_id},
        )

        rows = result.fetchall()

        if not rows:
            return "**No fields available yet** - Upload and parse artifacts first.\n"

        # Organize fields by event type
        fields_by_type: Dict[str, List[str]] = {}
        for event_type, field_name in rows:
            fields_by_type.setdefault(event_type, []).append(field_name)

        logger.info(
            f"Generating field dictionary for {len(rows)} fields across {len(fields_by_type)} event types..."
        )

        # Check which fields already have descriptions in the database
        existing_result = await db.execute(
            text(
                """
                SELECT event_type, field_name, description, sample_values
                FROM field_dictionary
                WHERE event_type = ANY(:event_types)
            """
            ),
            {"event_types": list(fields_by_type.keys())},
        )

        existing_descriptions: Dict[tuple, Dict] = {}
        for event_type, field_name, description, sample_values in existing_result.fetchall():
            existing_descriptions[(event_type, field_name)] = {
                "description": description,
                "sample_values": sample_values or [],
            }

        # Identify fields that need descriptions
        fields_needing_descriptions: Dict[str, List[str]] = {}
        for event_type, field_list in fields_by_type.items():
            for field_name in field_list:
                if (event_type, field_name) not in existing_descriptions:
                    fields_needing_descriptions.setdefault(event_type, []).append(field_name)

        # Generate descriptions for new fields using LLM (batched for efficiency)
        if fields_needing_descriptions and llm_client:
            total_fields = sum(len(v) for v in fields_needing_descriptions.values())
            logger.info(
                f"Generating descriptions for {total_fields} new fields across {len(fields_needing_descriptions)} event types..."
            )

            # Calculate optimal batch size based on LLM context window
            # Use up to 75% of max context for output tokens (16K max for most models)
            max_output_tokens = min(16_384, int(llm_max_context * 0.75))
            # Estimate ~15 tokens per field (field name + description)
            # This allows us to process many more fields per batch
            batch_size = max(200, int(max_output_tokens / 15))

            logger.info(
                f"Using batch size of {batch_size} fields (max_output_tokens={max_output_tokens})"
            )

            event_types_list = list(fields_needing_descriptions.items())
            current_batch = []
            current_field_count = 0

            for event_type, field_list in event_types_list:
                # Check if adding this event type would exceed batch size
                if current_field_count + len(field_list) > batch_size and current_batch:
                    # Process current batch
                    await _process_field_batch(
                        db,
                        investigation_id,
                        llm_client,
                        current_batch,
                        existing_descriptions,
                        max_output_tokens,
                    )
                    current_batch = []
                    current_field_count = 0

                # Add to current batch
                current_batch.append((event_type, field_list))
                current_field_count += len(field_list)

            # Process remaining batch
            if current_batch:
                await _process_field_batch(
                    db,
                    investigation_id,
                    llm_client,
                    current_batch,
                    existing_descriptions,
                    max_output_tokens,
                )

        # Build formatted dictionary organized by event type
        dict_parts = ["\n### Field Dictionary\n\n"]
        dict_parts.append(
            "**Available JSONB fields** (use exact names with `query_jsonb_field` or `aggregate_jsonb_field`):\n\n"
        )

        # Format fields organized by event type
        for event_type in sorted(fields_by_type.keys()):
            field_list = sorted(fields_by_type[event_type])

            # Show event type header
            dict_parts.append(f"\n**{event_type}**:\n")

            # Show fields with descriptions (limit per event type)
            shown_count = 0
            for field_name in field_list:
                if shown_count >= max_fields_per_type:
                    break

                desc_data = existing_descriptions.get((event_type, field_name))
                if desc_data:
                    description = desc_data["description"]
                    dict_parts.append(f"- `{field_name}` - {description}\n")
                else:
                    dict_parts.append(f"- `{field_name}`\n")

                shown_count += 1

            # Show count of additional fields
            if len(field_list) > max_fields_per_type:
                dict_parts.append(f"  *(+{len(field_list) - max_fields_per_type} more fields)*\n")

        formatted_dict = "".join(dict_parts)

        logger.info(f"Generated field dictionary for {len(fields_by_type)} event types")

        return formatted_dict

    except Exception as e:
        logger.error(f"Failed to generate field dictionary: {e}", exc_info=True)
        return "**Error generating field dictionary**\n"


async def _process_field_batch(
    db: AsyncSession,
    investigation_id: str,
    llm_client,
    batch: List[tuple],
    existing_descriptions: Dict[tuple, Dict],
    max_output_tokens: int = 16384,
) -> None:
    """
    Process a batch of event types and their JSONB fields by sampling existing payload values, generating concise forensic descriptions via a single LLM call, and persisting the results.

    Parameters:
        db (AsyncSession): Asynchronous SQLAlchemy session used for querying samples and inserting descriptions.
        investigation_id (str): Identifier of the investigation whose events are being analyzed.
        llm_client: Client object providing `stream_chat` and `parse_stream_to_message` methods to interact with the language model.
        batch (List[tuple]): Collection of `(event_type, field_list)` tuples where `field_list` is an ordered list of JSONB field names for that event type.
        existing_descriptions (Dict[tuple, Dict]): Mapping that will be updated in-place with newly generated descriptions keyed by `(event_type, field_name)`.
        max_output_tokens (int, optional): Upper limit on the number of tokens the LLM may emit. Defaults to 16384.

    The function performs the following steps:
    1. For each event type in `batch`, sample up to two distinct values for the first ten fields using a lightweight SQL query.
    2. Assemble a single prompt that includes sampled values and the full field list for every event type.
    3. Invoke the LLM once, requesting a JSON object where each event type maps to its fields and brief (5-10 word) descriptions.
    4. Parse the model’s response, extract the JSON payload, and insert or update rows in the `field_dictionary` table with the generated description and any sampled values.
    5. Update `existing_descriptions` with the new entries and commit the transaction.

    Raises:
        Exception: Any exception raised during database access, LLM interaction, or JSON parsing is caught internally; a warning is logged but the exception is not re-raised.
    """
    # Build comprehensive prompt for all event types in batch
    event_type_sections = []
    all_field_samples = {}

    for event_type, field_list in batch:
        # Sample values for top fields only (limit to 10 per event type)
        field_samples = {}
        for field_name in field_list[:10]:
            try:
                sample_result = await db.execute(
                    text(
                        """
                        SELECT DISTINCT payload->>:field_name as value
                        FROM events
                        WHERE investigation_id = :investigation_id
                          AND event_type = :event_type
                          AND payload ? :field_name
                        LIMIT 2
                    """
                    ),
                    {
                        "investigation_id": investigation_id,
                        "event_type": event_type,
                        "field_name": field_name,
                    },
                )
                values = [row[0] for row in sample_result.fetchall() if row[0]]
                if values:
                    field_samples[field_name] = values
            except Exception as e:
                logger.debug(f"Failed to sample field {field_name}: {e}")

        # Build section for this event type
        section = f"\n{event_type}:\n"
        if field_samples:
            section += f"  Sample fields: {json.dumps(field_samples, default=str)[:500]}\n"
        section += f"  All fields: {', '.join(field_list)}\n"
        event_type_sections.append(section)
        all_field_samples[event_type] = field_samples

    # Build single prompt for entire batch
    prompt = f"""Generate brief forensic descriptions (5-10 words each) for JSONB fields from multiple event types.

Event Types and Fields:
{''.join(event_type_sections)}

Return ONLY a JSON object with this structure:
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
"""

    try:
        messages = [
            {"role": "system", "content": "You are a forensic analyst. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ]

        # Call LLM once for entire batch with dynamic max_tokens
        stream = llm_client.stream_chat(
            messages=messages,
            temperature=0.3,
            max_tokens=max_output_tokens,
        )

        response_msg = await llm_client.parse_stream_to_message(stream)
        content = response_msg.content or "{}"

        # Extract JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        batch_descriptions = json.loads(content)

        # Store all descriptions in database
        stored_count = 0
        for event_type, field_descriptions in batch_descriptions.items():
            field_samples = all_field_samples.get(event_type, {})

            for field_name, description in field_descriptions.items():
                sample_values = field_samples.get(field_name, [])

                await db.execute(
                    text(
                        """
                        INSERT INTO field_dictionary (event_type, field_name, description, sample_values)
                        VALUES (:event_type, :field_name, :description, :sample_values)
                        ON CONFLICT (event_type, field_name)
                        DO UPDATE SET
                            description = EXCLUDED.description,
                            sample_values = EXCLUDED.sample_values,
                            updated_at = NOW()
                    """
                    ),
                    {
                        "event_type": event_type,
                        "field_name": field_name,
                        "description": description,
                        "sample_values": sample_values,
                    },
                )

                # Update existing_descriptions
                existing_descriptions[(event_type, field_name)] = {
                    "description": description,
                    "sample_values": sample_values,
                }
                stored_count += 1

        await db.commit()
        event_types_processed = len(batch_descriptions)
        logger.info(
            f"Batch: Stored {stored_count} descriptions for {event_types_processed} event types"
        )

    except Exception as e:
        logger.warning(f"Batch LLM call failed: {e}")
        # Don't raise - continue with next batch


__all__ = [
    "generate_field_dictionary",
]
