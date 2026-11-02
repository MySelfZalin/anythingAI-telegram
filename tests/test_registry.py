from types import SimpleNamespace

import pytest

from bot.config import Defaults, ModelConfig, ProviderConfig, ProvidersConfig
from bot.providers.base import ModelInfo
from bot.providers.openai_compat import OpenAICompatProvider
from bot.providers.registry import ProviderEntry, Registry, filter_models
from tests.conftest import FakeProvider, make_registry


def test_filter_models_include_and_exclude() -> None:
    ids = ["gpt-4o", "gpt-4o-mini-tts", "text-embedding-3", "o3-mini"]
    assert filter_models(ids, [], ["embed", "tts"]) == ["gpt-4o", "o3-mini"]
    assert filter_models(ids, ["^gpt-"], ["tts"]) == ["gpt-4o"]


def test_from_config_skips_providers_without_key() -> None:
    config = ProvidersConfig(
        providers=[
            ProviderConfig(name="a", type="openai", api_key_env="A_KEY"),
            ProviderConfig(name="b", type="anthropic", api_key_env="B_KEY"),
        ]
    )
    created = []

    def factory(provider: ProviderConfig, api_key: str, timeout: float) -> FakeProvider:
        created.append((provider.name, api_key))
        return FakeProvider()

    registry = Registry.from_config(config, {"A_KEY": "secret", "B_KEY": " "}, factory)
    assert [entry.name for entry in registry.entries] == ["a"]
    assert created == [("a", "secret")]


async def test_refresh_applies_filters_and_adds_configured_models() -> None:
    provider = FakeProvider(models=["gpt-4o", "whisper-1"])
    registry = make_registry(provider, {"custom-model": ModelConfig()})
    await registry.refresh()
    assert [m.id for m in registry.entries[0].models] == ["custom-model", "gpt-4o"]


async def test_refresh_failure_keeps_previous_models() -> None:
    provider = FakeProvider(models=["gpt-4o"])
    registry = make_registry(provider)
    await registry.refresh()
    provider.error = RuntimeError("boom")
    await registry.refresh()
    assert [m.id for m in registry.entries[0].models] == ["gpt-4o"]


async def test_refresh_failure_falls_back_to_configured_models() -> None:
    provider = FakeProvider()
    provider.error = RuntimeError("no /models endpoint")
    registry = make_registry(provider, {"glm-4": ModelConfig(context=128000)})
    await registry.refresh()
    assert [m.id for m in registry.entries[0].models] == ["glm-4"]


def test_context_priority() -> None:
    config = ProviderConfig(
        name="p",
        type="openai",
        api_key_env="K",
        models={"configured": ModelConfig(context=5000)},
    )
    entry = ProviderEntry(
        config,
        FakeProvider(),
        [ModelInfo("configured", 9000), ModelInfo("from-api", 7000), ModelInfo("unknown")],
    )
    registry = Registry([entry], Defaults(context=1234))
    assert registry.select("p", "configured").context == 5000
    assert registry.select("p", "from-api").context == 7000
    assert registry.select("p", "unknown").context == 1234


async def test_resolve_order() -> None:
    registry = make_registry(FakeProvider(models=["a", "b", "c:free"]))
    await registry.refresh()
    assert registry.resolve(("fake", "b"), "fake:a").model.id == "b"
    assert registry.resolve(("fake", "gone"), "fake:c:free").model.id == "c:free"
    assert registry.resolve(None, "").model.id == "a"
    assert registry.select("missing", "a") is None


async def test_resolve_without_models_returns_none() -> None:
    registry = make_registry(FakeProvider())
    await registry.refresh()
    assert registry.resolve(None, "") is None


async def test_close_closes_clients() -> None:
    provider = FakeProvider()
    await make_registry(provider).close()
    assert provider.closed


async def test_openai_compat_strips_gemini_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatProvider(api_key="x", base_url=None, timeout=5)

    async def models():
        for model_id in ("models/gemini-3.5-flash", "gpt-4o"):
            yield SimpleNamespace(id=model_id, model_extra={})

    monkeypatch.setattr(provider._client.models, "list", models)
    assert [m.id for m in await provider.list_models()] == ["gemini-3.5-flash", "gpt-4o"]
    await provider.close()
