"""Musiqa/Media downloader bot: foydalanuvchi handlerlari."""
import asyncio
import html
import logging
import re

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message

import db
import gemini
from audio_fx import FX, apply_fx, fx_kb, video_to_mp3
from common import btn
from config import MAX_UPLOAD
from downloader import (cleanup, download_audio, download_video, explain,
                        extract_url, new_workdir, search_music)

log = logging.getLogger(__name__)
router = Router()
SEM = asyncio.Semaphore(4)  # bir vaqtda ko'pi bilan 4 ta yuklash


class K(StatesGroup):
    wait = State()


def safe_name(s):
    return re.sub(r"[^\w\-. ()]", "", s or "audio")[:60].strip() or "audio"


def dur(sec):
    return f"{sec // 60}:{sec % 60:02d}" if sec else ""


@router.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 Instagram / TikTok / YouTube havolasini yuboring — video va MP3 olasiz.\n"
        "🔎 Qo'shiq nomini yozing — musiqa topib beraman.\n"
        "🎤 /karaoke — ovozingizni AI baholaydi."
    )


# ---------------- Karaoke
@router.message(Command("karaoke"))
async def karaoke(m: Message, state: FSMContext):
    if not await gemini.is_enabled():
        return await m.answer("🤖 AI hozircha faol emas (admin Gemini API kalitini kiritmagan).")
    await state.set_state(K.wait)
    await m.answer("🎤 Qo'shiq aytib <b>ovozli xabar</b> (yoki audio) yuboring.\nBekor qilish: /cancel")


@router.message(K.wait, F.voice | F.audio)
async def karaoke_rate(m: Message, state: FSMContext):
    f = m.voice or m.audio
    if (f.duration or 0) > 300:
        return await m.answer("⏱ Iltimos, 5 daqiqadan qisqa yozuv yuboring.")
    if (f.file_size or 0) > 19 * 1024 * 1024:
        return await m.answer("📦 Fayl juda katta (20MB gacha).")
    st = await m.answer("🎧 Tinglayapman va baholayapman...")
    wd = new_workdir()
    try:
        dst = wd / "in.bin"
        await m.bot.download(f.file_id, destination=dst)
        mime = f.mime_type or "audio/ogg"
        score, body = await gemini.rate_voice(dst.read_bytes(), mime)
        head = ""
        if score:
            filled = score // 10
            head = f"⭐ <b>Bahoyingiz: {score}/100</b>\n[{'█' * filled}{'░' * (10 - filled)}]\n\n"
        await st.edit_text(f"🎤 <b>AI Karaoke natijasi</b>\n\n{head}{body}")
        await state.clear()
    except Exception as e:
        log.exception("karaoke")
        await st.edit_text(f"❌ AI baholashda xatolik: {html.escape(str(e)[:200])}")
    finally:
        cleanup(wd)


@router.message(K.wait)
async def karaoke_wrong(m: Message):
    await m.answer("🎤 Iltimos, ovozli xabar yoki audio yuboring. Bekor qilish: /cancel")


# ---------------- Havola
async def handle_link(m: Message, url: str):
    st = await m.answer("⏳ Yuklanmoqda...")
    wd = new_workdir()
    try:
        async with SEM:
            video, info = await download_video(url, wd)
        title = info.get("title") or "Video"
        me = await m.bot.get_me()
        await m.answer_video(FSInputFile(video), caption=f"🎬 {html.escape(title[:200])}\n\n📥 @{me.username}",
                             supports_streaming=True)
        mp3 = wd / "audio.mp3"
        try:
            await video_to_mp3(video, mp3)
            if mp3.stat().st_size <= MAX_UPLOAD:
                await m.answer_audio(FSInputFile(mp3, filename=f"{safe_name(title)}.mp3"), title=title[:60],
                                     performer=info.get("uploader"), reply_markup=fx_kb())
        except Exception:
            log.exception("audio ajratish")
        await st.delete()
    except Exception as e:
        log.exception("link yuklash: %s", url)
        await st.edit_text(f"❌ Yuklab bo'lmadi.\n<i>{explain(e)}</i>")
    finally:
        cleanup(wd)


# ---------------- Matn: havola yoki qidiruv
@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def on_text(m: Message):
    text = m.text.strip()
    url = extract_url(text)
    if url:
        return await handle_link(m, url)
    if len(text) < 2:
        return
    st = await m.answer("🔎 Qidirilmoqda...")
    try:
        res = await search_music(text)
    except Exception:
        log.exception("qidiruv")
        return await st.edit_text("❌ Qidiruvda xatolik. Birozdan so'ng urinib ko'ring.")
    if not res:
        return await st.edit_text("😕 Hech narsa topilmadi. Boshqacha yozib ko'ring.")
    rows = []
    for i, r in enumerate(res, 1):
        t = f"{i}. {r['title'][:48]} · {dur(r['duration'])}".strip(" ·")
        rows.append([btn(t, f"dl:{r['id']}")])
    await st.edit_text(f"🎵 <b>{html.escape(text[:60])}</b> bo'yicha natijalar:",
                       reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("dl:"))
async def dl(c: CallbackQuery):
    vid = c.data[3:]
    await c.answer("⏳ Yuklanmoqda...")
    st = await c.message.answer("⏳ Musiqa yuklanmoqda, biroz kuting...")
    wd = new_workdir()
    try:
        async with SEM:
            path, info = await download_audio(f"https://www.youtube.com/watch?v={vid}", wd)
        title = info.get("title") or "Musiqa"
        me = await c.bot.get_me()
        await c.message.answer_audio(
            FSInputFile(path, filename=f"{safe_name(title)}.mp3"),
            title=title[:60], performer=info.get("uploader"), duration=int(info.get("duration") or 0),
            caption=f"🎧 @{me.username}", reply_markup=fx_kb(),
        )
        await st.delete()
    except Exception as e:
        log.exception("musiqa yuklash: %s", vid)
        await st.edit_text(f"❌ Yuklab bo'lmadi.\n<i>{explain(e)}</i>\nBoshqa natijani tanlab ko'ring.")
    finally:
        cleanup(wd)


# ---------------- Effektlar
@router.callback_query(F.data.startswith("fx:"))
async def fx(c: CallbackQuery):
    key = c.data[3:]
    aud = c.message.audio
    if key not in FX or not aud:
        return await c.answer("Xatolik", show_alert=True)
    label = FX[key][0]
    if (aud.file_size or 0) > 19 * 1024 * 1024:
        return await c.answer("Fayl 20MB dan katta, qayta ishlab bo'lmaydi", show_alert=True)
    await c.answer(f"⏳ {label} qo'llanmoqda...")
    st = await c.message.answer(f"⏳ {label} effekti tayyorlanmoqda...")
    wd = new_workdir()
    try:
        src, out = wd / "in.mp3", wd / "out.mp3"
        await c.bot.download(aud.file_id, destination=src)
        async with SEM:
            await apply_fx(src, out, key)
        title = aud.title or "Musiqa"
        await c.message.answer_audio(FSInputFile(out, filename=f"{safe_name(title)} ({key}).mp3"),
                                     title=f"{title[:45]} [{label}]", performer=aud.performer,
                                     reply_markup=fx_kb())
        await st.delete()
    except Exception:
        log.exception("fx")
        await st.edit_text("❌ Effektni qo'llab bo'lmadi (ffmpeg o'rnatilganini tekshiring).")
    finally:
        cleanup(wd)
