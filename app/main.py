import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import settings
from app.handlers import admin, media, start
from app.middlewares.tracking import TrackingMiddleware
from app.services import storage


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
    await storage.init_db()

    dp = Dispatcher()
    dp.message.outer_middleware(TrackingMiddleware())
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(media.router)

    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
