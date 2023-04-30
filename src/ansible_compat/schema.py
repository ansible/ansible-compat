"""Utils for JSON Schema validation."""
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Union

import jsonschema
from jsonschema.validators import validator_for

from ansible_compat.types import JSON


def to_path(schema_path: Sequence[Union[str, int]]) -> str:
    """Flatten a path to a dot delimited string.

    :param schema_path: The schema path
    :returns: The dot delimited path
    """
    return ".".join(str(index) for index in schema_path)


def json_path(absolute_path: Sequence[Union[str, int]]) -> str:
    """Flatten a data path to a dot delimited string.

    :param absolute_path: The path
    :returns: The dot delimited string
    """
    path = "$"
    for elem in absolute_path:
        if isinstance(elem, int):
            path += "[" + str(elem) + "]"
        else:
            path += "." + elem
    return path


@dataclass(order=True)
class JsonSchemaError:
    # pylint: disable=too-many-instance-attributes
    """Data structure to hold a json schema validation error."""

    # order of attributes below is important for sorting
    schema_path: str
    data_path: str
    json_path: str
    message: str
    expected: Union[bool, int, str]
    relative_schema: str
    validator: str
    found: str

    def to_friendly(self) -> str:
        """Provide a friendly explanation of the error.

        :returns: The error message
        """
        return f"In '{self.data_path}': {self.message}."


def validate(
    schema: JSON,
    data: JSON,
) -> list[JsonSchemaError]:
    """Validate some data against a JSON schema.

    :param schema: the JSON schema to use for validation
    :param data: The data to validate
    :returns: Any errors encountered
    """
    errors: list[JsonSchemaError] = []

    if isinstance(schema, str):
        schema = json.loads(schema)
    try:
        if not isinstance(schema, Mapping):
            msg = "Invalid schema, must be a mapping"
            raise jsonschema.SchemaError(msg)  # noqa: TRY301
        validator = validator_for(schema)
        validator.check_schema(schema)
    except jsonschema.SchemaError as exc:
        error = JsonSchemaError(
            message=str(exc),
            data_path="schema sanity check",
            json_path="",
            schema_path="",
            relative_schema="",
            expected="",
            validator="",
            found="",
        )
        errors.append(error)
        return errors

    for validation_error in validator(schema).iter_errors(data):
        if isinstance(validation_error, jsonschema.ValidationError):
            error = JsonSchemaError(
                message=validation_error.message,
                data_path=to_path(validation_error.absolute_path),
                json_path=json_path(validation_error.absolute_path),
                schema_path=to_path(validation_error.schema_path),
                relative_schema=validation_error.schema,
                expected=validation_error.validator_value,
                validator=str(validation_error.validator),
                found=str(validation_error.instance),
            )
            errors.append(error)
    return sorted(errors)
