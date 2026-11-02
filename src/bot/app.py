from aiogram import Dispatcher

from bot.handlers import chat, commands, models
from bot.middlewares import AccessMiddleware


def create_dispatcher(allowed_user_ids: frozenset[int]) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(AccessMiddleware(allowed_user_ids))
    dispatcher.include_routers(commands.router, models.router, chat.router)
    return dispatcher
