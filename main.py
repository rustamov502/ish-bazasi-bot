import asyncio
import html
import logging
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from threading import Thread

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton as B,
    InlineKeyboardMarkup as IK,
    KeyboardButton as KB,
    ReplyKeyboardMarkup as RK,
    WebAppInfo,
)

# FastAPI va veb-server kutubxonalari (Mini App uchun)
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import uvicorn


# ============================================================
# ISH BAZASI BOT — FINAL + MINI APP
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = int(os.getenv("ADMIN_ID", "8451295149"))
ADMIN_CONTACT = os.getenv("ADMIN_CONTACT", "@rustamovvvll")

CHANNEL_ID = os.getenv("CHANNEL_ID", "@Ishbazasi")
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@Ishbazasi")

INSTAGRAM_URL = os.getenv(
    "INSTAGRAM_URL",
    "https://instagram.com/ishbazasi"
)

CARD_NUMBER = os.getenv("CARD_NUMBER", "")
CARD_HOLDER = os.getenv("CARD_HOLDER", "Diyorbek Rustamov")

DB_PATH = os.getenv("DB_PATH", "bot.db")

RECEIPT_MINUTES = int(
    os.getenv("RECEIPT_MINUTES", "10")
)


if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi. Railway Variables ga BOT_TOKEN kiriting."
    )


# ============================================================
# FASTAPI (Mini App uchun veb-server)
# ============================================================

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def serve_miniapp():
    # 'miniapp' papkasi ichidagi 'index.html' ni o'qib beradi
    html_path = os.path.join("miniapp", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "Mini App topilmadi! index.html fayli miniapp papkasida ekanligini tekshiring."

def run_fastapi():
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

log = logging.getLogger("ishbazasi")


# ============================================================
# BOT
# ============================================================

bot = Bot(TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ============================================================
# TARIFLAR
# ============================================================

DEFAULT_TARIFFS = {
    1: {
        "name": "1 kun — 2 MARTA",
        "days": 1,
        "posts": 2,
        "interval_hours": 12,
        "price": 22000,
        "vip": 0,
    },
    2: {
        "name": "1 kun — 4 MARTA",
        "days": 1,
        "posts": 4,
        "interval_hours": 6,
        "price": 35000,
        "vip": 0,
    },
    3: {
        "name": "3 kun — 6 MARTA",
        "days": 3,
        "posts": 6,
        "interval_hours": 12,
        "price": 69000,
        "vip": 0,
    },
    4: {
        "name": "VIP — 7 kun — kuniga 3 MARTA",
        "days": 7,
        "posts": 21,
        "interval_hours": 8,
        "price": 159000,
        "vip": 1,
    },
}


# ============================================================
# DATABASE
# ============================================================

def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def now():
    return datetime.now(timezone.utc)


def iso(value):
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def parse_dt(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def esc(value):
    return html.escape(str(value or ""))


def money(value):
    return f"{int(value):,}".replace(",", " ")


# ============================================================
# DATABASE INIT / MIGRATION
# ============================================================

def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                blocked INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                user_id INTEGER,
                title TEXT DEFAULT '',
                location TEXT DEFAULT '',
                profession TEXT DEFAULT '',
                conditions TEXT DEFAULT '',
                contact TEXT DEFAULT '',
                image_file_id TEXT,
                tariff_id INTEGER DEFAULT 1,
                days INTEGER DEFAULT 1,
                price INTEGER DEFAULT 0,
                lifetime INTEGER DEFAULT 0,
                repeats_total INTEGER DEFAULT 1,
                repeats_done INTEGER DEFAULT 0,
                interval_hours INTEGER DEFAULT 12,
                status TEXT DEFAULT 'pending',
                expires_at TEXT,
                next_post_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad_id INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT DEFAULT 'waiting',
                receipt_file_id TEXT,
                expires_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tariff_settings (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                days INTEGER NOT NULL,
                posts INTEGER NOT NULL,
                interval_hours INTEGER NOT NULL,
                price INTEGER NOT NULL,
                vip INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS ad_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        columns = {
            row["name"]
            for row in c.execute(
                "PRAGMA table_info(ads)"
            ).fetchall()
        }

        additions = {
            "tariff_id": "INTEGER DEFAULT 1",
            "days": "INTEGER DEFAULT 1",
            "price": "INTEGER DEFAULT 0",
            "lifetime": "INTEGER DEFAULT 0",
            "repeats_total": "INTEGER DEFAULT 1",
            "repeats_done": "INTEGER DEFAULT 0",
            "interval_hours": "INTEGER DEFAULT 12",
            "status": "TEXT DEFAULT 'pending'",
            "expires_at": "TEXT",
            "next_post_at": "TEXT",
        }

        for name, typ in additions.items():
            if name not in columns:
                c.execute(
                    f"ALTER TABLE ads ADD COLUMN {name} {typ}"
                )

        for tariff_id, tariff in DEFAULT_TARIFFS.items():
            c.execute(
                """
                INSERT INTO tariff_settings
                (id, name, days, posts, interval_hours, price, vip)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    days=excluded.days,
                    posts=excluded.posts,
                    interval_hours=excluded.interval_hours,
                    vip=excluded.vip
                """,
                (
                    tariff_id,
                    tariff["name"],
                    tariff["days"],
                    tariff["posts"],
                    tariff["interval_hours"],
                    tariff["price"],
                    tariff["vip"],
                ),
            )


# ============================================================
# USER FUNCTIONS
# ============================================================

def register_user(user: types.User):
    current = iso(now())

    with db() as c:
        c.execute(
            """
            INSERT INTO users
            (telegram_id, username, first_name, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id)
            DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_seen=excluded.last_seen
            """,
            (
                user.id,
                user.username,
                user.first_name,
                current,
                current,
            ),
        )


def get_user_db_id(telegram_id):
    with db() as c:
        row = c.execute(
            """
            SELECT id FROM users
            WHERE telegram_id=?
            """,
            (telegram_id,),
        ).fetchone()

    return row["id"] if row else None


# ============================================================
# GETTERS
# ============================================================

def get_ad(ad_id):
    with db() as c:
        return c.execute(
            """
            SELECT * FROM ads
            WHERE id=?
            """,
            (ad_id,),
        ).fetchone()


def get_payment(payment_id):
    with db() as c:
        return c.execute(
            """
            SELECT * FROM payments
            WHERE id=?
            """,
            (payment_id,),
        ).fetchone()


def latest_payment(ad_id):
    with db() as c:
        return c.execute(
            """
            SELECT * FROM payments
            WHERE ad_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (ad_id,),
        ).fetchone()


def get_tariffs():
    with db() as c:
        rows = c.execute(
            """
            SELECT * FROM tariff_settings
            ORDER BY id
            """
        ).fetchall()

    return {
        row["id"]: dict(row)
        for row in rows
    }


def get_tariff(tariff_id):
    return get_tariffs().get(tariff_id)


def update_tariff_price(tariff_id, price):
    with db() as c:
        c.execute(
            """
            UPDATE tariff_settings
            SET price=?
            WHERE id=?
            """,
            (price, tariff_id),
        )


# ============================================================
# STATUS
# ============================================================

def status_text(status):
    return {
        "pending": "⏳ Kutilmoqda",
        "published": "🟢 Faol",
        "expired": "⌛ Tugagan",
        "rejected": "❌ Rad etilgan",
        "cancelled": "🚫 Bekor qilingan",
    }.get(status, status)


# ============================================================
# MAIN MENU (Mini App tugmasi qo'shilgan)
# ============================================================

def main_menu():
    # Railway bergan domeingiz ulandi[cite: 2, 3]
    web_app_url = "https://ish-bazasi-bot-production.up.railway.app"

    return RK(
        keyboard=[
            [
                KB(text="🚀 E'lon berish"),
                KB(text="📢 E'lonlarni ko'rish"),
            ],
            [
                KB(text="🌐 Mini App ochish", web_app=WebAppInfo(url=web_app_url)),
            ],
            [
                KB(text="📞 Admin bilan bog'lanish"),
            ],
        ],
        resize_keyboard=True,
    )


# ============================================================
# SUBSCRIPTION
# ============================================================

def subscription_keyboard():
    return IK(
        inline_keyboard=[
            [
                B(
                    text="📢 Telegram kanal",
                    url=(
                        f"https://t.me/"
                        f"{REQUIRED_CHANNEL.lstrip('@')}"
                    ),
                )
            ],
            [
                B(
                    text="📸 Instagram",
                    url=INSTAGRAM_URL,
                )
            ],
            [
                B(
                    text="✅ Obunani tekshirish",
                    callback_data="check_subscription",
                )
            ],
        ]
    )


async def telegram_subscribed(user_id):
    try:
        member = await bot.get_chat_member(
            chat_id=REQUIRED_CHANNEL,
            user_id=user_id,
        )

        return member.status not in (
            "left",
            "kicked",
        )

    except Exception as e:
        log.error(
            "Subscription check error: %s",
            e,
        )
        return False


async def show_subscription(target):
    text = """
👋 <b>ISH BAZASI</b> botiga xush kelibsiz!

Botdan foydalanish uchun avval
Telegram kanalimizga obuna bo‘ling.

📢 <b>Telegram — MAJBURIY</b>
📸 Instagram — bizning sahifamiz

Obuna bo‘lgach:

<b>✅ Obunani tekshirish</b>

tugmasini bosing.
"""

    if isinstance(target, types.Message):
        await target.answer(
            text,
            reply_markup=subscription_keyboard(),
            parse_mode="HTML",
        )
    else:
        await target.message.answer(
            text,
            reply_markup=subscription_keyboard(),
            parse_mode="HTML",
        )


async def ensure_subscription(message):
    if await telegram_subscribed(
        message.from_user.id
    ):
        return True

    await show_subscription(message)
    return False


# ============================================================
# STATES
# ============================================================

class AdForm(StatesGroup):
    title = State()
    location = State()
    profession = State()
    conditions = State()
    contact = State()
    image = State()
    tariff = State()
    receipt = State()


# ============================================================
# START
# ============================================================

@dp.message(Command("start"))
async def start(
    message: types.Message,
    state: FSMContext,
):
    await state.clear()
    register_user(message.from_user)

    if not await telegram_subscribed(
        message.from_user.id
    ):
        await show_subscription(message)
        return

    await message.answer(
        """
🎉 <b>Xush kelibsiz!</b>

🚀 Ishchi kerak bo‘lsa,
shu bot orqali e’lon bering.

📢 E'lonlaringiz ISH BAZASI kanalida
kerakli auditoriyaga yetib boradi.
""",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )


# ============================================================
# CHECK SUBSCRIPTION
# ============================================================

@dp.callback_query(F.data == "check_subscription")
async def check_subscription(
    callback: types.CallbackQuery,
):
    if await telegram_subscribed(
        callback.from_user.id
    ):
        await callback.answer(
            "✅ Obuna tasdiqlandi!",
            show_alert=True,
        )

        await callback.message.answer(
            """
🎉 <b>Obuna tasdiqlandi!</b>

Endi botdan foydalanishingiz mumkin.
""",
            reply_markup=main_menu(),
            parse_mode="HTML",
        )

    else:
        await callback.answer(
            "❌ Avval Telegram kanalga obuna bo‘ling!",
            show_alert=True,
        )


# ============================================================
# ADMIN CONTACT & VIEW ADS (Qolgan qismlari o'zgarishsiz)
# ============================================================

@dp.message(F.text == "📞 Admin bilan bog'lanish")
async def admin_contact(message: types.Message):
    if not await ensure_subscription(message):
        return
    await message.answer(f"📞 <b>Admin bilan bog‘lanish</b>\n\n👨‍💼 Admin: {esc(ADMIN_CONTACT)}", parse_mode="HTML")


@dp.message(F.text == "📢 E'lonlarni ko'rish")
async def view_ads(message: types.Message):
    if not await ensure_subscription(message):
        return

    with db() as c:
        rows = c.execute("SELECT * FROM ads WHERE status='published' ORDER BY id DESC LIMIT 15").fetchall()

    if not rows:
        await message.answer("📢 <b>E'lonlar</b>\n\nHozircha faol e'lonlar yo‘q.", parse_mode="HTML")
        return

    buttons = []
    for ad in rows:
        buttons.append([B(text=f"📌 {ad['title'][:45]}", callback_data=f"public_ad_{ad['id']}")])

    await message.answer("📢 <b>ISH BAZASI — FAOL E'LONLAR</b>\n\nKerakli e'lonni tanlang:", reply_markup=IK(inline_keyboard=buttons), parse_mode="HTML")


# ============================================================
# MAIN RUN (Bot va Veb-serverni birga yoqish)
# ============================================================

async def main():
    init_db()
    
    # FastAPI veb-serverini fon rejimida (thread) ishga tushiramiz
    server_thread = Thread(target=run_fastapi, daemon=True)
    server_thread.start()
    
    log.info("Bot va Mini App serveri ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
