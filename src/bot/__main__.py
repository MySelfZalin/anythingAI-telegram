import asyncio
import logging
import os

from aiogram import Bot
from dotenv import find_dotenv, load_dotenv

from bot.app import create_dispatcher
from bot.config import Settings, load_providers_config
from bot.handlers.commands import COMMANDS
from bot.middlewares import UserLocks
from bot.providers.registry import Registry
from bot.storage import Database


async def main() -> None:
    load_dotenv(find_dotenv(usecwd=True))
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    registry = Registry.from_config(load_providers_config(settings.providers_file), os.environ)
    await registry.refresh()
    provider_name, _, model_id = settings.default_model.partition(":")
    if settings.default_model and registry.select(provider_name, model_id) is None:
        logging.warning("DEFAULT_MODEL %s not found, using first available", settings.default_model)
    db = await Database.open(settings.database_path)
    bot = Bot(settings.bot_token.get_secret_value())

    dispatcher = create_dispatcher(settings.allowed_user_ids)

    if not settings.allowed_user_ids:
        logging.warning("ALLOWED_USER_IDS is empty: the bot will answer everyone")

    try:
        await bot.set_my_commands(COMMANDS)
        await dispatcher.start_polling(
            bot, db=db, registry=registry, settings=settings, locks=UserLocks()
        )
    finally:
        await bot.session.close()
        await db.close()
        await registry.close()


if __name__ == "__main__":
    asyncio.run(main())
