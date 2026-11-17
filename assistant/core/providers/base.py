from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelDecision:
    text: str = ""
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None


class ProviderError(Exception):
    pass


class RateLimitError(ProviderError):
    pass


class Provider(Protocol):
    def choose(
        self,
        command: str,
        tools: list[dict[str, Any]],
        system_prompt: str,
    ) -> ModelDecision:
        ...
