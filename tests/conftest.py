from collections.abc import AsyncIterator

import pytest

from bot.config import Defaults, ModelConfig, ProviderConfig
from bot.providers.base import ChatMessage, ModelInfo, Usage
from bot.providers.registry import ProviderEntry, Registry
from bot.storage import Database


class FakeProvider:
    def __init__(self, models: list[str] | None = None, chunks: list[str] | None = None) -> None:
        self.models = models or []
        self.chunks = chunks or []
        self.usage = Usage(10, 5)
        self.error: Exception | None = None
        self.calls: list[list[ChatMessage]] = []
        self.closed = False

    async def list_models(self) -> list[ModelInfo]:
        if self.error:
            raise self.error
        return [ModelInfo(model_id) for model_id in self.models]

    async def stream(
        self, model: str, messages: list[ChatMessage], system: str, max_tokens: int
    ) -> AsyncIterator[str | Usage]:
        self.calls.append(messages)
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error
        yield self.usage

    async def close(self) -> None:
        self.closed = True


class Clock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def make_registry(provider: FakeProvider, models: dict[str, ModelConfig] | None = None) -> Registry:
    config = ProviderConfig(name="fake", type="openai", api_key_env="FAKE_KEY", models=models or {})
    return Registry(
        [ProviderEntry(config, provider)], Defaults(context=1000, max_output_tokens=100)
    )


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
async def db(clock: Clock) -> AsyncIterator[Database]:
    database = await Database.open(":memory:", clock=clock)
    yield database
    await database.close()
