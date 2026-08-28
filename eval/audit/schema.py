from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class SchemaValidationError(ValueError):
    pass


def _type_ok(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, Mapping), "array": isinstance(value, Sequence) and not isinstance(value, (str, bytes)),
        "string": isinstance(value, str), "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool), "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)


def validate_schema(instance: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    """Small dependency-free JSON Schema subset used by audit definitions.

    Supports type, required, properties, items, enum, minimum, maximum and
    additionalProperties=false. Install jsonschema for full draft support.
    """
    expected = schema.get("type")
    allowed_types = [expected] if isinstance(expected, str) else list(expected or [])
    if allowed_types and not any(_type_ok(instance, item) for item in allowed_types):
        raise SchemaValidationError(f"{path}: expected {allowed_types}, got {type(instance).__name__}")
    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaValidationError(f"{path}: value is not in enum")
    if isinstance(instance, Mapping):
        missing = [name for name in schema.get("required", []) if name not in instance]
        if missing:
            raise SchemaValidationError(f"{path}: missing required fields {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = sorted(set(instance) - set(properties))
            if extras:
                raise SchemaValidationError(f"{path}: unexpected fields {extras}")
        for key, child in properties.items():
            if key in instance:
                validate_schema(instance[key], child, f"{path}.{key}")
    if isinstance(instance, Sequence) and not isinstance(instance, (str, bytes)) and "items" in schema:
        for index, item in enumerate(instance):
            validate_schema(item, schema["items"], f"{path}[{index}]")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            raise SchemaValidationError(f"{path}: below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            raise SchemaValidationError(f"{path}: above maximum")
