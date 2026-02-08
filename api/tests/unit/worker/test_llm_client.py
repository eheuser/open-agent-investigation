import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from worker.core.llm_client import LLMClient, _strip_thinking_tags
from worker.models import AssistantMessage, ToolCall


@pytest.mark.unit
class TestStripThinkingTags:
    """Test thinking tag removal utility."""

    def test_strip_thinking_tags_removes_think_tags(self):
        """Test that _strip_thinking_tags removes <think> tags."""
        text = "Before <think>internal reasoning</think> After"
        result = _strip_thinking_tags(text)
        assert result == "Before  After"
        assert "internal reasoning" not in result

    def test_strip_thinking_tags_removes_thinking_tags(self):
        """Test that _strip_thinking_tags removes <thinking> tags."""
        text = "Before <thinking>internal reasoning</thinking> After"
        result = _strip_thinking_tags(text)
        assert result == "Before  After"
        assert "internal reasoning" not in result

    def test_strip_thinking_tags_removes_thought_tags(self):
        """Test that _strip_thinking_tags removes <thought> tags."""
        text = "Before <thought>internal reasoning</thought> After"
        result = _strip_thinking_tags(text)
        assert result == "Before  After"
        assert "internal reasoning" not in result

    def test_strip_thinking_tags_removes_reflection_tags(self):
        """Test that _strip_thinking_tags removes <reflection> tags."""
        text = "Before <reflection>internal reasoning</reflection> After"
        result = _strip_thinking_tags(text)
        assert result == "Before  After"
        assert "internal reasoning" not in result

    def test_strip_thinking_tags_removes_reasoning_tags(self):
        """Test that _strip_thinking_tags removes <reasoning> tags."""
        text = "Before <reasoning>internal reasoning</reasoning> After"
        result = _strip_thinking_tags(text)
        assert result == "Before  After"
        assert "internal reasoning" not in result

    def test_strip_thinking_tags_handles_multiline(self):
        """Test that _strip_thinking_tags handles multiline thinking blocks."""
        text = "Start\n<think>\nLine 1\nLine 2\n</think>\nEnd"
        result = _strip_thinking_tags(text)
        assert "Line 1" not in result
        assert "Line 2" not in result
        assert "Start" in result
        assert "End" in result

    def test_strip_thinking_tags_case_insensitive(self):
        """Test that tag removal is case-insensitive."""
        text = "Before <THINK>reasoning</THINK> middle <ThInKiNg>more</ThInKiNg> After"
        result = _strip_thinking_tags(text)
        assert "reasoning" not in result
        assert "more" not in result
        assert "Before" in result
        assert "After" in result

    def test_strip_thinking_tags_removes_orphaned_opening_tags(self):
        """Test that orphaned opening tags are removed."""
        text = "Before <think> some text After"
        result = _strip_thinking_tags(text)
        assert "<think>" not in result
        assert "Before" in result
        assert "some text After" in result

    def test_strip_thinking_tags_removes_orphaned_closing_tags(self):
        """Test that orphaned closing tags are removed."""
        text = "Before some text </think> After"
        result = _strip_thinking_tags(text)
        assert "</think>" not in result
        assert "Before some text" in result
        assert "After" in result

    def test_strip_thinking_tags_removes_self_closing_tags(self):
        """Test that self-closing tags are removed."""
        text = "Before <think/> After"
        result = _strip_thinking_tags(text)
        assert "<think/>" not in result
        assert "Before" in result
        assert "After" in result

    def test_strip_thinking_tags_multiple_tags(self):
        """Test removal of multiple different thinking tags."""
        text = "Begin <think>hidden1</think> middle <reasoning>hidden2</reasoning> end <thought>hidden3</thought> final"
        result = _strip_thinking_tags(text)
        assert "hidden1" not in result
        assert "hidden2" not in result
        assert "hidden3" not in result
        assert "Begin" in result
        assert "middle" in result
        assert "end" in result
        assert "final" in result

    def test_strip_thinking_tags_normalizes_whitespace(self):
        """Test that excessive newlines are normalized."""
        text = "Line 1\n\n\n\n\nLine 2"
        result = _strip_thinking_tags(text)
        assert result == "Line 1\n\nLine 2"

    def test_strip_thinking_tags_empty_string(self):
        """Test that empty string is handled correctly."""
        result = _strip_thinking_tags("")
        assert result == ""

    def test_strip_thinking_tags_none(self):
        """Test that None is handled correctly."""
        result = _strip_thinking_tags(None)
        assert result is None

    def test_strip_thinking_tags_no_tags(self):
        """Test that text without tags is unchanged."""
        text = "This is normal text without any thinking tags."
        result = _strip_thinking_tags(text)
        assert result == text

    def test_strip_thinking_tags_nested_tags(self):
        """Test handling of nested thinking tags."""
        text = "Before <think>outer <thinking>inner</thinking> outer</think> After"
        result = _strip_thinking_tags(text)
        # Regex will remove the innermost matched pair first
        assert "inner" not in result
        assert "outer" not in result
        assert "Before" in result
        assert "After" in result

    def test_strip_thinking_tags_preserves_similar_text(self):
        """Test that text similar to tags but not tags is preserved."""
        text = "I think this is good reasoning for thought leadership"
        result = _strip_thinking_tags(text)
        assert result == text


@pytest.mark.unit
class TestLLMClientThinkingTagRemoval:
    """Test that LLM client removes thinking tags from responses."""

    async def test_parse_stream_removes_thinking_tags(self):
        """Test that parse_stream_to_message removes thinking tags from content."""
        client = LLMClient(
            endpoint="http://test",
            model="test-model",
        )

        # Mock stream with thinking tags
        async def mock_stream():
            yield {
                "choices": [{
                    "delta": {
                        "content": "Here is my answer <think>let me think about this</think> to your question."
                    }
                }]
            }

        message = await client.parse_stream_to_message(mock_stream())
        
        assert message.content == "Here is my answer  to your question."
        assert "let me think about this" not in message.content

    async def test_parse_stream_removes_multiple_thinking_tags(self):
        """Test removal of multiple thinking tag types."""
        client = LLMClient(
            endpoint="http://test",
            model="test-model",
        )

        async def mock_stream():
            yield {
                "choices": [{
                    "delta": {
                        "content": "Begin <think>secret1</think> middle <reasoning>secret2</reasoning> end"
                    }
                }]
            }

        message = await client.parse_stream_to_message(mock_stream())
        
        assert "secret1" not in message.content
        assert "secret2" not in message.content
        assert "Begin" in message.content
        assert "middle" in message.content
        assert "end" in message.content

    async def test_parse_stream_handles_empty_after_cleaning(self):
        """Test that message content is None if only thinking tags were present."""
        client = LLMClient(
            endpoint="http://test",
            model="test-model",
        )

        async def mock_stream():
            yield {
                "choices": [{
                    "delta": {
                        "content": "<think>only thinking content</think>"
                    }
                }]
            }

        message = await client.parse_stream_to_message(mock_stream())
        
        assert message.content is None

    async def test_parse_stream_preserves_tool_calls(self):
        """Test that thinking tag removal doesn't affect tool calls."""
        client = LLMClient(
            endpoint="http://test",
            model="test-model",
        )

        async def mock_stream():
            yield {
                "choices": [{
                    "delta": {
                        "content": "I'll search <think>need to query</think> for events",
                        "tool_calls": [{
                            "index": 0,
                            "id": "call_123",
                            "function": {
                                "name": "query_jsonb_field",
                                "arguments": '{"jsonb_path": "test"}'
                            }
                        }]
                    }
                }]
            }

        message = await client.parse_stream_to_message(mock_stream())
        
        assert "I'll search  for events" == message.content
        assert len(message.tool_calls) == 1
        assert message.tool_calls[0].function["name"] == "query_jsonb_field"

    async def test_parse_stream_incremental_content_with_tags(self):
        """Test thinking tag removal with incremental content chunks."""
        client = LLMClient(
            endpoint="http://test",
            model="test-model",
        )

        async def mock_stream():
            # Simulate streaming where tags come in chunks
            yield {"choices": [{"delta": {"content": "Start "}}]}
            yield {"choices": [{"delta": {"content": "<think>thinking"}}]}
            yield {"choices": [{"delta": {"content": " process</think>"}}]}
            yield {"choices": [{"delta": {"content": " End"}}]}

        message = await client.parse_stream_to_message(mock_stream())
        
        assert "thinking process" not in message.content
        assert "Start" in message.content
        assert "End" in message.content
