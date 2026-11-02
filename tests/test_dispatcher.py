from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, SendMessage, TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot.app import create_dispatcher
from bot.config import Settings
from bot.handlers import chat, models
from bot.middlewares import UserLocks
from bot.storage import Database
from tests.conftest import FakeProvider, make_registry

USER = User(id=42, is_bot=False, first_name="test")
CHAT = Chat(id=42, type="private")
DISPATCHER = create_dispatcher(frozenset({USER.id}))


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None):  # noqa: ASYNC109
        self.requests.append(method)
        if isinstance(method, SendMessage):
            return Message(message_id=len(self.requests), date=datetime.now(UTC), chat=CHAT)
        return True

    async def stream_content(self, *args: Any, **kwargs: Any):
        raise NotImplementedError
        yield b""

    async def close(self) -> None:
        pass

    def texts(self) -> list[str]:
        return [r.text for r in self.requests if isinstance(r, SendMessage)]


def message_update(text: str, user: User = USER) -> Update:
    message = Message(message_id=1, date=datetime.now(UTC), chat=CHAT, from_user=user, text=text)
    return Update(update_id=1, message=message)


@pytest.fixture
async def env(db: Database):
    provider = FakeProvider(models=[f"model-{i:02}" for i in range(12)], chunks=["pong"])
    registry = make_registry(provider)
    await registry.refresh()
    session = RecordingSession()
    bot = Bot("123456:TEST", session=session)
    kwargs = {
        "db": db,
        "registry": registry,
        "settings": Settings(bot_token="123456:TEST"),
        "locks": UserLocks(),
    }

    async def feed(update: Update) -> None:
        await DISPATCHER.feed_update(bot, update, **kwargs)

    return feed, session, db, provider


async def test_text_goes_to_llm(env) -> None:
    feed, _, db, provider = env
    await feed(message_update("ping"))
    assert len(provider.calls) == 1
    assert len(await db.get_history(42)) == 2


async def test_reset_clears_history(env) -> None:
    feed, session, db, _ = env
    await feed(message_update("ping"))
    await feed(message_update("/reset"))
    assert await db.get_history(42) == []
    assert "Контекст сброшен" in session.texts()[-1]


async def test_stranger_is_ignored(env) -> None:
    feed, session, _, provider = env
    await feed(message_update("ping", User(id=7, is_bot=False, first_name="x")))
    assert provider.calls == []
    assert session.requests == []


async def test_model_menu_paginates_and_selects(env) -> None:
    feed, session, db, _ = env
    await feed(message_update("/model"))
    keyboard = session.requests[-1].reply_markup.inline_keyboard
    model_buttons = [row[0] for row in keyboard if row[0].text.startswith(("model", "✅"))]
    assert len(model_buttons) == models.PAGE_SIZE
    assert keyboard[-2][-1].text == "▶️"

    pick = models.PickModel(provider=0, model=10).pack()
    callback = CallbackQuery(
        id="1",
        from_user=USER,
        chat_instance="x",
        data=pick,
        message=Message(message_id=5, date=datetime.now(UTC), chat=CHAT, text="menu"),
    )
    await feed(Update(update_id=2, callback_query=callback))
    assert await db.get_model(42) == ("fake", "model-10")
    assert any(isinstance(r, AnswerCallbackQuery) for r in session.requests)


async def test_stale_callback_is_rejected(env) -> None:
    feed, session, db, _ = env
    callback = CallbackQuery(
        id="1",
        from_user=USER,
        chat_instance="x",
        data=models.PickModel(provider=0, model=999).pack(),
    )
    await feed(Update(update_id=3, callback_query=callback))
    assert await db.get_model(42) is None
    assert session.requests[-1].show_alert is True


async def test_stats_command(env) -> None:
    feed, session, _, _ = env
    await feed(message_update("ping"))
    await feed(message_update("/stats"))
    assert "Статистика" in session.texts()[-1]
    assert "fake/model-00" in session.texts()[-1]


async def test_non_text_message(env) -> None:
    feed, session, _, _ = env
    sticker_like = Message(message_id=1, date=datetime.now(UTC), chat=CHAT, from_user=USER)
    await feed(Update(update_id=4, message=sticker_like))
    assert session.texts()[-1] == chat.TEXT_ONLY
