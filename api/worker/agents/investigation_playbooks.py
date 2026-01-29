from typing import Any, Dict, List, Optional

from .playbooks import select_playbook_for_query, Playbook


async def get_playbook_for_query(user_question: str, llm_client) -> Optional[str]:
    """
    Use LLM to select the most relevant investigation playbook.
    
    Args:
        user_question: The investigation question/query from the user
        llm_client: LLM client for playbook selection
        
    Returns:
        Relevant playbook text, or None if no specific playbook matches
    """
    playbook: Optional[Playbook] = await select_playbook_for_query(user_question, llm_client)
    
    if playbook:
        return playbook.playbook
    
    return None


async def get_investigation_strategy_prompt(
    user_question: str,
    iteration: int,
    max_iterations: int,
    tool_execution_log: List[Dict[str, Any]],
    llm_client,
) -> str:
    """
    Generate strategic guidance for the current iteration based on:
    - The user's question (to select playbook)
    - Current iteration (to guide phase)
    - Previous tool executions (to avoid repetition)
    
    Args:
        user_question: The investigation question
        iteration: Current iteration number
        max_iterations: Maximum iterations available
        tool_execution_log: History of tool executions
        
    Returns:
        Strategic guidance text to inject into the prompt
    """
    playbook = await get_playbook_for_query(user_question, llm_client)
    
    if not playbook:
        # Generic investigation guidance
        return """
## INVESTIGATION STRATEGY

Use a systematic approach:
1. **Understand the Question**: What specific evidence would answer it?
2. **Identify Relevant Data**: Which event types contain that evidence?
3. **Query Strategically**: Start broad (aggregate), then narrow (specific queries)
4. **Analyze Patterns**: Look for anomalies, outliers, temporal clustering
5. **Build Narrative**: Connect evidence into a coherent story
6. **Validate**: Cross-reference multiple data sources

**Progress Tracking**:
- Iteration {iteration}/{max_iterations}
- Previous queries: {len(tool_execution_log)} tools executed
- Remember: Each iteration should answer ONE specific question
"""
    
    # Add progress context to playbook
    progress = f"""
---
**YOUR PROGRESS**:
- Iteration: {iteration}/{max_iterations}
- Tools executed so far: {len(tool_execution_log)}

"""
    
    # Add iteration-specific guidance
    if iteration <= 2:
        progress += """
**CURRENT PHASE**: Discovery
- Focus on understanding what data exists
- Use aggregation to find patterns
- Identify suspicious accounts/systems/processes
- Don't dive too deep yet - get the lay of the land
"""
    elif iteration <= 4:
        progress += """
**CURRENT PHASE**: Analysis
- Investigate specific suspicious indicators found in discovery
- Query for detailed events related to your leads
- Start building timeline of key events
- Look for correlations across event types
"""
    else:
        progress += """
**CURRENT PHASE**: Validation & Completion
- Validate your findings with additional evidence
- Fill any gaps in your narrative
- Register key evidence to timeline
- Prepare to complete investigation with comprehensive summary
"""
    
    # Add what's been checked
    if tool_execution_log:
        checked_tools: set[str] = set(str(entry.get('tool_name', '')) for entry in tool_execution_log)
        checked_event_types: set[str] = set()
        checked_fields: set[str] = set()
        
        for entry in tool_execution_log:
            args = entry.get('arguments', {})
            if 'event_type' in args:
                event_type = args['event_type']
                if event_type:
                    checked_event_types.add(str(event_type))
            if 'jsonb_path' in args:
                jsonb_path = args['jsonb_path']
                if jsonb_path:
                    checked_fields.add(str(jsonb_path))
        
        progress += f"""
**ALREADY CHECKED**:
- Tools used: {', '.join(checked_tools)}
"""
        if checked_event_types:
            progress += f"- Event types queried: {', '.join(list(checked_event_types)[:5])}\n"
        if checked_fields:
            progress += f"- Fields analyzed: {', '.join(list(checked_fields)[:5])}\n"
        
        progress += "\n⚠️ **Don't repeat the same queries** - build on what you've learned!\n"
    
    progress += "\n---\n"
    
    return progress + playbook


__all__ = [
    'get_playbook_for_query',
    'get_investigation_strategy_prompt',
]
