import pytest
import json

from worker.parsers.utils import sanitize_for_jsonb, safe_json_dumps


class TestSanitizeForJsonb:
    """Test JSONB sanitization functions."""
    
    def test_sanitize_null_bytes_in_string(self):
        """Test that null bytes are removed from strings."""
        input_str = "Hello\x00World\x00Test"
        result = sanitize_for_jsonb(input_str)
        
        assert result == "HelloWorldTest"
        assert "\x00" not in result
    
    def test_sanitize_control_characters(self):
        """Test that control characters are removed (except newline, tab, carriage return)."""
        # Include various control characters
        input_str = "Normal\x01Text\x02With\x03Controls\nBut\tKeep\rThese"
        result = sanitize_for_jsonb(input_str)
        
        # Should keep newline, tab, carriage return
        assert "\n" in result
        assert "\t" in result
        assert "\r" in result
        
        # Should remove other control characters
        assert "\x01" not in result
        assert "\x02" not in result
        assert "\x03" not in result
    
    def test_sanitize_nested_dict(self):
        """Test sanitization of nested dictionaries."""
        input_dict = {
            "key1": "value\x00with\x00nulls",
            "key2": {
                "nested": "more\x00nulls",
                "number": 42
            }
        }
        
        result = sanitize_for_jsonb(input_dict)
        
        assert result["key1"] == "valuewithnulls"
        assert result["key2"]["nested"] == "morenulls"
        assert result["key2"]["number"] == 42
    
    def test_sanitize_list(self):
        """Test sanitization of lists."""
        input_list = [
            "string\x00with\x00nulls",
            {"key": "value\x00here"},
            42,
            None
        ]
        
        result = sanitize_for_jsonb(input_list)
        
        assert result[0] == "stringwithnulls"
        assert result[1]["key"] == "valuehere"
        assert result[2] == 42
        assert result[3] is None
    
    def test_sanitize_bytes(self):
        """Test that bytes are converted to hex strings."""
        input_bytes = b'\x00\x01\x02\xff'
        result = sanitize_for_jsonb(input_bytes)
        
        assert result == "000102ff"
        assert isinstance(result, str)
    
    def test_sanitize_primitives(self):
        """Test that primitives pass through unchanged."""
        assert sanitize_for_jsonb(None) is None
        assert sanitize_for_jsonb(True) is True
        assert sanitize_for_jsonb(False) is False
        assert sanitize_for_jsonb(42) == 42
        assert sanitize_for_jsonb(3.14) == 3.14
    
    def test_sanitize_unknown_type(self):
        """Test that unknown types are converted to strings."""
        class CustomObject:
            def __str__(self):
                return "custom_object"
        
        obj = CustomObject()
        result = sanitize_for_jsonb(obj)
        
        assert result == "custom_object"
        assert isinstance(result, str)


class TestSafeJsonDumps:
    """Test safe JSON serialization."""
    
    def test_safe_json_dumps_with_nulls(self):
        """Test that safe_json_dumps removes null bytes before serialization."""
        input_dict = {
            "key": "value\x00with\x00nulls",
            "nested": {
                "data": "more\x00nulls"
            }
        }
        
        result = safe_json_dumps(input_dict)
        
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["key"] == "valuewithnulls"
        assert parsed["nested"]["data"] == "morenulls"
    
    def test_safe_json_dumps_with_bytes(self):
        """Test that bytes are converted to hex strings."""
        input_dict = {
            "binary_data": b'\x00\x01\x02\xff'
        }
        
        result = safe_json_dumps(input_dict)
        parsed = json.loads(result)
        
        assert parsed["binary_data"] == "000102ff"
    
    def test_safe_json_dumps_unicode(self):
        """Test that Unicode characters are preserved."""
        input_dict = {
            "unicode": "Hello 世界 🌍",
            "emoji": "🔥💯✨"
        }
        
        result = safe_json_dumps(input_dict)
        parsed = json.loads(result)
        
        assert parsed["unicode"] == "Hello 世界 🌍"
        assert parsed["emoji"] == "🔥💯✨"
    
    def test_safe_json_dumps_registry_example(self):
        """Test with a realistic registry value example."""
        # Simulate a registry value with null bytes
        input_dict = {
            "key_path": "\\ROOT\\ControlSet001\\Control",
            "value_name": "BinaryValue",
            "value_type": "3",
            "value_data": "0200000001000000",  # Hex string, but might contain nulls in raw
            "last_modified": "2021-05-08T08:20:41"
        }
        
        # Add some null bytes to value_data
        input_dict["value_data"] = "02\x0000\x0000\x0001\x0000\x0000\x0000"
        
        result = safe_json_dumps(input_dict)
        
        # Should be valid JSON without null bytes
        parsed = json.loads(result)
        assert "\x00" not in parsed["value_data"]
        assert parsed["key_path"] == "\\ROOT\\ControlSet001\\Control"


class TestJsonbCompatibility:
    """Test that sanitized data is compatible with PostgreSQL JSONB."""
    
    def test_no_null_bytes_in_output(self):
        """Test that output never contains null bytes."""
        # Create input with various null byte scenarios
        inputs = [
            "simple\x00string",
            {"key": "value\x00here"},
            ["item1\x00", "item2\x00"],
            {"nested": {"deep": "value\x00"}},
        ]
        
        for input_data in inputs:
            result = safe_json_dumps(input_data)
            assert "\x00" not in result
            
            # Should be valid JSON
            parsed = json.loads(result)
            assert parsed is not None
    
    def test_control_characters_removed(self):
        """Test that problematic control characters are removed."""
        input_str = "Test\x01\x02\x03\x04\x05String"
        result = safe_json_dumps({"data": input_str})
        
        parsed = json.loads(result)
        # Control characters should be removed
        assert "\x01" not in parsed["data"]
        assert "\x02" not in parsed["data"]
        assert "\x03" not in parsed["data"]


__all__ = [
    "TestSanitizeForJsonb",
    "TestSafeJsonDumps",
    "TestJsonbCompatibility",
]
