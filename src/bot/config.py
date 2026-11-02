from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode

DEFAULT_EXCLUDE = (
    "embed",
    "tts",
    "whisper",
    "dall-e",
    "moderation",
    "transcribe",
    "image",
    "realtime",
    "audio",
    "davinci",
    "babbage",
)


class Settings(BaseSettings):
    bot_token: SecretStr
    allowed_user_ids: Annotated[frozenset[int], NoDecode] = frozenset()
    default_model: str = ""
    system_prompt: str = ""
    providers_file: Path = Path("providers.yaml")
    database_path: Path = Path("data/bot.db")
    log_level: str = "INFO"

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def parse_user_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return frozenset(int(part) for part in value.replace(" ", "").split(",") if part)
        return value


class ModelConfig(BaseModel):
    context: int | None = Field(default=None, gt=0)
    price_in: float | None = Field(default=None, ge=0)
    price_out: float | None = Field(default=None, ge=0)


class ProviderConfig(BaseModel):
    name: str = Field(pattern=r"^[\w.-]{1,32}$")
    type: Literal["openai", "anthropic"]
    base_url: str | None = None
    api_key_env: str
    include: list[str] = Field(default_factory=list)
    exclude: list[str] | None = None
    models: dict[str, ModelConfig] = Field(default_factory=dict)

    @property
    def exclude_patterns(self) -> list[str]:
        if self.exclude is not None:
            return self.exclude
        return list(DEFAULT_EXCLUDE) if self.type == "openai" else []


class Defaults(BaseModel):
    context: int = Field(default=32_000, gt=0)
    max_output_tokens: int = Field(default=4096, gt=0)
    request_timeout: float = Field(default=120, gt=0)


class ProvidersConfig(BaseModel):
    defaults: Defaults = Field(default_factory=Defaults)
    providers: list[ProviderConfig]

    @field_validator("providers")
    @classmethod
    def unique_names(cls, providers: list[ProviderConfig]) -> list[ProviderConfig]:
        names = [provider.name for provider in providers]
        if len(names) != len(set(names)):
            raise ValueError("provider names must be unique")
        return providers


def load_providers_config(path: Path) -> ProvidersConfig:
    with path.open(encoding="utf-8") as file:
        return ProvidersConfig.model_validate(yaml.safe_load(file) or {})
