"""Musiqa boti admin paneli."""
import asyncio
import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import db
import gemini
from common import broadcast, btn, parse_buttons, parse_channel, safe_edit
from config import ADMIN_IDS, DEFAULT_PIN

log = logging.getLogger(__name__)
router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))
_tasks: set = set()


class A(StatesGroup):
    bc_msg = State()
    bc_btn = State()
    ch_add = State()
    pin_new = State()
    ai_key = State()


BACK = [btn("⬅️ Orqaga", "adm:home")]


def kb(*rows):
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def home_kb():
    return kb(
        [btn("📊 Statistika", "adm:stats"), btn("📢 Reklama", "adm:bc")],
        [btn("🔐 Majburiy obuna", "adm:ch"), btn("🔑 PIN-kod", "adm:pin")],
        [btn("🤖 Gemini AI API", "adm:ai")],
    )


@router.message(Command("admin"))
async def admin_cmd(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("🛠 <b>Admin panel</b>", reply_markup=home_kb())


@router.callback_query(F.data == "adm:home")
async def home(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(c.message, "🛠 <b>Admin panel</b>", home_kb())
    await c.answer()


# ---------- Statistika
@router.callback_query(F.data == "adm:stats")
async def stats(c: CallbackQuery):
    s = await db.stats("main")
    n = await db.count_children()
    await safe_edit(c.message, (
        "📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{s['total']}</b>\n"
        f"🟢 Oxirgi 24 soat faol: <b>{s['d1']}</b>\n"
        f"📅 Oxirgi 7 kun faol: <b>{s['d7']}</b>\n"
        f"🆕 Bugun qo'shilgan: <b>{s['new']}</b>\n"
        f"🎬 Kino botlar: <b>{n}</b>"), kb(BACK))
    await c.answer()


# ---------- Reklama
@router.callback_query(F.data == "adm:bc")
async def bc_start(c: CallbackQuery, state: FSMContext):
    await state.set_state(A.bc_msg)
    await safe_edit(c.message, "📢 Yuboriladigan xabarni yuboring (matn, rasm, video, forward — istalgani).", kb(BACK))
    await c.answer()


@router.message(A.bc_msg)
async def bc_msg(m: Message, state: FSMContext):
    await state.update_data(chat=m.chat.id, mid=m.message_id)
    await state.set_state(A.bc_btn)
    await m.answer("🔘 Inline tugmalar kerakmi? Har qatorga: <code>Matn - https://link</code>\nKerak bo'lmasa <b>yo'q</b> deb yozing.")


@router.message(A.bc_btn, F.text)
async def bc_btn(m: Message, state: FSMContext):
    markup = None
    if m.text.strip().lower() not in ("yo'q", "yoq", "yo`q", "-"):
        markup = parse_buttons(m.text)
        if not markup:
            return await m.answer("❌ Format noto'g'ri. Masalan: <code>Kanal - https://t.me/kanal</code>")
    await state.update_data(btns=m.text if markup else None)
    d = await state.get_data()
    await m.bot.copy_message(m.chat.id, d["chat"], d["mid"], reply_markup=markup)
    await m.answer("👆 Shu xabar hammaga yuborilsinmi?", reply_markup=kb(
        [btn("✅ Yuborish", "adm:go:copy")],
        [btn("↪️ Forward qilib yuborish (tugmasiz)", "adm:go:fwd")],
        [btn("❌ Bekor qilish", "adm:home")]))


@router.callback_query(F.data.startswith("adm:go:"), A.bc_btn)
async def bc_go(c: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    fwd = c.data.endswith("fwd")
    markup = parse_buttons(d["btns"]) if d.get("btns") else None
    await c.message.edit_text("🚀 Yuborish boshlandi...")
    await c.answer()

    async def job():
        ok, fail = await broadcast(c.bot, "main", d["chat"], d["mid"], markup, fwd)
        await c.bot.send_message(c.from_user.id, f"✅ Reklama tugadi\n\n📬 Yetkazildi: {ok}\n🚫 Yetkazilmadi: {fail}")

    t = asyncio.create_task(job())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


# ---------- Majburiy obuna
async def ch_view(c):
    chs = await db.get_channels("main", "sub")
    rows = [[btn(f"🗑 {x['title']}", f"adm:chdel:{x['id']}")] for x in chs]
    rows += [[btn("➕ Kanal qo'shish", "adm:chadd")], BACK]
    txt = "🔐 <b>Majburiy obuna kanallari</b>\n\n" + ("\n".join(f"• {html.escape(x['title'])}" for x in chs) or "Hozircha yo'q.")
    await safe_edit(c.message, txt, InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "adm:ch")
async def ch(c: CallbackQuery):
    await ch_view(c)
    await c.answer()


@router.callback_query(F.data.startswith("adm:chdel:"))
async def ch_del(c: CallbackQuery):
    await db.del_channel(int(c.data.split(":")[2]))
    await ch_view(c)
    await c.answer("O'chirildi")


@router.callback_query(F.data == "adm:chadd")
async def ch_add_start(c: CallbackQuery, state: FSMContext):
    await state.set_state(A.ch_add)
    await safe_edit(c.message, "➕ Kanalni yuboring:\n<code>@kanal_username</code>\nyoki yopiq kanal uchun:\n<code>-100123456789 https://t.me/+xxxx</code>\n\n⚠️ Bot kanalda admin bo'lishi shart.", kb(BACK))
    await c.answer()


@router.message(A.ch_add, F.text)
async def ch_add(m: Message, state: FSMContext):
    try:
        info = await parse_channel(m.bot, m.text)
    except ValueError as e:
        return await m.answer(f"❌ {html.escape(str(e))}")
    await db.add_channel("main", "sub", info["chat_id"], info["title"], info["link"])
    await state.clear()
    await m.answer(f"✅ Qo'shildi: <b>{html.escape(info['title'])}</b>", reply_markup=kb(BACK))


# ---------- PIN
async def pin_view(c):
    pin = await db.get_setting("pin", DEFAULT_PIN)
    on = await db.get_setting("pin_enabled", "1") == "1"
    await safe_edit(c.message, (
        "🔑 <b>PIN-kod boshqaruvi</b> (/creatorkodlikinobot)\n\n"
        f"Holat: {'🔒 PIN-kodli' if on else '🔓 PIN-kodsiz'}\nPIN: <code>{html.escape(pin)}</code>"),
        kb([btn("✏️ PIN o'zgartirish", "adm:pinset")],
           [btn("🔓 PIN so'ramaslik" if on else "🔒 PIN so'rashni yoqish", "adm:pintog")], BACK))


@router.callback_query(F.data == "adm:pin")
async def pin(c: CallbackQuery):
    await pin_view(c)
    await c.answer()


@router.callback_query(F.data == "adm:pintog")
async def pin_toggle(c: CallbackQuery):
    on = await db.get_setting("pin_enabled", "1") == "1"
    await db.set_setting("pin_enabled", "0" if on else "1")
    await pin_view(c)
    await c.answer("Saqlandi")


@router.callback_query(F.data == "adm:pinset")
async def pin_set(c: CallbackQuery, state: FSMContext):
    await state.set_state(A.pin_new)
    await safe_edit(c.message, "✏️ Yangi PIN-kodni yuboring (3-12 belgi, bo'sh joysiz):", kb(BACK))
    await c.answer()


@router.message(A.pin_new, F.text)
async def pin_new(m: Message, state: FSMContext):
    p = m.text.strip()
    if not (3 <= len(p) <= 12) or " " in p:
        return await m.answer("❌ 3-12 belgi, bo'sh joysiz bo'lsin.")
    await db.set_setting("pin", p)
    await db.set_setting("pin_enabled", "1")
    await state.clear()
    try:
        await m.delete()
    except Exception:
        pass
    await m.answer("✅ PIN-kod yangilandi.", reply_markup=kb(BACK))


# ---------- Gemini
async def ai_view(c):
    on = await gemini.is_enabled()
    rows = [[btn("🔑 Kalit kiritish/yangilash", "adm:aiset")]]
    if on:
        rows.append([btn("🗑 Kalitni o'chirish", "adm:aidel")])
    rows.append(BACK)
    await safe_edit(c.message, f"🤖 <b>Gemini AI</b>\n\nHolat: {'✅ Faol (/karaoke ishlaydi)' if on else '❌ Kalit kiritilmagan'}", InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "adm:ai")
async def ai(c: CallbackQuery):
    await ai_view(c)
    await c.answer()


@router.callback_query(F.data == "adm:aiset")
async def ai_set(c: CallbackQuery, state: FSMContext):
    await state.set_state(A.ai_key)
    await safe_edit(c.message, "🔑 Google Gemini API kalitini yuboring (aistudio.google.com/apikey):", kb(BACK))
    await c.answer()


@router.callback_query(F.data == "adm:aidel")
async def ai_del(c: CallbackQuery):
    await db.del_setting("gemini_key")
    await ai_view(c)
    await c.answer("O'chirildi")


@router.message(A.ai_key, F.text)
async def ai_key(m: Message, state: FSMContext):
    key = m.text.strip()
    try:
        await m.delete()
    except Exception:
        pass
    st = await m.answer("⏳ Kalit tekshirilmoqda...")
    try:
        await gemini.validate_key(key)
    except Exception as e:
        return await st.edit_text(f"❌ Kalit ishlamadi: {html.escape(str(e)[:200])}\nQayta yuboring yoki orqaga qayting.")
    await db.set_setting("gemini_key", key)
    await state.clear()
    await st.edit_text("✅ Kalit saqlandi. AI funksiyalar (/karaoke) faollashdi!", reply_markup=kb(BACK))
