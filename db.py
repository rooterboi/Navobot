import time
import aiosqlite

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(scope TEXT, user_id INTEGER, name TEXT, joined INTEGER, last_active INTEGER, PRIMARY KEY(scope,user_id));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS channels(id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT, kind TEXT, chat_id INTEGER, title TEXT, link TEXT);
CREATE TABLE IF NOT EXISTS child_bots(bot_id INTEGER PRIMARY KEY, token TEXT, username TEXT, owner_id INTEGER, active INTEGER DEFAULT 1, created INTEGER);
CREATE TABLE IF NOT EXISTS movies(id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, code TEXT, title TEXT, year TEXT, quality TEXT, country TEXT, lang TEXT, genre TEXT, file_id TEXT, views INTEGER DEFAULT 0, created INTEGER, UNIQUE(bot_id,code));
"""


async def init(path: str):
    global _db
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.commit()


async def close():
    if _db:
        await _db.close()


async def run(q, p=()):
    cur = await _db.execute(q, p)
    await _db.commit()
    return cur


async def fetchall(q, p=()):
    async with _db.execute(q, p) as c:
        return await c.fetchall()


async def fetchone(q, p=()):
    async with _db.execute(q, p) as c:
        return await c.fetchone()


# ---- settings
async def get_setting(key, default=None):
    r = await fetchone("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else default


async def set_setting(key, value):
    await run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


async def del_setting(key):
    await run("DELETE FROM settings WHERE key=?", (key,))


# ---- users
async def add_user(scope, uid, name):
    now = int(time.time())
    await run(
        "INSERT INTO users VALUES(?,?,?,?,?) ON CONFLICT(scope,user_id) DO UPDATE SET last_active=excluded.last_active, name=excluded.name",
        (scope, uid, name, now, now),
    )


async def user_ids(scope):
    return [r["user_id"] for r in await fetchall("SELECT user_id FROM users WHERE scope=?", (scope,))]


async def stats(scope):
    now = int(time.time())
    r = await fetchone(
        "SELECT COUNT(*) t, SUM(last_active>=?) a1, SUM(last_active>=?) a7, SUM(joined>=?) n FROM users WHERE scope=?",
        (now - 86400, now - 7 * 86400, now - now % 86400, scope),
    )
    return {"total": r["t"] or 0, "d1": r["a1"] or 0, "d7": r["a7"] or 0, "new": r["n"] or 0}


# ---- channels
async def get_channels(scope, kind):
    return await fetchall("SELECT * FROM channels WHERE scope=? AND kind=?", (scope, kind))


async def add_channel(scope, kind, chat_id, title, link):
    await run("DELETE FROM channels WHERE scope=? AND kind=? AND chat_id=?", (scope, kind, chat_id))
    await run("INSERT INTO channels(scope,kind,chat_id,title,link) VALUES(?,?,?,?,?)", (scope, kind, chat_id, title, link))


async def del_channel(cid):
    await run("DELETE FROM channels WHERE id=?", (cid,))


async def clear_channels(scope, kind):
    await run("DELETE FROM channels WHERE scope=? AND kind=?", (scope, kind))


# ---- child bots
async def save_child(bot_id, token, username, owner_id):
    await run(
        "INSERT INTO child_bots VALUES(?,?,?,?,1,?) ON CONFLICT(bot_id) DO UPDATE SET token=excluded.token, username=excluded.username, owner_id=excluded.owner_id, active=1",
        (bot_id, token, username, owner_id, int(time.time())),
    )


async def active_children():
    return await fetchall("SELECT * FROM child_bots WHERE active=1")


async def count_children():
    return (await fetchone("SELECT COUNT(*) c FROM child_bots WHERE active=1"))["c"]


# ---- movies
async def next_code(bot_id):
    r = await fetchone("SELECT MAX(CAST(code AS INTEGER)) m FROM movies WHERE bot_id=?", (bot_id,))
    return str((r["m"] or 0) + 1)


async def code_exists(bot_id, code):
    return bool(await fetchone("SELECT 1 FROM movies WHERE bot_id=? AND code=?", (bot_id, code)))


async def add_movie(bot_id, d):
    await run(
        "INSERT INTO movies(bot_id,code,title,year,quality,country,lang,genre,file_id,created) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (bot_id, d["code"], d["title"], d["year"], d["quality"], d["country"], d["lang"], d["genre"], d["file_id"], int(time.time())),
    )


async def get_movie(bot_id, code):
    return await fetchone("SELECT * FROM movies WHERE bot_id=? AND code=?", (bot_id, code))


async def inc_views(mid):
    await run("UPDATE movies SET views=views+1 WHERE id=?", (mid,))


async def list_movies(bot_id, offset, limit):
    return await fetchall("SELECT * FROM movies WHERE bot_id=? ORDER BY id DESC LIMIT ? OFFSET ?", (bot_id, limit, offset))


async def del_movie(mid, bot_id):
    await run("DELETE FROM movies WHERE id=? AND bot_id=?", (mid, bot_id))


async def movie_stats(bot_id):
    r = await fetchone("SELECT COUNT(*) c, COALESCE(SUM(views),0) v FROM movies WHERE bot_id=?", (bot_id,))
    return r["c"], r["v"]
