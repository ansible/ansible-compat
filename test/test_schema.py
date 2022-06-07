"""Tests for schema utilities."""
import json
import os
from typing import Any

import pytest

from ansible_compat.schema import JsonSchemaError, validate

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


def json_from_asset(file_name: str) -> Any:
    """Load a json file from disk."""
    file_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), file_name)
    with open(file_name, encoding="utf-8") as f:
        return json.load(f)


def jsonify(data: Any) -> Any:
    """Convert object in JSON data structure."""
    return json.loads(json.dumps(data, default=vars))


@pytest.mark.parametrize("index", range(1))
def test_schema(index: int) -> None:
    """Test the schema validator."""
    schema = json_from_asset(f"assets/validate{index}_schema.json")
    data = json_from_asset(f"assets/validate{index}_data.json")
    expected = json_from_asset(f"assets/validate{index}_expected.json")

    # ensure we produce consistent results between runs
    for _ in range(1, 100):
        found_errors = validate(schema=schema, data=data)
        # ensure returned results are already sorted, as we assume our class
        # knows how to sort itself
        assert sorted(found_errors) == found_errors, "multiple errors not sorted"

        found_errors_json = jsonify(found_errors)
        assert (
            found_errors_json == expected
        ), f"inconsistent returns: {found_errors_json}"
