# Musiqa + Kino bot (aiogram 3)

## O'rnatish
sudo apt install -y ffmpeg nodejs     # ffmpeg shart; nodejs (yoki deno) YouTube uchun kerak
python -m venv venv && source venv/bin/activate
pip install -U -r requirements.txt
cp .env.example .env   # BOT_TOKEN va ADMIN_IDS ni to'ldiring
python main.py

## Muhim
- Yuklash ishlamay qolsa, avval:  pip install -U "yt-dlp[default]"
- Server IP si bloklansa (YouTube/Instagram): brauzerdan cookies.txt eksport qilib, .env da COOKIES_FILE ga yo'lini yozing.
- Admin: /admin. Yashirin kino-bot yaratish: /creatorkodlikinobot (PIN: 0009).
