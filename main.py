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
    html_path = os.path.join("miniapp", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "Mini App topilmadi! index.html fayli miniapp papkasida ekanligini tekshiring."

@app.get("/api/ads")
async def get_ads_api():
    with db() as c:
        rows = c.execute("SELECT * FROM ads WHERE status='published' ORDER BY id DESC LIMIT 20").fetchall()
    return [dict(row) for row in rows]

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
# MAIN MENU (Mini App tugmasi)
# ============================================================

def main_menu():
    web_app_url = "https://ish-bazasi-bot-production.up.railway.app"

    return RK(
        keyboard=[
            [
                KB(text="🚀 E'lon berish"),
                KB(text="📢 E'lonlarni ko'rish"),
            ],
            [
                KB(text="🌐 Ish bazasi", web_app=WebAppInfo(url=web_app_url)),
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
        log.error("Subscription check error: %s", e)
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
    if await telegram_subscribed(message.from_user.id):
        return True

    await show_subscription(message)
    return False


# ============================================================
# STATES (Sarlavha olib tashlandi)
# ============================================================

class AdForm(StatesGroup):
    location = State()
    profession = State()
    conditions = State()
    contact = State()
    image = State()
    tariff = State()
    receipt = State()


class RejectForm(StatesGroup):
    reason = State()


class AdminImageForm(StatesGroup):
    image = State()


class BroadcastForm(StatesGroup):
    message = State()


class TariffPriceForm(StatesGroup):
    price = State()


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

    if not await telegram_subscribed(message.from_user.id):
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


@dp.callback_query(F.data == "check_subscription")
async def check_subscription(
    callback: types.CallbackQuery,
):
    if await telegram_subscribed(callback.from_user.id):
        await callback.answer("✅ Obuna tasdiqlandi!", show_alert=True)
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


@dp.message(F.text == "📞 Admin bilan bog'lanish")
async def admin_contact(message: types.Message):
    if not await ensure_subscription(message):
        return

    await message.answer(
        f"""
📞 <b>Admin bilan bog‘lanish</b>

👨‍💼 Admin: {esc(ADMIN_CONTACT)}
""",
        parse_mode="HTML",
    )


@dp.message(F.text == "📢 E'lonlarni ko'rish")
async def view_ads(message: types.Message):
    if not await ensure_subscription(message):
        return

    with db() as c:
        rows = c.execute(
            """
            SELECT * FROM ads
            WHERE status='published'
            ORDER BY id DESC
            LIMIT 15
            """
        ).fetchall()

    if not rows:
        await message.answer(
            """
📢 <b>E'lonlar</b>

Hozircha faol e'lonlar yo‘q.
""",
            parse_mode="HTML",
        )
        return

    buttons = []
    for ad in rows:
        buttons.append(
            [
                B(
                    text=f"📌 {ad['profession'][:25]} - {ad['location'][:20]}",
                    callback_data=f"public_ad_{ad['id']}",
                )
            ]
        )

    await message.answer(
        """
📢 <b>ISH BAZASI — FAOL E'LONLAR</b>

Kerakli e'lonni tanlang:
""",
        reply_markup=IK(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.regexp(r"^public_ad_\d+$"))
async def public_ad(callback: types.CallbackQuery):
    ad_id = int(callback.data.split("_")[-1])
    ad = get_ad(ad_id)

    if not ad or ad["status"] != "published":
        await callback.answer("❌ Bu e'lon endi faol emas.", show_alert=True)
        return

    with db() as c:
        post = c.execute(
            """
            SELECT message_id FROM ad_posts
            WHERE ad_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (ad_id,),
        ).fetchone()

    if post and CHANNEL_ID.startswith("@"):
        username = CHANNEL_ID[1:]
        await callback.answer()
        await callback.message.answer(
            f"""
📍 <b>Manzil:</b> {esc(ad['location'])}
💼 <b>Kasb:</b> {esc(ad['profession'])}

Kanalda to‘liq ko‘rish:
👇
""",
            reply_markup=IK(
                inline_keyboard=[
                    [
                        B(
                            text="📢 E'lonni kanalda ko‘rish",
                            url=f"https://t.me/{username}/{post['message_id']}",
                        )
                    ]
                ]
            ),
            parse_mode="HTML",
        )
    else:
        await callback.answer("📢 Kanalga o'ting.", show_alert=True)


# ============================================================
# START AD (Sarlavha olib tashlandi, to'g'ridan-to'g'ri manzil)
# ============================================================

@dp.message(F.text == "🚀 E'lon berish")
async def start_ad(message: types.Message, state: FSMContext):
    register_user(message.from_user)

    if not await ensure_subscription(message):
        return

    await state.clear()
    await state.set_state(AdForm.location)

    await message.answer(
        """
🚀 <b>E'LON BERISH</b>

📍 <b>Manzilni yozing.</b>

Masalan:
Toshkent, Chilonzor
""",
        parse_mode="HTML",
    )


@dp.message(AdForm.location)
async def ad_location(message: types.Message, state: FSMContext):
    value = (message.text or "").strip()
    if not value:
        await message.answer("❌ Manzilni yozing.")
        return

    await state.update_data(location=value)
    await state.set_state(AdForm.profession)

    await message.answer(
        """
💼 <b>Qanday ishchi kerak?</b>

Masalan:
Ofitsiant
Sotuvchi
Haydovchi
""",
        parse_mode="HTML",
    )


@dp.message(AdForm.profession)
async def ad_profession(message: types.Message, state: FSMContext):
    value = (message.text or "").strip()
    if not value:
        await message.answer("❌ Ish turini yozing.")
        return

    await state.update_data(profession=value)
    await state.set_state(AdForm.conditions)

    await message.answer(
        """
📋 <b>Ish haqida batafsil ma'lumot yozing.</b>

Maosh, ish vaqti, talablar va hokazo.
""",
        parse_mode="HTML",
    )


@dp.message(AdForm.conditions)
async def ad_conditions(message: types.Message, state: FSMContext):
    value = (message.text or "").strip()
    if not value:
        await message.answer("❌ Ma'lumotni yozing.")
        return

    await state.update_data(conditions=value)
    await state.set_state(AdForm.contact)

    await message.answer(
        """
📞 <b>Aloqa ma'lumotini yozing.</b>

Telefon raqami yoki Telegram username.
""",
        parse_mode="HTML",
    )


@dp.message(AdForm.contact)
async def ad_contact(message: types.Message, state: FSMContext):
    value = (message.text or "").strip()
    if not value:
        await message.answer("❌ Aloqa ma'lumotini yozing.")
        return

    await state.update_data(contact=value)
    await state.set_state(AdForm.image)

    await message.answer(
        """
🖼 <b>E'lon uchun rasm yuboring.</b>

Agar rasm bo‘lmasa:

⏭ <b>O‘tkazib yuborish</b>
""",
        reply_markup=IK(
            inline_keyboard=[
                [
                    B(
                        text="⏭ O‘tkazib yuborish",
                        callback_data="skip_image",
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )


# ============================================================
# IMAGE
# ============================================================

@dp.message(AdForm.image, F.photo)
async def ad_image(message: types.Message, state: FSMContext):
    await state.update_data(image_file_id=message.photo[-1].file_id)
    await state.set_state(AdForm.tariff)

    await message.answer(
        "💰 <b>Tarifni tanlang:</b>",
        reply_markup=tariff_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(AdForm.image, F.data == "skip_image")
async def skip_image(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(image_file_id=None)
    await state.set_state(AdForm.tariff)

    await callback.message.edit_text(
        "💰 <b>Tarifni tanlang:</b>",
        reply_markup=tariff_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(AdForm.image)
async def wrong_image(message: types.Message):
    await message.answer(
        """
🖼 Rasm yuboring.

Yoki:
⏭ <b>O‘tkazib yuborish</b>
""",
        parse_mode="HTML",
    )


# ============================================================
# TARIFF KEYBOARD (Dinamik bazadan olinadi)
# ============================================================

def tariff_keyboard():
    tariffs = get_tariffs()
    icons = {1: "🟢", 2: "🔥", 3: "⭐", 4: "👑"}
    rows = []

    for tariff_id in range(1, 5):
        if tariff_id not in tariffs:
            continue
        t = tariffs[tariff_id]
        rows.append(
            [
                B(
                    text=f"{icons.get(tariff_id, '🟢')} {t['name']} — {money(t['price'])} so'm",
                    callback_data=f"tariff_{tariff_id}",
                )
            ]
        )
    return IK(inline_keyboard=rows)


# ============================================================
# CREATE AD / PAYMENT
# ============================================================

def create_ad(telegram_id, data, tariff):
    user_id = get_user_db_id(telegram_id)

    with db() as c:
        cursor = c.execute(
            """
            INSERT INTO ads (
                telegram_id, user_id, title, location, profession,
                conditions, contact, image_file_id, tariff_id, days,
                price, lifetime, repeats_total, repeats_done,
                interval_hours, status, created_at
            )
            VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, ?, 'pending', ?)
            """,
            (
                telegram_id,
                user_id,
                data["location"],
                data["profession"],
                data["conditions"],
                data["contact"],
                data.get("image_file_id"),
                tariff["id"],
                tariff["days"],
                tariff["price"],
                tariff["posts"],
                tariff["interval_hours"],
                iso(now()),
            ),
        )
        return cursor.lastrowid


def create_payment(ad_id, telegram_id, amount):
    expires = now() + timedelta(minutes=RECEIPT_MINUTES)
    with db() as c:
        cursor = c.execute(
            """
            INSERT INTO payments (
                ad_id, telegram_id, amount, status, expires_at, created_at
            )
            VALUES (?, ?, ?, 'waiting', ?, ?)
            """,
            (ad_id, telegram_id, amount, iso(expires), iso(now())),
        )
        return cursor.lastrowid


@dp.callback_query(AdForm.tariff, F.data.regexp(r"^tariff_[1-4]$"))
async def choose_tariff(callback: types.CallbackQuery, state: FSMContext):
    tariff_id = int(callback.data.split("_")[1])
    tariff = get_tariff(tariff_id)

    if not tariff:
        await callback.answer("❌ Tarif topilmadi.", show_alert=True)
        return

    tariff = dict(tariff)
    tariff["id"] = tariff_id
    data = await state.get_data()

    ad_id = create_ad(callback.from_user.id, data, tariff)
    payment_id = create_payment(ad_id, callback.from_user.id, tariff["price"])

    await state.update_data(ad_id=ad_id, payment_id=payment_id)
    await state.set_state(AdForm.receipt)

    card = CARD_NUMBER if CARD_NUMBER else "CARD_NUMBER kiritilmagan"

    await callback.message.edit_text(
        f"""
💳 <b>TO‘LOV</b>

📦 <b>{esc(tariff['name'])}</b>

💰 <b>{money(tariff['price'])} so'm</b>

💳 Karta:
<code>{esc(card)}</code>

👤 Karta egasi:
<b>{esc(CARD_HOLDER)}</b>

To‘lovni amalga oshiring.
Keyin <b>💳 To‘lov qildim</b> tugmasini bosing.

⏰ Chekni {RECEIPT_MINUTES} daqiqa ichida yuboring.
""",
        reply_markup=IK(
            inline_keyboard=[
                [
                    B(
                        text="💳 To‘lov qildim",
                        callback_data=f"paid_{payment_id}",
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.regexp(r"^paid_\d+$"))
async def paid(callback: types.CallbackQuery, state: FSMContext):
    payment_id = int(callback.data.split("_")[1])
    payment = get_payment(payment_id)

    if not payment or payment["telegram_id"] != callback.from_user.id:
        await callback.answer("❌ Ruxsat yo‘q.", show_alert=True)
        return

    with db() as c:
        c.execute("UPDATE payments SET status='paid' WHERE id=?", (payment_id,))

    await state.update_data(payment_id=payment_id, ad_id=payment["ad_id"])
    await state.set_state(AdForm.receipt)

    await callback.message.answer(
        f"""
📸 <b>Endi to‘lov chekini RASM qilib yuboring.</b>

⏰ {RECEIPT_MINUTES} daqiqa ichida yuboring.
""",
        parse_mode="HTML",
    )
    await callback.answer("✅ Chekni yuboring.")


@dp.message(AdForm.receipt, F.photo)
async def receive_receipt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    payment_id = data.get("payment_id")

    if not payment_id:
        await state.clear()
        await message.answer("❌ To‘lov topilmadi.")
        return

    payment = get_payment(payment_id)
    if not payment:
        await state.clear()
        await message.answer("❌ To‘lov topilmadi.")
        return

    receipt_id = message.photo[-1].file_id
    with db() as c:
        c.execute(
            """
            UPDATE payments
            SET receipt_file_id=?, status='receipt_received'
            WHERE id=?
            """,
            (receipt_id, payment_id),
        )

    await state.clear()
    await send_ad_to_admin(payment["ad_id"])

    await message.answer(
        """
✅ <b>Chek qabul qilindi!</b>

👨‍💼 Admin to‘lovni tekshiradi.
Tasdiqlangandan keyin e'lon kanalga chiqariladi.
""",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )


@dp.message(AdForm.receipt)
async def receipt_not_photo(message: types.Message):
    await message.answer("📸 Chekni rasm qilib yuboring.")


# ============================================================
# ADMIN KEYBOARDS & AD TEXT (Admin eslatmasi bilan)
# ============================================================

def admin_keyboard():
    return IK(
        inline_keyboard=[
            [
                B(text="📊 Statistika", callback_data="admin_stats"),
                B(text="📢 E'lonlar", callback_data="admin_ads"),
            ],
            [
                B(text="💳 To‘lovlar", callback_data="admin_payments"),
                B(text="👥 Foydalanuvchilar", callback_data="admin_users"),
            ],
            [
                B(text="💰 Tariflar", callback_data="admin_tariffs"),
                B(text="📣 Hammaga xabar", callback_data="admin_broadcast"),
            ],
        ]
    )


def admin_ad_keyboard(ad_id, has_image):
    rows = []
    if not has_image:
        rows.append(
            [
                B(
                    text="🖼 Rasm qo‘yish",
                    callback_data=f"admin_image_{ad_id}",
                )
            ]
        )

    rows.append(
        [
            B(text="✅ Tasdiqlash", callback_data=f"approve_{ad_id}"),
            B(text="❌ Rad etish", callback_data=f"reject_{ad_id}"),
        ]
    )
    return IK(inline_keyboard=rows)


def admin_ad_text(ad):
    payment = latest_payment(ad["id"])
    tariff = get_tariff(ad["tariff_id"])
    tariff_name = tariff["name"] if tariff else "Noma'lum tarif"

    receipt = (
        "✅ Yuborilgan"
        if payment and payment["receipt_file_id"]
        else "❌ Yo‘q"
    )

    # Siz so'ragan aniq eslatma:
    if not ad["image_file_id"]:
        reminder_note = "⚠️ <b>Foydalanuvchi rasm tashamadi, o'zingiz rasm tashang!</b>"
    else:
        reminder_note = "🖼 <b>Rasm mavjud</b>"

    return f"""
📥 <b>YANGI E'LON #{ad['id']}</b>

👤 Telegram ID: <code>{ad['telegram_id']}</code>
📍 {esc(ad['location'])}
💼 {esc(ad['profession'])}
📋 {esc(ad['conditions'])}
📞 {esc(ad['contact'])}

📦 <b>{esc(tariff_name)}</b>
💰 <b>{money(ad['price'])} so'm</b>

{reminder_note}
"""


async def send_ad_to_admin(ad_id):
    ad = get_ad(ad_id)
    if not ad:
        return

    payment = latest_payment(ad_id)
    text = admin_ad_text(ad)
    keyboard = admin_ad_keyboard(ad_id, bool(ad["image_file_id"]))

    if payment and payment["receipt_file_id"]:
        await bot.send_photo(
            ADMIN_ID,
            payment["receipt_file_id"],
            caption=f"💳 <b>TO‘LOV CHEKI</b>\n\n{text}",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    elif ad["image_file_id"]:
        await bot.send_photo(
            ADMIN_ID,
            ad["image_file_id"],
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await bot.send_message(
            ADMIN_ID,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )


# ============================================================
# CHANNEL TEXT
# ============================================================

def build_channel_text(ad):
    return f"""
📍 <b>Manzil:</b>
{esc(ad['location'])}

💼 <b>Ish:</b>
{esc(ad['profession'])}

📋 <b>Ma'lumot:</b>
{esc(ad['conditions'])}

📞 <b>Aloqa:</b>
{esc(ad['contact'])}

🆔 <b>E'lon #{ad['id']}</b>

📢 <b>ISH BAZASI</b>

📸 Instagram:
<a href="{esc(INSTAGRAM_URL)}">@ishbazasi</a>
"""


async def publish_ad(ad_id):
    ad = get_ad(ad_id)
    if not ad:
        return None

    text = build_channel_text(ad)

    if ad["image_file_id"]:
        sent = await bot.send_photo(
            CHANNEL_ID,
            ad["image_file_id"],
            caption=text,
            parse_mode="HTML",
        )
    else:
        sent = await bot.send_message(
            CHANNEL_ID,
            text,
            parse_mode="HTML",
        )

    with db() as c:
        c.execute(
            """
            INSERT INTO ad_posts (ad_id, message_id, created_at)
            VALUES (?, ?, ?)
            """,
            (ad_id, sent.message_id, iso(now())),
        )
        c.execute(
            """
            UPDATE ads
            SET repeats_done=repeats_done+1
            WHERE id=?
            """,
            (ad_id,),
        )
    return sent


async def delete_ad_posts(ad_id):
    with db() as c:
        rows = c.execute(
            "SELECT message_id FROM ad_posts WHERE ad_id=?", (ad_id,)
        ).fetchall()

    for row in rows:
        try:
            await bot.delete_message(CHANNEL_ID, row["message_id"])
        except Exception as e:
            log.warning("Post o‘chirish xatosi #%s: %s", ad_id, e)

    with db() as c:
        c.execute("DELETE FROM ad_posts WHERE ad_id=?", (ad_id,))


# ============================================================
# ADMIN PANEL & ACTIONS
# ============================================================

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "👨‍💼 <b>ISH BAZASI ADMIN PANEL</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "admin_home")
async def admin_home(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "👨‍💼 <b>ISH BAZASI ADMIN PANEL</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    with db() as c:
        users = c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        ads = c.execute("SELECT COUNT(*) n FROM ads").fetchone()["n"]
        active = c.execute("SELECT COUNT(*) n FROM ads WHERE status='published'").fetchone()["n"]
        payments = c.execute("SELECT COALESCE(SUM(amount),0) n FROM payments WHERE status='approved'").fetchone()["n"]

    await callback.message.edit_text(
        f"""
📊 <b>STATISTIKA</b>

👥 Foydalanuvchilar: <b>{users}</b>
📢 Jami e'lonlar: <b>{ads}</b>
🟢 Faol e'lonlar: <b>{active}</b>
💰 To‘lovlar: <b>{money(payments)} so'm</b>
""",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ============================================================
# TARIFLARNI O'ZGARTIRISH (Admin xohlagan vaqtda o'zgartiradi)
# ============================================================

def admin_tariff_keyboard():
    tariffs = get_tariffs()
    rows = []
    for tariff_id in range(1, 5):
        if tariff_id not in tariffs:
            continue
        t = tariffs[tariff_id]
        rows.append(
            [
                B(
                    text=f"{t['name']} — {money(t['price'])} so'm",
                    callback_data=f"edit_tariff_{tariff_id}",
                )
            ]
        )
    rows.append([B(text="⬅️ Admin panel", callback_data="admin_home")])
    return IK(inline_keyboard=rows)


@dp.callback_query(F.data == "admin_tariffs")
async def admin_tariffs(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    await callback.message.edit_text(
        "💰 <b>TARIFLAR NARXINI O'ZGARTIRISH</b>\n\nO'zgartirmoqchi bo'lgan tarifni tanlang:",
        reply_markup=admin_tariff_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.regexp(r"^edit_tariff_[1-4]$"))
async def edit_tariff(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    tariff_id = int(callback.data.split("_")[-1])
    tariff = get_tariff(tariff_id)

    await state.set_state(TariffPriceForm.price)
    await state.update_data(tariff_id=tariff_id)

    await callback.message.answer(
        f"""
💰 <b>{esc(tariff['name'])}</b>

Hozirgi narx: <b>{money(tariff['price'])} so'm</b>

Yangi narxni faqat raqam bilan yuboring (masalan: 25000):
""",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(TariffPriceForm.price)
async def save_tariff_price(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        price = int((message.text or "").replace(" ", "").replace(",", ""))
        if price < 0:
            raise ValueError
    except Exception:
        await message.answer("❌ Xato! Narxni faqat raqam bilan yuboring.")
        return

    data = await state.get_data()
    update_tariff_price(data["tariff_id"], price)
    await state.clear()

    await message.answer(
        "✅ Tarif narxi muvaffaqiyatli o'zgartirildi!",
        reply_markup=admin_keyboard(),
    )


# ============================================================
# ADMIN RASM QO'SHISH (Foydalanuvchi rasm tashlamasa)
# ============================================================

@dp.callback_query(F.data.regexp(r"^admin_image_\d+$"))
async def admin_image_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    ad_id = int(callback.data.split("_")[-1])
    await state.set_state(AdminImageForm.image)
    await state.update_data(ad_id=ad_id)

    await callback.message.answer(
        f"🖼 <b>#{ad_id}</b> e'lon uchun o'zingiz rasm yuboring:",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(AdminImageForm.image, F.photo)
async def admin_receive_image(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    ad_id = data.get("ad_id")
    if not ad_id:
        await state.clear()
        return

    photo_id = message.photo[-1].file_id

    with db() as c:
        c.execute(
            "UPDATE ads SET image_file_id=? WHERE id=?",
            (photo_id, ad_id),
        )

    await state.clear()
    await message.answer("✅ E'longa rasm muvaffaqiyatli qo'shildi! Endi uni tasdiqlashingiz mumkin.", reply_markup=admin_keyboard())


# APPROVE
@dp.callback_query(F.data.regexp(r"^approve_\d+$"))
async def approve_ad(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    ad_id = int(callback.data.split("_")[1])
    ad = get_ad(ad_id)

    if not ad or ad["status"] != "pending":
        await callback.answer("⚠️ Xatolik yoki e'lon allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    payment = latest_payment(ad_id)
    if not payment or payment["status"] != "receipt_received":
        await callback.answer("❌ Chek topilmadi yoki tasdiqlanmagan.", show_alert=True)
        return

    tariff = get_tariff(ad["tariff_id"])
    if not tariff:
        await callback.answer("❌ Tarif topilmadi.", show_alert=True)
        return

    try:
        await publish_ad(ad_id)
    except Exception:
        log.exception("Kanalga chiqarish xatosi")
        await callback.answer("❌ Kanalga yuborilmadi. Bot admin ekanini tekshiring.", show_alert=True)
        return

    start_time = now()
    expires_at = start_time + timedelta(days=tariff["days"])
    next_post = start_time + timedelta(hours=tariff["interval_hours"]) if tariff["posts"] > 1 else None

    with db() as c:
        c.execute("UPDATE payments SET status='approved' WHERE id=?", (payment["id"],))
        c.execute(
            """
            UPDATE ads
            SET status='published', expires_at=?, next_post_at=?
            WHERE id=?
            """,
            (iso(expires_at), iso(next_post), ad_id),
        )

    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption="✅ <b>TASDIQLANDI</b>\n\n📢 E'lon kanalga chiqarildi.", parse_mode="HTML")
        else:
            await callback.message.edit_text("✅ <b>TASDIQLANDI</b>\n\n📢 E'lon kanalga chiqarildi.", parse_mode="HTML")
    except Exception:
        pass

    try:
        await bot.send_message(
            ad["telegram_id"],
            f"""
🎉 <b>E'loningiz tasdiqlandi!</b>
📢 E'lon kanalga chiqarildi.
📦 {esc(tariff['name'])}
""",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.answer("✅ E'lon tasdiqlandi!")


# REJECT
@dp.callback_query(F.data.regexp(r"^reject_\d+$"))
async def reject_ad(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    ad_id = int(callback.data.split("_")[1])
    await state.set_state(RejectForm.reason)
    await state.update_data(ad_id=ad_id)
    await callback.message.answer("❌ Rad etish sababini yozing.")
    await callback.answer()


@dp.message(RejectForm.reason)
async def reject_reason(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    ad = get_ad(data.get("ad_id"))

    if ad:
        with db() as c:
            c.execute("UPDATE ads SET status='rejected' WHERE id=?", (ad["id"],))
            payment = latest_payment(ad["id"])
            if payment:
                c.execute("UPDATE payments SET status='rejected' WHERE id=?", (payment["id"],))

        try:
            await bot.send_message(
                ad["telegram_id"],
                f"❌ <b>E'loningiz rad etildi.</b>\n\n<b>Sabab:</b> {esc(message.text)}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await state.clear()
    await message.answer("✅ E'lon rad etildi.", reply_markup=admin_keyboard())


# ============================================================
# SCHEDULER (Avtomatik 12 soatda o'chib, qayta tashlash)
# ============================================================

async def scheduler_loop():
    while True:
        try:
            current = now()

            with db() as c:
                expired = c.execute(
                    """
                    SELECT * FROM ads
                    WHERE status='published'
                    AND expires_at IS NOT NULL
                    AND expires_at <= ?
                    """,
                    (iso(current),),
                ).fetchall()

            for ad in expired:
                try:
                    await delete_ad_posts(ad["id"])
                except Exception:
                    pass

                with db() as c:
                    c.execute(
                        "UPDATE ads SET status='expired', next_post_at=NULL WHERE id=?",
                        (ad["id"],),
                    )

                try:
                    await bot.send_message(
                        ad["telegram_id"],
                        f"⌛ <b>E'loningiz #{ad['id']} muddati tugadi.</b>",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

            with db() as c:
                due = c.execute(
                    """
                    SELECT * FROM ads
                    WHERE status='published'
                    AND next_post_at IS NOT NULL
                    AND next_post_at <= ?
                    AND repeats_done < repeats_total
                    AND expires_at > ?
                    """,
                    (iso(current), iso(current)),
                ).fetchall()

            for ad in due:
                try:
                    await delete_ad_posts(ad["id"])
                    await publish_ad(ad["id"])

                    updated = get_ad(ad["id"])
                    if not updated:
                        continue

                    if updated["repeats_done"] >= updated["repeats_total"]:
                        with db() as c:
                            c.execute(
                                "UPDATE ads SET next_post_at=NULL WHERE id=?",
                                (ad["id"],),
                            )
                    else:
                        tariff = get_tariff(updated["tariff_id"])
                        hours = tariff["interval_hours"] if tariff else updated["interval_hours"]
                        next_time = current + timedelta(hours=hours)

                        expires = parse_dt(updated["expires_at"])
                        if expires and next_time >= expires:
                            next_time = None

                        with db() as c:
                            c.execute(
                                "UPDATE ads SET next_post_at=? WHERE id=?",
                                (iso(next_time), ad["id"]),
                            )
                except Exception:
                    log.exception("Scheduler repost error #%s", ad["id"])

        except Exception:
            log.exception("Scheduler umumiy xatosi")

        await asyncio.sleep(20)


async def payment_cleanup_loop():
    while True:
        try:
            current = iso(now())
            with db() as c:
                rows = c.execute(
                    """
                    SELECT id, ad_id FROM payments
                    WHERE status IN ('waiting', 'paid')
                    AND expires_at IS NOT NULL
                    AND expires_at <= ?
                    """,
                    (current,),
                ).fetchall()

            for row in rows:
                with db() as c:
                    c.execute("UPDATE payments SET status='expired' WHERE id=?", (row["id"],))
                    c.execute("UPDATE ads SET status='cancelled' WHERE id=? AND status='pending'", (row["ad_id"],))
        except Exception:
            pass
        await asyncio.sleep(30)


# ============================================================
# MAIN
# ============================================================

async def main():
    init_db()

    server_thread = Thread(target=run_fastapi, daemon=True)
    server_thread.start()

    asyncio.create_task(scheduler_loop())
    asyncio.create_task(payment_cleanup_loop())

    log.info("ISH BAZASI BOT VA MINI APP ISHGA TUSHDI")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
