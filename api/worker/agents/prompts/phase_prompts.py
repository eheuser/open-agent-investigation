

def get_tool_execution_prompt(user_question: str, iteration: int) -> str:
    """
    Generate a Phase 1 tool-execution prompt with chain-of-thought scaffolding.

    Args:
        user_question (str): The original question posed by the user.
        iteration (int): The current iteration number (starting at 1).

    Returns:
        str: A formatted multi-line prompt for the tool execution phase, including
             instructions, pagination reminders, and usage limits. The content varies
             depending on whether it is the first iteration or a subsequent one.
    """
    if iteration == 1:
        return f"""**PHASE 1 - TOOL EXECUTION** (Iteration {iteration})

User's Question: "{user_question}"

Execute 1-3 forensic data query tools to gather initial evidence. **MAXIMUM 5 tools enforced**.

**CRITICAL - TOOL CALLS ONLY**:
Do NOT output any text. Do NOT explain your reasoning.
Just execute tool calls directly. Your analysis will happen in Phase 2.

**TAKE SMALL BITES**:
- Don't try to solve the entire problem in one iteration
- Execute 1-3 focused queries to explore a specific aspect
- You'll have multiple iterations to build a complete picture
- Smaller queries = better context management = better analysis

**Available Tool Categories**:
- search_events_by_type: Search for specific event types (paginated, default 50 events)
- query_jsonb_field: Query specific JSONB fields with operators (paginated, default 50 events)
- aggregate_jsonb_field: Aggregate and count field values (returns top N values)
- search_events_by_timerange: Search within time windows (paginated, default 50 events)
- hybrid_search: Advanced search combining BM25 + vector similarity (for semantic queries)

**PAGINATION REMINDER**:
- If a search returns exactly 50 events, there are likely MORE events
- Use offset parameter to page through: offset=0 (first page), offset=50 (second page)
- Check the 'has_more' field in results to know if more data exists
- Don't assume the first page tells the complete story

**REQUIREMENTS**:
- Each tool MUST have a 'description' argument (shown in UI)
- Focus on gathering data relevant to the user's question
- Don't execute complete_investigation or register_timeline_entry yet (those are for Phase 2)
- Execute 1-3 tools, not all 5 (save capacity for follow-up queries)

**EXECUTE TOOL CALLS NOW - NO TEXT OUTPUT**"""
    else:
        return f"""**PHASE 1 - TOOL EXECUTION** (Iteration {iteration})

Continue your investigation. Execute 1-3 additional forensic tools to gather more evidence.

**CRITICAL - TOOL CALLS ONLY**:
Do NOT output any text. Just execute tool calls.
Your analysis happens in Phase 2.

**REMINDER - TAKE SMALL BITES**:
- Focus on one specific aspect per iteration
- Don't flood the context window with too much data at once
- Execute 1-3 targeted queries based on what you've learned

**EXECUTE TOOL CALLS NOW - NO TEXT OUTPUT**"""


def get_analysis_prompt(user_question: str, iteration: int, tool_results_summary: str) -> str:
    """
    Generate a formatted prompt for Phase 2 (Result Analysis) of the investigation workflow.

    Args:
        user_question (str): The original question posed by the user.
        iteration (int): The current iteration number within the investigative loop.
        tool_results_summary (str): A pre-formatted summary of the results returned by tools in Phase 1.

    Returns:
        str: A multi-line prompt string that includes the user's question, the tool results,
             iteration progress information, and detailed instructions for analysis,
             pagination checking, timeline registration, and completion criteria.
    """
    # Inform agent about iteration progress and when they can complete
    MIN_ITERATIONS_BEFORE_COMPLETION = 4
    iteration_info = ""

    if iteration < MIN_ITERATIONS_BEFORE_COMPLETION:
        remaining = MIN_ITERATIONS_BEFORE_COMPLETION - iteration
        iteration_info = f"""\n\n**Investigation Progress**: Iteration {iteration}/{MIN_ITERATIONS_BEFORE_COMPLETION} (minimum)
- You need {remaining} more iteration(s) before you can complete the investigation
- Focus on analyzing the data you gathered and planning next steps
- Register important events to the timeline
- Identify what additional data you need\n"""
    else:
        iteration_info = f"""\n\n**Investigation Progress**: Iteration {iteration} (minimum {MIN_ITERATIONS_BEFORE_COMPLETION} reached)
- You may now call complete_investigation if you have thoroughly answered the question
- Only complete if: (1) You have explored all relevant data, (2) You can provide a complete narrative, (3) All pagination has been checked\n"""

    return f"""**PHASE 2 - RESULT ANALYSIS** (Iteration {iteration})

User's Question: "{user_question}"

{tool_results_summary}{iteration_info}

**YOUR TASK**:
1. **Analyze the tool results above in detail**:
   - What specific events did you find? (mention event IDs)
   - What patterns or anomalies stand out?
   - What questions do these results raise?
   
2. **CHECK PAGINATION**: Look for 'total_count', 'current_page', 'total_pages' in results
   - If total_count > count returned: There's MORE data to explore!
   - If current_page < total_pages: Use offset parameter to get next page
   - If has_more is true: Continue exploring with offset=50, offset=100, etc.
   
3. **Write your analysis summary** (3-5 sentences):
   - What did you learn from this iteration?
   - What specific events or patterns are significant?
   - What do you need to investigate next?
   
4. **Register timeline entries** (if you found significant events):
   - Use register_timeline_entry for events that directly relate to the investigation
   - Include event_id, title, description, and relevant tags
   - Only register events you've actually examined, not just search results

**CRITICAL REQUIREMENTS**:
- Your summary will be added to the conversation history
- Include specific event IDs and key findings in your summary
- **DO NOT execute data query tools in Phase 2** (search_events, query_jsonb_field, etc.)
- Data queries happen in Phase 1 ONLY - explain what you need and wait for next iteration
- Phase 2 is for ANALYSIS and REGISTRATION only

**PROVIDE YOUR ANALYSIS NOW"""


def get_completion_enforcement_prompt(
    user_question: str, iterations_completed: int, tools_executed: int, timeline_entries: int
) -> str:
    """
    Generate a prompt that forces the agent to finalize the investigation.

    Args:
        user_question (str): The original question posed by the user.
        iterations_completed (int): Number of iteration cycles already performed.
        tools_executed (int): Total count of forensic query tools executed so far.
        timeline_entries (int): Number of entries that have been added to the investigative timeline.

    Returns:
        str: A formatted enforcement prompt instructing the agent to call `complete_investigation` immediately, summarizing findings and prohibiting further tool usage.
    """
    return f"""**INVESTIGATION MUST COMPLETE NOW**

You have completed {iterations_completed} iterations and executed {tools_executed} forensic queries.
Timeline entries created: {timeline_entries}

User's Question: "{user_question}"

**MANDATORY**: Call **complete_investigation** NOW with your findings.

Your summary should include:
- Direct answer to the user's question
- Key event IDs discovered
- Number of timeline entries created
- Any important patterns or observations

**DO NOT** execute more data query tools. **ONLY** call complete_investigation.
"""


__all__ = [
    "get_tool_execution_prompt",
    "get_analysis_prompt",
    "get_completion_enforcement_prompt",
]
