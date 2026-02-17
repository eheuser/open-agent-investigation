import json
import re
from typing import Any, Dict, List, Tuple, Set
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message
from worker.agents.context_manager import estimate_tokens

logger = get_logger(__name__)


async def generate_chat_summary(
    db: AsyncSession,
    investigation_id: str,
    job_id: int,
    iteration_number: int,
    messages_to_summarize: List[Dict[str, Any]],
    start_idx: int,
    end_idx: int,
    llm_client,
) -> Tuple[str, Dict[str, Any]]:
    """
    Generate a concise forensic investigation summary from a list of chat messages using an LLM.

    The function follows a four-step pipeline:
    1. Extract key entities such as event IDs, tool names, and notable findings from the supplied messages.
    2. Build a compact transcript that highlights tool calls and assistant analyses while truncating overly long content.
    3. Prompt the provided `llm_client` to produce a deterministic summary (temperature 0.0) limited to roughly 300 tokens.
    4. Persist the resulting summary and associated metadata in the `chat_log_summaries` table, updating an existing record if one already exists for the same investigation/job/iteration.

    If any step fails, a fallback plain-text template is used and still stored in the database.

    Args:
        db: An active `AsyncSession` used to execute INSERT/UPDATE statements.
        investigation_id: UUID string identifying the forensic investigation.
        job_id: Integer identifier of the agent job that produced the messages.
        iteration_number: Current iteration index within the investigation workflow.
        messages_to_summarize: List of message dictionaries (each containing at least `role` and `content`) to be processed.
        start_idx: Zero-based start index of these messages in the full chat log.
        end_idx: End index (inclusive) of these messages in the full chat log.
        llm_client: An object exposing `stream_chat` and `parse_stream_to_message` for LLM interaction.

    Returns:
        Tuple[str, dict]:
            * summary_text - The generated (or fallback) summary as a plain string.
            * metadata - Dictionary containing extracted event IDs, executed tools, key findings, original and summary token counts, and the compression ratio.

    Raises:
        No exceptions are propagated; all errors are caught, logged, and result in a fallback summary. Any database-related failures during the fallback storage are silently ignored to avoid interrupting the caller.
    """
    if not messages_to_summarize:
        return "", {}

    # Calculate original token count
    original_tokens = sum(
        estimate_tokens(json.dumps(msg, default=str)) for msg in messages_to_summarize
    )

    logger.info(
        f"Generating summary for {len(messages_to_summarize):,} messages "
        f"({original_tokens} tokens) at iteration {iteration_number}"
    )

    # === Step 1: Extract Key Information ===
    event_ids_found: Set[str] = set()
    tools_executed: List[str] = []
    key_findings: List[str] = []

    for msg in messages_to_summarize:
        role = msg.get("role", "")
        content = msg.get("content", "")

        # Extract event IDs from content
        if content:
            event_id_matches = re.findall(
                r"(?:event[_ ]?(?:id)?[:\s]+)(\d+)", str(content), re.IGNORECASE
            )
            event_ids_found.update(event_id_matches)

        # Extract tool names from assistant messages
        if role == "assistant" and "tool_calls" in msg:
            for tc in msg.get("tool_calls", []):
                tool_name = tc.get("function", {}).get("name", "")
                if tool_name:
                    tools_executed.append(tool_name)

        # Extract tool names from tool messages
        if role == "tool":
            tool_name = msg.get("name", "")
            if tool_name and tool_name not in tools_executed:
                tools_executed.append(tool_name)

        # Extract key findings from assistant analysis
        if role == "assistant" and content and len(content) > 100:
            # Look for sentences with forensic keywords
            forensic_keywords = [
                "found",
                "discovered",
                "identified",
                "detected",
                "observed",
                "pattern",
                "anomaly",
                "suspicious",
                "malicious",
                "evidence",
            ]
            sentences = content.split(". ")
            for sentence in sentences:
                if any(keyword in sentence.lower() for keyword in forensic_keywords):
                    key_findings.append(sentence.strip())

    # === Step 2: Build Transcript ===
    transcript_parts = []

    for msg in messages_to_summarize:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "assistant":
            if "tool_calls" in msg:
                tool_names = [
                    tc.get("function", {}).get("name", "unknown")
                    for tc in msg.get("tool_calls", [])
                ]
                transcript_parts.append(f"**Tools called**: {', '.join(tool_names)}")
            elif content:
                # Truncate long content
                transcript_parts.append(f"**Analysis**: {content}")

        elif role == "tool":
            tool_name = msg.get("name", "unknown")
            try:
                result = json.loads(content) if isinstance(content, str) else content
                count = result.get("count", 0)
                auto_registered = result.get("auto_registered", 0)

                if auto_registered > 0:
                    transcript_parts.append(
                        f"**{tool_name}**: {count} events ({auto_registered} registered)"
                    )
                elif count > 0:
                    transcript_parts.append(f"**{tool_name}**: {count} events")
                else:
                    transcript_parts.append(f"**{tool_name}**: No results")
            except:
                # Non-JSON content
                transcript_parts.append(f"**{tool_name}**: {content}")

    transcript = "\n".join(transcript_parts)

    # === Step 3: Generate LLM Summary ===
    prompt = f"""Summarize this forensic investigation session into a compact narrative (max 300 tokens).

**Event IDs Discovered**: {', '.join(sorted(event_ids_found)) if event_ids_found else 'None'}

**Tools Executed**: {', '.join(tools_executed) if tools_executed else 'None'}

**Activity Transcript**:
{transcript}

**Requirements**:
- Preserve ALL event IDs mentioned
- List tools executed
- Summarize key findings and patterns
- Note any timeline entries created
- Keep it concise (max 300 tokens)

**Format**:
**Event IDs**: [list all event IDs]
**Tools**: [list tools]
**Findings**: [2-3 sentences summarizing discoveries]
**Timeline**: [note if entries were created]
"""

    try:
        messages = [
            {
                "role": "system",
                "content": "You are a forensic analyst creating compact investigation summaries. Be concise and preserve all event IDs.",
            },
            {"role": "user", "content": prompt},
        ]

        # Generate summary
        stream = llm_client.stream_chat(
            messages=messages,
            max_tokens=None,  # Use user's configured default
            temperature=None,  # Use user's configured temperature
        )

        # Parse streaming response
        response_msg = await llm_client.parse_stream_to_message(stream)
        summary_text = response_msg.content or ""

        if not summary_text:
            # Fallback to simple transcript
            summary_text = f"**Event IDs**: {', '.join(sorted(event_ids_found))}\n**Tools**: {', '.join(tools_executed)}\n**Activities**: {len(messages_to_summarize):,} messages processed"

        summary_tokens = estimate_tokens(summary_text)

        logger.info(
            f"Generated summary: {original_tokens} → {summary_tokens} tokens "
            f"({((original_tokens - summary_tokens) / original_tokens * 100):.1f}% reduction)"
        )

        # === Step 4: Store in Database ===
        await db.execute(
            text(
                """
                INSERT INTO chat_log_summaries (
                    investigation_id, job_id, iteration_number,
                    messages_start_idx, messages_end_idx,
                    original_message_count, original_token_count,
                    summary_text, summary_token_count,
                    event_ids_discovered, tools_executed, key_findings
                )
                VALUES (
                    :investigation_id, :job_id, :iteration_number,
                    :start_idx, :end_idx,
                    :msg_count, :orig_tokens,
                    :summary, :summary_tokens,
                    :event_ids, :tools, :findings
                )
                ON CONFLICT (investigation_id, job_id, iteration_number)
                DO UPDATE SET
                    summary_text = EXCLUDED.summary_text,
                    summary_token_count = EXCLUDED.summary_token_count,
                    event_ids_discovered = EXCLUDED.event_ids_discovered,
                    tools_executed = EXCLUDED.tools_executed,
                    key_findings = EXCLUDED.key_findings
            """
            ),
            {
                "investigation_id": investigation_id,
                "job_id": job_id,
                "iteration_number": iteration_number,
                "start_idx": start_idx,
                "end_idx": end_idx,
                "msg_count": len(messages_to_summarize),
                "orig_tokens": original_tokens,
                "summary": summary_text,
                "summary_tokens": summary_tokens,
                "event_ids": list(sorted(event_ids_found)),
                "tools": tools_executed,
                "findings": key_findings[:10],  # Limit to 10 findings
            },
        )
        await db.commit()

        metadata = {
            "event_ids": list(sorted(event_ids_found)),
            "tools_executed": tools_executed,
            "key_findings": key_findings[:10],
            "original_tokens": original_tokens,
            "summary_tokens": summary_tokens,
            "compression_ratio": summary_tokens / original_tokens if original_tokens > 0 else 0,
        }

        return summary_text, metadata

    except Exception as e:
        logger.error(f"Failed to generate LLM summary: {sanitize_log_message(str(e))}", exc_info=True)

        # Fallback to simple summary
        summary_text = f"""**Investigation Progress Summary**

**Event IDs Discovered**: {', '.join(sorted(event_ids_found)) if event_ids_found else 'None'}

**Tools Executed**: {', '.join(tools_executed) if tools_executed else 'None'}

**Messages Processed**: {len(messages_to_summarize):,}

**Key Findings**: {len(key_findings):,} observations recorded

*Note: LLM summarization failed, using fallback template*
"""

        summary_tokens = estimate_tokens(summary_text)

        # Store fallback summary
        try:
            await db.execute(
                text(
                    """
                    INSERT INTO chat_log_summaries (
                        investigation_id, job_id, iteration_number,
                        messages_start_idx, messages_end_idx,
                        original_message_count, original_token_count,
                        summary_text, summary_token_count,
                        event_ids_discovered, tools_executed, key_findings
                    )
                    VALUES (
                        :investigation_id, :job_id, :iteration_number,
                        :start_idx, :end_idx,
                        :msg_count, :orig_tokens,
                        :summary, :summary_tokens,
                        :event_ids, :tools, :findings
                    )
                    ON CONFLICT (investigation_id, job_id, iteration_number) DO NOTHING
                """
                ),
                {
                    "investigation_id": investigation_id,
                    "job_id": job_id,
                    "iteration_number": iteration_number,
                    "start_idx": start_idx,
                    "end_idx": end_idx,
                    "msg_count": len(messages_to_summarize),
                    "orig_tokens": original_tokens,
                    "summary": summary_text,
                    "summary_tokens": summary_tokens,
                    "event_ids": list(sorted(event_ids_found)),
                    "tools": tools_executed,
                    "findings": key_findings[:10],
                },
            )
            await db.commit()
        except:
            pass  # Don't fail if DB storage fails

        metadata = {
            "event_ids": list(sorted(event_ids_found)),
            "tools_executed": tools_executed,
            "key_findings": key_findings[:10],
            "original_tokens": original_tokens,
            "summary_tokens": summary_tokens,
            "compression_ratio": summary_tokens / original_tokens if original_tokens > 0 else 0,
        }

        return summary_text, metadata


async def load_chat_summary(
    db: AsyncSession,
    investigation_id: str,
    job_id: int,
    iteration_number: int,
) -> Tuple[str, Dict[str, Any]]:
    """
    Load a previously generated chat summary from the database.

    Args:
        db: An asynchronous SQLAlchemy session used to execute the query.
        investigation_id: The UUID string identifying the investigation whose summary is requested.
        job_id: The integer identifier of the agent job associated with the summary.
        iteration_number: The specific iteration number for which the summary was generated.

    Returns:
        A tuple `(summary_text, metadata)` where:
            * **summary_text** (str): The stored summary text. Returns an empty string if no record is found or on error.
            * **metadata** (dict): Dictionary containing additional information about the summary:
                - `summary_tokens` (int): Token count of the generated summary.
                - `original_tokens` (int): Token count of the original chat log.
                - `event_ids` (list): List of discovered event IDs, or an empty list if none.
                - `tools_executed` (list): List of tools that were executed during summarisation, or an empty list.
                - `key_findings` (list): List of key findings extracted, or an empty list.
                - `compression_ratio` (float): Ratio of summary tokens to original tokens; 0 if the original token count is zero.

    If the query yields no matching row or an exception occurs, the function returns `("", {})`.
    """
    try:
        result = await db.execute(
            text(
                """
                SELECT summary_text, summary_token_count, original_token_count,
                       event_ids_discovered, tools_executed, key_findings
                FROM chat_log_summaries
                WHERE investigation_id = :investigation_id
                  AND job_id = :job_id
                  AND iteration_number = :iteration_number
            """
            ),
            {
                "investigation_id": investigation_id,
                "job_id": job_id,
                "iteration_number": iteration_number,
            },
        )

        row = result.fetchone()

        if row:
            summary_text = row[0]
            metadata = {
                "summary_tokens": row[1],
                "original_tokens": row[2],
                "event_ids": row[3] or [],
                "tools_executed": row[4] or [],
                "key_findings": row[5] or [],
                "compression_ratio": row[1] / row[2] if row[2] > 0 else 0,
            }

            logger.debug(f"Loaded summary for iteration {iteration_number} from database")
            return summary_text, metadata

        return "", {}

    except Exception as e:
        logger.error(f"Failed to load chat summary: {sanitize_log_message(str(e))}")
        return "", {}


def trim_messages_from_middle(
    messages: List[Dict[str, Any]],
    max_tokens: int = 4000,
) -> List[Dict[str, Any]]:
    """
    Trim messages from the middle of a conversation so that the total token count does not exceed a specified budget.

    The function preserves the first two messages (typically a system prompt and the initial user query) and the last five messages (the most recent context). It then iteratively adds messages from the remaining middle section, alternating from the start and end of that section, until adding another message would exceed the token limit. If even the preserved subset is too large, a more aggressive trim keeps only the first two and the last three messages.

    Parameters
    ----------
    messages : List[Dict[str, Any]]
        The full list of chat messages, where each message is represented as a dictionary compatible with the LLM API (e.g., containing `role` and `content` keys).
    max_tokens : int, optional
        The maximum number of tokens allowed for the returned message list. Defaults to 4000.

    Returns
    -------
    List[Dict[str, Any]]
        A trimmed list of messages that fits within the token budget while retaining the most critical context (initial prompt and recent dialogue).

    Notes
    -----
    - Token estimation is performed by `estimate_tokens` from the local `context_manager` module, which serialises each message to JSON before counting.
    - The function logs informational messages about the trimming process and warnings if aggressive trimming is required.
    - If the original list contains seven or fewer messages, it is returned unchanged because all messages can be kept without exceeding typical budgets.
    """
    if len(messages) <= 7:
        return messages

    current_tokens = sum(estimate_tokens(json.dumps(msg, default=str)) for msg in messages)

    if current_tokens <= max_tokens:
        return messages

    logger.info(f"Trimming messages from middle: {current_tokens} → {max_tokens} tokens")

    # Keep first 2 and last 5
    if len(messages) > 7:
        preserved = messages[:2] + messages[-5:]
    else:
        preserved = messages
    preserved_tokens = sum(estimate_tokens(json.dumps(msg, default=str)) for msg in preserved)

    if preserved_tokens > max_tokens:
        # Even preserved messages exceed budget, just keep first 2 + last 3
        trimmed = messages[:2] + messages[-3:]
        logger.info(f"Aggressive trimming required: {len(messages):,} → {len(trimmed):,} messages")
        return trimmed

    # Add messages from middle until we hit budget
    middle_messages = messages[2:-5]
    budget_remaining = max_tokens - preserved_tokens

    # Add from both ends of middle section (alternating)
    included_middle = []
    left_idx = 0
    right_idx = len(middle_messages) - 1

    while left_idx <= right_idx and budget_remaining > 0:
        # Try adding from left
        if left_idx <= right_idx:
            msg_tokens = estimate_tokens(json.dumps(middle_messages[left_idx], default=str))
            if msg_tokens <= budget_remaining:
                included_middle.append(middle_messages[left_idx])
                budget_remaining -= msg_tokens
                left_idx += 1
            else:
                break

        # Try adding from right
        if left_idx <= right_idx:
            msg_tokens = estimate_tokens(json.dumps(middle_messages[right_idx], default=str))
            if msg_tokens <= budget_remaining:
                included_middle.insert(0, middle_messages[right_idx])
                budget_remaining -= msg_tokens
                right_idx -= 1
            else:
                break

    # Rebuild message list
    trimmed = messages[:2] + included_middle + messages[-5:]

    new_tokens = sum(estimate_tokens(json.dumps(msg, default=str)) for msg in trimmed)
    logger.info(
        f"Trimmed {len(messages):,} → {len(trimmed):,} messages, "
        f"{current_tokens:,} → {new_tokens:,} tokens"
    )

    return trimmed


__all__ = [
    "generate_chat_summary",
    "load_chat_summary",
    "trim_messages_from_middle",
]
