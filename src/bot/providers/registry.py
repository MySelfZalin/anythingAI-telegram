import asyncio
import logging
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from bot.config import Defaults, ModelConfig, ProviderConfig, ProvidersConfig
from bot.providers.anthropic import AnthropicProvider
from bot.providers.base import LLMProvider, ModelInfo
from bot.providers.openai_compat import OpenAICompatProvider

logger = logging.getLogger(__name__)

ClientFactory = Callable[[ProviderConfig, str, float], LLMProvider]


def create_client(config: ProviderConfig, api_key: str, timeout: float) -> LLMProvider:
    provider_class = AnthropicProvider if config.type == "anthropic" else OpenAICompatProvider
    return provider_class(api_key=api_key, base_url=config.base_url, timeout=timeout)


def filter_models(ids: Iterable[str], include: list[str], exclude: list[str]) -> list[str]:
    def matches(model_id: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, model_id, re.IGNORECASE) for pattern in patterns)

    return [
        model_id
        for model_id in ids
        if (not include or matches(model_id, include)) and not matches(model_id, exclude)
    ]


@dataclass
class ProviderEntry:
    config: ProviderConfig
    client: LLMProvider
    models: list[ModelInfo] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.config.name


@dataclass(frozen=True)
class Selection:
    entry: ProviderEntry
    model: ModelInfo
    context: int

    @property
    def label(self) -> str:
        return f"{self.entry.name}/{self.model.id}"

    @property
    def config(self) -> ModelConfig | None:
        return self.entry.config.models.get(self.model.id)


class Registry:
    def __init__(self, entries: list[ProviderEntry], defaults: Defaults) -> None:
        self.entries = entries
        self.defaults = defaults

    @classmethod
    def from_config(
        cls,
        config: ProvidersConfig,
        env: Mapping[str, str],
        factory: ClientFactory = create_client,
    ) -> "Registry":
        entries = []
        for provider in config.providers:
            api_key = env.get(provider.api_key_env, "").strip()
            if not api_key:
                logger.warning(
                    "Provider %s skipped: %s is empty", provider.name, provider.api_key_env
                )
                continue
            client = factory(provider, api_key, config.defaults.request_timeout)
            entries.append(ProviderEntry(provider, client))
        return cls(entries, config.defaults)

    async def refresh(self) -> None:
        await asyncio.gather(*(self._load_models(entry) for entry in self.entries))

    async def _load_models(self, entry: ProviderEntry) -> None:
        try:
            async with asyncio.timeout(self.defaults.request_timeout):
                fetched = await entry.client.list_models()
        except Exception as error:  # noqa: BLE001
            logger.warning("Provider %s: cannot list models (%s)", entry.name, type(error).__name__)
            if entry.models:
                return
            fetched = []

        allowed = set(
            filter_models(
                (m.id for m in fetched), entry.config.include, entry.config.exclude_patterns
            )
        )
        models = {m.id: m for m in fetched if m.id in allowed}
        for model_id in entry.config.models:
            models.setdefault(model_id, ModelInfo(model_id))
        entry.models = sorted(models.values(), key=lambda m: m.id)
        logger.info("Provider %s: %d models available", entry.name, len(entry.models))

    def select(self, provider_name: str, model_id: str) -> Selection | None:
        entry = next((e for e in self.entries if e.name == provider_name), None)
        if entry is None:
            return None
        model = next((m for m in entry.models if m.id == model_id), None)
        if model is None:
            return None
        configured = entry.config.models.get(model_id)
        context = (configured and configured.context) or model.context or self.defaults.context
        return Selection(entry, model, context)

    def resolve(self, saved: tuple[str, str] | None, default_spec: str) -> Selection | None:
        candidates = [saved] if saved else []
        if ":" in default_spec:
            provider_name, model_id = default_spec.split(":", 1)
            candidates.append((provider_name, model_id))
        for provider_name, model_id in candidates:
            if selection := self.select(provider_name, model_id):
                return selection
        for entry in self.entries:
            if entry.models:
                return self.select(entry.name, entry.models[0].id)
        return None

    async def close(self) -> None:
        await asyncio.gather(*(entry.client.close() for entry in self.entries))
