from bot.config import ModelConfig
from bot.context import estimate_tokens, fit_context
from bot.pricing import calculate_cost
from bot.providers.base import ChatMessage, Usage


def dialog(count: int, size: int = 30) -> list[ChatMessage]:
    roles = ("user", "assistant")
    return [ChatMessage(roles[i % 2], "x" * size) for i in range(count)]


def test_fit_context_keeps_everything_when_it_fits() -> None:
    messages = dialog(5)
    kept, trimmed = fit_context(messages, budget=10_000)
    assert kept == messages
    assert not trimmed


def test_fit_context_drops_oldest_and_starts_with_user() -> None:
    messages = dialog(5)
    per_message = estimate_tokens("x" * 30)
    kept, trimmed = fit_context(messages, budget=per_message * 2)
    assert trimmed
    assert kept[0].role == "user"
    assert kept[-1] is messages[-1]
    assert len(kept) == 1


def test_fit_context_always_keeps_last_message() -> None:
    messages = dialog(1, size=10_000)
    kept, trimmed = fit_context(messages, budget=1)
    assert kept == messages
    assert not trimmed


def test_cost_with_prices() -> None:
    config = ModelConfig(price_in=2.0, price_out=8.0)
    assert calculate_cost(Usage(1_000_000, 500_000), config) == 6.0


def test_cost_without_prices() -> None:
    assert calculate_cost(Usage(10, 10), None) is None
    assert calculate_cost(Usage(10, 10), ModelConfig(price_in=1.0)) is None
