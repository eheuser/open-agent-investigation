from typing import Dict, Any, List, Optional
from datetime import datetime
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..utils.log_setup import get_logger

logger = get_logger(__name__)


async def generate_investigation_report(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    user_prompt: Optional[str] = None,
    llm_client=None,
) -> Dict[str, Any]:
    """
    Generate a comprehensive forensic investigation report in markdown format.

    The function gathers all relevant data for a given investigation-including metadata, artifacts, timeline entries, and event statistics-optionally enriches the content with an LLM-generated narrative, and assembles a structured markdown document. The resulting dictionary contains the rendered markdown together with summary metadata useful for downstream processing or storage.

    Args:
        db (AsyncSession): An active asynchronous SQLAlchemy session used to query investigation data.
        investigation_id (UUID): Unique identifier of the investigation to report on.
        user_id (int): Identifier of the requesting user; currently passed through to the LLM client for configuration or auditing purposes.
        user_prompt (Optional[str]): Optional free-form prompt supplied by the user to influence the tone, focus, or style of the LLM-generated narrative. If omitted, a default narrative is used.
        llm_client (optional): An initialized LLM client capable of asynchronous text generation. When `None` the function falls back to a minimal placeholder narrative.

    Returns:
        dict: A mapping with the following keys:
            * `markdown` (str): The full investigation report rendered in markdown.
            * `title` (str): Title of the investigated case.
            * `generated_at` (str): ISO-8601 timestamp indicating when the report was created.
            * `artifacts_count` (int): Number of artifacts included in the report.
            * `timeline_entries_count` (int): Number of timeline entries processed.
            * `event_types_count` (int): Count of distinct event types summarized.

    Raises:
        None explicitly; if the investigation cannot be found, a dictionary containing an `error` key is returned instead of the full report.
    """
    logger.info(f"Generating report for investigation {investigation_id}")

    # === Step 1: Gather Investigation Data ===

    # Get investigation metadata
    inv_result = await db.execute(
        text(
            """
            SELECT title, created_at, owner_user_id
            FROM investigations
            WHERE investigation_id = :inv_id
        """
        ),
        {"inv_id": str(investigation_id)},
    )
    inv_row = inv_result.fetchone()

    if not inv_row:
        return {"error": "Investigation not found"}

    inv_title = inv_row[0]
    inv_created = inv_row[1]

    # Get artifacts
    artifacts_result = await db.execute(
        text(
            """
            SELECT artifact_id, filename, classification, upload_ts, 
                   length(blob) as size_bytes, encode(sha256, 'hex') as sha256_hex
            FROM artifacts
            WHERE investigation_id = :inv_id
            ORDER BY upload_ts
        """
        ),
        {"inv_id": str(investigation_id)},
    )
    artifacts = [
        {
            "id": row[0],
            "filename": row[1],
            "classification": row[2],
            "uploaded": row[3],
            "size_bytes": row[4],
            "sha256": row[5],
        }
        for row in artifacts_result.fetchall()
    ]

    # Get timeline entries
    timeline_result = await db.execute(
        text(
            """
            SELECT entry_id, timestamp, entry_type, title, description, tags
            FROM timeline_entries
            WHERE investigation_id = :inv_id
            ORDER BY timestamp ASC
        """
        ),
        {"inv_id": str(investigation_id)},
    )
    timeline_entries = [
        {
            "id": row[0],
            "timestamp": row[1],
            "type": row[2],
            "title": row[3],
            "description": row[4],
            "tags": row[5] or [],
        }
        for row in timeline_result.fetchall()
    ]

    # Get event counts by type
    events_result = await db.execute(
        text(
            """
            SELECT event_type, COUNT(*) as count
            FROM events
            WHERE investigation_id = :inv_id
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 20
        """
        ),
        {"inv_id": str(investigation_id)},
    )
    event_counts = {row[0]: row[1] for row in events_result.fetchall()}

    # === Step 2: Generate LLM Narrative ===

    if llm_client:
        narrative = await _generate_llm_narrative(
            investigation_title=inv_title,
            artifacts=artifacts,
            timeline_entries=timeline_entries,
            event_counts=event_counts,
            user_prompt=user_prompt,
            llm_client=llm_client,
        )
    else:
        narrative = {
            "executive_summary": "No LLM configured. Report generated from data only.",
            "findings": "See timeline below for chronological events.",
            "recommendations": "Configure LLM for detailed narrative generation.",
        }

    # === Step 3: Build Markdown Report ===

    report_md = _build_markdown_report(
        investigation_title=inv_title,
        investigation_created=inv_created,
        artifacts=artifacts,
        timeline_entries=timeline_entries,
        event_counts=event_counts,
        narrative=narrative,
    )

    logger.info(f"Generated report: {len(report_md)} chars")

    return {
        "markdown": report_md,
        "title": inv_title,
        "generated_at": datetime.utcnow().isoformat(),
        "artifacts_count": len(artifacts),
        "timeline_entries_count": len(timeline_entries),
        "event_types_count": len(event_counts),
    }


async def _generate_llm_narrative(
    investigation_title: str,
    artifacts: List[Dict[str, Any]],
    timeline_entries: List[Dict[str, Any]],
    event_counts: Dict[str, int],
    user_prompt: Optional[str],
    llm_client,
) -> Dict[str, Any]:
    """
    Generate a forensic narrative using an LLM based on investigation metadata.

    Parameters
    ----------
    investigation_title: str
        The title or short description of the investigation.
    artifacts: List[Dict[str, Any]]
        A list of artifact dictionaries; each entry represents a file or object collected during the investigation.
    timeline_entries: List[Dict[str, Any]]
        Chronologically ordered events extracted from the data source. Each dictionary must contain at least `timestamp` (a datetime or `None`), `title` (str) and optionally `tags` (list of str).
    event_counts: Dict[str, int]
        Mapping of event type names to their occurrence counts.
    user_prompt: Optional[str]
        An optional custom prompt supplied by the user to guide the LLM; if omitted a default instruction is used.
    llm_client
        An asynchronous client exposing `stream_chat` and `parse_stream_to_message` methods for interacting with the language model.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing the parsed narrative sections:

        - `executive_summary` (str): The generated executive summary markdown text.
        - `findings` (str): Bullet-point key findings markdown text.
        - `recommendations` (str): Bullet-point recommendations markdown text.

    Raises
    ------
    Exception
        Any exception raised during LLM interaction is caught internally; the function logs the error and returns a fallback dictionary with error information in the `executive_summary` field.
    """
    # Build context for LLM
    context_parts = [
        f"**Investigation**: {investigation_title}",
        f"\n**Artifacts**: {len(artifacts)} files uploaded",
        f"\n**Timeline Entries**: {len(timeline_entries)} events",
        f"\n**Event Types**: {len(event_counts)} distinct types",
    ]

    # Add timeline summary
    if timeline_entries:
        context_parts.append("\n\n**Timeline Summary** (first 20 entries):\n")
        for entry in timeline_entries[:20]:
            ts = (
                entry["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
                if entry["timestamp"]
                else "Unknown"
            )
            context_parts.append(f"- {ts}: {entry['title']}")
            if entry["tags"]:
                context_parts.append(f" [Tags: {', '.join(entry['tags'])}]")
            context_parts.append("\n")

    context = "".join(context_parts)

    # Build prompt
    prompt = f"""Generate a forensic investigation report narrative based on the following data:

{context[:3000]}

{user_prompt or "Generate a professional forensic report with objective findings."}

**Generate the following sections** (markdown format):

1. **Executive Summary** (2-3 paragraphs)
   - High-level overview of the investigation
   - Key findings and timeline scope
   - Overall assessment

2. **Key Findings** (bullet points)
   - Significant events discovered
   - Patterns and anomalies identified
   - ATT&CK techniques observed (if applicable)

3. **Recommendations** (bullet points)
   - Immediate actions required
   - Further investigation needed
   - Preventive measures

**Format**: Return ONLY the sections in markdown. Use ## for section headers.
"""

    try:
        messages = [
            {
                "role": "system",
                "content": "You are a senior forensic analyst writing investigation reports. Be objective, precise, and cite specific evidence.",
            },
            {"role": "user", "content": prompt},
        ]

        stream = llm_client.stream_chat(
            messages=messages,
            temperature=0.3,
            max_tokens=2000,
        )

        # Parse streaming response
        response_msg = await llm_client.parse_stream_to_message(stream)
        content = response_msg.content or ""

        # Parse sections from response
        sections = _parse_narrative_sections(content)

        return sections

    except Exception as e:
        logger.error(f"LLM narrative generation failed: {e}")
        return {
            "executive_summary": f"Error generating narrative: {str(e)}",
            "findings": "See timeline below for detailed events.",
            "recommendations": "Review timeline manually for investigation leads.",
        }


def _parse_narrative_sections(content: str) -> Dict[str, str]:
    """
    Parse an LLM-generated narrative into predefined sections.

    Parameters
    ----------
    content: str
        The raw text returned by the language model. Expected to contain markdown headings that denote sections such as “Executive Summary”, “Findings” (or “Key Findings”), and “Recommendations”.

    Returns
    -------
    Dict[str, str]
        A dictionary with three keys-`executive_summary`, `findings`, and `recommendations`-each mapping to the extracted body text for the corresponding section. If a section is not found in *content*, its value will be an empty string.

    Notes
    -----
    The parser performs a simple line-by-line scan:

    * It treats any line containing `## executive summary` or `# executive summary` (case-insensitive) as the start of the *executive_summary* section.
    * Lines containing `## key findings`, `## findings`, or `# findings` mark the beginning of the *findings* section.
    * Lines containing `## recommendations` or `# recommendations` mark the beginning of the *recommendations* section.

    Only non-empty lines that appear after a recognized heading are appended to the current section, preserving their original line breaks. Sections not present in the input remain empty strings.
    """
    sections = {
        "executive_summary": "",
        "findings": "",
        "recommendations": "",
    }

    # Simple section extraction
    current_section = None
    lines = content.split("\n")

    for line in lines:
        line_lower = line.lower()

        if "## executive summary" in line_lower or "# executive summary" in line_lower:
            current_section = "executive_summary"
        elif (
            "## key findings" in line_lower
            or "## findings" in line_lower
            or "# findings" in line_lower
        ):
            current_section = "findings"
        elif "## recommendations" in line_lower or "# recommendations" in line_lower:
            current_section = "recommendations"
        elif current_section and line.strip():
            sections[current_section] += line + "\n"

    return sections


def _build_markdown_report(
    investigation_title: str,
    investigation_created: datetime,
    artifacts: List[Dict[str, Any]],
    timeline_entries: List[Dict[str, Any]],
    event_counts: Dict[str, int],
    narrative: Dict[str, Any],
) -> str:
    """
    Build a complete forensic investigation report in Markdown format.

    Parameters
    ----------
    investigation_title: str
        The title of the investigation to be displayed in the report header.
    investigation_created: datetime.datetime
        Timestamp indicating when the investigation was originally created; used in the metadata section.
    artifacts: List[Dict[str, Any]]
        A list of artifact dictionaries. Each dictionary must contain at least `filename`, `classification`, `size_bytes` and `sha256` keys. The function renders a table summarising these artifacts.
    timeline_entries: List[Dict[str, Any]]
        Chronological entries describing events observed during the investigation. Expected keys are `timestamp` (datetime or None), `type`, `title`, `description` and `tags`. Each entry is rendered as a sub-section in the timeline narrative.
    event_counts: Dict[str, int]
        Mapping of event type names to their occurrence counts. Used to generate an event distribution table and aggregate statistics.
    narrative: Dict[str, Any]
        Pre-generated narrative content produced by an LLM or other source. Expected keys are `executive_summary`, `findings` and `recommendations`; missing keys fall back to placeholder text.

    Returns
    -------
    str
        The fully assembled Markdown report as a single string, ready for writing to a file or further processing.
    """
    lines = []

    # Title
    lines.append(f"# Investigation Report: {investigation_title}\n\n")
    lines.append(f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  \n")
    lines.append(
        f"**Investigation Created**: {investigation_created.strftime('%Y-%m-%d %H:%M:%S UTC')}  \n\n"
    )
    lines.append("---\n\n")

    # Section 1: Executive Summary
    lines.append("## 1. Executive Summary\n\n")
    lines.append(narrative.get("executive_summary", "No summary available."))
    lines.append("\n\n---\n\n")

    # Section 2: Investigation Scope & Artifacts
    lines.append("## 2. Investigation Scope & Artifacts\n\n")
    lines.append(f"**Artifacts Analyzed**: {len(artifacts)}  \n")
    lines.append(f"**Timeline Entries**: {len(timeline_entries)}  \n")
    lines.append(f"**Event Types**: {len(event_counts)}  \n")
    lines.append(f"**Total Events**: {sum(event_counts.values())}  \n\n")

    if artifacts:
        lines.append("### Artifacts\n\n")
        lines.append("| Filename | Type | Size | SHA256 |\n")
        lines.append("|----------|------|------|--------|\n")
        for artifact in artifacts:
            filename = artifact["filename"]
            classification = artifact["classification"]
            size_mb = artifact["size_bytes"] / (1024 * 1024)
            sha256 = artifact["sha256"][:16] + "..."
            lines.append(f"| {filename} | {classification} | {size_mb:.2f} MB | `{sha256}` |\n")
        lines.append("\n")

    if event_counts:
        lines.append("### Event Distribution\n\n")
        lines.append("| Event Type | Count |\n")
        lines.append("|------------|-------|\n")
        for event_type, count in list(event_counts.items())[:15]:
            lines.append(f"| `{event_type}` | {count} |\n")
        lines.append("\n")

    lines.append("---\n\n")

    # Section 3: Timeline Narrative
    lines.append("## 3. Timeline Narrative\n\n")

    if timeline_entries:
        lines.append(f"**Total Entries**: {len(timeline_entries)}  \n\n")

        for entry in timeline_entries:
            ts = (
                entry["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
                if entry["timestamp"]
                else "Unknown Time"
            )
            entry_type = entry["type"]
            title = entry["title"]
            description = entry["description"] or ""
            tags = entry["tags"] or []

            lines.append(f"### {ts} - {title}\n\n")
            lines.append(f"**Type**: {entry_type}  \n")
            if tags:
                lines.append(f"**Tags**: {', '.join(tags)}  \n")
            if description:
                lines.append(f"\n{description}\n")
            lines.append("\n")
    else:
        lines.append("*No timeline entries recorded.*\n")

    lines.append("\n---\n\n")

    # Section 4: Findings & ATT&CK Mapping
    lines.append("## 4. Findings & ATT&CK Mapping\n\n")
    lines.append(narrative.get("findings", "No findings documented."))
    lines.append("\n\n---\n\n")

    # Section 5: Recommendations
    lines.append("## 5. Recommendations\n\n")
    lines.append(narrative.get("recommendations", "No recommendations provided."))
    lines.append("\n\n---\n\n")

    # Footer
    lines.append("*Report generated by Open Agent Investigation*\n")

    return "".join(lines)


__all__ = ["generate_investigation_report"]
