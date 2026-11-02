from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.config import ModelConfig, Settings
from bot.handlers.chat import BUSY, NO_MODELS, SERVER_ERROR, TRIMMED, chat, describe_error
from bot.middlewares import UserLocks
from bot.providers.base import ChatMessage, Usage
from bot.storage import Database
from tests.conftest import FakeProvider, make_registry


def fake_message(text: str, user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=user_id),
        chat=SimpleNamespace(id=user_id),
        answer=AsyncMock(),
    )


def fake_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.send_message.return_value = SimpleNamespace(message_id=1)
    return bot


def settings() -> Settings:
    return Settings(bot_token="token", system_prompt="be nice")


async def test_chat_streams_answer_and_saves_history(db: Database) -> None:
    provider = FakeProvider(models=["m"], chunks=["Hel", "lo"])
    registry = make_registry(provider, {"m": ModelConfig(price_in=1.0, price_out=2.0)})
    await registry.refresh()
    bot = fake_bot()

    await chat(fake_message("hi"), bot, db, registry, settings(), UserLocks())

    assert provider.calls == [[ChatMessage("user", "hi")]]
    assert bot.edit_message_text.await_args.args[0] == "Hello"
    assert await db.get_history(1) == [
        ChatMessage("user", "hi"),
        ChatMessage("assistant", "Hello"),
    ]
    totals = await db.totals(1)
    assert (totals.input_tokens, totals.output_tokens) == (10, 5)
    assert totals.cost == (10 * 1.0 + 5 * 2.0) / 1_000_000


async def test_chat_sends_previous_history(db: Database) -> None:
    provider = FakeProvider(models=["m"], chunks=["ok"])
    registry = make_registry(provider)
    await registry.refresh()
    await db.add_exchange(1, "first", "answer")

    await chat(fake_message("second"), fake_bot(), db, registry, settings(), UserLocks())

    assert [m.content for m in provider.calls[0]] == ["first", "answer", "second"]


async def test_provider_error_is_not_saved(db: Database) -> None:
    provider = FakeProvider(models=["m"], chunks=["partial"])
    registry = make_registry(provider)
    await registry.refresh()
    provider.error = RuntimeError("secret details")
    bot = fake_bot()

    await chat(fake_message("hi"), bot, db, registry, settings(), UserLocks())

    shown = bot.edit_message_text.await_args.args[0]
    assert "RuntimeError" in shown
    assert "secret details" not in shown
    assert await db.get_history(1) == []
    assert (await db.totals(1)).requests == 0


async def test_trimmed_history_warns_user(db: Database) -> None:
    provider = FakeProvider(models=["m"], chunks=["ok"])
    provider.usage = Usage(1, 1)
    registry = make_registry(provider)
    await registry.refresh()
    for _ in range(20):
        await db.add_exchange(1, "x" * 300, "y" * 300)
    message = fake_message("hi")

    await chat(message, fake_bot(), db, registry, settings(), UserLocks())

    assert len(provider.calls[0]) < 41
    message.answer.assert_awaited_with(TRIMMED)


async def test_busy_user_gets_wait_message(db: Database) -> None:
    registry = make_registry(FakeProvider(models=["m"]))
    await registry.refresh()
    locks = UserLocks()
    message = fake_message("hi")

    async with locks.get(1):
        await chat(message, fake_bot(), db, registry, settings(), locks)

    message.answer.assert_awaited_once_with(BUSY)


async def test_no_models(db: Database) -> None:
    registry = make_registry(FakeProvider())
    await registry.refresh()
    message = fake_message("hi")

    await chat(message, fake_bot(), db, registry, settings(), UserLocks())

    message.answer.assert_awaited_once_with(NO_MODELS)


class StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__("raw provider body")
        self.status_code = status_code


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, "лимит"),
        (404, "не найдена"),
        (401, "API-ключ"),
        (503, SERVER_ERROR),
        (500, SERVER_ERROR),
    ],
)
def test_describe_error_by_status(status: int, expected: str) -> None:
    text = describe_error(StatusError(status))
    assert expected in text
    assert "raw provider body" not in text
