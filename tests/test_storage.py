from bot.providers.base import ChatMessage, Usage
from bot.storage import Database
from tests.conftest import Clock


async def test_model_selection_roundtrip(db: Database) -> None:
    assert await db.get_model(1) is None
    await db.set_model(1, "openai", "gpt-4o")
    await db.set_model(1, "anthropic", "claude")
    assert await db.get_model(1) == ("anthropic", "claude")


async def test_history_and_reset(db: Database) -> None:
    await db.set_model(1, "openai", "gpt-4o")
    await db.add_exchange(1, "hi", "hello")
    await db.add_exchange(2, "other", "user")
    assert await db.get_history(1) == [ChatMessage("user", "hi"), ChatMessage("assistant", "hello")]

    await db.reset_session(1)
    assert await db.get_history(1) == []
    assert await db.count_messages(2) == 2
    assert await db.get_model(1) == ("openai", "gpt-4o")


async def test_reset_without_settings_does_not_set_model(db: Database) -> None:
    await db.reset_session(1)
    assert await db.get_model(1) is None


async def test_usage_totals_by_period(db: Database, clock: Clock) -> None:
    await db.add_usage(1, "openai", "gpt-4o", Usage(100, 50), 0.01)
    clock.now = 2000
    await db.reset_session(1)
    await db.add_usage(1, "openai", "gpt-4o", Usage(10, 5), None)
    await db.add_usage(1, "deepseek", "chat", Usage(1000, 500), 0.002)

    total = await db.totals(1)
    assert (total.requests, total.input_tokens, total.output_tokens) == (3, 1110, 555)
    assert round(total.cost, 6) == 0.012
    assert total.unpriced == 1

    session = await db.totals(1, since=await db.session_started_at(1))
    assert session.requests == 2
    assert await db.last_usage(1, since=2000) == Usage(1000, 500)
    assert await db.last_usage(1, since=3000) is None


async def test_totals_by_model_sorted_by_tokens(db: Database) -> None:
    await db.add_usage(1, "openai", "small", Usage(1, 1), None)
    await db.add_usage(1, "openai", "big", Usage(100, 100), 1.0)
    labels = [item.label for item in await db.totals_by_model(1)]
    assert labels == ["openai/big", "openai/small"]


async def test_sql_injection_is_stored_as_text(db: Database) -> None:
    payload = "'); DROP TABLE messages; --"
    await db.add_exchange(1, payload, "ok")
    assert (await db.get_history(1))[0].content == payload
