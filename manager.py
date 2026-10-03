"""Child (kino) botlarni fonda boshqarish."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import db
from cinema import build_router

log = logging.getLogger(__name__)
running: dict[int, asyncio.Task] = {}


async def _run(dp, bot, bot_id):
    try:
        await dp.start_polling(bot, handle_signals=False, allowed_updates=dp.resolve_used_update_types())
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("Child bot %s to'xtadi", bot_id)
    finally:
        running.pop(bot_id, None)
        await bot.session.close()


async def start_child(token: str, owner_id: int):
    bot = Bot(token, session=AiohttpSession(timeout=300), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    if me.id in running:
        await bot.session.close()
        return me
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_router(me, owner_id))
    running[me.id] = asyncio.create_task(_run(dp, bot, me.id))
    log.info("Child bot ishga tushdi: @%s", me.username)
    return me


async def start_all():
    for r in await db.active_children():
        try:
            await start_child(r["token"], r["owner_id"])
        except Exception:
            log.exception("Child bot %s ishga tushmadi", r["bot_id"])


async def stop_all():
    for t in list(running.values()):
        t.cancel()
    await asyncio.gather(*running.values(), return_exceptions=True)
