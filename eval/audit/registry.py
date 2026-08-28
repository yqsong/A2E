from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from .models import AuditDefinition
from .schema import validate_schema


class AuditRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, AuditDefinition] = {}

    def register(self, definition: AuditDefinition, *, replace: bool = False) -> None:
        key = definition.definition_id
        if key in self._definitions and not replace:
            raise ValueError(f"audit definition already registered: {key}")
        self._definitions[key] = definition

    def load_file(self, path: str | Path, *, replace: bool = False) -> AuditDefinition:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        schema_path = Path(__file__).with_name("schemas") / "audit-definition-v1.schema.json"
        validate_schema(value, json.loads(schema_path.read_text(encoding="utf-8")))
        definition = AuditDefinition.from_dict(value)
        self.register(definition, replace=replace)
        return definition

    def load_directory(self, path: str | Path, *, replace: bool = False) -> list[AuditDefinition]:
        return [self.load_file(item, replace=replace) for item in sorted(Path(path).glob("*.audit.json"))]

    def get(self, name: str, version: str | None = None) -> AuditDefinition:
        if version is not None:
            return self._definitions[f"{name}@{version}"]
        matches = [item for item in self._definitions.values() if item.name == name and not item.deprecated]
        if not matches:
            raise KeyError(name)
        def version_key(item: AuditDefinition) -> tuple[tuple[int, int | str], ...]:
            parts = re.findall(r"\d+|[^\d]+", item.version)
            return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts)
        return sorted(matches, key=version_key)[-1]

    def definitions(self) -> Iterable[AuditDefinition]:
        return self._definitions.values()
