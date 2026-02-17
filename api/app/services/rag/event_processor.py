from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
import json

from .filter_engine import FilterEngine
from .embedding_service import generate_embedding_for_timeline_entry
from ...crud.llm_config import get_active_llm_config
from ...models.filter_config import FilterConfig

from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message

logger = get_logger(__name__)


async def _get_filter_config(db: AsyncSession, investigation_id: UUID) -> Dict[str, Any]:
    """
    Get the filter configuration for a given investigation.

    This coroutine queries the database for the most recent `FilterConfig` record
    associated with *investigation_id*. If a configuration is found, its `content`
    field (expected to be a mapping) is returned as a plain dictionary. When no
    record exists or the `content` attribute is missing/empty, the function falls
    back to the default configuration defined by :class:`FilterEngine`.

    Args:
        db: An active asynchronous SQLAlchemy session used to execute the query.
        investigation_id: The UUID identifying the investigation whose filter settings
            are being requested.

    Returns:
        A dictionary containing the filter configuration. This will be either the
        stored configuration for the investigation or, if none is present,
        `FilterEngine.DEFAULT_CONFIG`.
    """
    result = await db.execute(
        select(FilterConfig)
        .where(FilterConfig.investigation_id == investigation_id)
        .order_by(FilterConfig.updated_at.desc())
    )
    filter_config = result.scalars().first()

    if filter_config:
        # Extract content using getattr to satisfy type checker
        content = getattr(filter_config, "content", None)
        if content:
            return dict(content)

    # Return default config
    return FilterEngine.DEFAULT_CONFIG


async def _batch_create_embeddings(
    db: AsyncSession,
    interesting_events: list,
    user_id: int,
    llm_config,
) -> int:
    """
    Batch creates vector embeddings for a list of interesting events and stores them in the database.

    The function iterates over the provided `interesting_events` in batches (default size 200). For each event it formats a human-readable text representation using :func:`_format_event_for_timeline`, generates an embedding via the configured LLM provider, and performs a bulk insert of all embeddings in the batch. If bulk insert fails, it falls back to individual inserts to identify problematic events.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used for executing INSERT statements and committing transactions.
        interesting_events: A list of tuples `(event_id, event_type, payload)` representing events that should receive embeddings.
        user_id: Identifier of the user whose embedding configuration should be applied. (Currently unused but retained for future per-user logic.)
        llm_config: An object containing LLM embedding settings; expected attributes are `embedding_provider`, `embedding_api_url`, optional `embedding_api_key` and optional `embedding_model_name`.

    Returns:
        int: The total number of embeddings that were successfully created and persisted in the database.

    Raises:
        None explicitly. All errors encountered while generating embeddings or inserting rows are caught, logged, and cause a rollback of the current transaction without propagating exceptions.

    Performance:
        Batch size of 200 events provides good balance between API efficiency and memory usage.
        Bulk inserts reduce database round-trips from 200 commits per batch to 1 commit per batch.
    """
    from .embedding import Embedder

    if not interesting_events:
        return 0

    # Check if embeddings are configured
    embedding_provider = getattr(llm_config, "embedding_provider", None)
    if not embedding_provider:
        return 0

    embedding_api_url_val = getattr(llm_config, "embedding_api_url", None)
    if not embedding_api_url_val:
        return 0

    embedding_api_url = str(embedding_api_url_val)
    embedding_api_key_val = getattr(llm_config, "embedding_api_key", None)
    embedding_api_key = str(embedding_api_key_val) if embedding_api_key_val else None
    embedding_model_name_val = getattr(llm_config, "embedding_model_name", None)
    embedding_model_name = (
        str(embedding_model_name_val) if embedding_model_name_val else "nomic-embed-text"
    )

    # Initialize embedder
    embedder = Embedder(
        provider=embedding_provider,
        api_url=embedding_api_url,
        api_key=embedding_api_key,
        model_name=embedding_model_name,
    )

    created_count = 0
    batch_size = 200  # Process 200 events at a time

    for i in range(0, len(interesting_events), batch_size):
        batch = interesting_events[i : i + batch_size]

        # Build text representations
        texts = []
        event_ids = []
        for event_id, event_type, payload in batch:
            title, description = _format_event_for_timeline(event_type, payload)
            text_content = f"{title}\n{description}"
            if len(text_content.strip()) >= 10:
                texts.append(text_content)
                event_ids.append(event_id)

        if not texts:
            continue

        try:
            # Generate embeddings for the batch
            logger.debug(
                f"Generating embeddings for batch {i//batch_size + 1} ({len(texts):,} events)"
            )
            embeddings = await embedder.embed(texts)

            # Bulk insert embeddings for the entire batch
            try:
                # Build all parameters for bulk insert
                insert_params = []
                for event_id, embedding_vec in zip(event_ids, embeddings):
                    # Convert numpy array to list, then to PostgreSQL vector format string
                    vec_list = embedding_vec.tolist()
                    vec_str = "[" + ",".join(map(str, vec_list)) + "]"

                    insert_params.append(
                        {
                            "event_id": event_id,
                            "model_name": embedding_model_name,
                            "vec_str": vec_str,
                        }
                    )

                # Execute bulk insert using executemany
                await db.execute(
                    text(
                        """
                        INSERT INTO embeddings (owner_type, owner_id, model_name, vector)
                        VALUES ('tool', :event_id, :model_name, CAST(:vec_str AS vector))
                    """
                    ),
                    insert_params,
                )

                # Commit once per batch
                await db.commit()
                created_count += len(insert_params)

                logger.debug(f"Created {created_count} embeddings so far...")

            except Exception as e:
                # Log error and rollback the batch
                logger.error(f"Failed to bulk insert embeddings for batch: {sanitize_log_message(str(e))}")
                await db.rollback()

                # Fall back to individual inserts for this batch to identify problematic events
                logger.info(f"Retrying batch with individual inserts to identify failures...")
                for event_id, embedding_vec in zip(event_ids, embeddings):
                    try:
                        vec_list = embedding_vec.tolist()
                        vec_str = "[" + ",".join(map(str, vec_list)) + "]"

                        await db.execute(
                            text(
                                """
                                INSERT INTO embeddings (owner_type, owner_id, model_name, vector)
                                VALUES ('tool', :event_id, :model_name, CAST(:vec_str AS vector))
                            """
                            ),
                            {
                                "event_id": event_id,
                                "model_name": embedding_model_name,
                                "vec_str": vec_str,
                            },
                        )
                        await db.commit()
                        created_count += 1
                    except Exception as individual_error:
                        logger.debug(
                            f"Failed to insert embedding for event {event_id}: {sanitize_log_message(str(individual_error))}"
                        )
                        try:
                            await db.rollback()
                        except Exception as rollback_error:
                            logger.debug(f"Rollback failed: {sanitize_log_message(str(rollback_error))}")
                        continue

        except Exception as e:
            logger.error(f"Failed to generate embeddings for batch: {sanitize_log_message(str(e))}")
            await db.rollback()
            continue

    return created_count


async def _create_embedding_for_event(
    db: AsyncSession,
    event_id: int,
    event_type: str,
    payload: Dict[str, Any],
    user_id: int,
) -> Optional[int]:
    """
    Create an embedding for an event that is considered interesting and store it in the database.

    The function builds a human-readable representation of the event using its type and payload,
    generates a vector embedding via the user’s configured LLM embedding provider, and inserts
    the resulting vector into the `embeddings` table.  If any required configuration is missing,
    if the generated text is too short, or if an error occurs during embedding generation, the
    function returns `None` without raising.

    Parameters
    ----------
    db: AsyncSession
        An active asynchronous SQLAlchemy session used to execute the INSERT statement.
    event_id: int
        The primary-key identifier of the event for which the embedding is being created.
    event_type: str
        A string describing the type of the event (e.g., `"file_created"`, `"login_attempt"`).
    payload: Dict[str, Any]
        The raw data associated with the event; it is formatted into a title and description
        that become the text input for the embedding model.
    user_id: int
        Identifier of the user whose LLM configuration (provider, API URL, key, model name) should be used.

    Returns
    -------
    Optional[int]
        The primary-key identifier of the newly created `embeddings` record if insertion succeeds,
        otherwise `None` when no embedding is generated or an error occurs.
    """
    from .embedding_service import generate_embedding_for_timeline_entry
    from ...crud.llm_config import get_active_llm_config
    from .embedding import Embedder

    # Build a readable text representation of the event
    title, description = _format_event_for_timeline(event_type, payload)
    text_content = f"{title}\n{description}"

    if len(text_content.strip()) < 10:
        return None

    # Get user's LLM configuration
    llm_config = await get_active_llm_config(db, user_id)
    if not llm_config:
        logger.debug(f"No active LLM config for user {user_id}")
        return None

    # Check if embeddings are configured
    embedding_provider = getattr(llm_config, "embedding_provider", None)
    if not embedding_provider:
        logger.debug(f"No embedding provider configured for user {user_id}")
        return None

    # Extract embedding config
    embedding_api_url_val = getattr(llm_config, "embedding_api_url", None)
    if not embedding_api_url_val:
        logger.debug(f"No embedding API URL configured for user {user_id}")
        return None
    embedding_api_url = str(embedding_api_url_val)

    # API key is optional (e.g., for local Ollama)
    embedding_api_key_val = getattr(llm_config, "embedding_api_key", None)
    embedding_api_key = str(embedding_api_key_val) if embedding_api_key_val else None

    embedding_model_name_val = getattr(llm_config, "embedding_model_name", None)
    embedding_model_name = (
        str(embedding_model_name_val) if embedding_model_name_val else "nomic-embed-text"
    )

    try:
        # Initialize embedder
        embedder = Embedder(
            provider=embedding_provider,
            api_url=embedding_api_url,
            api_key=embedding_api_key,
            model_name=embedding_model_name,
        )

        # Generate embedding
        embeddings = await embedder.embed([text_content])

        if len(embeddings) == 0:
            return None

        # Insert embedding - use 'tool' as owner_type for raw events
        # (we'll use a convention: tool results for events, timeline for actual timeline entries)
        # Convert numpy array to list, then to PostgreSQL vector format string
        vec_list = embeddings[0].tolist()
        vec_str = "[" + ",".join(map(str, vec_list)) + "]"

        result = await db.execute(
            text(
                """
                INSERT INTO embeddings (owner_type, owner_id, model_name, vector)
                VALUES ('tool', :event_id, :model_name, CAST(:vec_str AS vector))
                ON CONFLICT DO NOTHING
                RETURNING id
            """
            ),
            {
                "event_id": event_id,
                "model_name": embedding_model_name,
                "vec_str": vec_str,
            },
        )

        row = result.fetchone()
        embedding_id = row[0] if row else None

        if embedding_id:
            logger.debug(f"Created embedding {embedding_id} for event {event_id}")

        return embedding_id
    except Exception as e:
        logger.debug(f"Error generating embedding for event {event_id}: {sanitize_log_message(str(e))}")
        return None


def _format_event_for_timeline(event_type: str, payload: Dict[str, Any]) -> tuple[str, str]:
    """
    Format an event into a human-readable title and description suitable for timeline display.

    Args:
        event_type: The raw identifier of the event (e.g., `"evtx_sysmon_1"`). It encodes the source channel and, for EVTX events, the numeric ID.
        payload: A dictionary containing the parsed fields of the event. The expected keys depend on the specific event type.

    Returns:
        A two-element tuple `(title, description)` where `title` is a short, human-friendly summary of the event and `description` provides additional context or details.

    The function dispatches to specialized formatters based on the `event_type` prefix:

    * EVTX events (`evtx_<channel>_<id>`) are routed to channel-specific helpers
      (e.g., Sysmon, Security, System, PowerShell).
    * MFT, Registry, Prefetch, and LNK events are handled by their respective formatters.
    * If no specialized formatter matches, a generic formatter is used as a fallback.
    """
    # Extract event type components
    parts = event_type.split("_")

    if len(parts) >= 3 and parts[0] == "evtx":
        channel = parts[1]
        event_id = parts[2]

        # Format based on channel and event ID
        if channel == "sysmon":
            return _format_sysmon_event(event_id, payload)
        elif channel == "security":
            return _format_security_event(event_id, payload)
        elif channel == "system":
            return _format_system_event(event_id, payload)
        elif channel == "powershell":
            return _format_powershell_event(event_id, payload)

    elif event_type.startswith("mft_"):
        return _format_mft_event(payload)

    elif event_type in ("registry_key", "registry_value"):
        return _format_registry_event(payload)

    elif event_type.startswith("prefetch_"):
        return _format_prefetch_event(payload)

    elif event_type.startswith("lnk_"):
        return _format_lnk_event(payload)

    # Fallback: generic formatting
    return _format_generic_event(event_type, payload)


def _format_sysmon_event(event_id: str, payload: Dict[str, Any]) -> tuple[str, str]:
    """
    Format a Sysmon event into a concise title and description suitable for timeline display.

    Parameters
    ----------
    event_id : str
        The Sysmon event identifier as a string (e.g., `"1"`, `"3"`, `"11"`). It will be converted to an integer internally.
    payload : dict[str, Any]
        A dictionary containing the raw event data. Fields may be accessed either directly (e.g., `"Image"`) or via a dotted key prefix (e.g., `"event_data.Image"`).

    Returns
    -------
    tuple[str, str]
        A two-element tuple where the first element is a short title summarising the event and the second element is a multi-line description providing relevant details. For known event IDs (1, 3, 11) the description contains key fields; for all other IDs a generic title is returned along with a JSON-formatted snippet of the payload (truncated to 500 characters).
    """
    event_id_int = int(event_id)

    # Helper to get field value (try dotted key first, then non-dotted)
    def get_field(field_name: str, default: str = "") -> str:
        """
        Retrieve a field value from the event payload.

        Parameters
        ----------
        field_name : str
            The name of the field to look up.
        default : str, optional
            Value to return if the field is not found in either `event_data.<field_name>` or `<field_name>`, defaults to an empty string.

        Returns
        -------
        str
            The string representation of the located value, or the provided default if the field is missing.
        """
        return str(payload.get(f"event_data.{field_name}", payload.get(field_name, default)))

    # Sysmon Event ID 1: Process Creation
    if event_id_int == 1:
        image = get_field("Image", "Unknown")
        cmdline = get_field("CommandLine")
        parent = get_field("ParentImage")

        title = f"Process Created: {image}"
        description = f"Command Line: {cmdline}\nParent Process: {parent}"
        return (title, description)

    # Sysmon Event ID 3: Network Connection
    elif event_id_int == 3:
        image = get_field("Image", "Unknown")
        dest_ip = get_field("DestinationIp")
        dest_port = get_field("DestinationPort")

        title = f"Network Connection: {image}"
        description = f"Destination: {dest_ip}:{dest_port}"
        return (title, description)

    # Sysmon Event ID 11: File Created
    elif event_id_int == 11:
        image = get_field("Image", "Unknown")
        target = get_field("TargetFilename")

        title = f"File Created: {target}"
        description = f"Created by: {image}"
        return (title, description)

    # Generic Sysmon event
    else:
        title = f"Sysmon Event {event_id}"
        description = json.dumps(payload, indent=2)[:4096]
        return (title, description)


def _format_security_event(event_id: str, payload: Dict[str, Any]) -> tuple[str, str]:
    """
    Format a security event into a human-readable title and description for timeline display.

    Parameters
    ----------
    event_id: str
        The identifier of the Windows security event (e.g., "4624").
    payload: Dict[str, Any]
        The raw event data parsed from the source. Fields may be accessed directly or via a dotted `event_data.<field>` key.

    Returns
    -------
    tuple[str, str]
        A two-element tuple where the first element is a concise title summarising the event and the second element is a multiline description containing relevant details. For known event IDs (4624, 4625, 4688, 4720, 7045) the function extracts specific fields; for all other IDs it returns a generic title and a JSON-formatted excerpt of the payload (up to 500 characters).
    """
    event_id_int = int(event_id)

    # Helper to get field value (try dotted key first, then non-dotted)
    def get_field(field_name: str, default: str = "") -> str:
        """
        Fetches a specific field value from the event payload.

        Args:
            field_name: The name of the field to retrieve. It may be referenced directly or prefixed with `event_data.` in the payload.
            default: The fallback value to return if the field is not present in the payload. Defaults to an empty string.

        Returns:
            A string representation of the retrieved field value, or the provided default if the field is missing.
        """
        return str(payload.get(f"event_data.{field_name}", payload.get(field_name, default)))

    # Event ID 4624: Successful Logon
    if event_id_int == 4624:
        user = get_field("TargetUserName", "Unknown")
        logon_type = get_field("LogonType")
        source_ip = get_field("IpAddress")

        title = f"Successful Logon: {user}"
        description = f"Logon Type: {logon_type}\nSource IP: {source_ip}"
        return (title, description)

    # Event ID 4625: Failed Logon
    elif event_id_int == 4625:
        user = get_field("TargetUserName", "Unknown")
        source_ip = get_field("IpAddress")

        title = f"Failed Logon: {user}"
        description = f"Source IP: {source_ip}"
        return (title, description)

    # Event ID 4688: Process Creation
    elif event_id_int == 4688:
        process = get_field("NewProcessName", "Unknown")
        cmdline = get_field("CommandLine")

        title = f"Process Created: {process}"
        description = f"Command Line: {cmdline}"
        return (title, description)

    # Event ID 4720: User Account Created
    elif event_id_int == 4720:
        user = get_field("TargetUserName", "Unknown")

        title = f"User Account Created: {user}"
        description = ""
        return (title, description)

    # Event ID 7045: Service Installation
    elif event_id_int == 7045:
        service = get_field("ServiceName", "Unknown")
        image_path = get_field("ImagePath")

        title = f"Service Installed: {service}"
        description = f"Image Path: {image_path}"
        return (title, description)

    # Generic Security event
    else:
        title = f"Security Event {event_id}"
        description = json.dumps(payload, indent=2)[:4096]
        return (title, description)


def _format_system_event(event_id: str, payload: Dict[str, Any]) -> tuple[str, str]:
    """
    Format a system event into a title and description for timeline display.

    Parameters
    ----------
    event_id : str
        The numeric identifier of the Windows system event as a string.
    payload : dict[str, Any]
        Dictionary containing the raw event data. Fields may be accessed either
        directly (e.g., `'ServiceName'`) or via a dotted notation
        (e.g., `'event_data.ServiceName'`).

    Returns
    -------
    tuple[str, str]
        A two-element tuple where the first element is a concise title and the
        second element is a human-readable description. For event ID 7045 the
        title describes the installed service and the description includes the
        image path; for all other IDs a generic title and a JSON-formatted snippet
        of the payload (truncated to 500 characters) are returned.

    Notes
    -----
    The function converts `event_id` to an integer internally. If required fields
    are missing, default placeholders such as `'Unknown'` are used.
    """
    event_id_int = int(event_id)

    # Helper to get field value (try dotted key first, then non-dotted)
    def get_field(field_name: str, default: str = "") -> str:
        """
        Retrieve a field value from the event payload.

        Args:
            field_name (str): The name of the field to extract. It may be referenced directly or prefixed with `event_data.`.
            default (str, optional): Value to return if the field is not present in the payload. Defaults to an empty string.

        Returns:
            str: The extracted value as a string, or the provided default if the field is missing.
        """
        return str(payload.get(f"event_data.{field_name}", payload.get(field_name, default)))

    # Event ID 7045: Service Installation
    if event_id_int == 7045:
        service = get_field("ServiceName", "Unknown")
        image_path = get_field("ImagePath")

        title = f"Service Installed: {service}"
        description = f"Image Path: {image_path}"
        return (title, description)

    # Generic System event
    else:
        title = f"System Event {event_id}"
        description = json.dumps(payload, indent=2)[:4096]
        return (title, description)


def _format_powershell_event(event_id: str, payload: Dict[str, Any]) -> tuple[str, str]:
    """
    Format a PowerShell event into a concise title and description suitable for timeline entries.

    Args:
        event_id: The identifier of the event being processed.
        payload: A dictionary containing the raw event data. Expected keys include either
            `event_data.ScriptBlockText` or `ScriptBlockText` which hold the PowerShell script
            that was executed.

    Returns:
        tuple[str, str]: A two-element tuple where the first element is a short title (always
        `"PowerShell Execution"`) and the second element is a description containing the
        script block text truncated to 500 characters.
    """

    # Helper to get field value (try dotted key first, then non-dotted)
    def get_field(field_name: str, default: str = "") -> str:
        """
        Retrieve a string value from the payload based on a given field name.

        Args:
            field_name (str): The key of the desired field. The function first looks for this key prefixed with `event_data.` in the payload, then falls back to the plain key.
            default (str, optional): Value to return if neither lookup yields a result. Defaults to an empty string.

        Returns:
            str: The extracted value converted to a string, or the provided default if the field is not present.
        """
        return str(payload.get(f"event_data.{field_name}", payload.get(field_name, default)))

    script_block = get_field("ScriptBlockText")

    title = f"PowerShell Execution"
    description = f"Script: {script_block[:4096]}"
    return (title, description)


def _format_mft_event(payload: Dict[str, Any]) -> tuple[str, str]:
    """
    Format an MFT (Master File Table) event into a concise title and a truncated JSON description suitable for timeline display.

    Parameters:
        payload (Dict[str, Any]): The raw event data parsed from the artifact. Expected keys include either `'path'` or `'file_path'`; if neither is present, `"Unknown"` will be used as the file identifier.

    Returns:
        tuple[str, str]: A two-element tuple where the first element is a human-readable title in the form `"File Activity: <path>"` and the second element is a JSON-formatted string representation of the payload, indented for readability and truncated to the first 500 characters.
    """
    path = payload.get("path", payload.get("file_path", "Unknown"))

    title = f"File Activity: {path}"
    description = json.dumps(payload, indent=2)[:4096]
    return (title, description)


def _format_registry_event(payload: Dict[str, Any]) -> tuple[str, str]:
    """
    Format a Windows Registry event into a concise title and a truncated JSON description suitable for timeline display.

    Parameters
    ----------
    payload : dict[str, Any]
        The parsed registry event data. Expected keys include `key_path` or `path` which identify the affected registry key. Additional fields are included in the description.

    Returns
    -------
    tuple[str, str]
        A two-element tuple where:
        * **title** - a short string summarizing the event, e.g., `"Registry Key: HKLM\\Software\\Example"`.
        * **description** - a JSON-formatted representation of the full payload, indented for readability and truncated to the first 500 characters.
    """
    key_path = payload.get("key_path", payload.get("path", "Unknown"))

    title = f"Registry Key: {key_path}"
    description = json.dumps(payload, indent=2)[:4096]
    return (title, description)


def _format_prefetch_event(payload: Dict[str, Any]) -> tuple[str, str]:
    """
    Format a Prefetch event into a concise title and description for timeline display.

    Parameters
    ----------
    payload : dict[str, Any]
        A dictionary containing the parsed fields of a Prefetch artifact. Expected keys include:
        - `executable` or `name`: The name of the executable associated with the event.
        - `run_count`: The number of times the executable has been run.

    Returns
    -------
    tuple[str, str]
        A two-element tuple where the first element is a title string formatted as `"Prefetch: <executable>"`, and the second element is a description string containing the run count (e.g., `"Run Count: 5"`). If expected keys are missing, defaults to `"Unknown"` for the executable name and `0` for the run count.
    """
    executable = payload.get("executable", payload.get("name", "Unknown"))
    run_count = payload.get("run_count", 0)

    title = f"Prefetch: {executable}"
    description = f"Run Count: {run_count}"
    return (title, description)


def _format_lnk_event(payload: Dict[str, Any]) -> tuple[str, str]:
    """
    Format a Windows shortcut (LNK) event into a concise title and a truncated JSON-encoded description suitable for timeline display.

    Parameters
    ----------
    payload : dict[str, Any]
        The parsed event data containing at least the keys `target_path` or `target` that identify the linked file. Additional fields are included in the description.

    Returns
    -------
    tuple[str, str]
        A two-element tuple where the first element is a human-readable title of the form `"LNK File: <path>"` and the second element is a JSON-formatted string representation of the payload, indented for readability and limited to the first 500 characters.
    """
    target = payload.get("target_path", payload.get("target", "Unknown"))

    title = f"LNK File: {target}"
    description = json.dumps(payload, indent=2)[:4096]
    return (title, description)


def _format_generic_event(event_type: str, payload: Dict[str, Any]) -> tuple[str, str]:
    """
    Format a generic artifact event into a concise title and description suitable for timeline display.

    Parameters
    ----------
    event_type: str
        The type identifier of the event (e.g., `"file_created"`, `"login_attempt"`).
    payload: dict[str, Any]
        A dictionary containing the raw event data. It may include nested structures; only a JSON-encoded excerpt is used for the description.

    Returns
    -------
    tuple[str, str]
        A two-element tuple where:

        * **title** - A short string prefixed with `"Event: "` followed by the provided `event_type`.
        * **description** - A pretty-printed JSON representation of `payload`, truncated to the first 500 characters to keep the output succinct.
    """
    title = f"Event: {event_type}"
    description = json.dumps(payload, indent=2)[:4096]
    return (title, description)


async def process_interesting_events(
    db: AsyncSession,
    investigation_id: UUID,
    artifact_id: int,
    user_id: int = 1,
) -> int:
    """
    Process events from a parsed artifact, filter those deemed interesting according to the investigation’s filter configuration, create timeline entries for them, and generate vector embeddings using the user-specific LLM embedding service.

    The function performs three main steps:

    1. Retrieve the active LLM configuration for `user_id` and log any missing or incomplete settings.
    2. Load all events belonging to `artifact_id` (and `investigation_id`) that do not already have an associated embedding, then apply the appropriate filter logic based on the event type.
    3. Batch-create embeddings for the filtered “interesting” events and commit the transaction.

    Parameters
    ----------
    db : AsyncSession
        An active asynchronous SQLAlchemy session used for all database queries and writes.
    investigation_id : UUID
        The unique identifier of the investigation to which the artifact belongs; used to fetch filter rules.
    artifact_id : int
        Identifier of the artifact whose events are being processed. Only events linked to this artifact are examined.
    user_id : int, optional
        Identifier of the user whose LLM configuration should be consulted when generating embeddings. Defaults to `1` (admin).

    Returns
    -------
    int
        The number of embeddings successfully created for interesting events.

    Raises
    ------
    Exception
        Propagates any unexpected error after rolling back the database transaction and logging the failure.
    """
    try:
        logger.debug(f"Processing interesting events for artifact {artifact_id}")

        # Check embedding configuration once at the start
        from ...crud.llm_config import get_active_llm_config

        llm_config = await get_active_llm_config(db, user_id)
        if llm_config:
            embedding_provider = getattr(llm_config, "embedding_provider", None)
            embedding_url = getattr(llm_config, "embedding_api_url", None)
            embedding_model = getattr(llm_config, "embedding_model_name", None)
            has_key = bool(getattr(llm_config, "embedding_api_key", None))
            logger.debug(
                f"Embedding config for user {user_id}: "
                f"provider={embedding_provider}, url={embedding_url}, "
                f"model={embedding_model}, has_api_key={has_key}"
            )
            if not embedding_provider or not embedding_url:
                logger.warning(
                    f"Incomplete embedding config - provider and URL are required. "
                    f"Embeddings will not be generated."
                )
        else:
            logger.warning(
                f"No LLM config found for user {user_id} - embeddings will not be generated"
            )

        # Get filter configuration
        filter_config = await _get_filter_config(db, investigation_id)
        filter_engine = FilterEngine(filter_config)

        # Fetch all events from this artifact that don't have embeddings yet
        result = await db.execute(
            text(
                """
                SELECT e.event_id, e.event_type, e.event_ts, e.payload
                FROM events e
                LEFT JOIN embeddings emb ON emb.owner_type = 'tool' AND emb.owner_id = e.event_id
                WHERE e.artifact_id = :artifact_id
                AND e.investigation_id = :investigation_id
                AND emb.id IS NULL
                ORDER BY e.event_ts
            """
            ),
            {
                "artifact_id": artifact_id,
                "investigation_id": str(investigation_id),
            },
        )

        events = result.fetchall()
        logger.debug(
            f"Processing {len(events):,} events for embedding generation (artifact {artifact_id})"
        )

        # First pass: filter for interesting events
        interesting_events = []
        for event_id, event_type, event_ts, payload_json in events:
            try:
                payload = (
                    json.loads(payload_json) if isinstance(payload_json, str) else payload_json
                )
                is_interesting = False

                if event_type.startswith("evtx_"):
                    is_interesting, _ = filter_engine.is_interesting_evtx(payload)
                elif event_type.startswith("mft_"):
                    path = payload.get("path", payload.get("file_path", ""))
                    extension = payload.get("extension", "")
                    is_interesting = filter_engine.is_interesting_mft(path, extension)
                elif event_type in ("registry_key", "registry_value"):
                    key_path = payload.get("key_path", payload.get("path", ""))
                    is_interesting = filter_engine.is_interesting_registry(key_path)
                elif event_type.startswith("prefetch_"):
                    executable = payload.get("executable", payload.get("name", ""))
                    is_interesting = filter_engine.is_interesting_prefetch(executable)
                elif event_type.startswith("lnk_"):
                    target = payload.get("target_path", payload.get("target", ""))
                    is_interesting = filter_engine.is_interesting_lnk(target)
                elif event_type in (
                    "cryptnet_cache",
                    "pca_execution",
                    "scheduled_task",
                    "srum_data",
                    "windows_search",
                    "notification",
                    "browser_history",
                    "registry_amcache",
                    "registry_userassist",
                    "registry_bam",
                    "registry_shellbags_ntuser",
                    "registry_shimcache",
                ):
                    is_interesting = True

                if is_interesting:
                    interesting_events.append((event_id, event_type, payload))
            except Exception as e:
                logger.debug(f"Failed to filter event {event_id}: {sanitize_log_message(str(e))}")
                continue

        logger.debug(f"Found {len(interesting_events):,} interesting events")

        # Second pass: batch generate embeddings
        created_count = await _batch_create_embeddings(db, interesting_events, user_id, llm_config)

        # Ensure session is in clean state
        try:
            if created_count > 0:
                await db.commit()
            else:
                # No changes made, but ensure transaction is closed
                await db.rollback()
        except Exception as commit_error:
            logger.debug(f"Error finalizing transaction: {sanitize_log_message(str(commit_error))}")
            try:
                await db.rollback()
            except Exception as rollback_error:
                logger.debug(f"Rollback failed: {sanitize_log_message(str(rollback_error))}")

        logger.debug(
            f"Processed {len(events):,} events from artifact {artifact_id}: "
            f"{len(interesting_events):,} interesting, {created_count:,} embeddings created"
        )
        return created_count

    except Exception as e:
        # Rollback any partial changes on error
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.debug(f"Rollback failed: {sanitize_log_message(str(rollback_error))}")

        logger.error(f"Error processing interesting events for artifact {artifact_id}: {sanitize_log_message(str(e))}")
        raise  # Re-raise to let caller handle


__all__ = [
    "process_interesting_events",
]
