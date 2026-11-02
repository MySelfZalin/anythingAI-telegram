from html import escape
from math import ceil

from aiogram import F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import Settings
from bot.providers.registry import Registry, Selection
from bot.storage import Database

PAGE_SIZE = 8
NO_PROVIDERS = "Нет доступных провайдеров. Проверьте providers.yaml и API-ключи."
STALE_LIST = "Список устарел, откройте /model заново."

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE, F.from_user)


class ProviderPage(CallbackData, prefix="prov"):
    provider: int
    page: int = 0


class PickModel(CallbackData, prefix="pick"):
    provider: int
    model: int


class ModelMenu(CallbackData, prefix="menu"):
    action: str


def current_text(selection: Selection | None) -> str:
    label = f"<code>{escape(selection.label)}</code>" if selection else "не выбрана"
    return f"🤖 Текущая модель: {label}"


def providers_keyboard(registry: Registry) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, entry in enumerate(registry.entries):
        builder.button(
            text=f"{entry.name} ({len(entry.models)})",
            callback_data=ProviderPage(provider=index),
        )
    builder.button(text="🔄 Обновить список", callback_data=ModelMenu(action="refresh"))
    builder.adjust(1)
    return builder.as_markup()


def models_keyboard(
    registry: Registry, provider_index: int, page: int, current: Selection | None
) -> InlineKeyboardMarkup:
    entry = registry.entries[provider_index]
    pages = max(1, ceil(len(entry.models) / PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    start = page * PAGE_SIZE

    builder = InlineKeyboardBuilder()
    for index, model in enumerate(entry.models[start : start + PAGE_SIZE], start=start):
        is_current = current is not None and current.label == f"{entry.name}/{model.id}"
        builder.button(
            text=f"✅ {model.id}" if is_current else model.id,
            callback_data=PickModel(provider=provider_index, model=index),
        )
    builder.adjust(1)

    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=ProviderPage(provider=provider_index, page=page - 1).pack(),
            )
        )
    navigation.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{pages}", callback_data=ModelMenu(action="noop").pack()
        )
    )
    if page < pages - 1:
        navigation.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=ProviderPage(provider=provider_index, page=page + 1).pack(),
            )
        )
    builder.row(*navigation)

    back = "back" if len(registry.entries) > 1 else "refresh"
    back_text = "⬅️ К провайдерам" if back == "back" else "🔄 Обновить список"
    builder.row(InlineKeyboardButton(text=back_text, callback_data=ModelMenu(action=back).pack()))
    return builder.as_markup()


def menu_markup(
    registry: Registry, current: Selection | None
) -> tuple[str, InlineKeyboardMarkup] | None:
    if not registry.entries:
        return None
    if len(registry.entries) == 1:
        return current_text(current), models_keyboard(registry, 0, 0, current)
    return f"{current_text(current)}\n\nВыберите провайдера:", providers_keyboard(registry)


async def edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except TelegramBadRequest as error:
        if "not modified" not in error.message:
            raise


async def current_selection(
    user_id: int, db: Database, registry: Registry, settings: Settings
) -> Selection | None:
    return registry.resolve(await db.get_model(user_id), settings.default_model)


@router.message(Command("model"))
async def choose_model(
    message: Message, db: Database, registry: Registry, settings: Settings
) -> None:
    menu = menu_markup(
        registry, await current_selection(message.from_user.id, db, registry, settings)
    )
    if menu is None:
        await message.answer(NO_PROVIDERS)
        return
    text, markup = menu
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=markup)


@router.callback_query(ProviderPage.filter())
async def open_provider(
    callback: CallbackQuery,
    callback_data: ProviderPage,
    db: Database,
    registry: Registry,
    settings: Settings,
) -> None:
    if not 0 <= callback_data.provider < len(registry.entries):
        await callback.answer(STALE_LIST, show_alert=True)
        return
    current = await current_selection(callback.from_user.id, db, registry, settings)
    entry = registry.entries[callback_data.provider]
    text = f"{current_text(current)}\n\nПровайдер: <b>{escape(entry.name)}</b>"
    await edit(
        callback,
        text,
        models_keyboard(registry, callback_data.provider, callback_data.page, current),
    )
    await callback.answer()


@router.callback_query(PickModel.filter())
async def pick_model(
    callback: CallbackQuery,
    callback_data: PickModel,
    db: Database,
    registry: Registry,
) -> None:
    entries = registry.entries
    if not 0 <= callback_data.provider < len(entries) or not (
        0 <= callback_data.model < len(entries[callback_data.provider].models)
    ):
        await callback.answer(STALE_LIST, show_alert=True)
        return
    entry = entries[callback_data.provider]
    model = entry.models[callback_data.model]
    await db.set_model(callback.from_user.id, entry.name, model.id)
    selection = registry.select(entry.name, model.id)
    await edit(callback, f"✅ Выбрана модель\n{current_text(selection)}", None)
    await callback.answer("Модель выбрана")


@router.callback_query(ModelMenu.filter(F.action.in_({"back", "refresh"})))
async def show_providers(
    callback: CallbackQuery,
    callback_data: ModelMenu,
    db: Database,
    registry: Registry,
    settings: Settings,
) -> None:
    if callback_data.action == "refresh":
        await callback.answer("Обновляю список моделей…")
        await registry.refresh()
    else:
        await callback.answer()
    menu = menu_markup(
        registry, await current_selection(callback.from_user.id, db, registry, settings)
    )
    if menu is None:
        await edit(callback, NO_PROVIDERS, None)
        return
    await edit(callback, *menu)


@router.callback_query(ModelMenu.filter(F.action == "noop"))
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
