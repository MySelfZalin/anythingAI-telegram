from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText

from bot.streaming import StreamWriter
from tests.conftest import Clock


def fake_bot() -> AsyncMock:
    bot = AsyncMock()
    counter = iter(range(100, 200))
    bot.send_message.side_effect = lambda *a, **kw: SimpleNamespace(message_id=next(counter))
    return bot


async def test_updates_are_throttled() -> None:
    bot, clock = fake_bot(), Clock(0)
    writer = StreamWriter(bot, chat_id=1, interval=1.0, clock=clock)
    await writer.start()
    await writer.update("a")
    clock.now = 1.5
    await writer.update("ab")
    await writer.update("abc")
    assert bot.edit_message_text.await_count == 1
    assert bot.edit_message_text.await_args.args[0] == "ab"


async def test_finish_renders_html() -> None:
    bot = fake_bot()
    writer = StreamWriter(bot, chat_id=1)
    await writer.start()
    await writer.finish("**hi**")
    call = bot.edit_message_text.await_args
    assert call.args[0] == "<b>hi</b>"
    assert call.kwargs["parse_mode"] == ParseMode.HTML


async def test_finish_falls_back_to_plain_text() -> None:
    bot = fake_bot()
    error = TelegramBadRequest(EditMessageText(text="x"), "can't parse entities")
    bot.edit_message_text.side_effect = [error, None]
    writer = StreamWriter(bot, chat_id=1)
    await writer.start()
    await writer.finish("**hi**")
    assert bot.edit_message_text.await_args.args[0] == "**hi**"
    assert bot.edit_message_text.await_args.kwargs["parse_mode"] is None


async def test_long_answer_is_split_into_messages() -> None:
    bot = fake_bot()
    writer = StreamWriter(bot, chat_id=1)
    await writer.start()
    await writer.finish("\n".join("word " * 20 for _ in range(100)))
    assert bot.send_message.await_count > 1
