

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

Execute 1-3 forensic data query tools to gather initial evidence. **MAXIMUM 3 tools enforced**.

**CRITICAL - TOOL CALLS ONLY**:
Do NOT output any text in Phase 1.
Just execute tool calls directly. Your analysis will happen in Phase 2.

**BEFORE YOU CALL TOOLS - THINK**:
- What did I learn in the last iteration?
- What specific question am I trying to answer NOW?
- Which tool and parameters will answer that question?
- Am I repeating a query I already ran?

**INVESTIGATIVE STRATEGY - BE FOCUSED**:
- Start with the MOST SPECIFIC queries related to the user's question
- Use the field_dictionary to identify relevant JSONB fields
- Prefer query_jsonb_field over broad searches
- Query for HIGH-VALUE data, not everything
- Think: "What specific evidence would answer this question?"

**Available Tool Categories**:
- query_jsonb_field: Query specific JSONB fields with operators (PREFERRED - focused results, supports event_type filter)
- aggregate_jsonb_field: Aggregate and count field values (good for overview, ONLY supports event_type filter - NO time filtering)
- search_events_by_content: Search event data using text/patterns
- hybrid_search: Advanced semantic search (for complex queries)
- get_event_by_id: Retrieve specific events
- count_events: Count events (supports event_type, start_time, end_time filters)
- execute_sql: Advanced SQL queries (use sparingly)

**CRITICAL - TOOL PARAMETERS** (READ THIS):
- ONLY use parameters EXACTLY as defined in the tool schema
- DO NOT invent parameters like: query_name, time_start, time_end, query_string, query_jsonb_field
- aggregate_jsonb_field: ONLY accepts jsonb_path, aggregation, event_type, limit, description
- query_jsonb_field: ONLY accepts jsonb_path, operator, value, event_type, limit, offset, description
- If the tool schema doesn't list a parameter, you CANNOT use it - it will cause errors
- Check the tool specification carefully before calling

**QUERY BEST PRACTICES**:
- If a query returns >50 events: TOO BROAD - add more filters
- If a query returns 0 events: TOO SPECIFIC - broaden or try different fields
- Target: 5-50 events per query for optimal analysis
- Use limit parameter to control result size
- Combine multiple field conditions for precision

**FIELD DICTIONARY USAGE**:
- Review the field_dictionary provided in context
- Identify which fields contain the data you need
- Use exact field paths in query_jsonb_field
- Example: EventData.TargetUserName, EventData.IpAddress, etc.

**REQUIREMENTS**:
- Each tool MUST have a 'description' argument (shown in UI)
- Focus on gathering HIGH-VALUE data relevant to the question
- Don't execute complete_investigation or register_timeline_entry yet (those are for Phase 2)
- Execute 1-3 tools maximum (quality over quantity)

**EXECUTE TOOL CALLS NOW - NO TEXT OUTPUT**"""
    else:
        return f"""**PHASE 1 - TOOL EXECUTION** (Iteration {iteration})

Continue your investigation. Execute 1-3 additional forensic tools to gather more evidence.

**CRITICAL - TOOL CALLS ONLY**:
Do NOT output any text. Just execute tool calls.
Your analysis happens in Phase 2.

**CRITICAL - AVOID REPETITION**:
⚠️ **DO NOT repeat queries from previous iterations!**
- Check what you already queried
- Build on previous results
- If you found suspicious users, query THOSE SPECIFIC USERS
- If you found suspicious IPs, query THOSE SPECIFIC IPs
- Progress from broad → specific → detailed

**INVESTIGATIVE PROGRESSION**:
Iteration 1: Aggregate to find patterns (who/what/where)
Iteration 2: Query specific suspicious entities found in iteration 1
Iteration 3: Get detailed events for those entities
Iteration 4+: Correlate across event types, build timeline

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
   
4. **Register timeline entries** (ONLY if forensically significant):
   - **BE HIGHLY SELECTIVE** - Timeline is for KEY EVIDENCE only
   - Register ONLY events that:
     * Directly answer the investigation question
     * Show malicious/suspicious activity
     * Indicate compromise or security incidents
     * Represent pivot points in an attack chain
     * Are explicitly requested by the user
   - **DO NOT register**:
     * Routine system operations (file deletions, service operations)
     * Benign administrative tasks
     * Normal Windows maintenance
     * Events just because they exist
   - Quality over quantity - a timeline with 5-10 key events is better than 50 routine ones

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
