import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from bot.formatting import markdown_to_html, split_text

logger = logging.getLogger(__name__)


@dataclass
class _Sent:
    message_id: int
    text: str
    html: bool


class StreamWriter:
    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        interval: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._interval = interval
        self._clock = clock
        self._last_update = 0.0
        self._sent: list[_Sent] = []

    async def start(self, placeholder: str = "⏳") -> None:
        message = await self._bot.send_message(self._chat_id, placeholder)
        self._sent.append(_Sent(message.message_id, placeholder, html=False))
        self._last_update = self._clock()

    async def update(self, text: str) -> None:
        if self._clock() - self._last_update < self._interval:
            return
        self._last_update = self._clock()
        await self._render(text, html=False, retry=False)

    async def finish(self, text: str) -> None:
        await self._render(text, html=True, retry=True)

    async def _render(self, text: str, html: bool, retry: bool) -> None:
        for index, chunk in enumerate(split_text(text)):
            if not chunk.strip():
                continue
            if index < len(self._sent):
                sent = self._sent[index]
                if (sent.text, sent.html) == (chunk, html):
                    continue
                await self._deliver(chunk, html, retry, sent.message_id)
                sent.text, sent.html = chunk, html
            else:
                message_id = await self._deliver(chunk, html, retry)
                if message_id is not None:
                    self._sent.append(_Sent(message_id, chunk, html))

    async def _deliver(
        self, text: str, html: bool, retry: bool, message_id: int | None = None
    ) -> int | None:
        try:
            return await self._send(text, html, message_id)
        except TelegramRetryAfter as error:
            if not retry:
                return None
            await asyncio.sleep(error.retry_after)
            return await self._send(text, html, message_id)

    async def _send(self, text: str, html: bool, message_id: int | None) -> int | None:
        attempts = [(markdown_to_html(text), ParseMode.HTML)] if html else []
        attempts.append((text, None))
        for body, parse_mode in attempts:
            try:
                if message_id is None:
                    message = await self._bot.send_message(
                        self._chat_id, body, parse_mode=parse_mode
                    )
                    return message.message_id
                await self._bot.edit_message_text(
                    body, chat_id=self._chat_id, message_id=message_id, parse_mode=parse_mode
                )
            except TelegramBadRequest as error:
                if "not modified" in error.message:
                    return message_id
                logger.debug("Telegram rejected message: %s", error.message)
            else:
                return message_id
        return None
