import os
from pathlib import Path
from typing import List, Dict, Optional
import yaml

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


class Playbook:
    """Represents a single investigation playbook."""
    
    def __init__(self, name: str, description: str, playbook: str, display_name: Optional[str] = None):
        self.name = name
        self.display_name = display_name or self._generate_display_name(name)
        self.description = description
        self.playbook = playbook
    
    def _generate_display_name(self, name: str) -> str:
        """Generate a friendly display name from the playbook name."""
        # Convert snake_case to Title Case
        return ' '.join(word.capitalize() for word in name.split('_'))
    
    def __repr__(self):
        return f"Playbook(name={self.name})"


class PlaybookRegistry:
    """Registry of all available investigation playbooks."""
    
    def __init__(self):
        self.playbooks: List[Playbook] = []
        self._playbooks_dir = Path(__file__).parent
        self._load_playbooks()
    
    def reload_playbooks(self):
        """Reload all playbooks from disk (for dynamic updates)."""
        self.playbooks = []
        self._load_playbooks()
        logger.info(f"Reloaded {len(self.playbooks)} playbooks")
    
    def _load_playbooks(self):
        """Load all YAML playbooks from the playbooks directory."""
        cnt = 0
        for yaml_file in self._playbooks_dir.glob("*.yaml"):
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                
                playbook = Playbook(
                    name=data['name'],
                    description=data['description'],
                    playbook=data['playbook'],
                    display_name=data.get('display_name')  # Optional field
                )
                self.playbooks.append(playbook)
                cnt += 1
                logger.debug(f"Loaded playbook: {playbook.name}")
            
            except Exception as e:
                logger.error(f"Failed to load playbook {yaml_file}: {e}")
        logger.info(f"Loaded {cnt:,} playbooks")
    
    def get_all_descriptions(self) -> str:
        """
        Get formatted list of all playbook descriptions for LLM selection.
        
        Returns:
            Formatted string with all playbook options
        """
        if not self.playbooks:
            return "No playbooks available."
        
        lines = ["Available Investigation Playbooks:\n"]
        for i, pb in enumerate(self.playbooks, 1):
            lines.append(f"{i}. **{pb.name}**: {pb.description}")
        
        return "\n".join(lines)
    
    def get_playbook_by_name(self, name: str) -> Optional[Playbook]:
        """Get a specific playbook by name."""
        for pb in self.playbooks:
            if pb.name == name:
                return pb
        return None


# Global registry instance
_registry = None


def get_playbook_registry(reload: bool = False) -> PlaybookRegistry:
    """Get the global playbook registry (singleton).
    
    Args:
        reload: If True, reload playbooks from disk
    """
    global _registry
    if _registry is None:
        _registry = PlaybookRegistry()
    elif reload:
        _registry.reload_playbooks()
    return _registry


async def select_playbook_for_query(
    user_question: str,
    llm_client
) -> Optional[Playbook]:
    """
    Use LLM to select the most relevant playbook for the user's question.
    
    Args:
        user_question: The investigation question from the user
        llm_client: LLM client instance for making the selection
        
    Returns:
        Selected Playbook object, or None if no playbook is relevant
    """
    registry = get_playbook_registry()
    
    if not registry.playbooks:
        logger.warning("No playbooks available for selection")
        return None
    
    # Build selection prompt
    playbook_descriptions = registry.get_all_descriptions()
    
    selection_prompt = f"""You are helping select the most relevant forensic investigation playbook.

User's Investigation Question:
{user_question}

{playbook_descriptions}

Respond with ONLY the playbook name (e.g., "lateral_movement") if one is relevant, or "none" if no playbook matches.

Your response (playbook name or "none"):"""
    
    try:
        # Call LLM for selection using streaming API
        messages = [{"role": "user", "content": selection_prompt}]
        
        # Use stream_chat and collect the response
        stream = llm_client.stream_chat(
            messages=messages,
            temperature=0.0,
            max_tokens=50,
            tools=None,
            tool_choice="none"
        )
        
        # Parse the stream to get the full response
        assistant_msg = await llm_client.parse_stream_to_message(stream)
        
        # Extract the playbook name from the response
        response_text = assistant_msg.content or ""
        selected_name = response_text.strip().lower()
        
        if selected_name == "none":
            logger.info("LLM selected no playbook")
            return None
        
        # Find and return the selected playbook
        playbook = registry.get_playbook_by_name(selected_name)
        
        if playbook:
            logger.info(f"LLM selected playbook: {playbook.name}")
        else:
            logger.warning(f"LLM returned unknown playbook name: {selected_name}")
        
        return playbook
    
    except Exception as e:
        logger.error(f"Failed to select playbook via LLM: {e}")
        return None


__all__ = [
    'Playbook',
    'PlaybookRegistry',
    'get_playbook_registry',
    'select_playbook_for_query',
]
