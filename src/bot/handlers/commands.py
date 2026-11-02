from datetime import UTC, datetime
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, Message

from bot.config import Settings
from bot.providers.registry import Registry
from bot.stats import StatsView, render_stats
from bot.storage import Database

COMMANDS = [
    BotCommand(command="start", description="Начать новый чат"),
    BotCommand(command="reset", description="Сбросить контекст"),
    BotCommand(command="model", description="Выбрать модель"),
    BotCommand(command="stats", description="Статистика использования"),
]

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE, F.from_user)


@router.message(CommandStart())
async def start(message: Message, db: Database, registry: Registry, settings: Settings) -> None:
    await db.reset_session(message.from_user.id)
    selection = registry.resolve(await db.get_model(message.from_user.id), settings.default_model)
    model = f"<code>{escape(selection.label)}</code>" if selection else "нет доступных моделей"
    await message.answer(
        "👋 Привет! Просто напиши сообщение — и я передам его модели.\n\n"
        f"🤖 Модель: {model}\n\n"
        "/model — выбрать модель\n"
        "/reset — начать чат заново\n"
        "/stats — статистика использования",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("reset"))
async def reset(message: Message, db: Database) -> None:
    await db.reset_session(message.from_user.id)
    await message.answer("🧹 Контекст сброшен, начинаем с чистого листа.")


@router.message(Command("stats"))
async def stats(message: Message, db: Database, registry: Registry, settings: Settings) -> None:
    user_id = message.from_user.id
    selection = registry.resolve(await db.get_model(user_id), settings.default_model)
    session_start = await db.session_started_at(user_id)
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    last = await db.last_usage(user_id, since=session_start)
    view = StatsView(
        model=selection.label if selection else None,
        context_used=last.input_tokens + last.output_tokens if last else None,
        context_limit=selection.context if selection else None,
        session_messages=await db.count_messages(user_id),
        session=await db.totals(user_id, since=session_start),
        today=await db.totals(user_id, since=day_start),
        total=await db.totals(user_id),
        by_model=await db.totals_by_model(user_id),
    )
    await message.answer(render_stats(view), parse_mode=ParseMode.HTML)
