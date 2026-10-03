import asyncio
import logging
import re
import time

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import db

log = logging.getLogger(__name__)
_ok_cache: dict[tuple, float] = {}


def btn(text, data=None, url=None):
    return InlineKeyboardButton(text=text, callback_data=data, url=url)


async def safe_edit(msg, text, kb=None):
    try:
        await msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            await msg.answer(text, reply_markup=kb)


async def not_joined(bot, scope, uid):
    out = []
    for c in await db.get_channels(scope, "sub"):
        try:
            m = await bot.get_chat_member(c["chat_id"], uid)
            if m.status in ("left", "kicked"):
                out.append(c)
        except Exception as e:  # bot kanalda admin emas va h.k. - o'tkazib yuboramiz
            log.warning("Obuna tekshiruvi xatosi (%s): %s", c["chat_id"], e)
    return out


class TrackMiddleware(BaseMiddleware):
    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, handler, event, data):
        u = data.get("event_from_user")
        if u and not u.is_bot:
            try:
                await db.add_user(self.scope, u.id, u.full_name)
            except Exception:
                log.exception("add_user")
        return await handler(event, data)


class SubMiddleware(BaseMiddleware):
    """Majburiy obuna (Check Join)."""

    def __init__(self, scope, is_admin):
        self.scope, self.is_admin = scope, is_admin

    async def __call__(self, handler, event, data):
        u = data.get("event_from_user")
        if not u or u.is_bot or self.is_admin(u.id):
            return await handler(event, data)
        key = (self.scope, u.id)
        is_chk = isinstance(event, CallbackQuery) and event.data == "chk"
        if not is_chk and _ok_cache.get(key, 0) > time.time():
            return await handler(event, data)
        chs = await not_joined(data["bot"], self.scope, u.id)
        if is_chk:
            if chs:
                return await event.answer("❌ Hali barcha kanallarga a'zo bo'lmadingiz", show_alert=True)
            _ok_cache[key] = time.time() + 60
            await event.answer("✅ Rahmat! Endi foydalanishingiz mumkin")
            try:
                await event.message.delete()
            except Exception:
                pass
            return
        if not chs:
            _ok_cache[key] = time.time() + 60
            return await handler(event, data)
        rows = [[btn(f"📢 {c['title'] or 'Kanal'}", url=c["link"])] for c in chs]
        rows.append([btn("✅ Tekshirish", "chk")])
        text = "❗️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:"
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        if isinstance(event, CallbackQuery):
            await event.answer()
            await event.message.answer(text, reply_markup=kb)
        else:
            await event.answer(text, reply_markup=kb)


async def parse_channel(bot, text):
    """'@kanal' yoki '-100123 https://t.me/+xxxx' -> dict. Xato bo'lsa ValueError."""
    parts = (text or "").strip().split()
    if not parts or not (parts[0].startswith("@") or re.fullmatch(r"-?\d+", parts[0])):
        raise ValueError("Format: @kanal_username yoki -100123456 https://t.me/+havola")
    try:
        chat = await bot.get_chat(parts[0] if parts[0].startswith("@") else int(parts[0]))
        member = await bot.get_chat_member(chat.id, bot.id)
    except TelegramBadRequest as e:
        raise ValueError(f"Kanal topilmadi yoki bot unga qo'shilmagan: {e.message}")
    if member.status not in ("administrator", "creator"):
        raise ValueError("Bot kanalda admin emas. Avval botni kanalga admin qiling.")
    link = parts[1] if len(parts) > 1 else (f"https://t.me/{chat.username}" if chat.username else None)
    if not link:
        raise ValueError("Yopiq kanal uchun havolani ham yozing: -100123456 https://t.me/+xxxx")
    return {"chat_id": chat.id, "title": chat.title or str(chat.id), "link": link}


def parse_buttons(text):
    rows = []
    for line in text.splitlines():
        if " - " not in line:
            continue
        t, u = line.split(" - ", 1)
        u = u.strip()
        if u.startswith("t.me/"):
            u = "https://" + u
        if t.strip() and u.startswith("http"):
            rows.append([btn(t.strip(), url=u)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def broadcast(bot, scope, from_chat, msg_id, markup=None, forward=False):
    ok = fail = 0
    for uid in await db.user_ids(scope):
        for attempt in range(2):
            try:
                if forward:
                    await bot.forward_message(uid, from_chat, msg_id)
                else:
                    await bot.copy_message(uid, from_chat, msg_id, reply_markup=markup)
                ok += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except (TelegramForbiddenError, TelegramBadRequest):
                fail += 1
                break
            except Exception:
                fail += 1
                break
        await asyncio.sleep(0.05)
    return ok, fail
