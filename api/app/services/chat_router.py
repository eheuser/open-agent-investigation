from typing import Dict, Any, AsyncIterator, Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from ..schemas.chat_message import IntentType, ClassificationResult
from ..schemas.routing_metadata import create_routing_metadata
from ..crud.llm_config import get_active_llm_config
from ..models.chat_history import ChatMessage
from .handlers.event_handler import handle_event_insertion
from .handlers.policy_handler import handle_policy_execution
from .handlers.timeline_handler import handle_timeline_query
from .handlers.general_chat_handler import handle_general_chat
from .handlers.rag_handler import handle_rag_query
from .query_expander import expand_query
from .llm_service import LLMService
from .context_manager import ChatContextManager
from .embedding_queue import get_embedding_status

from ..utils.log_setup import get_logger

logger = get_logger(__name__)


# Intent classification prompt - comprehensive forensics context
CLASSIFICATION_PROMPT_SYSTEM = """# SYSTEM CONTEXT

You are the query router for **Open Agent Investigation**, an AI-powered digital forensics platform for Windows artifact analysis.

## Platform Architecture

This platform analyzes Windows forensic artifacts to reconstruct security incidents:

**Data Sources (Artifacts)**:
- **EVTX Files** - Windows Event Logs (Security.evtx, System.evtx, etc.)
- **Registry Hives** - Windows Registry (SYSTEM, SOFTWARE, SAM, SECURITY, NTUSER.DAT)
- **MFT** - Master File Table ($MFT) - file system metadata
- **Prefetch Files** - Application execution artifacts (*.pf)
- **LNK Files** - Windows shortcuts with file access history

**Data Model**:
1. **Events Table** - Parsed forensic events from artifacts (login events, process creation, file modifications, registry changes, network connections)
   - Each event has: timestamp, event_type (e.g., "evtx_security_4624"), source_artifact, event_data (JSONB with event details)
   - Example event types: evtx_security_4624 (successful logon), evtx_security_4625 (failed logon), evtx_security_4688 (process creation), registry_key_modified, mft_file_created
   - Events are RAW FORENSIC DATA parsed from artifacts

2. **Timeline Entries Table** - Curated evidence timeline built by investigators
   - Timeline entries are MANUALLY SELECTED significant events
   - Each entry references an event_id (foreign key to Events table)
   - Timeline entries have: title, description, tags, significance, event_id
   - Timeline is the INVESTIGATION OUTPUT - the story being built
   - Timeline entries are FINDINGS, not raw data

**Key Distinction**:
- **Events** = Raw forensic data (thousands of events from logs/artifacts)
- **Timeline Entries** = Curated evidence (tens of entries selected for significance)

## Your Task: Intent Classification

Classify the user's query into ONE of these categories:

### 1. **insert_events**
User is providing RAW EVENT DATA to be inserted into the Events table (CSV, JSON, YAML, or natural language description of FORENSIC EVENTS)

**Examples**:
- "Add these login events: ..."
- "Here's some network traffic data: ..."
- "Insert event: user logged in at 10:30"
- "Parse this EVTX data: ..."

### 2. **timeline_query**
User wants to query, add, update, or delete **TIMELINE ENTRIES** (the curated evidence timeline)

**Timeline Operations**:
- Query timeline entries (filter by date, tags, significance)
- Add new timeline entry (create finding)
- Update existing timeline entry (edit title/description/tags)
- Delete timeline entry (remove finding)
- Get timeline statistics (count, date range)

**Examples**:
- "Show me timeline entries from March 20-24"
- "What's on the timeline tagged as suspicious?"
- "Add a timeline entry for this suspicious login"
- "Delete timeline entry 42"
- "Update timeline entry 15 to mark it as critical"
- "Timeline statistics"
- "What findings do we have so far?"
- "Show me high-significance timeline entries"

### 3. **general_chat**
User asks GENERAL QUESTIONS about investigation metadata (no database queries needed)

**Answers from context only** (investigation title, description, artifact count, timeline stats)

**Examples**:
- "What is this investigation about?"
- "How many timeline entries do we have?"
- "What data sources are available?"
- "Summarize the investigation"
- "What's the date range of our data?"
- "How many artifacts have been uploaded?"

### 4. **execute_agent_policy**
User requests SEARCHING/ANALYZING RAW EVENT DATA or COMPLEX FORENSIC ANALYSIS

**Uses agent with 11+ forensic query tools**:
- search_events_by_type - Find events by type (e.g., failed logons, process creation)
- search_events_by_timerange - Find events in time window
- search_events_by_jsonb_field - Search event_data JSON fields
- aggregate_jsonb_field - Aggregate patterns (e.g., count failed logins per user)
- query_jsonb_nested - Complex nested JSON queries
- register_timeline_entry - Auto-add significant events to timeline

**Examples**:
- "Find remote logons in the event data"
- "Search for failed login attempts"
- "Look for process creation events"
- "Analyze suspicious PowerShell activity"
- "What files were modified by user jsmith?"
- "Investigate lateral movement patterns"
- "Find all events from IP address 192.168.1.50"
- "Search for registry persistence mechanisms"
- "Identify brute force login attempts"

## Classification Rules

**Decision Tree**:
1. Is user providing raw data to insert? → **insert_events**
2. Is user asking about TIMELINE ENTRIES (add/query/update/delete findings)? → **timeline_query**
3. Is user asking simple metadata question (no database query)? → **general_chat**
4. Is user searching/analyzing RAW EVENTS or requesting complex analysis? → **execute_agent_policy**

**Key Distinctions**:
- "Show me timeline entries" → **timeline_query** (querying curated findings)
- "Find failed login events" → **execute_agent_policy** (searching raw event data)
- "How many timeline entries?" → **general_chat** (simple metadata from context)
- "Add a timeline entry" → **timeline_query** (creating a finding)
- "Search for suspicious activity" → **execute_agent_policy** (complex analysis of events)

## Classification Instructions

You will receive:
1. **Conversation History** (recent messages for context)
2. **Current User Query** (the message to classify)

Analyze the current query IN CONTEXT of the conversation history to determine the user's intent.

**Important**: Follow-up questions and pronoun references ("that", "those", "it", "them") should be interpreted based on conversation context.

## Your Response

Respond with ONLY the category name (insert_events, timeline_query, general_chat, or execute_agent_policy). No explanation, no punctuation, just the category name."""

# User message template for classification
CLASSIFICATION_USER_PROMPT = """## Conversation History

{chat_history}

## Current User Query

{query}

---

Classify the current user query based on the conversation context above."""


async def _fetch_recent_chat_history(
    db: AsyncSession, investigation_id: UUID, limit: int = 10
) -> List[Dict[str, str]]:
    """
    Fetch recent chat messages for a given investigation to provide context for downstream processing.

    Args:
        db: An active asynchronous SQLAlchemy session used to query the database.
        investigation_id: The unique identifier of the investigation whose chat history should be retrieved.
        limit: Optional maximum number of messages to return. Defaults to 10, returning the most recent messages up to this count.

    Returns:
        A list of dictionaries representing the chat history in chronological order (oldest first). Each dictionary contains two keys:
            - "role": The role of the message sender (e.g., "user" or "assistant").
            - "content": The textual content of the message, or "(no content)" if the stored content is empty.

    The function filters out messages that are marked as excluded from LLM context, soft-deleted, and orders them by creation timestamp before applying the limit. It then reverses the result to ensure chronological ordering.
    """
    # Fetch recent messages that should be included in LLM context
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.investigation_id == investigation_id)
        .where(ChatMessage.include_in_llm_context == True)
        .where(ChatMessage.deleted_at.is_(None))  # Exclude soft-deleted messages
        .order_by(desc(ChatMessage.created_at))
        .limit(limit)
    )

    messages = list(result.scalars().all())
    messages.reverse()  # Chronological order (oldest first)

    # Convert to simple format for classification prompt
    history = []
    for msg in messages:
        history.append({"role": msg.role, "content": msg.content or "(no content)"})

    return history


async def classify_intent(
    db: AsyncSession,
    user_id: int,
    investigation_id: UUID,
    user_query: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    allow_rag: bool = True,
) -> ClassificationResult:
    """
    Classify a user query into an intent type using an LLM or heuristic fallback.

    Args:
        db: An asynchronous SQLAlchemy session used to retrieve configuration and chat history.
        user_id: Identifier of the user whose LLM settings should be applied.
        investigation_id: Unique identifier of the investigation, used when fetching recent conversation context.
        user_query: The raw natural-language input provided by the user.
        chat_history: Optional list of previously exchanged messages (each a dict with `role` and `content`). If omitted, the function fetches up to ten recent messages for the given investigation.

    Returns:
        A :class:`ClassificationResult` instance containing the detected :class:`IntentType` and an associated confidence score.

    Raises:
        None. All errors are caught internally; on failure the function falls back to a heuristic classifier and returns its result.
    """
    # Check if RAG mode should be available
    if allow_rag:
        # Check if embeddings are still being generated
        embedding_status = await get_embedding_status(db, investigation_id)
        if not embedding_status["is_complete"]:
            allow_rag = False
            logger.debug(f"[CHAT_ROUTER] RAG mode disabled - embeddings pending ({embedding_status['total_pending_events']} events)")
    
    # Fetch chat history if not provided
    if chat_history is None:
        chat_history = await _fetch_recent_chat_history(db, investigation_id, limit=10)

    # Format chat history for prompt
    if chat_history:
        history_text = "\n".join(
            [
                f"{msg['role'].upper()}: {msg['content'][:200]}{'...' if len(msg['content']) > 200 else ''}"
                for msg in chat_history[-5:]  # Last 5 messages for context
            ]
        )
    else:
        history_text = "(No previous conversation)"

    # Create LLM service from user config
    llm_service = await LLMService.from_user_config(db, user_id)

    if not llm_service:
        # Fallback: use simple heuristics (without context)
        return _fallback_classification(user_query)

    try:
        # Prepare classification context using context manager
        messages = ChatContextManager.prepare_classification_context(
            system_prompt=CLASSIFICATION_PROMPT_SYSTEM,
            user_query=user_query,
            chat_history=chat_history,
            max_history_messages=5,
        )

        # Call LLM via centralized service
        data = await llm_service.call_llm(
            messages=messages,
            max_tokens=150,  # Fixed for classification
            temperature=0.1,  # Low temperature for consistent classification
            enforce_context_limit=False,  # Already managed by context manager
        )

        # Extract response text
        response_text = await llm_service.extract_text_response(data)

        if not response_text:
            return _fallback_classification(user_query)

        response_text = str(response_text).strip().lower()

        # Map response to intent
        if "insert_events" in response_text or "insert" in response_text:
            return ClassificationResult(intent=IntentType.INSERT_EVENTS, confidence=0.9)
        elif "timeline_query" in response_text or "timeline" in response_text:
            return ClassificationResult(intent=IntentType.TIMELINE_QUERY, confidence=0.9)
        elif "general_chat" in response_text or "general" in response_text:
            return ClassificationResult(intent=IntentType.GENERAL_CHAT, confidence=0.9)
        elif "execute_agent_policy" in response_text or "execute" in response_text:
            return ClassificationResult(intent=IntentType.EXECUTE_POLICY, confidence=0.9)
        else:
            return _fallback_classification(user_query)

    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        return _fallback_classification(user_query)


def _fallback_classification(user_query: str) -> ClassificationResult:
    """
    Fallback classification using simple keyword heuristics when an LLM is unavailable.

    Args:
        user_query (str): The raw query string provided by the user.

    Returns:
        ClassificationResult: An object describing the inferred intent, a confidence score, and a short reasoning message. The intent will be one of the IntentType enum values (TIMELINE_QUERY, GENERAL_CHAT, EXECUTE_POLICY, or INSERT_EVENTS) based on keyword matches and simple question analysis.
    """
    query_lower = user_query.lower()

    # Check for TIMELINE keywords FIRST
    timeline_keywords = [
        "timeline entry",
        "timeline entries",
        "on the timeline",
        "add timeline",
        "delete timeline",
        "update timeline",
        "timeline stats",
        "timeline statistics",
    ]
    if any(kw in query_lower for kw in timeline_keywords):
        return ClassificationResult(
            intent=IntentType.TIMELINE_QUERY, confidence=0.9, reasoning="Timeline operation"
        )

    # Check for GENERAL CHAT keywords (metadata questions)
    general_keywords = [
        "what is this investigation",
        "what's this investigation",
        "how many timeline",
        "how many events",
        "how many artifacts",
        "summarize",
        "summary",
        "what data",
        "available data",
        "date range",
        "time range of data",
    ]
    if any(kw in query_lower for kw in general_keywords):
        return ClassificationResult(
            intent=IntentType.GENERAL_CHAT, confidence=0.85, reasoning="General question"
        )

    # Check for EVENT SEARCH keywords (these need Agent)
    event_search_keywords = [
        "find",
        "search",
        "look for",
        "locate",
        "discover",
        "failed login",
        "logon",
        "process creation",
        "powershell",
        "registry",
        "file modification",
        "network connection",
        "analyze",
        "investigate",
    ]
    if any(kw in query_lower for kw in event_search_keywords):
        return ClassificationResult(
            intent=IntentType.EXECUTE_POLICY,
            confidence=0.85,
            reasoning="Event search: requires agent",
        )

    # Check for event insertion keywords (structured data)
    insert_keywords = [
        "add event",
        "insert event",
        "paste",
        "import",
        "upload data",
        "here's",
        "here is",
    ]
    if any(kw in query_lower for kw in insert_keywords):
        return ClassificationResult(
            intent=IntentType.INSERT_EVENTS, confidence=0.8, reasoning="Event insertion"
        )

    # Check for question words - route to general chat if simple, agent if complex
    question_starters = ["what", "which", "who", "when", "where", "how many"]
    if any(query_lower.startswith(kw) for kw in question_starters):
        # Simple metadata questions go to general chat
        if any(kw in query_lower for kw in ["how many", "what is", "what's"]):
            return ClassificationResult(
                intent=IntentType.GENERAL_CHAT, confidence=0.7, reasoning="Simple question"
            )
        # Complex questions need agent
        return ClassificationResult(
            intent=IntentType.EXECUTE_POLICY, confidence=0.75, reasoning="Complex question"
        )

    # Default to general chat for safety (less expensive than agent)
    return ClassificationResult(
        intent=IntentType.GENERAL_CHAT, confidence=0.6, reasoning="Default: general chat"
    )


async def route_chat_message(
    db: AsyncSession,
    investigation_id: UUID,
    user_query: str,
    user_id: int,
    effort: str = "medium",
    router_mode: str = "auto",
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Main routing coroutine for incoming chat messages.

    Processes a user query by optionally expanding it, classifying its intent, and delegating execution to one of several specialized handlers. The function supports explicit mode overrides (augmented, agent, timeline) that bypass automatic classification, and yields incremental response objects suitable for streaming over a WebSocket connection.

    Args:
        db: An active asynchronous SQLAlchemy session used for all database interactions.
        investigation_id: Unique identifier of the investigation context in which the query is executed.
        user_query: Raw natural-language input supplied by the end-user.
        user_id: Identifier of the user issuing the query; used for audit logging and permission checks.
        effort: Desired level of computational effort for agent execution (default "medium"). Accepted values are "low", "medium", or "high".
        router_mode: Optional override that forces routing to a specific handler. Valid options are:
            - "auto": Perform normal intent classification (default).
            - "augmented": Directly invoke the RAG-based chat handler; requires an embedding provider to be configured.
            - "agent": Bypass classification and run the policy execution agent.
            - "timeline": Bypass classification and run the timeline CRUD handler.
        chat_history: Optional list of prior message dictionaries (each with keys “role” and “content”) providing conversational context. If omitted, recent history is fetched from the database.

    Yields:
        Dict objects representing incremental messages to be sent to the client. The dictionary always contains a "type" key indicating the payload kind; possible types include:

        - "error": An error occurred (e.g., missing embedding configuration or unknown intent). Contains a "message" field and optionally "details".
        - "query_expanded": Indicates that the original query was automatically expanded. Includes "original" and "expanded" fields.
        - "intent_classified": Reports the result of intent classification with "intent" (string) and "confidence" (float).
        - "answer_chunk": A fragment of the final answer. Fields: "content" (text), "chunk_id" (int, starting at 0), and "is_final" (bool). May be emitted multiple times for streamed responses.
        - Other custom types produced by specific handlers (e.g., tool execution results).

    Raises:
        No exceptions are propagated to the caller; all errors are captured, logged, and yielded as an "error" message with optional diagnostic information.
    """
    logger.info(f"[CHAT_ROUTER] Routing query: {user_query[:100]}... (mode={router_mode})")

    # Step 0: Handle router mode override
    if router_mode == "augmented":
        logger.info("[CHAT_ROUTER] → Route OVERRIDE: Augmented Chat Handler (user-selected)")
        # Check if embeddings are configured
        llm_config = await get_active_llm_config(db, user_id)
        if not llm_config or not getattr(llm_config, "embedding_provider", None):
            yield {
                "type": "error",
                "message": "Augmented Chat mode requires embedding configuration. Please configure an embedding provider in LLM settings or use 'Auto', 'Agent', or 'Timeline' mode.",
            }
            return
        
        # Check if embeddings are still being generated
        embedding_status = await get_embedding_status(db, investigation_id)
        if not embedding_status["is_complete"]:
            pending_events = embedding_status["total_pending_events"]
            yield {
                "type": "error",
                "message": f"Augmented Chat mode is unavailable while embeddings are being generated ({pending_events:,} events pending). Please wait for embedding to complete or use 'Auto', 'Agent', or 'Timeline' mode.",
            }
            return
        
        # The chat handler will persist tool executions after the message is created
        async for chunk in handle_rag_query(db, investigation_id, user_query, user_id):
            yield chunk
        return
    elif router_mode == "agent":
        logger.info("[CHAT_ROUTER] → Route OVERRIDE: Agent Handler (user-selected)")
        result = await handle_policy_execution(
            db, investigation_id, user_query, user_id, effort=effort
        )
        yield result
        return
    elif router_mode == "timeline":
        logger.info("[CHAT_ROUTER] → Route OVERRIDE: Timeline Handler (user-selected)")
        result = await handle_timeline_query(db, investigation_id, user_query, user_id)
        if result.get("success"):
            message = result.get("message", "")
            summary = result.get("summary", "")
            if summary:
                message += f"\n\n---\n📊 {summary}"
            yield {
                "type": "answer_chunk", 
                "content": message, 
                "chunk_id": 0, 
                "is_final": True,
                "metadata": {
                    "routing_metadata": result.get("routing_metadata"),
                },
            }
        else:
            yield result
        return

    # Step 1: Fetch chat history for context (if not provided)
    if chat_history is None:
        chat_history = await _fetch_recent_chat_history(db, investigation_id, limit=10)
        logger.info(f"[CHAT_ROUTER] Fetched {len(chat_history):,} messages for context")

    # Step 2: Expand query with context (for short/curt queries)
    expanded_query = await expand_query(db, investigation_id, user_query, user_id)
    if expanded_query != user_query:
        logger.info(
            f"[CHAT_ROUTER] Query expanded: {user_query[:50]}... -> {expanded_query[:100]}..."
        )
        yield {
            "type": "query_expanded",
            "original": user_query,
            "expanded": expanded_query,
        }

    # Use expanded query for all downstream processing
    processing_query = expanded_query

    # Check if RAG mode should be available (for auto classification)
    allow_rag = True
    if router_mode == "auto":
        # Check if embeddings are still being generated
        embedding_status = await get_embedding_status(db, investigation_id)
        if not embedding_status["is_complete"]:
            allow_rag = False
            logger.debug(f"[CHAT_ROUTER] RAG mode disabled for auto classification - embeddings pending ({embedding_status['total_pending_events']} events)")

    # Step 3: Classify intent with conversation context
    classification = await classify_intent(
        db=db,
        user_id=user_id,
        investigation_id=investigation_id,
        user_query=processing_query,
        chat_history=chat_history,
        allow_rag=allow_rag,
    )
    logger.info(
        f"[CHAT_ROUTER] Classified as: {classification.intent.value} (confidence: {classification.confidence})"
    )

    # Emit classification result with routing decision
    routing_decision = {
        "type": "intent_classified",
        "intent": classification.intent.value,
        "confidence": classification.confidence,
        "router_mode": router_mode,
        "query_expanded": expanded_query != user_query,
    }
    yield routing_decision

    # Step 4: Route to appropriate handler (EXPLICIT ROUTING)
    try:
        if classification.intent == IntentType.INSERT_EVENTS:
            logger.info(f"[CHAT_ROUTER] → Route 1: Event Insertion Handler")
            result = await handle_event_insertion(db, investigation_id, processing_query, user_id)

            if result.get("success"):
                yield {
                    "type": "answer_chunk",
                    "content": result.get("message", "Events inserted successfully."),
                    "chunk_id": 0,
                    "is_final": True,
                }
            else:
                yield result

        elif classification.intent == IntentType.TIMELINE_QUERY:
            logger.info(f"[CHAT_ROUTER] → Route 2: Timeline Handler")
            result = await handle_timeline_query(db, investigation_id, processing_query, user_id)

            # Send result as answer with summary
            if result.get("success"):
                message = result.get("message", "")
                summary = result.get("summary", "")

                # Add summary footer if available
                if summary:
                    message += f"\n\n---\n📊 {summary}"

                yield {
                    "type": "answer_chunk", 
                    "content": message, 
                    "chunk_id": 0, 
                    "is_final": True,
                    "metadata": {
                        "routing_metadata": result.get("routing_metadata"),
                    },
                }
            else:
                yield result

        elif classification.intent == IntentType.GENERAL_CHAT:
            logger.info(f"[CHAT_ROUTER] → Route 3: General Chat Handler")
            result = await handle_general_chat(db, investigation_id, processing_query, user_id)

            if result.get("success"):
                yield {
                    "type": "answer_chunk",
                    "content": result.get("message", ""),
                    "chunk_id": 0,
                    "is_final": True,
                    "metadata": {
                        "routing_metadata": result.get("routing_metadata"),
                    },
                }
            else:
                yield result

        elif classification.intent == IntentType.EXECUTE_POLICY:
            logger.info(f"[CHAT_ROUTER] → Route 4: Agent Handler (effort={effort})")
            result = await handle_policy_execution(
                db, investigation_id, processing_query, user_id, effort=effort
            )
            
            # Check if parsing is in progress
            if result.get("type") == "parsing_in_progress":
                logger.info(f"[CHAT_ROUTER] Parsing in progress, delaying agent execution")
                yield {
                    "type": "answer_chunk",
                    "content": result.get("message", "Waiting for parsing to complete..."),
                    "chunk_id": 0,
                    "is_final": True,
                    "metadata": {
                        "parsing_in_progress": True,
                        "active_jobs": result.get("active_jobs", 0),
                    },
                }
            else:
                yield result

        elif classification.intent == IntentType.QUERY_KG:
            logger.warning(f"[CHAT_ROUTER] KG query deprecated - routing to general chat")
            result = await handle_general_chat(db, investigation_id, processing_query, user_id)
            if result.get("success"):
                yield {
                    "type": "answer_chunk",
                    "content": result.get("message", ""),
                    "chunk_id": 0,
                    "is_final": True,
                }
            else:
                yield result

        elif classification.intent == IntentType.MUTATE_KG:
            logger.warning(f"[CHAT_ROUTER] KG mutation deprecated - routing to timeline handler")
            result = await handle_timeline_query(db, investigation_id, processing_query, user_id)
            if result.get("success"):
                yield {
                    "type": "answer_chunk",
                    "content": result.get("message", ""),
                    "chunk_id": 0,
                    "is_final": True,
                }
            else:
                yield result

        else:
            logger.error(f"[CHAT_ROUTER] Unknown intent: {classification.intent}")
            yield {
                "type": "error",
                "message": f"Unknown intent type: {classification.intent.value}",
            }

    except Exception as e:
        logger.error(f"[CHAT_ROUTER] Error: {e}", exc_info=True)
        yield {
            "type": "error",
            "message": f"Error processing query: {str(e)}",
            "details": classification.reasoning,
        }

    logger.info(f"[CHAT_ROUTER] Routing complete")


async def handle_clarification_response(
    db: AsyncSession,
    investigation_id: UUID,
    policy_id: str,
    rule_values: Dict[str, Any],
    original_question: str,
    user_id: int,
) -> Dict[str, Any]:
    """
    Handle a user's clarification response for policy rule evaluation.

    This function forwards the original question together with the user-provided rule values to the policy routing
    logic, captures any errors that occur during routing, logs relevant diagnostic information, and returns the
    routing result.

    Args:
        db: An active asynchronous SQLAlchemy session used by the routing layer.
        investigation_id: The unique identifier of the investigation associated with the request.
        policy_id: Identifier of the policy that prompted the clarification step.
        rule_values: A mapping of rule names to the values supplied by the user in response to the clarification
            prompt.
        original_question: The initial question asked by the user before clarification was required.
        user_id: Numeric identifier of the user submitting the clarification.

    Returns:
        dict: A dictionary describing the outcome of the routing operation.  On success it contains whatever
        structure `route_question` returns (e.g., a job queue acknowledgement).  If an error occurs, the
        dictionary has the form `{"type": "error", "message": <human-readable message>}`.

    Raises:
        None.  All exceptions are caught internally; unexpected errors result in an error dictionary being
        returned after logging the exception details.
    """
    from .policy_router import route_question

    try:
        result = await route_question(
            db=db,
            investigation_id=investigation_id,
            question=original_question,
            user_id=user_id,
            policy_id=policy_id,
            rule_values=rule_values,
        )

        if result.get("type") == "error":
            logger.error(
                f"Policy routing error in clarification for investigation {investigation_id}: "
                f"policy={policy_id}, error={result.get('message')}"
            )

        return result
    except Exception as e:
        logger.error(
            f"Unexpected error in handle_clarification_response for investigation {investigation_id}: {e}",
            exc_info=True,
        )
        return {
            "type": "error",
            "message": "An error occurred while processing your request. Please try again.",
        }


__all__ = [
    "classify_intent",
    "route_chat_message",
    "handle_clarification_response",
]
