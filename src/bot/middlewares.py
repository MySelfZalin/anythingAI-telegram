import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

logger = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class AccessMiddleware(BaseMiddleware):
    def __init__(self, allowed_user_ids: frozenset[int]) -> None:
        self._allowed = allowed_user_ids

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if self._allowed:
            user: User | None = data.get("event_from_user")
            if user is None or user.id not in self._allowed:
                logger.debug("Ignored update from user %s", user.id if user else None)
                return None
        return await handler(event, data)


class UserLocks:
    def __init__(self) -> None:
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    def get(self, user_id: int) -> asyncio.Lock:
        return self._locks[user_id]
