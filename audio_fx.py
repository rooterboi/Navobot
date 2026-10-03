import asyncio
from aiogram.types import InlineKeyboardMarkup

from common import btn

FX = {
    "8d": ("🎧 8D", "aformat=channel_layouts=stereo,apulsator=hz=0.125,aecho=0.8:0.88:40:0.25"),
    "concert": ("🏟 Concert Hall", "aecho=0.8:0.9:700|1300:0.35|0.25,bass=g=3"),
    "slowed": ("🐢 Slowed", "aresample=44100,asetrate=44100*0.82,aresample=44100,aecho=0.8:0.88:60:0.25"),
    "minus": ("🎤 Minus", "aformat=channel_layouts=stereo,pan=stereo|c0=c0-c1|c1=c1-c0"),
}


def fx_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("🎧 8D", "fx:8d"), btn("🏟 Concert Hall", "fx:concert")],
        [btn("🐢 Slowed", "fx:slowed"), btn("🎤 Minus", "fx:minus")],
    ])


async def run_ffmpeg(*args):
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *map(str, args),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await asyncio.wait_for(proc.communicate(), timeout=600)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg: " + err.decode(errors="ignore")[-400:])


async def apply_fx(src, dst, key):
    await run_ffmpeg("-i", src, "-vn", "-af", FX[key][1], "-c:a", "libmp3lame", "-b:a", "192k", dst)


async def video_to_mp3(src, dst):
    await run_ffmpeg("-i", src, "-vn", "-acodec", "libmp3lame", "-b:a", "192k", dst)
