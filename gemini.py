import asyncio
import html
import re

import google.generativeai as genai

import db
from config import GEMINI_MODEL

PROMPT = """Sen professional vokal ustoz va musiqa mutaxassisisan. Foydalanuvchi yuborgan ovoz yozuvini tingla va ijroni baholab ber.
Javob formati (aynan shunday):
BAL: <1 dan 100 gacha butun son>
🎙 Talaffuz: <1-2 jumla>
🥁 Ritm: <1-2 jumla>
🎼 Ijro mahorati: <1-2 jumla>
💬 Taqriz: <qiziqarli, do'stona, lekin professional izoh va 1-2 maslahat>
Agar yozuvda qo'shiq aytilmasa, buni halol ayt va BAL ni past qo'y. O'zbek tilida yoz. Markdown ishlatma."""


async def is_enabled():
    return bool(await db.get_setting("gemini_key"))


def _model(key):
    genai.configure(api_key=key)
    return genai.GenerativeModel(GEMINI_MODEL)


async def validate_key(key):
    await asyncio.to_thread(lambda: _model(key).generate_content("Salom, 'ok' deb javob ber").text)


async def rate_voice(data: bytes, mime: str):
    key = await db.get_setting("gemini_key")
    if not key:
        raise RuntimeError("Gemini API kaliti kiritilmagan")
    resp = await asyncio.to_thread(lambda: _model(key).generate_content([PROMPT, {"mime_type": mime, "data": data}]))
    text = resp.text.strip()
    m = re.search(r"BAL:\s*(\d{1,3})", text)
    score = max(1, min(100, int(m.group(1)))) if m else None
    body = re.sub(r"^\s*BAL:.*\n?", "", text, count=1).strip()
    body = html.escape(body)
    body = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", body)
    return score, body
