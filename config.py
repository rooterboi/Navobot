import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}
DB_PATH = os.getenv("DB_PATH", "bot.db")
COOKIES_FILE = os.getenv("COOKIES_FILE", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_PIN = "0009"
TMP_DIR = Path(os.getenv("TMP_DIR", "downloads"))
TMP_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = 49 * 1024 * 1024  # Telegram bot yuklash limiti ~50MB
