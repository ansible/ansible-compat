"""Tests for schema utilities."""
from ansible_compat.schema import JsonSchemaError, validate

schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "properties": {
        "environment": {"type": "object", "additionalProperties": {"type": "string"}}
    },
}

instance = {"environment": {"a": False, "b": True, "c": "foo"}}

expected_results = [
    JsonSchemaError(
        message="False is not of type 'string'",
        data_path="environment.a",
        json_path="$.environment.a",
        schema_path="properties.environment.additionalProperties.type",
        relative_schema='{"type": "string"}',
        expected="string",
        validator="type",
        found="False",
    ),
    JsonSchemaError(
        message="True is not of type 'string'",
        data_path="environment.b",
        json_path="$.environment.b",
        schema_path="properties.environment.additionalProperties.type",
        relative_schema='{"type": "string"}',
        expected="string",
        validator="type",
        found="True",
    ),
]


def test_schema() -> None:
    """Test the schema validator."""
    results = validate(schema=schema, data=instance)
    # ensure we produce consistent results between runs
    for _ in range(1, 100):
        new_results = validate(schema=schema, data=instance)
        assert results == new_results, "inconsistent returns"
        # print(result)
    assert len(results) == len(expected_results)
    assert sorted(results) == results, "multiple errors not sorted"
    for i, result in enumerate(results):
        assert result == expected_results[i]
