from pathlib import Path

import pytest
from pydantic import ValidationError

from bot.config import DEFAULT_EXCLUDE, ProviderConfig, Settings, load_providers_config


def test_allowed_user_ids_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2,,3")
    assert Settings().allowed_user_ids == frozenset({1, 2, 3})


def test_allowed_user_ids_empty_means_everyone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("ALLOWED_USER_IDS", "")
    assert Settings().allowed_user_ids == frozenset()


def test_bot_token_is_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "super-secret")
    assert "super-secret" not in repr(Settings())


def test_load_providers_config(tmp_path: Path) -> None:
    path = tmp_path / "providers.yaml"
    path.write_text(
        """
defaults:
  context: 8000
providers:
  - name: deepseek
    type: openai
    base_url: https://api.deepseek.com/v1
    api_key_env: DEEPSEEK_API_KEY
    models:
      deepseek-chat: {context: 64000, price_in: 0.27, price_out: 1.1}
""",
        encoding="utf-8",
    )
    config = load_providers_config(path)
    assert config.defaults.context == 8000
    assert config.providers[0].models["deepseek-chat"].context == 64000


def test_duplicate_provider_names_rejected(tmp_path: Path) -> None:
    path = tmp_path / "providers.yaml"
    path.write_text(
        """
providers:
  - {name: a, type: openai, api_key_env: K}
  - {name: a, type: anthropic, api_key_env: K}
""",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_providers_config(path)


def test_invalid_provider_type_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(name="x", type="gemini", api_key_env="K")


def test_default_exclude_only_for_openai() -> None:
    openai = ProviderConfig(name="o", type="openai", api_key_env="K")
    anthropic = ProviderConfig(name="a", type="anthropic", api_key_env="K")
    custom = ProviderConfig(name="c", type="openai", api_key_env="K", exclude=[])
    assert openai.exclude_patterns == list(DEFAULT_EXCLUDE)
    assert anthropic.exclude_patterns == []
    assert custom.exclude_patterns == []
