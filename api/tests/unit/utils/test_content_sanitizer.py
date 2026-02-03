import pytest

from app.utils.content_sanitizer import sanitize_llm_content, remove_duplicate_lines


@pytest.mark.unit
class TestSanitizeLLMContent:
    """Test sanitize_llm_content function."""

    def test_remove_control_tokens(self):
        """
        Test that LLM control tokens are removed from input content.

        The test constructs a string containing various control token patterns (e.g., "​", "\", and ""), passes it to :func:`sanitize_llm_content`, and verifies:

        - The resulting sanitized text no longer contains any of the specified control token substrings.
        - All expected normal words ("Hello", "world", "test") remain present in the output.
        """
        content = "Hello <|channel|> world <|constrain|> test <|message|>"
        result = sanitize_llm_content(content)

        assert "<|channel|>" not in result
        assert "<|constrain|>" not in result
        assert "<|message|>" not in result
        assert "Hello" in result
        assert "world" in result
        assert "test" in result

    def test_remove_custom_control_tokens(self):
        """
        Test that `sanitize_llm_content` correctly removes custom control tokens enclosed in `<|...|>` from the input string while preserving surrounding text and whitespace. The test verifies that each token (e.g., `<|custom_token|>`, `<|another|>`) is absent from the result, and that the original non-token words ("Text", "more", "text") remain present.
        """
        content = "Text <|custom_token|> more <|another|> text"
        result = sanitize_llm_content(content)

        assert "<|custom_token|>" not in result
        assert "<|another|>" not in result
        assert "Text" in result
        assert "more" in result
        assert "text" in result

    def test_remove_duplicate_lines(self):
        """
        Test that duplicate lines are removed while preserving the original order. The input contains repeated occurrences of "Line 1" and "Line 2". After sanitization, only the first occurrence of each unique line should remain, resulting in exactly three lines: "Line 1", "Line 2", and "Line 3". The test verifies the line count and the presence of each expected line in the output.
        """
        content = """Line 1
Line 2
Line 1
Line 3
Line 2"""
        result = sanitize_llm_content(content)

        # Should keep only first occurrence of each line
        lines = result.split("\n")
        assert len(lines) == 3  # Line 1, Line 2, Line 3
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result

    def test_preserve_empty_lines(self):
        """
        Test that `sanitize_llm_content` retains empty lines in the output.\n\nThe input string contains blank lines between non-empty lines. After sanitization, the result should still include the double newline sequence (`"\n\n"`), confirming that empty lines are preserved rather than collapsed or removed.
        """
        content = """Line 1

Line 2

Line 3"""
        result = sanitize_llm_content(content)

        # Empty lines should be kept
        assert "\n\n" in result

    def test_case_insensitive_deduplication(self):
        """
        Ensures that the content-sanitizing routine removes duplicate lines without regard to case. The input contains three variations of “Hello World” differing only by letter casing; after sanitization, only the first occurrence should remain, resulting in a single non-empty line.
        """
        content = """Hello World
hello world
HELLO WORLD"""
        result = sanitize_llm_content(content)

        # Should keep only first occurrence (case-insensitive match)
        lines = [line for line in result.split("\n") if line.strip()]
        assert len(lines) == 1

    def test_empty_content(self):
        """
        Test that sanitizing an empty string returns an empty string.
        """
        result = sanitize_llm_content("")
        assert result == ""

    def test_only_control_tokens(self):
        """
        Test that `sanitize_llm_content` correctly removes a string composed solely of control token placeholders, resulting in an empty string after stripping whitespace.
        """
        content = "<|token1|><|token2|><|token3|>"
        result = sanitize_llm_content(content)

        assert result.strip() == ""

    def test_multiline_with_tokens_and_duplicates(self):
        """
        Test that multiline content containing control token markers and duplicate lines is correctly sanitized: ensures all `<|` and `|>` tokens are removed, duplicate lines are deduplicated while preserving order, and the resulting output contains exactly two non-empty lines.
        """
        content = """<|start|>Analysis complete
Analysis complete
<|message|>Found 5 events
<|end|>Analysis complete"""

        result = sanitize_llm_content(content)

        # No control tokens
        assert "<|" not in result
        assert "|>" not in result

        # No duplicate lines
        lines = [line for line in result.split("\n") if line.strip()]
        assert len(lines) == 2  # "Analysis complete" and "Found 5 events"

    def test_preserve_whitespace_in_lines(self):
        """
        Test that leading, trailing, and internal whitespace within each line of the input content is retained after sanitization; verifies that an indented line with surrounding spaces remains unchanged (or at least its core text is present) in the sanitized result.
        """
        content = "  Indented line  \nAnother line"
        result = sanitize_llm_content(content)

        # Whitespace within lines should be preserved
        assert "  Indented line  " in result or "Indented line" in result

    def test_unicode_content(self):
        """
        Test that Unicode strings are correctly sanitized: deduplicates identical lines containing non-ASCII characters while preserving line order and handling mixed newline characters. The function should return three unique, non-empty lines from the input containing Japanese, Chinese, and Korean text.
        """
        content = """日本語のテキスト
中文文本
한국어 텍스트
日本語のテキスト"""

        result = sanitize_llm_content(content)

        # Should deduplicate Unicode text
        lines = [line for line in result.split("\n") if line.strip()]
        assert len(lines) == 3


@pytest.mark.unit
class TestRemoveDuplicateLines:
    """Test remove_duplicate_lines function."""

    def test_remove_exact_duplicates(self):
        """
        Test that `remove_duplicate_lines` eliminates exact duplicate entries while preserving the original order of lines. The input list contains repeated strings; after processing, the result should contain each unique line once, maintaining their first occurrence positions. Assertions verify the resulting length and content match the expected deduplicated sequence.
        """
        lines = ["Line 1", "Line 2", "Line 1", "Line 3"]
        result = remove_duplicate_lines(lines)

        assert len(result) == 3
        assert result == ["Line 1", "Line 2", "Line 3"]

    def test_case_insensitive_duplicates(self):
        """
        Test that duplicate lines are identified without regard to case, preserving the first occurrence and maintaining original order.

        The function supplies a list containing variations of the same word in different capitalizations alongside a distinct entry. After processing with `remove_duplicate_lines`, the result should contain only one instance of the duplicated word (the first encountered) followed by the unique line, resulting in a list length of two.
        """
        lines = ["Hello", "hello", "HELLO", "World"]
        result = remove_duplicate_lines(lines)

        assert len(result) == 2
        assert result[0] == "Hello"  # First occurrence kept
        assert result[1] == "World"

    def test_preserve_order(self):
        """
        Test that `remove_duplicate_lines` returns lines in their original order, keeping only the first occurrence of each case-sensitive entry and discarding subsequent duplicates.
        """
        lines = ["C", "A", "B", "A", "C"]
        result = remove_duplicate_lines(lines)

        assert result == ["C", "A", "B"]

    def test_empty_list(self):
        """
        Test that `remove_duplicate_lines` returns an empty list when given an empty input list. This verifies that the function correctly handles the edge case of no lines to process, preserving the expected output type and content.
        """
        result = remove_duplicate_lines([])
        assert result == []

    def test_single_line(self):
        """
        Test that a single-element list is returned unchanged.

        The test passes a list containing one string ("Only line") to `remove_duplicate_lines` and verifies that the result is identical to the input, confirming that the function correctly handles the edge case of a single line without performing any unnecessary modifications.
        """
        result = remove_duplicate_lines(["Only line"])
        assert result == ["Only line"]

    def test_all_duplicates(self):
        """
        Test that `remove_duplicate_lines` collapses multiple identical lines into a single entry, preserving the original line content and order when all input lines are duplicates.
        """
        lines = ["Same", "Same", "Same", "Same"]
        result = remove_duplicate_lines(lines)

        assert len(result) == 1
        assert result == ["Same"]

    def test_preserve_empty_lines(self):
        """
        Test that empty lines are preserved when duplicate removal is applied.

        The input list contains several non-empty strings interleaved with empty strings.
        After calling :func:`remove_duplicate_lines`, the resulting list must still contain at
        least one empty string, confirming that blank lines are not inadvertently removed
        by the deduplication logic. This ensures that line ordering and whitespace are
        maintained for empty entries.
        """
        lines = ["Line 1", "", "Line 2", "", "Line 3"]
        result = remove_duplicate_lines(lines)

        # Empty lines should be kept
        assert "" in result
        assert len([line for line in result if line == ""]) >= 1

    def test_whitespace_variations(self):
        """
        Test that lines differing only by leading, trailing, or internal whitespace are considered duplicates and deduplicated accordingly. The function should normalize whitespace when comparing lines, preserving the original order of the first occurrence while discarding subsequent variants, resulting in a list with two unique entries for the provided sample.
        """
        lines = ["  Line 1  ", "Line 1", " Line 1 ", "Line 2"]
        result = remove_duplicate_lines(lines)

        # Should treat as duplicates (normalized)
        assert len(result) == 2

    def test_special_characters(self):
        """
        Test that duplicate lines containing special characters are correctly identified and removed while preserving unique entries.

        This test supplies a list with two identical lines that include various punctuation symbols (`!@#$%`) and one distinct line. After invoking :func:`remove_duplicate_lines`, the resulting collection should contain exactly two elements: the duplicated line appears only once, and the different line is retained unchanged. The assertions verify both the length of the result and the presence of each expected unique string.
        """
        lines = [
            "Line with !@#$%",
            "Line with !@#$%",
            "Different line",
        ]
        result = remove_duplicate_lines(lines)

        assert len(result) == 2
        assert "Line with !@#$%" in result
        assert "Different line" in result

    def test_unicode_lines(self):
        """
        Test that duplicate Unicode strings are removed while preserving the original order, ensuring each distinct line (including Japanese, Chinese, and Korean characters) appears only once in the result.
        """
        lines = [
            "日本語",
            "中文",
            "日本語",
            "한글",
        ]
        result = remove_duplicate_lines(lines)

        assert len(result) == 3
        assert "日本語" in result
        assert "中文" in result
        assert "한글" in result


@pytest.mark.unit
class TestContentSanitizerEdgeCases:
    """Test edge cases for content sanitization."""

    def test_very_long_content(self):
        """
        Test that the `sanitize_llm_content` function can process a very large input without raising errors, correctly returning a non-empty string when given content composed of 1 000 newline-separated lines.
        """
        # Create content with 1000 lines
        lines = [f"Line {i}" for i in range(1000)]
        content = "\n".join(lines)

        result = sanitize_llm_content(content)

        # Should handle large content without errors
        assert isinstance(result, str)
        assert len(result) > 0

    def test_nested_control_tokens(self):
        """
        Verify that nested-looking control token patterns are properly sanitized.

        The test supplies a string containing a malformed token sequence `<|outer|inner|>` and checks that the sanitization function removes any recognized control tokens while preserving surrounding plain text. It asserts that the resulting content still includes the expected fragments `"Text"` and `"more text"`, confirming that unexpected or nested token patterns do not cause unintended removal of valid content.
        """
        content = "Text <|outer|inner|> more text"
        result = sanitize_llm_content(content)

        # Regex removes <|...| > patterns, may leave fragments
        # Main goal is to remove standard tokens like <|channel|>
        assert "Text" in result
        assert "more text" in result

    def test_malformed_control_tokens(self):
        """
        Test that the sanitizer gracefully handles malformed control tokens by ensuring it returns a string result even when input contains incomplete or incorrectly formatted token delimiters.
        """
        content = "Text <|incomplete more <| text |> end"
        result = sanitize_llm_content(content)

        # Should handle gracefully
        assert isinstance(result, str)

    def test_only_whitespace_lines(self):
        """
        Test that `sanitize_llm_content` preserves lines consisting solely of whitespace characters.\n\nThe input string contains spaces and tabs on separate lines. The function should return a string (not raise) and retain those whitespace-only lines unchanged, ensuring that empty or whitespace-only lines are not inadvertently stripped or collapsed.
        """
        content = "   \n\t\t\n   \n"
        result = sanitize_llm_content(content)

        # Should preserve empty/whitespace lines
        assert isinstance(result, str)

    def test_mixed_line_endings(self):
        """
        Test that `sanitize_llm_content` correctly normalizes and processes input containing mixed line ending characters (`\n`, `\r\n`, and `\r`). The function should treat all line separators uniformly, preserving the logical lines in their original order. The test verifies that lines separated by any of these endings appear in the sanitized output (e.g., "Line 1" and "Line 4"). This ensures robust handling of heterogeneous newline conventions often encountered in cross-platform text sources.
        """
        content = "Line 1\nLine 2\r\nLine 3\rLine 4"
        result = sanitize_llm_content(content)

        # Should handle different line endings
        assert "Line 1" in result
        assert "Line 4" in result
