from collections.abc import AsyncIterator
from typing import Any

from anthropic import AsyncAnthropic

from bot.providers.base import ChatMessage, ModelInfo, Usage


class AnthropicProvider:
    def __init__(self, api_key: str, base_url: str | None, timeout: float) -> None:
        self._client = AsyncAnthropic(api_key=api_key, base_url=base_url, timeout=timeout)

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(m.id, getattr(m, "max_input_tokens", None))
            async for m in self._client.models.list(limit=100)
        ]

    async def stream(
        self,
        model: str,
        messages: list[ChatMessage],
        system: str,
        max_tokens: int,
    ) -> AsyncIterator[str | Usage]:
        extra: dict[str, Any] = {"system": system} if system else {}
        async with self._client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            **extra,
        ) as stream:
            async for text in stream.text_stream:
                yield text
            final = await stream.get_final_message()
        usage = final.usage
        input_tokens = (
            usage.input_tokens
            + (usage.cache_read_input_tokens or 0)
            + (usage.cache_creation_input_tokens or 0)
        )
        yield Usage(input_tokens, usage.output_tokens)

    async def close(self) -> None:
        await self._client.close()
