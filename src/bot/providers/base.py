from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class ModelInfo:
    id: str
    context: int | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(Protocol):
    async def list_models(self) -> list[ModelInfo]: ...

    def stream(
        self,
        model: str,
        messages: list[ChatMessage],
        system: str,
        max_tokens: int,
    ) -> AsyncIterator[str | Usage]: ...

    async def close(self) -> None: ...
