from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Dict


ToolHandler = Callable[[dict], Awaitable[dict]]


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    handler: ToolHandler
    risk: RiskLevel
    timeout_seconds: float
    max_retries: int
    required_permissions: frozenset[str]
    idempotent: bool


class ToolRegistry:
    def __init__(self):
        self._definitions: Dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"Tool `{definition.name}` is already registered.")
        if definition.max_retries and not definition.idempotent:
            raise ValueError(f"Non-idempotent tool `{definition.name}` cannot be retried.")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._definitions.get(name)

    def names(self) -> list[str]:
        return sorted(self._definitions)


tool_registry = ToolRegistry()
