"""/creatorkodlikinobot — yashirin kino bot yaratish mexanizmi."""
import hmac
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import db
import manager
from config import DEFAULT_PIN

log = logging.getLogger(__name__)
router = Router()
TOKEN_RE = re.compile(r"^\d{6,12}:[\w-]{30,}$")


class C(StatesGroup):
    pin = State()
    token = State()


@router.message(Command("creatorkodlikinobot"))
async def entry(m: Message, state: FSMContext):
    if await db.get_setting("pin_enabled", "1") == "1":
        await state.set_state(C.pin)
        await state.update_data(tries=0)
        return await m.answer("🔐 PIN-kodni kiriting:")
    await state.set_state(C.token)
    await m.answer("🤖 @BotFather dan olgan yangi bot <b>tokenini</b> yuboring:")


@router.message(C.pin, F.text)
async def check_pin(m: Message, state: FSMContext):
    pin = await db.get_setting("pin", DEFAULT_PIN)
    try:
        await m.delete()
    except Exception:
        pass
    if hmac.compare_digest(m.text.strip(), pin):
        await state.set_state(C.token)
        return await m.answer("✅ To'g'ri. Endi @BotFather dan olgan yangi bot <b>tokenini</b> yuboring:")
    tries = (await state.get_data()).get("tries", 0) + 1
    if tries >= 3:
        await state.clear()
        return await m.answer("🚫 3 marta xato kiritildi.")
    await state.update_data(tries=tries)
    await m.answer(f"❌ Noto'g'ri PIN. Qolgan urinish: {3 - tries}")


@router.message(C.token, F.text)
async def get_token(m: Message, state: FSMContext):
    token = m.text.strip()
    try:
        await m.delete()  # tokenni chatda qoldirmaymiz
    except Exception:
        pass
    if not TOKEN_RE.match(token):
        return await m.answer("❌ Token formati noto'g'ri. Qayta yuboring yoki /cancel.")
    tmp = Bot(token)
    try:
        me = await tmp.get_me()
    except Exception:
        return await m.answer("❌ Token yaroqsiz. Qayta yuboring yoki /cancel.")
    finally:
        await tmp.session.close()
    try:
        await db.save_child(me.id, token, me.username, m.from_user.id)
        await manager.start_child(token, m.from_user.id)
    except Exception:
        log.exception("child start")
        return await m.answer("❌ Botni ishga tushirib bo'lmadi. Keyinroq urinib ko'ring.")
    await state.clear()
    await m.answer(
        f"🎉 <b>Kino bot tayyor!</b> @{me.username}\n\n"
        f"1️⃣ Botga kirib /admin ni yuboring (siz uning egasisiz).\n"
        f"2️⃣ Avto-post uchun botni kanalingizga <b>admin</b> qiling va admin paneldan «📡 Post kanal»ni ulang.\n"
        f"3️⃣ «➕ Kino qo'shish» orqali kinolarni kiriting."
    )
