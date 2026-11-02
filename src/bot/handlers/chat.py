import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from bot.config import Settings
from bot.context import estimate_tokens, fit_context
from bot.middlewares import UserLocks
from bot.pricing import calculate_cost
from bot.providers.base import ChatMessage, Usage
from bot.providers.registry import Registry, Selection
from bot.storage import Database
from bot.streaming import StreamWriter

logger = logging.getLogger(__name__)

BUSY = "⏳ Дождитесь ответа на предыдущее сообщение."
NO_MODELS = "Нет доступных моделей. Проверьте providers.yaml и API-ключи."
EMPTY_ANSWER = "🤷 Модель вернула пустой ответ."
TRIMMED = "⚠️ Начало диалога не влезло в контекст модели и было отброшено. /reset — начать заново."
TEXT_ONLY = "Пока поддерживаются только текстовые сообщения."
UNKNOWN_COMMAND = "Неизвестная команда. Доступно: /start, /reset, /model, /stats"
PROVIDER_ERRORS = {
    401: "провайдер не принял API-ключ",
    403: "нет доступа к этой модели",
    404: "модель не найдена или больше не доступна",
    429: "превышен лимит запросов или закончилась квота",
}
SERVER_ERROR = "модель перегружена или временно недоступна"


def describe_error(error: Exception) -> str:
    status = getattr(error, "status_code", None)
    if isinstance(status, int) and status >= 500:
        reason = SERVER_ERROR
    else:
        reason = PROVIDER_ERRORS.get(status, f"ошибка {type(error).__name__}")
    return f"⚠️ Ошибка провайдера: {reason}. Попробуйте позже или выберите другую модель: /model"


router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE, F.from_user)


@router.message(F.text, ~F.text.startswith("/"))
async def chat(
    message: Message,
    bot: Bot,
    db: Database,
    registry: Registry,
    settings: Settings,
    locks: UserLocks,
) -> None:
    lock = locks.get(message.from_user.id)
    if lock.locked():
        await message.answer(BUSY)
        return
    async with lock:
        selection = registry.resolve(
            await db.get_model(message.from_user.id), settings.default_model
        )
        if selection is None:
            await message.answer(NO_MODELS)
            return
        await answer(message, bot, db, selection, settings.system_prompt, registry)


async def answer(
    message: Message,
    bot: Bot,
    db: Database,
    selection: Selection,
    system: str,
    registry: Registry,
) -> None:
    user_id, question = message.from_user.id, message.text or ""
    max_output = registry.defaults.max_output_tokens
    budget = selection.context - max_output - estimate_tokens(system)
    history = [*await db.get_history(user_id), ChatMessage("user", question)]
    messages, trimmed = fit_context(history, budget)

    writer = StreamWriter(bot, message.chat.id)
    await writer.start()
    text, usage = "", Usage()
    try:
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            stream = selection.entry.client.stream(selection.model.id, messages, system, max_output)
            async for event in stream:
                if isinstance(event, Usage):
                    usage = event
                else:
                    text += event
                    await writer.update(text)
    except Exception as error:  # noqa: BLE001
        status = getattr(error, "status_code", None)
        logger.warning("Provider %s failed: %s %s", selection.label, type(error).__name__, status)
        notice = describe_error(error)
        await writer.finish(f"{text}\n\n{notice}" if text else notice)
        return

    if not text.strip():
        await writer.finish(EMPTY_ANSWER)
        return
    await writer.finish(text)
    await db.add_exchange(user_id, question, text)
    await db.add_usage(
        user_id,
        selection.entry.name,
        selection.model.id,
        usage,
        calculate_cost(usage, selection.config),
    )
    if trimmed:
        await message.answer(TRIMMED)


@router.message(F.text)
async def unknown_command(message: Message) -> None:
    await message.answer(UNKNOWN_COMMAND)


@router.message()
async def unsupported(message: Message) -> None:
    await message.answer(TEXT_ONLY)
