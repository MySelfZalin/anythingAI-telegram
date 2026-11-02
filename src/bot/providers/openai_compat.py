from collections.abc import AsyncIterator

from openai import AsyncOpenAI
from openai.types import Model

from bot.providers.base import ChatMessage, ModelInfo, Usage

GEMINI_MODEL_PREFIX = "models/"


def _context_length(model: Model) -> int | None:
    value = (model.model_extra or {}).get("context_length")
    return value if isinstance(value, int) and value > 0 else None


class OpenAICompatProvider:
    def __init__(self, api_key: str, base_url: str | None, timeout: float) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(m.id.removeprefix(GEMINI_MODEL_PREFIX), _context_length(m))
            async for m in self._client.models.list()
        ]

    async def stream(
        self,
        model: str,
        messages: list[ChatMessage],
        system: str,
        max_tokens: int,  # noqa: ARG002
    ) -> AsyncIterator[str | Usage]:
        payload = [{"role": "system", "content": system}] if system else []
        payload += [{"role": m.role, "content": m.content} for m in messages]
        response = await self._client.chat.completions.create(
            model=model,
            messages=payload,
            stream=True,
            stream_options={"include_usage": True},
        )
        usage = Usage()
        async for chunk in response:
            if chunk.usage:
                usage = Usage(chunk.usage.prompt_tokens or 0, chunk.usage.completion_tokens or 0)
            for choice in chunk.choices:
                if choice.delta and choice.delta.content:
                    yield choice.delta.content
        yield usage

    async def close(self) -> None:
        await self._client.close()
