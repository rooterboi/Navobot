"""Kodli Kino Bot (child bot). Har bir child uchun alohida router quriladi."""
import html
import logging
import re
import sqlite3

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import db
from common import (SubMiddleware, TrackMiddleware, broadcast, btn,
                    parse_channel, safe_edit)

log = logging.getLogger(__name__)
esc = html.escape

FIELDS = [
    ("title", "🎬 Kino nomini kiriting:"),
    ("year", "📅 Yilini kiriting (masalan: 2024):"),
    ("quality", "🖥 Sifatini kiriting (masalan: 1080p):"),
    ("country", "🗽 Davlatini kiriting (masalan: AQSH):"),
    ("lang", "🇺🇿 Tilini kiriting (masalan: O'zbek tilida):"),
    ("genre", "🍿 Janrlarini vergul bilan kiriting (masalan: Jangari, Drama):"),
    ("code", "🔢 Kino kodini kiriting (raqam) yoki <b>auto</b> deb yozing:"),
]


class CS(StatesGroup):
    video = State()
    fields = State()
    ch_add = State()
    bc = State()


def tags(g: str) -> str:
    parts = re.split(r"[,#]+", g) if "," in g else g.split()
    return " ".join("#" + re.sub(r"[^\w]", "", p) for p in parts if re.sub(r"[^\w]", "", p))


def info_text(d, username, post=False):
    t = (
        f"🎬 <b>{esc(d['title'])}</b>\n"
        f"📅 Yili: {esc(d['year'])}\n"
        f"🖥 Sifati: {esc(d['quality'])}\n"
        f"🗽 Davlati: {esc(d['country'])}\n"
        f"🇺🇿 Tili: {esc(d['lang'])}\n"
        f"🍿 Janri: {esc(tags(d['genre']))}\n"
    )
    if post:
        t += f"✅ Filmni ko'rish uchun &lt;&lt; <b>{esc(d['code'])}</b> ⬆️ kodini @{username} ga yuboring 🍿"
    else:
        t += f"\n📥 @{username}"
    return t


def build_router(me, owner_id: int) -> Router:
    scope, username = str(me.id), me.username
    root, ar, ur = Router(name=f"cinema_{me.id}"), Router(), Router()

    sub = SubMiddleware(scope, lambda uid: uid == owner_id)
    root.message.outer_middleware(TrackMiddleware(scope))
    root.message.outer_middleware(sub)
    root.callback_query.outer_middleware(sub)
    ar.message.filter(F.from_user.id == owner_id)
    ar.callback_query.filter(F.from_user.id == owner_id)

    back = [btn("⬅️ Orqaga", "c:home")]

    def menu():
        return InlineKeyboardMarkup(inline_keyboard=[
            [btn("➕ Kino qo'shish", "c:add"), btn("🎞 Kinolar", "c:list:0")],
            [btn("📊 Statistika", "c:stats"), btn("📢 Majburiy obuna", "c:ch:sub")],
            [btn("📡 Post kanal", "c:ch:post"), btn("📨 Reklama", "c:bc")],
        ])

    # ================= ADMIN =================
    @ar.message(Command("admin"))
    async def admin_cmd(m: Message, state: FSMContext):
        await state.clear()
        await m.answer("🛠 <b>Kino bot admin paneli</b>", reply_markup=menu())

    @ar.callback_query(F.data == "c:home")
    async def home(c: CallbackQuery, state: FSMContext):
        await state.clear()
        await safe_edit(c.message, "🛠 <b>Kino bot admin paneli</b>", menu())
        await c.answer()

    @ar.callback_query(F.data == "c:stats")
    async def stats(c: CallbackQuery):
        s = await db.stats(scope)
        cnt, views = await db.movie_stats(me.id)
        await safe_edit(c.message, (
            "📊 <b>Statistika</b>\n\n"
            f"👥 Foydalanuvchilar: <b>{s['total']}</b>\n🟢 24 soat faol: <b>{s['d1']}</b>\n"
            f"📅 7 kun faol: <b>{s['d7']}</b>\n🆕 Bugun: <b>{s['new']}</b>\n"
            f"🎬 Kinolar: <b>{cnt}</b>\n👁 Ko'rishlar: <b>{views}</b>"), InlineKeyboardMarkup(inline_keyboard=[back]))
        await c.answer()

    # ---- kino qo'shish
    @ar.callback_query(F.data == "c:add")
    async def add_start(c: CallbackQuery, state: FSMContext):
        await state.set_state(CS.video)
        await safe_edit(c.message, "🎥 Kino <b>videosini</b> yuboring (bekor: /cancel):")
        await c.answer()

    @ar.message(Command("cancel"))
    async def cancel(m: Message, state: FSMContext):
        await state.clear()
        await m.answer("❌ Bekor qilindi.", reply_markup=menu())

    @ar.message(CS.video, F.video | F.document)
    async def got_video(m: Message, state: FSMContext):
        fid = m.video.file_id if m.video else m.document.file_id
        await state.update_data(file_id=fid, i=0, vals={})
        await state.set_state(CS.fields)
        await m.answer(FIELDS[0][1])

    @ar.message(CS.video)
    async def not_video(m: Message):
        await m.answer("❗️ Iltimos, video fayl yuboring.")

    @ar.message(CS.fields, F.text)
    async def got_field(m: Message, state: FSMContext):
        d = await state.get_data()
        i, vals = d["i"], d["vals"]
        key, _ = FIELDS[i]
        val = m.text.strip()
        if key == "code":
            if val.lower() == "auto":
                val = await db.next_code(me.id)
            elif not val.isdigit():
                return await m.answer("❌ Kod faqat raqam bo'lishi kerak.")
            if await db.code_exists(me.id, val):
                return await m.answer("❌ Bu kod band. Boshqa kod kiriting yoki <b>auto</b>.")
        vals[key] = val
        if i + 1 < len(FIELDS):
            await state.update_data(i=i + 1, vals=vals)
            return await m.answer(FIELDS[i + 1][1])
        movie = {**vals, "file_id": d["file_id"]}
        await state.clear()
        try:
            await db.add_movie(me.id, movie)
        except sqlite3.IntegrityError:
            return await m.answer("❌ Bu kod band, qaytadan /admin orqali urinib ko'ring.")
        err = await autopost(m, movie)
        await m.answer(f"✅ Kino saqlandi! Kod: <b>{esc(movie['code'])}</b>" + (f"\n⚠️ {err}" if err else "\n📡 Kanalga post tashlandi."),
                       reply_markup=menu())

    async def autopost(m, movie):
        chs = await db.get_channels(scope, "post")
        if not chs:
            return "Post kanal ulanmagan, avto-post tashlanmadi."
        kb = InlineKeyboardMarkup(inline_keyboard=[[btn("🍿 Kinoni ko'rish", url=f"https://t.me/{username}?start={movie['code']}")]])
        errs = []
        for ch in chs:
            try:
                await m.bot.send_message(ch["chat_id"], info_text(movie, username, post=True), reply_markup=kb)
            except Exception as e:
                log.warning("autopost: %s", e)
                errs.append(f"Kanalga post tashlab bo'lmadi ({esc(ch['title'])}): bot admin ekanini tekshiring.")
        return " ".join(errs)

    # ---- kinolar ro'yxati
    @ar.callback_query(F.data.startswith("c:list:"))
    async def movie_list(c: CallbackQuery):
        page = int(c.data.split(":")[2])
        total, _ = await db.movie_stats(me.id)
        movies = await db.list_movies(me.id, page * 10, 10)
        rows = [[btn(f"🗑 {x['code']} · {x['title'][:35]}", f"c:del:{x['id']}:{page}")] for x in movies]
        nav = []
        if page > 0:
            nav.append(btn("◀️", f"c:list:{page - 1}"))
        if (page + 1) * 10 < total:
            nav.append(btn("▶️", f"c:list:{page + 1}"))
        if nav:
            rows.append(nav)
        rows.append(back)
        await safe_edit(c.message, f"🎞 <b>Kinolar</b> ({total} ta)\nO'chirish uchun kinoni bosing:" if total else "🎞 Kinolar yo'q.",
                        InlineKeyboardMarkup(inline_keyboard=rows))
        await c.answer()

    @ar.callback_query(F.data.startswith("c:del:"))
    async def movie_del(c: CallbackQuery):
        _, _, mid, page = c.data.split(":")
        await db.del_movie(int(mid), me.id)
        await c.answer("🗑 O'chirildi")
        c.data = f"c:list:{page}"
        await movie_list(c)

    # ---- kanallar (obuna / post)
    async def ch_view(c, kind):
        chs = await db.get_channels(scope, kind)
        title = "📢 <b>Majburiy obuna kanallari</b>" if kind == "sub" else "📡 <b>Avto-post kanali</b>"
        rows = [[btn(f"🗑 {x['title']}", f"c:chdel:{x['id']}:{kind}")] for x in chs]
        rows += [[btn("➕ Qo'shish" if kind == "sub" else "🔄 Kanalni ulash/almashtirish", f"c:chadd:{kind}")], back]
        await safe_edit(c.message, title + "\n\n" + ("\n".join(f"• {esc(x['title'])}" for x in chs) or "Hozircha yo'q."),
                        InlineKeyboardMarkup(inline_keyboard=rows))

    @ar.callback_query(F.data.startswith("c:ch:"))
    async def ch(c: CallbackQuery):
        await ch_view(c, c.data.split(":")[2])
        await c.answer()

    @ar.callback_query(F.data.startswith("c:chdel:"))
    async def ch_del(c: CallbackQuery):
        _, _, cid, kind = c.data.split(":")
        await db.del_channel(int(cid))
        await ch_view(c, kind)
        await c.answer("O'chirildi")

    @ar.callback_query(F.data.startswith("c:chadd:"))
    async def ch_add_start(c: CallbackQuery, state: FSMContext):
        await state.set_state(CS.ch_add)
        await state.update_data(kind=c.data.split(":")[2])
        await safe_edit(c.message, "➕ Kanalni yuboring: <code>@kanal</code> yoki <code>-100123 https://t.me/+xxxx</code>\n⚠️ Bot kanalda admin bo'lishi shart. Bekor: /cancel")
        await c.answer()

    @ar.message(CS.ch_add, F.text)
    async def ch_add(m: Message, state: FSMContext):
        kind = (await state.get_data())["kind"]
        try:
            info = await parse_channel(m.bot, m.text)
        except ValueError as e:
            return await m.answer(f"❌ {esc(str(e))}")
        if kind == "post":
            await db.clear_channels(scope, "post")
        await db.add_channel(scope, kind, info["chat_id"], info["title"], info["link"])
        await state.clear()
        await m.answer(f"✅ Qo'shildi: <b>{esc(info['title'])}</b>", reply_markup=menu())

    # ---- reklama
    @ar.callback_query(F.data == "c:bc")
    async def bc_start(c: CallbackQuery, state: FSMContext):
        await state.set_state(CS.bc)
        await safe_edit(c.message, "📨 Hammaga yuboriladigan xabarni yuboring (bekor: /cancel):")
        await c.answer()

    @ar.message(CS.bc)
    async def bc_send(m: Message, state: FSMContext):
        await state.clear()
        await m.answer("🚀 Yuborilmoqda...")
        ok, fail = await broadcast(m.bot, scope, m.chat.id, m.message_id)
        await m.answer(f"✅ Tugadi\n📬 Yetkazildi: {ok}\n🚫 Yetkazilmadi: {fail}", reply_markup=menu())

    # ================= FOYDALANUVCHI =================
    async def send_by_code(m: Message, code: str):
        mv = await db.get_movie(me.id, code)
        if not mv:
            return await m.answer("❌ Bunday kodli kino topilmadi.")
        try:
            await m.answer_video(mv["file_id"], caption=info_text(dict(mv), username))
        except Exception:
            try:
                await m.answer_document(mv["file_id"], caption=info_text(dict(mv), username))
            except Exception:
                log.exception("kino yuborish")
                return await m.answer("⚠️ Kinoni yuborib bo'lmadi, keyinroq urinib ko'ring.")
        await db.inc_views(mv["id"])

    @ur.message(CommandStart(deep_link=True))
    async def start_code(m: Message, command: CommandObject):
        await send_by_code(m, command.args.strip())

    @ur.message(CommandStart())
    async def start(m: Message):
        extra = "\n\n🛠 Admin panel: /admin" if m.from_user.id == owner_id else ""
        await m.answer(f"🎬 <b>Kino botga xush kelibsiz!</b>\n\nKino kodini (raqam) yuboring — kinoni topib beraman.{extra}")

    @ur.message(StateFilter(None), F.text.regexp(r"^\d{1,12}$"))
    async def by_code(m: Message):
        await send_by_code(m, m.text.strip())

    @ur.message(StateFilter(None), F.text, ~F.text.startswith("/"))
    async def other(m: Message):
        await m.answer("🔢 Iltimos, kino kodini raqam ko'rinishida yuboring.")

    root.include_router(ar)
    root.include_router(ur)
    return root
