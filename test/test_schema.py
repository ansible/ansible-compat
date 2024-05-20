"""Tests for schema utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from ansible_compat.schema import JsonSchemaError, json_path, validate

if TYPE_CHECKING:
    from ansible_compat.types import JSON

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


def json_from_asset(file_name: str) -> JSON:
    """Load a json file from disk."""
    file = Path(__file__).parent / file_name
    with file.open(encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


def jsonify(data: Any) -> JSON:  # noqa: ANN401
    """Convert object in JSON data structure."""
    return json.loads(json.dumps(data, default=vars, sort_keys=True))  # type: ignore[no-any-return]


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


def test_json_path() -> None:
    """Test json_path function."""
    assert json_path(["a", 1, "b"]) == "$.a[1].b"


def test_validate_invalid_schema() -> None:
    """Test validate function error handling."""
    schema = "[]"
    data = json_from_asset("assets/validate0_data.json")
    errors = validate(schema, data)

    assert len(errors) == 1
    assert (
        errors[0].to_friendly()
        == "In 'schema sanity check': Invalid schema, must be a mapping."
    )
