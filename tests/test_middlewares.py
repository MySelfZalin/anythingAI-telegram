from typing import Any

from aiogram.types import User

from bot.middlewares import AccessMiddleware, UserLocks


async def handler(event: object, data: dict[str, Any]) -> str:
    return "handled"


def user(user_id: int) -> User:
    return User(id=user_id, is_bot=False, first_name="test")


async def test_empty_allow_list_lets_everyone_in() -> None:
    middleware = AccessMiddleware(frozenset())
    assert await middleware(handler, object(), {"event_from_user": user(42)}) == "handled"


async def test_allowed_user_passes() -> None:
    middleware = AccessMiddleware(frozenset({42}))
    assert await middleware(handler, object(), {"event_from_user": user(42)}) == "handled"


async def test_other_user_is_ignored() -> None:
    middleware = AccessMiddleware(frozenset({42}))
    assert await middleware(handler, object(), {"event_from_user": user(7)}) is None
    assert await middleware(handler, object(), {}) is None


def test_user_locks_are_per_user() -> None:
    locks = UserLocks()
    assert locks.get(1) is locks.get(1)
    assert locks.get(1) is not locks.get(2)
