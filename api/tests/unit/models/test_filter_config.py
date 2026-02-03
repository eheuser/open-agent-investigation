import pytest
from uuid import uuid4

from app.models.filter_config import FilterConfig


@pytest.mark.unit
class TestFilterConfigModel:
    """Test FilterConfig model structure."""

    def test_filter_config_creation(self):
        """
        Test that a FilterConfig instance can be created with valid parameters and that its attributes (config_id, investigation_id, and content) are correctly assigned.
        """
        investigation_id = uuid4()
        content = {"rules": [{"field": "event_type", "operator": "equals", "value": "login"}]}

        config = FilterConfig(config_id=1, investigation_id=investigation_id, content=content)

        assert config.config_id == 1
        assert config.investigation_id == investigation_id
        assert config.content == content

    def test_filter_config_global(self):
        """
        Test creating a global filter configuration without an associated investigation.

        The test constructs a `FilterConfig` instance with:
        - `config_id` set to `1`.
        - `investigation_id` explicitly set to `None` to indicate a global scope.
        - `content` containing a `global` flag set to `True` and an empty `rules` list.

        It then asserts that:
        - The `investigation_id` attribute of the created instance remains `None`.
        - The `global` key within the `content` dictionary is `True`, confirming proper handling of global filter configurations.
        """
        content = {"global": True, "rules": []}

        config = FilterConfig(config_id=1, investigation_id=None, content=content)

        assert config.investigation_id is None
        assert config.content["global"] is True

    def test_filter_config_simple_rules(self):
        """
        Test that a FilterConfig instance correctly stores simple rule definitions.

        This test creates a configuration with two basic rules:
        - A numeric comparison on the `severity` field using the `>=` operator.
        - A string containment check on the `source` field using the `contains` operator.

        It then verifies that:
        * The `content` dictionary contains exactly two rule entries.
        * The first rule's `field` attribute is set to `"severity"`, confirming proper parsing and storage of the provided configuration data.
        """
        content = {
            "rules": [
                {"field": "severity", "operator": ">=", "value": 3},
                {"field": "source", "operator": "contains", "value": "suspicious"},
            ]
        }

        config = FilterConfig(config_id=1, investigation_id=uuid4(), content=content)

        assert len(config.content["rules"]) == 2
        assert config.content["rules"][0]["field"] == "severity"

    def test_filter_config_complex_rules(self):
        """
        Test that a FilterConfig instance correctly stores and exposes a complex nested rule structure, verifying the top-level logic operator, the number of primary rules, and the presence of an inner OR logic block within the second rule.
        """
        content = {
            "logic": "AND",
            "rules": [
                {
                    "field": "event_type",
                    "operator": "in",
                    "value": ["login", "logout", "failed_auth"],
                },
                {
                    "logic": "OR",
                    "rules": [
                        {"field": "user", "operator": "equals", "value": "admin"},
                        {"field": "user", "operator": "equals", "value": "root"},
                    ],
                },
            ],
        }

        config = FilterConfig(config_id=1, investigation_id=uuid4(), content=content)

        assert config.content["logic"] == "AND"
        assert len(config.content["rules"]) == 2
        assert config.content["rules"][1]["logic"] == "OR"

    def test_filter_config_empty_content(self):
        """
        Test that initializing a :class:`FilterConfig` with an empty `content` dictionary correctly stores an empty mapping.

        The test creates a `FilterConfig` instance using:
        - `config_id` set to `1`
        - `investigation_id` generated via `uuid4()`
        - `content` passed as an empty dict

        It then asserts that the `content` attribute of the resulting object is exactly the empty dictionary, verifying that no default values or transformations are applied when `content` is empty.
        """
        config = FilterConfig(config_id=1, investigation_id=uuid4(), content={})

        assert config.content == {}

    def test_filter_config_tablename(self):
        """
        Test that the `FilterConfig` model uses the expected table name `filter_config`.
        """
        assert FilterConfig.__tablename__ == "filter_config"

    def test_filter_config_has_required_columns(self):
        """
        Test that the FilterConfig model defines all mandatory attributes: `config_id`, `investigation_id`, `content`, and `updated_at`.
        """
        assert hasattr(FilterConfig, "config_id")
        assert hasattr(FilterConfig, "investigation_id")
        assert hasattr(FilterConfig, "content")
        assert hasattr(FilterConfig, "updated_at")


@pytest.mark.unit
class TestFilterConfigEdgeCases:
    """Test edge cases for FilterConfig model."""

    def test_filter_config_with_unicode_values(self):
        """
        Test that a `FilterConfig` instance correctly stores and preserves Unicode characters in rule values, ensuring both Japanese text and emoji are retained within the configuration content.
        """
        content = {
            "rules": [
                {"field": "user", "operator": "equals", "value": "ユーザー"},
                {"field": "message", "operator": "contains", "value": "エラー 🚫"},
            ]
        }

        config = FilterConfig(config_id=1, investigation_id=uuid4(), content=content)

        assert "ユーザー" in config.content["rules"][0]["value"]
        assert "🚫" in config.content["rules"][1]["value"]

    def test_filter_config_with_special_operators(self):
        """
        Test that a `FilterConfig` correctly stores rules using a wide variety of operators.

        The test builds a list of rule dictionaries, each containing:
        - `field`: a unique field name (`field_0`, `field_1`, …).
        - `operator`: one of the supported operator strings, including equality, containment, pattern matching, set membership, comparison symbols, and range checks.
        - `value`: a placeholder string `"test"`.

        These rules are wrapped in a `content` dictionary under the key `"rules"` and passed to the `FilterConfig` constructor along with a dummy `config_id` and a freshly generated `investigation_id`.

        The assertion verifies that the number of rules stored in the resulting configuration matches the number of operators supplied, ensuring that all operator variants are accepted without alteration.
        """
        operators = [
            "equals",
            "not_equals",
            "contains",
            "not_contains",
            "starts_with",
            "ends_with",
            "regex",
            "in",
            "not_in",
            ">",
            "<",
            ">=",
            "<=",
            "between",
        ]

        content = {
            "rules": [
                {"field": f"field_{i}", "operator": op, "value": "test"}
                for i, op in enumerate(operators)
            ]
        }

        config = FilterConfig(config_id=1, investigation_id=uuid4(), content=content)

        assert len(config.content["rules"]) == len(operators)

    def test_filter_config_with_nested_arrays(self):
        """
        Test that a `FilterConfig` correctly handles rule values defined as deeply nested arrays, verifying the type and length of the first rule's value list.
        """
        content = {
            "rules": [
                {
                    "field": "tags",
                    "operator": "contains_any",
                    "value": ["suspicious", "malware", "exploit"],
                },
                {
                    "field": "ips",
                    "operator": "in",
                    "value": ["192.168.1.1", "10.0.0.1", "172.16.0.1"],
                },
            ]
        }

        config = FilterConfig(config_id=1, investigation_id=uuid4(), content=content)

        assert isinstance(config.content["rules"][0]["value"], list)
        assert len(config.content["rules"][0]["value"]) == 3

    def test_filter_config_with_boolean_values(self):
        """
        Test that a `FilterConfig` instance correctly stores boolean values in its content.

        The test creates a configuration dictionary containing the keys `enabled` and `auto_apply` with boolean
        values `True` and `False` respectively, along with a simple rule. It then instantiates a
        :class:`~module.FilterConfig` (substituting the actual import path) using this dictionary and asserts that
        the stored content preserves the original boolean values. This ensures that boolean fields are neither
        coerced nor lost during model initialization.
        """
        content = {
            "enabled": True,
            "auto_apply": False,
            "rules": [{"field": "is_suspicious", "operator": "equals", "value": True}],
        }

        config = FilterConfig(config_id=1, investigation_id=uuid4(), content=content)

        assert config.content["enabled"] is True
        assert config.content["auto_apply"] is False

    def test_filter_config_with_null_values(self):
        """
        Test that a `FilterConfig` instance correctly stores `None` values in its content, specifically verifying that rules using the `"is_null"` operator retain a `None` value and that an optional top-level `"description"` field can also be `None`. This ensures null handling works as expected during model initialization.
        """
        content = {
            "rules": [{"field": "optional_field", "operator": "is_null", "value": None}],
            "description": None,
        }

        config = FilterConfig(config_id=1, investigation_id=uuid4(), content=content)

        assert config.content["rules"][0]["value"] is None
        assert config.content["description"] is None

    def test_filter_config_with_very_large_content(self):
        """
        Test that a `FilterConfig` instance can handle a configuration containing a very large number of rules, ensuring the `content` attribute correctly stores all 1,000 generated rule entries.
        """
        content = {
            "rules": [
                {"field": f"field_{i}", "operator": "equals", "value": f"value_{i}"}
                for i in range(1000)
            ]
        }

        config = FilterConfig(config_id=1, investigation_id=uuid4(), content=content)

        assert len(config.content["rules"]) == 1000
