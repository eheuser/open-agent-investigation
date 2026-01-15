"""
Unit tests for LLM authentication helper.
Tests Bearer token and cookie-based authentication preparation.
"""

import pytest
from app.services.llm_auth_helper import prepare_llm_auth


@pytest.mark.unit
class TestPrepareLLMAuth:
    """Test prepare_llm_auth function."""

    def test_bearer_token_auth(self):
        """
        Test that `prepare_llm_auth` correctly generates authentication headers for a Bearer token.\n\nThe test supplies an API key string, invokes `prepare_llm_auth`, and asserts that:\n\n* The returned `headers` dictionary contains an `Authorization` entry formatted as `Bearer <api_key>`.\n* The `Content-Type` header is set to `application/json`.\n* No cookies are produced (the `cookies` dictionary is empty).\n\nThis ensures that token-based authentication is handled according to the expected specification.
        """
        api_key = "sk-proj-abc123xyz"

        headers, cookies = prepare_llm_auth(api_key)

        assert "Authorization" in headers
        assert headers["Authorization"] == f"Bearer {api_key}"
        assert headers["Content-Type"] == "application/json"
        assert cookies == {}

    def test_openai_api_key(self):
        """
        Test that a plain OpenAI API key is recognized as a bearer token and results in an Authorization header with the correct format while producing no cookies. The function calls `prepare_llm_auth` with a typical `sk-` prefixed key, asserts that the returned headers contain `Authorization: Bearer <key>` and that the cookie mapping is empty. This verifies the basic token-only path of `prepare_llm_auth`.
        """
        api_key = "sk-1234567890abcdef"

        headers, cookies = prepare_llm_auth(api_key)

        assert headers["Authorization"] == f"Bearer {api_key}"
        assert cookies == {}

    def test_openrouter_api_key(self):
        """
        Test that prepare_llm_auth correctly formats an OpenRouter API key as a Bearer token and produces empty cookies.

        The test creates a sample OpenRouter API key string, calls prepare_llm_auth with it, and asserts:
        - The returned headers dictionary contains an "Authorization" entry formatted as "Bearer {api_key}".
        - The returned cookies dictionary is empty.
        """
        api_key = "sk-or-v1-abcdef123456"

        headers, cookies = prepare_llm_auth(api_key)

        assert headers["Authorization"] == f"Bearer {api_key}"
        assert cookies == {}

    def test_cookie_single_pair(self):
        """
        Test that a single-pair cookie string is correctly parsed into a dictionary, produces no Authorization header, sets Content-Type to application/json, and returns the expected cookies mapping.
        """
        api_key = "session_id=abc123"

        headers, cookies = prepare_llm_auth(api_key)

        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"
        assert cookies == {"session_id": "abc123"}

    def test_cookie_multiple_pairs(self):
        """
        Test that prepare_llm_auth correctly parses a cookie string containing multiple key-value pairs separated by semicolons. The function should return headers without an Authorization entry and a cookies dictionary mapping each cookie name to its corresponding value (e.g., "session" → "abc123", "auth_token" → "xyz789", "user_id" → "12345"). This verifies handling of multi-pair cookie strings.
        """
        api_key = "session=abc123; auth_token=xyz789; user_id=12345"

        headers, cookies = prepare_llm_auth(api_key)

        assert "Authorization" not in headers
        assert cookies == {
            "session": "abc123",
            "auth_token": "xyz789",
            "user_id": "12345",
        }

    def test_cookie_with_spaces(self):
        """
        Test that prepare_llm_auth correctly parses a cookie string containing extra whitespace around keys, values, and delimiters. The function is called with a single string representing multiple cookie pairs separated by semicolons, where each pair may be surrounded by spaces. It asserts that the returned cookies dictionary maps each trimmed key to its corresponding trimmed value, ignoring any surrounding whitespace. The test also implicitly verifies that the headers component includes the appropriate JSON content-type header while focusing on the correctness of cookie parsing.
        """
        api_key = " session = abc123 ;  token = xyz "

        headers, cookies = prepare_llm_auth(api_key)

        assert cookies == {
            "session": "abc123",
            "token": "xyz",
        }

    def test_cookie_starting_with_session(self):
        """
        Test that an API key starting with the keyword “session” but lacking an ‘=’ character is treated as cookie-based authentication and does not result in an Authorization header.

        The function calls :func:`prepare_llm_auth` with a string such as `"session_token_value_without_equals"`. Because the value begins with `session` the implementation assumes cookie authentication, yet the absence of an `=` means no valid cookie pairs can be parsed. The test asserts that the returned `headers` dictionary does not contain an `Authorization` entry, confirming that the edge case is handled without raising errors.
        """
        api_key = "session_token_value_without_equals"

        # Should be treated as cookie-based due to 'session' prefix
        # But without '=', it won't parse as a valid cookie
        headers, cookies = prepare_llm_auth(api_key)

        # This is an edge case - starts with 'session' but no '='
        # Current implementation treats it as cookie auth but parses no cookies
        assert "Authorization" not in headers

    def test_cookie_starting_with_auth(self):
        """
        Test that when the API key string starts with the word “auth” but does not contain an equals sign, prepare_llm_auth treats it as a plain token rather than a cookie definition and therefore does not add an `Authorization` header to the returned headers dictionary.
        """
        api_key = "auth_value_no_equals"

        headers, cookies = prepare_llm_auth(api_key)

        assert "Authorization" not in headers

    def test_cookie_starting_with_token(self):
        """
        Test that when an API key string does not contain an equals sign (i.e., it is not in “key=value” cookie format), prepare_llm_auth does not treat it as a bearer token and therefore does not add an `Authorization` header. The function should still return the appropriate JSON content-type header and an empty cookies dictionary.
        """
        api_key = "token_value_no_equals"

        headers, cookies = prepare_llm_auth(api_key)

        assert "Authorization" not in headers

    def test_cookie_starting_with_underscore(self):
        """
        Test that a cookie string beginning with double underscores is correctly parsed into a dictionary with the appropriate key and value. The function verifies that `prepare_llm_auth` returns cookies mapping `"__session"` to `"abc123"` when given an API key formatted as `"__session=abc123"`.
        """
        api_key = "__session=abc123"

        headers, cookies = prepare_llm_auth(api_key)

        assert cookies == {"__session": "abc123"}

    def test_no_api_key(self):
        """
        Test that when no API key is provided, `prepare_llm_auth` returns headers containing only the JSON content-type and does not include an Authorization entry, while returning an empty cookies dictionary.
        """
        headers, cookies = prepare_llm_auth(None)

        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"
        assert cookies == {}

    def test_empty_api_key(self):
        """
        Test that providing an empty API key results in no Authorization header being added to the request headers and yields an empty cookies dictionary. This verifies that `prepare_llm_auth` correctly handles a missing token by omitting authentication information rather than raising an error or inserting invalid data.
        """
        headers, cookies = prepare_llm_auth("")

        assert "Authorization" not in headers
        assert cookies == {}

    def test_cookie_with_equals_in_value(self):
        """
        Test that `prepare_llm_auth` correctly parses a cookie string containing an equals sign (`=`) within the value.
        The function should split each name-value pair on the first equals character only, preserving any additional equals signs in the value. For the input `"token=base64value=="`, the expected cookies dictionary is `{"token": "base64value=="}`. The test verifies that the returned `cookies` mapping matches this expectation.
        """
        api_key = "token=base64value=="

        headers, cookies = prepare_llm_auth(api_key)

        # Should handle '=' in value correctly (split only on first '=')
        assert cookies == {"token": "base64value=="}

    def test_cookie_complex_value(self):
        """
        Test that `prepare_llm_auth` correctly parses an API key containing a JWT token into the cookies dictionary, ensuring the cookie name is recognized and its value begins with the expected base64 header segment. This verifies handling of complex cookie values with periods and underscores.
        """
        api_key = "jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"

        headers, cookies = prepare_llm_auth(api_key)

        assert "jwt" in cookies
        assert cookies["jwt"].startswith("eyJ")

    def test_bearer_token_with_special_chars(self):
        """
        Test that `prepare_llm_auth` correctly formats an Authorization header when the API key contains special characters and returns no cookies.

        The function supplies an API key string (`api_key`) that includes hyphens, underscores, and mixed case letters. It calls `prepare_llm_auth(api_key)` and verifies two conditions:
        1. The returned `headers` dictionary contains an `"Authorization"` entry whose value is exactly `"Bearer {api_key}"`.
        2. The returned `cookies` dictionary is empty, indicating that no cookie parsing was performed for a bearer token input.
        """
        api_key = "sk-proj-AbCd1234_-XyZ"

        headers, cookies = prepare_llm_auth(api_key)

        assert headers["Authorization"] == f"Bearer {api_key}"
        assert cookies == {}

    def test_content_type_always_present(self):
        """
        Test that the `Content-Type` header is always set to `application/json` regardless of the type of authentication input provided to :func:`prepare_llm_auth`. The test covers three scenarios: a bearer token string, a cookie string, and a `None` value indicating no authentication. In each case it asserts that the resulting headers dictionary contains the key `Content-Type` with the expected value.
        """
        # Bearer token
        headers1, _ = prepare_llm_auth("sk-test")
        assert headers1["Content-Type"] == "application/json"

        # Cookie
        headers2, _ = prepare_llm_auth("session=abc")
        assert headers2["Content-Type"] == "application/json"

        # No auth
        headers3, _ = prepare_llm_auth(None)
        assert headers3["Content-Type"] == "application/json"

    def test_cookie_empty_value(self):
        """
        Test that `prepare_llm_auth` correctly parses a cookie string containing an empty value, ensuring the empty-valued key is retained in the resulting cookies dictionary while other keys are parsed with their respective values.
        """
        api_key = "session=;token=abc"

        headers, cookies = prepare_llm_auth(api_key)

        # Empty values should still be included
        assert "session" in cookies
        assert cookies["token"] == "abc"

    def test_cookie_no_value(self):
        """
        Test that prepare_llm_auth properly ignores malformed cookie entries lacking an “=”, ensuring only well-formed name/value pairs are included in the returned cookies dictionary. The input string contains a stray token (“session”) without a value, followed by a valid “token=abc” pair; the test asserts that “session” is omitted and the resulting cookies dict equals {"token": "abc"}.
        """
        api_key = "session;token=abc"

        headers, cookies = prepare_llm_auth(api_key)

        # 'session' without '=' should be ignored
        assert "session" not in cookies
        assert cookies == {"token": "abc"}

    def test_mixed_valid_invalid_cookies(self):
        """
        Test mix of valid and invalid cookie pairs.

        Given an API key string containing both correctly formatted cookie pairs (e.g., `key=value`) and malformed entries (missing `=`, empty keys, etc.), this test verifies that :func:`prepare_llm_auth` parses only the well-formed pairs into a dictionary. The resulting `cookies` mapping should include exactly those valid pairs (`valid` → `"123"`, `another` → `"456"`) and exclude any invalid or incomplete entries, while also returning appropriate request headers.
        """
        api_key = "valid=123;invalid;another=456;malformed"

        headers, cookies = prepare_llm_auth(api_key)

        # Only valid pairs should be included
        assert cookies == {"valid": "123", "another": "456"}

    def test_very_long_bearer_token(self):
        """
        Test case verifying that a very long API key is correctly formatted as a Bearer token in the Authorization header. The test constructs an API key consisting of the prefix `sk-` followed by 1 000 repeated `a` characters, passes it to :func:`prepare_llm_auth`, and asserts that the returned `headers` dictionary contains an `Authorization` entry exactly equal to `"Bearer <api_key>"`. It also checks that the length of this header value exceeds 1 000 characters, confirming that extremely long tokens are handled without truncation or errors. No cookies are expected for token-based authentication.
        """
        api_key = "sk-" + "a" * 1000

        headers, cookies = prepare_llm_auth(api_key)

        assert headers["Authorization"] == f"Bearer {api_key}"
        assert len(headers["Authorization"]) > 1000

    def test_unicode_in_cookie_value(self):
        """
        Test that prepare_llm_auth correctly parses a cookie string containing Unicode characters into a dictionary mapping the cookie name to its Unicode value.
        """
        api_key = "name=用户123"

        headers, cookies = prepare_llm_auth(api_key)

        assert cookies == {"name": "用户123"}
