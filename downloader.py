import asyncio
import logging
import os
import re
import shutil
import uuid
from pathlib import Path

import yt_dlp

from config import COOKIES_FILE, MAX_UPLOAD, TMP_DIR

log = logging.getLogger(__name__)
URL_RE = re.compile(r"https?://\S+")
DOMAINS = ("instagram.com", "tiktok.com", "youtube.com", "youtu.be")
YT_CLIENTS = [None, ["android"], ["ios"], ["tv"], ["web_safari"], ["mweb"]]
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov"}


class TooBig(Exception):
    pass


def new_workdir() -> Path:
    p = TMP_DIR / uuid.uuid4().hex
    p.mkdir(parents=True, exist_ok=True)
    return p


def cleanup(p: Path):
    shutil.rmtree(p, ignore_errors=True)


def extract_url(text: str):
    m = URL_RE.search(text or "")
    return m.group(0) if m and any(d in m.group(0) for d in DOMAINS) else None


def explain(e: Exception) -> str:
    s = str(e).lower()
    if isinstance(e, TooBig):
        return "Fayl Telegram limiti (50MB) dan katta."
    if "sign in" in s or "confirm you" in s or "cookies" in s or "login" in s:
        return "Manba kirishni (cookies) talab qilyapti. Admin COOKIES_FILE sozlashi kerak."
    if "private" in s or "unavailable" in s or "not available" in s:
        return "Video yopiq yoki mavjud emas."
    if "ffmpeg" in s:
        return "ffmpeg topilmadi yoki xato berdi."
    return "Yuklashda xatolik yuz berdi."


def _opts(workdir: Path, client=None):
    o = {
        "quiet": True, "no_warnings": True, "noplaylist": True, "retries": 5,
        "fragment_retries": 5, "socket_timeout": 30, "geo_bypass": True,
        "outtmpl": str(workdir / "%(id)s.%(ext)s"), "restrictfilenames": True,
        "concurrent_fragment_downloads": 4,
    }
    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        o["cookiefile"] = COOKIES_FILE
    if client:
        o["extractor_args"] = {"youtube": {"player_client": client}}
    return o


def _clients(url):
    return YT_CLIENTS if ("youtu" in url) else [None]


def _first(info):
    if info and info.get("entries"):
        info = next(e for e in info["entries"] if e)
    return info


# ---------------- qidiruv
def _search(query, n=8):
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True, "socket_timeout": 20}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    out = []
    for e in (info or {}).get("entries") or []:
        if not e or not e.get("id"):
            continue
        d = int(e.get("duration") or 0)
        if d > 1500:
            continue
        out.append({"id": e["id"], "title": e.get("title") or "Noma'lum", "duration": d})
    return out


async def search_music(query):
    return await asyncio.to_thread(_search, query)


# ---------------- audio
def _download_audio(url, workdir):
    last = None
    for client in _clients(url):
        opts = _opts(workdir, client)
        opts.update({
            "format": "bestaudio[filesize<45M]/bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        })
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = _first(ydl.extract_info(url, download=True))
            files = list(workdir.glob(f"{info['id']}*.mp3")) or list(workdir.glob("*.mp3"))
            if not files:
                raise RuntimeError("mp3 fayl hosil bo'lmadi (ffmpeg o'rnatilganmi?)")
            if files[0].stat().st_size > MAX_UPLOAD:
                raise TooBig()
            return files[0], info
        except TooBig:
            raise
        except Exception as e:
            last = e
            log.warning("audio urinish (client=%s) muvaffaqiyatsiz: %s", client, e)
    raise last or RuntimeError("Yuklab bo'lmadi")


async def download_audio(url, workdir):
    return await asyncio.to_thread(_download_audio, url, workdir)


# ---------------- video
def _download_video(url, workdir):
    last = None
    for h in (720, 480, 360):
        fmt = f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/b[height<={h}][ext=mp4]/bv*[height<={h}]+ba/b[height<={h}]/b"
        for client in _clients(url):
            opts = _opts(workdir, client)
            opts.update({"format": fmt, "merge_output_format": "mp4"})
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = _first(ydl.extract_info(url, download=True))
                files = [f for f in workdir.glob(f"{info['id']}*") if f.suffix.lower() in VIDEO_EXT]
                if not files:
                    raise RuntimeError("video fayl topilmadi")
                if files[0].stat().st_size > MAX_UPLOAD:
                    files[0].unlink(missing_ok=True)
                    last = TooBig()
                    break  # pastroq sifatga o'tamiz
                return files[0], info
            except Exception as e:
                last = e
                log.warning("video urinish (h=%s, client=%s): %s", h, client, e)
    raise last or RuntimeError("Yuklab bo'lmadi")


async def download_video(url, workdir):
    return await asyncio.to_thread(_download_video, url, workdir)
