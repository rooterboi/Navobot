import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

import admin
import creator
import db
import manager
import user
from common import SubMiddleware, TrackMiddleware
from config import ADMIN_IDS, BOT_TOKEN, DB_PATH


async def cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("❌ Bekor qilindi.")


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN .env faylida ko'rsatilmagan")
    await db.init(DB_PATH)
    bot = Bot(BOT_TOKEN, session=AiohttpSession(timeout=300), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cancel, Command("cancel"))
    sub = SubMiddleware("main", lambda uid: uid in ADMIN_IDS)
    dp.message.outer_middleware(TrackMiddleware("main"))
    dp.message.outer_middleware(sub)
    dp.callback_query.outer_middleware(sub)

    dp.include_router(admin.router)
    dp.include_router(creator.router)
    dp.include_router(user.router)

    await manager.start_all()
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await manager.stop_all()
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
