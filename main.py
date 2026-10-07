import asyncio
import html
import logging
import os
import sqlite3
from datetime import datetime, timezone, timedelta

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


# ============================================================
# ISH BAZASI BOT — FINAL
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = int(os.getenv("ADMIN_ID", "8451295149"))

ADMIN_CONTACT = os.getenv(
    "ADMIN_CONTACT",
    "@rustamovvvll"
)

CHANNEL_ID = os.getenv(
    "CHANNEL_ID",
    "@Ishbazasi"
)

REQUIRED_CHANNEL = os.getenv(
    "REQUIRED_CHANNEL",
    "@Ishbazasi"
)

INSTAGRAM_URL = os.getenv(
    "INSTAGRAM_URL",
    "https://instagram.com/ishbazasi"
)

# Mini App manzili.
# Railway Variables ichiga MINI_APP_URL qo'yiladi.
# Masalan:
# https://your-mini-app.up.railway.app
MINI_APP_URL = os.getenv(
    "MINI_APP_URL",
    ""
)

CARD_NUMBER = os.getenv(
    "CARD_NUMBER",
    ""
)

CARD_HOLDER = os.getenv(
    "CARD_HOLDER",
    "Diyorbek Rustamov"
)

DB_PATH = os.getenv(
    "DB_PATH",
    "bot.db"
)

RECEIPT_MINUTES = int(
    os.getenv(
        "RECEIPT_MINUTES",
        "10"
    )
)


if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi. Railway Variables ga BOT_TOKEN kiriting."
    )


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

dp = Dispatcher(
    storage=MemoryStorage()
)


# ============================================================
# DEFAULT TARIFLAR
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
        "name": "VIP — 7 kun — 3 MARTA",
        "days": 7,
        "posts": 3,
        "interval_hours": 72,
        "price": 159000,
        "vip": 1,
    },
}


# ============================================================
# DATABASE
# ============================================================

def db():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA journal_mode=WAL"
    )

    conn.execute(
        "PRAGMA busy_timeout=30000"
    )

    return conn


def now():
    return datetime.now(timezone.utc)


def iso(value):
    if value is None:
        return None

    return value.astimezone(
        timezone.utc
    ).isoformat()


def dt(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def esc(value):
    return html.escape(
        str(value or "")
    )


def money(value):
    return f"{int(value):,}".replace(
        ",",
        " "
    )


def channel_username():
    value = CHANNEL_ID.strip()

    if value.startswith("@"):
        return value[1:]

    return ""


def channel_url():
    username = channel_username()

    if username:
        return f"https://t.me/{username}"

    return ""


# ============================================================
# DATABASE INIT + MIGRATION
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
                location TEXT NOT NULL,
                profession TEXT NOT NULL,
                conditions TEXT NOT NULL,
                contact TEXT NOT NULL,

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

        # ----------------------------------------------------
        # ADS MIGRATION
        # ----------------------------------------------------

        existing = {
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

        for column, column_type in additions.items():

            if column not in existing:

                c.execute(
                    f"""
                    ALTER TABLE ads
                    ADD COLUMN {column} {column_type}
                    """
                )

        # ----------------------------------------------------
        # PAYMENTS MIGRATION
        # ----------------------------------------------------

        payment_columns = {
            row["name"]
            for row in c.execute(
                "PRAGMA table_info(payments)"
            ).fetchall()
        }

        payment_additions = {
            "receipt_file_id": "TEXT",
            "expires_at": "TEXT",
            "status": "TEXT DEFAULT 'waiting'",
        }

        for column, column_type in payment_additions.items():

            if column not in payment_columns:

                c.execute(
                    f"""
                    ALTER TABLE payments
                    ADD COLUMN {column} {column_type}
                    """
                )

        # ----------------------------------------------------
        # TARIFLAR
        # ----------------------------------------------------

        for tariff_id, tariff in DEFAULT_TARIFFS.items():

            c.execute(
                """
                INSERT INTO tariff_settings(
                    id,
                    name,
                    days,
                    posts,
                    interval_hours,
                    price,
                    vip
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT(id)
                DO NOTHING
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
# USER
# ============================================================

def register_user(user: types.User):

    current_time = iso(now())

    with db() as c:

        c.execute(
            """
            INSERT INTO users(
                telegram_id,
                username,
                first_name,
                created_at,
                last_seen
            )
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
                current_time,
                current_time,
            ),
        )


def get_user_db_id(telegram_id):

    with db() as c:

        row = c.execute(
            """
            SELECT id
            FROM users
            WHERE telegram_id=?
            """,
            (telegram_id,),
        ).fetchone()

        return row["id"] if row else None


# ============================================================
# DB GETTERS
# ============================================================

def get_ad(ad_id):

    with db() as c:

        return c.execute(
            """
            SELECT *
            FROM ads
            WHERE id=?
            """,
            (ad_id,),
        ).fetchone()


def get_payment(payment_id):

    with db() as c:

        return c.execute(
            """
            SELECT *
            FROM payments
            WHERE id=?
            """,
            (payment_id,),
        ).fetchone()


def latest_payment(ad_id):

    with db() as c:

        return c.execute(
            """
            SELECT *
            FROM payments
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
            SELECT *
            FROM tariff_settings
            ORDER BY id
            """
        ).fetchall()

    return {
        row["id"]: dict(row)
        for row in rows
    }


def get_tariff(tariff_id):

    return get_tariffs().get(
        tariff_id
    )


def update_tariff(
    tariff_id,
    price=None,
    posts=None,
    interval_hours=None,
    days=None
):

    tariff = get_tariff(
        tariff_id
    )

    if not tariff:
        return False

    price = (
        tariff["price"]
        if price is None
        else price
    )

    posts = (
        tariff["posts"]
        if posts is None
        else posts
    )

    interval_hours = (
        tariff["interval_hours"]
        if interval_hours is None
        else interval_hours
    )

    days = (
        tariff["days"]
        if days is None
        else days
    )

    with db() as c:

        c.execute(
            """
            UPDATE tariff_settings
            SET price=?,
                posts=?,
                interval_hours=?,
                days=?
            WHERE id=?
            """,
            (
                price,
                posts,
                interval_hours,
                days,
                tariff_id,
            ),
        )

    return True


def status_text(status):

    return {
        "pending": "⏳ Kutilmoqda",
        "published": "🟢 Faol",
        "expired": "⌛ Tugagan",
        "rejected": "❌ Rad etilgan",
        "cancelled": "🚫 Bekor qilingan",
    }.get(
        status,
        status
    )


def remaining_text(value):

    target = dt(value)

    if not target:
        return "—"

    seconds = int(
        (target - now()).total_seconds()
    )

    if seconds <= 0:
        return "0 daqiqa"

    days, remainder = divmod(
        seconds,
        86400
    )

    hours, remainder = divmod(
        remainder,
        3600
    )

    minutes = remainder // 60

    parts = []

    if days:
        parts.append(
            f"{days} kun"
        )

    if hours:
        parts.append(
            f"{hours} soat"
        )

    if minutes:
        parts.append(
            f"{minutes} daqiqa"
        )

    return " ".join(parts) or "<1 daqiqa"


# ============================================================
# USER MENU
# ============================================================

def main_menu():

    keyboard = [
        [
            KB(
                text="🚀 E'lon berish"
            )
        ],
        [
            KB(
                text="📢 E'lonlarni ko'rish"
            )
        ],
        [
            KB(
                text="📞 Admin bilan bog'lanish"
            )
        ],
    ]

    # Foydalanuvchiga "Mening e'lonlarim"
    # kerak emasligi kelishilgan.
    #
    # Admin panel oddiy foydalanuvchi menyusida chiqmaydi.

    return RK(
        keyboard=keyboard,
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
                    text="📢 Telegram",
                    url=(
                        f"https://t.me/"
                        f"{REQUIRED_CHANNEL.lstrip('@')}"
                    ),
                ),
                B(
                    text="📸 Instagram",
                    url=INSTAGRAM_URL,
                ),
            ],
            [
                B(
                    text="✅ Obunani tekshirish",
                    callback_data="check_subscription",
                )
            ],
        ]
    )


async def telegram_subscribed(
    user_id: int
):

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
            "Telegram obuna tekshirish xatosi: %s",
            e,
        )

        return False


async def show_subscription(target):

    text = """
👋 <b>ISH BAZASI</b> botiga xush kelibsiz!

Botdan foydalanish uchun
Telegram kanalga obuna bo'lishingiz kerak.

📢 Telegram — <b>MAJBURIY</b>
📸 Instagram — kanalimiz

Obuna bo'lgach:

<b>✅ Obunani tekshirish</b>
tugmasini bosing.
"""

    if isinstance(
        target,
        types.Message
    ):

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


async def ensure_subscription(
    message: types.Message
):

    if await telegram_subscribed(
        message.from_user.id
    ):

        return True

    await show_subscription(
        message
    )

    return False


# ============================================================
# PUBLIC MINI APP BUTTON
# ============================================================

def mini_app_button():

    if MINI_APP_URL:

        return B(
            text="📢 E'lonlarni ko'rish",
            web_app=WebAppInfo(
                url=MINI_APP_URL
            ),
        )

    channel = channel_url()

    if channel:

        return B(
            text="📢 E'lonlarni ko'rish",
            url=channel,
        )

    return B(
        text="📢 E'lonlarni ko'rish",
        callback_data="view_ads_channel",
    )


# ============================================================
# ADMIN KEYBOARD
# ============================================================

def admin_keyboard():

    return IK(
        inline_keyboard=[
            [
                B(
                    text="📊 Statistika",
                    callback_data="admin_stats",
                ),
                B(
                    text="📢 E'lonlar",
                    callback_data="admin_ads",
                ),
            ],
            [
                B(
                    text="💳 To'lovlar",
                    callback_data="admin_payments",
                ),
                B(
                    text="👥 Foydalanuvchilar",
                    callback_data="admin_users",
                ),
            ],
            [
                B(
                    text="💰 Tariflar",
                    callback_data="admin_tariffs",
                ),
                B(
                    text="📣 Hammaga xabar",
                    callback_data="admin_broadcast",
                ),
            ],
        ]
    )


def admin_tariff_keyboard():

    tariffs = get_tariffs()

    return IK(
        inline_keyboard=[
            [
                B(
                    text=(
                        f"1️⃣ {money(tariffs[1]['price'])}"
                    ),
                    callback_data="edit_tariff_1",
                ),
                B(
                    text=(
                        f"2️⃣ {money(tariffs[2]['price'])}"
                    ),
                    callback_data="edit_tariff_2",
                ),
            ],
            [
                B(
                    text=(
                        f"3️⃣ {money(tariffs[3]['price'])}"
                    ),
                    callback_data="edit_tariff_3",
                ),
                B(
                    text=(
                        f"4️⃣ {money(tariffs[4]['price'])}"
                    ),
                    callback_data="edit_tariff_4",
                ),
            ],
            [
                B(
                    text="⬅️ Admin panel",
                    callback_data="admin_home",
                )
            ],
        ]
    )


def image_skip_keyboard():

    return IK(
        inline_keyboard=[
            [
                B(
                    text="⏭ O'tkazib yuborish",
                    callback_data="skip_image",
                )
            ]
        ]
    )


def tariff_keyboard():

    tariffs = get_tariffs()

    icons = [
        "🟢",
        "🔥",
        "⭐",
        "👑",
    ]

    rows = []

    for tariff_id in range(1, 5):

        tariff = tariffs.get(
            tariff_id
        )

        if not tariff:
            continue

        rows.append(
            [
                B(
                    text=(
                        f"{icons[tariff_id - 1]} "
                        f"{tariff['name']} — "
                        f"{money(tariff['price'])} so'm"
                    ),
                    callback_data=(
                        f"tariff_{tariff_id}"
                    ),
                )
            ]
        )

    return IK(
        inline_keyboard=rows
    )


def admin_ad_keyboard(
    ad_id,
    has_image
):

    rows = []

    if not has_image:

        rows.append(
            [
                B(
                    text="🖼 Rasm qo'yish",
                    callback_data=(
                        f"admin_add_image_{ad_id}"
                    ),
                )
            ]
        )

    rows.append(
        [
            B(
                text="✅ Tasdiqlash",
                callback_data=f"approve_{ad_id}",
            ),
            B(
                text="❌ Rad etish",
                callback_data=f"reject_{ad_id}",
            ),
        ]
    )

    return IK(
        inline_keyboard=rows
    )


# ============================================================
# FSM
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


class AdminImageForm(StatesGroup):

    image = State()


class RejectForm(StatesGroup):

    reason = State()


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
    state: FSMContext
):

    await state.clear()

    register_user(
        message.from_user
    )

    if not await telegram_subscribed(
        message.from_user.id
    ):

        await show_subscription(
            message
        )

        return

    await message.answer(
        """
🎉 <b>ISH BAZASI</b>ga xush kelibsiz!

👷 Ishchi kerak bo'lsa,
shu yerning o'zida e'lon bering.

📢 E'lonlarni esa alohida
ko'rishingiz mumkin.
""",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )


# ============================================================
# CHECK SUBSCRIPTION
# ============================================================

@dp.callback_query(
    F.data == "check_subscription"
)
async def check_subscription(
    callback: types.CallbackQuery
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
🎉 <b>Tayyor!</b>

Endi botdan foydalanishingiz mumkin.
""",
            reply_markup=main_menu(),
            parse_mode="HTML",
        )

    else:

        await callback.answer(
            "❌ Avval Telegram kanalga obuna bo'ling!",
            show_alert=True,
        )


# ============================================================
# VIEW ADS
# ============================================================

@dp.message(
    F.text == "📢 E'lonlarni ko'rish"
)
async def view_ads(
    message: types.Message
):

    if not await ensure_subscription(
        message
    ):
        return

    if MINI_APP_URL:

        await message.answer(
            """
📢 <b>E'lonlar</b>

Quyidagi tugma orqali barcha
e'lonlarni ko'rishingiz mumkin.
""",
            reply_markup=IK(
                inline_keyboard=[
                    [
                        mini_app_button()
                    ]
                ]
            ),
            parse_mode="HTML",
        )

        return

    channel = channel_url()

    if channel:

        await message.answer(
            """
📢 <b>E'lonlar</b>

Kanalimizdagi barcha e'lonlarni
ko'rish uchun quyidagi tugmani bosing.
""",
            reply_markup=IK(
                inline_keyboard=[
                    [
                        B(
                            text="📢 E'lonlarni ko'rish",
                            url=channel,
                        )
                    ]
                ]
            ),
            parse_mode="HTML",
        )

    else:

        await message.answer(
            "📢 E'lonlarni ko'rish hozircha mavjud emas."
        )


@dp.callback_query(
    F.data == "view_ads_channel"
)
async def view_ads_channel(
    callback: types.CallbackQuery
):

    channel = channel_url()

    if channel:

        await callback.message.answer(
            "📢 Kanalimiz:",
            reply_markup=IK(
                inline_keyboard=[
                    [
                        B(
                            text="📢 E'lonlarni ko'rish",
                            url=channel,
                        )
                    ]
                ]
            ),
        )

    await callback.answer()


# ============================================================
# ADMIN CONTACT
# ============================================================

@dp.message(
    F.text == "📞 Admin bilan bog'lanish"
)
async def admin_contact(
    message: types.Message
):

    if not await ensure_subscription(
        message
    ):
        return

    await message.answer(
        f"""
📞 <b>Admin bilan bog'lanish</b>

👨‍💼 Admin: {esc(ADMIN_CONTACT)}
""",
        parse_mode="HTML",
    )


# ============================================================
# START AD
# ============================================================

@dp.message(
    F.text == "🚀 E'lon berish"
)
async def start_ad(
    message: types.Message,
    state: FSMContext
):

    register_user(
        message.from_user
    )

    if not await ensure_subscription(
        message
    ):
        return

    await state.clear()

    await state.set_state(
        AdForm.title
    )

    await message.answer(
        """
🚀 <b>E'LON BERISH</b>

📝 E'lon sarlavhasini yozing.

Masalan:
<i>Ofitsiantlar ishga taklif qilinadi</i>
""",
        parse_mode="HTML",
    )


# ============================================================
# AD FORM
# ============================================================

@dp.message(AdForm.title)
async def ad_title(
    message: types.Message,
    state: FSMContext
):

    value = (
        message.text or ""
    ).strip()

    if not value:

        await message.answer(
            "❌ Sarlavhani yozing."
        )

        return

    await state.update_data(
        title=value
    )

    await state.set_state(
        AdForm.location
    )

    await message.answer(
        """
📍 <b>Manzilni yozing.</b>

Masalan:
Toshkent, Chilonzor
""",
        parse_mode="HTML",
    )


@dp.message(AdForm.location)
async def ad_location(
    message: types.Message,
    state: FSMContext
):

    value = (
        message.text or ""
    ).strip()

    if not value:

        await message.answer(
            "❌ Manzilni yozing."
        )

        return

    await state.update_data(
        location=value
    )

    await state.set_state(
        AdForm.profession
    )

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
async def ad_profession(
    message: types.Message,
    state: FSMContext
):

    value = (
        message.text or ""
    ).strip()

    if not value:

        await message.answer(
            "❌ Ish turini yozing."
        )

        return

    await state.update_data(
        profession=value
    )

    await state.set_state(
        AdForm.conditions
    )

    await message.answer(
        """
📋 <b>Ish haqida batafsil ma'lumot yozing.</b>

Maosh, ish vaqti, talablar
va boshqa ma'lumotlarni yozing.
""",
        parse_mode="HTML",
    )


@dp.message(AdForm.conditions)
async def ad_conditions(
    message: types.Message,
    state: FSMContext
):

    value = (
        message.text or ""
    ).strip()

    if not value:

        await message.answer(
            "❌ Ma'lumotni yozing."
        )

        return

    await state.update_data(
        conditions=value
    )

    await state.set_state(
        AdForm.contact
    )

    await message.answer(
        """
📞 <b>Aloqa ma'lumotini yozing.</b>

Telefon raqami yoki Telegram username.
""",
        parse_mode="HTML",
    )


@dp.message(AdForm.contact)
async def ad_contact(
    message: types.Message,
    state: FSMContext
):

    value = (
        message.text or ""
    ).strip()

    if not value:

        await message.answer(
            "❌ Aloqa ma'lumotini yozing."
        )

        return

    await state.update_data(
        contact=value
    )

    await state.set_state(
        AdForm.image
    )

    await message.answer(
        """
🖼 <b>E'lon uchun rasm yuboring.</b>

Rasm yubormoqchi bo'lmasangiz:

⏭ <b>O'tkazib yuborish</b>

tugmasini bosing.

Admin kerak bo'lsa keyin rasm qo'yishi mumkin.
""",
        reply_markup=image_skip_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# IMAGE
# ============================================================

@dp.message(
    AdForm.image,
    F.photo
)
async def ad_image(
    message: types.Message,
    state: FSMContext
):

    await state.update_data(
        image_file_id=message.photo[-1].file_id
    )

    await state.set_state(
        AdForm.tariff
    )

    await message.answer(
        "💰 <b>Tarifni tanlang:</b>",
        reply_markup=tariff_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(
    AdForm.image,
    F.data == "skip_image"
)
async def skip_image(
    callback: types.CallbackQuery,
    state: FSMContext
):

    await state.update_data(
        image_file_id=None
    )

    await state.set_state(
        AdForm.tariff
    )

    await callback.message.edit_text(
        "💰 <b>Tarifni tanlang:</b>",
        reply_markup=tariff_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


@dp.message(AdForm.image)
async def wrong_image(
    message: types.Message
):

    await message.answer(
        """
🖼 Iltimos, rasm yuboring.

Yoki:

⏭ <b>O'tkazib yuborish</b>
""",
        reply_markup=image_skip_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# CREATE AD
# ============================================================

def create_ad(
    telegram_id,
    data,
    tariff
):

    user_id = get_user_db_id(
        telegram_id
    )

    with db() as c:

        cursor = c.execute(
            """
            INSERT INTO ads(
                telegram_id,
                user_id,
                title,
                location,
                profession,
                conditions,
                contact,
                image_file_id,
                tariff_id,
                days,
                price,
                lifetime,
                repeats_total,
                repeats_done,
                interval_hours,
                status,
                created_at
            )
            VALUES(
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, 0, ?, 0, ?,
                'pending', ?
            )
            """,
            (
                telegram_id,
                user_id,
                data["title"],
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


def create_payment(
    ad_id,
    telegram_id,
    amount
):

    expires = (
        now()
        +
        timedelta(
            minutes=RECEIPT_MINUTES
        )
    )

    with db() as c:

        cursor = c.execute(
            """
            INSERT INTO payments(
                ad_id,
                telegram_id,
                amount,
                status,
                expires_at,
                created_at
            )
            VALUES(
                ?, ?, ?, 'waiting', ?, ?
            )
            """,
            (
                ad_id,
                telegram_id,
                amount,
                iso(expires),
                iso(now()),
            ),
        )

        return cursor.lastrowid


# ============================================================
# TARIFF CHOICE
# ============================================================

@dp.callback_query(
    AdForm.tariff,
    F.data.regexp(r"^tariff_[1-4]$")
)
async def choose_tariff(
    callback: types.CallbackQuery,
    state: FSMContext
):

    tariff_id = int(
        callback.data.split("_")[1]
    )

    tariff = get_tariff(
        tariff_id
    )

    if not tariff:

        await callback.answer(
            "❌ Tarif topilmadi.",
            show_alert=True,
        )

        return

    tariff = dict(tariff)
    tariff["id"] = tariff_id

    data = await state.get_data()

    ad_id = create_ad(
        callback.from_user.id,
        data,
        tariff,
    )

    payment_id = create_payment(
        ad_id,
        callback.from_user.id,
        tariff["price"],
    )

    await state.update_data(
        ad_id=ad_id,
        payment_id=payment_id,
    )

    await state.set_state(
        AdForm.receipt
    )

    card = (
        CARD_NUMBER
        or
        "CARD_NUMBER sozlanmagan"
    )

    await callback.message.edit_text(
        f"""
💳 <b>TO'LOV</b>

📦 <b>{esc(tariff['name'])}</b>

🔄 Joylashlar:
<b>{tariff['posts']} marta</b>

⏱ Interval:
<b>{tariff['interval_hours']} soat</b>

💰 Narxi:
<b>{money(tariff['price'])} so'm</b>

💳 Karta:
<code>{esc(card)}</code>

👤 Karta egasi:
<b>{esc(CARD_HOLDER)}</b>

To'lovni amalga oshiring.

Keyin:

<b>💳 To'lov qildim</b>

tugmasini bosing.

⏰ Chekni {RECEIPT_MINUTES} daqiqa ichida yuboring.
""",
        reply_markup=IK(
            inline_keyboard=[
                [
                    B(
                        text="💳 To'lov qildim",
                        callback_data=(
                            f"paid_{payment_id}"
                        ),
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# PAID
# ============================================================

@dp.callback_query(
    F.data.regexp(r"^paid_\d+$")
)
async def paid(
    callback: types.CallbackQuery,
    state: FSMContext
):

    payment_id = int(
        callback.data.split("_")[1]
    )

    payment = get_payment(
        payment_id
    )

    if (
        not payment
        or
        payment["telegram_id"]
        != callback.from_user.id
    ):

        await callback.answer(
            "❌ To'lov topilmadi.",
            show_alert=True,
        )

        return

    if payment["status"] not in (
        "waiting",
        "paid",
    ):

        await callback.answer(
            "❌ Bu to'lov faol emas.",
            show_alert=True,
        )

        return

    expires = dt(
        payment["expires_at"]
    )

    if expires and expires <= now():

        with db() as c:

            c.execute(
                """
                UPDATE payments
                SET status='expired'
                WHERE id=?
                """,
                (payment_id,),
            )

            c.execute(
                """
                UPDATE ads
                SET status='cancelled'
                WHERE id=?
                """,
                (payment["ad_id"],),
            )

        await state.clear()

        await callback.answer(
            "❌ Chek yuborish vaqti tugagan.",
            show_alert=True,
        )

        return

    with db() as c:

        c.execute(
            """
            UPDATE payments
            SET status='paid'
            WHERE id=?
            """,
            (payment_id,),
        )

    await state.update_data(
        ad_id=payment["ad_id"],
        payment_id=payment_id,
    )

    await callback.message.answer(
        f"""
📸 <b>Endi to'lov chekini RASM qilib yuboring.</b>

⏰ Sizda {RECEIPT_MINUTES} daqiqa bor.
""",
        parse_mode="HTML",
    )

    await callback.answer(
        "✅ Chekni yuboring."
    )


# ============================================================
# RECEIPT
# ============================================================

@dp.message(
    AdForm.receipt,
    F.photo
)
async def receive_receipt(
    message: types.Message,
    state: FSMContext
):

    data = await state.get_data()

    payment_id = data.get(
        "payment_id"
    )

    if not payment_id:

        await state.clear()

        await message.answer(
            "❌ To'lov topilmadi."
        )

        return

    payment = get_payment(
        payment_id
    )

    if not payment:

        await state.clear()

        await message.answer(
            "❌ To'lov topilmadi."
        )

        return

    expires = dt(
        payment["expires_at"]
    )

    if expires and expires <= now():

        with db() as c:

            c.execute(
                """
                UPDATE payments
                SET status='expired'
                WHERE id=?
                """,
                (payment_id,),
            )

            c.execute(
                """
                UPDATE ads
                SET status='cancelled'
                WHERE id=?
                """,
                (payment["ad_id"],),
            )

        await state.clear()

        await message.answer(
            "❌ Chek yuborish vaqti tugagan."
        )

        return

    receipt_file_id = (
        message.photo[-1].file_id
    )

    with db() as c:

        c.execute(
            """
            UPDATE payments
            SET receipt_file_id=?,
                status='receipt_received'
            WHERE id=?
            """,
            (
                receipt_file_id,
                payment_id,
            ),
        )

    await state.clear()

    await send_ad_to_admin(
        payment["ad_id"]
    )

    await message.answer(
        """
✅ <b>Chek qabul qilindi!</b>

👨‍💼 Admin to'lovni tekshiradi.

Tasdiqlangandan keyin
e'lon kanalga chiqariladi.
""",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )


@dp.message(AdForm.receipt)
async def receipt_not_photo(
    message: types.Message
):

    await message.answer(
        "📸 Chekni <b>rasm</b> qilib yuboring.",
        parse_mode="HTML",
    )


# ============================================================
# ADMIN AD
# ============================================================

def admin_ad_text(ad):

    payment = latest_payment(
        ad["id"]
    )

    tariff = get_tariff(
        ad["tariff_id"]
    )

    tariff_name = (
        tariff["name"]
        if tariff
        else f"{ad['days']} kun"
    )

    receipt = (
        "yuborilgan"
        if payment and payment["receipt_file_id"]
        else "yo'q"
    )

    return f"""
📥 <b>YANGI E'LON #{ad['id']}</b>

👤 Telegram ID:
<code>{ad['telegram_id']}</code>

📝 <b>{esc(ad['title'])}</b>

📍 {esc(ad['location'])}

💼 {esc(ad['profession'])}

📋 {esc(ad['conditions'])}

📞 {esc(ad['contact'])}

📦 <b>{esc(tariff_name)}</b>

💰 {money(ad['price'])} so'm

🔄 {ad['repeats_done']}/{ad['repeats_total']} marta

🖼 Rasm:
{"bor" if ad["image_file_id"] else "yo'q"}

💳 Chek:
{receipt}
"""


async def send_ad_to_admin(
    ad_id
):

    ad = get_ad(
        ad_id
    )

    if not ad:
        return

    payment = latest_payment(
        ad_id
    )

    text = admin_ad_text(
        ad
    )

    keyboard = admin_ad_keyboard(
        ad_id,
        bool(ad["image_file_id"]),
    )

    if (
        payment
        and
        payment["receipt_file_id"]
    ):

        await bot.send_photo(
            ADMIN_ID,
            payment["receipt_file_id"],
            caption=(
                "💳 <b>TO'LOV CHEKI</b>\n\n"
                + text
            ),
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
# CHANNEL POST
# ============================================================

def build_channel_text(ad):

    text = f"""
🟢 <b>{esc(ad['title'])}</b>

📍 <b>Manzil:</b>
{esc(ad['location'])}

💼 <b>Ish:</b>
{esc(ad['profession'])}

📋 <b>Ma'lumot:</b>
{esc(ad['conditions'])}

📞 <b>Aloqa:</b>
{esc(ad['contact'])}

🆔 E'lon: <code>#{ad['id']}</code>

📢 <b>ISH BAZASI</b>
"""

    telegram_link = channel_url()

    if telegram_link:

        text += (
            f'\n🔗 <a href="{telegram_link}">'
            f'Kanalga kirish</a>'
        )

    text += (
        f'\n📸 <a href="{esc(INSTAGRAM_URL)}">'
        f'Instagram</a>'
    )

    return text


async def publish_ad(
    ad_id
):

    ad = get_ad(
        ad_id
    )

    if not ad:
        return None

    text = build_channel_text(
        ad
    )

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
            INSERT INTO ad_posts(
                ad_id,
                message_id,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (
                ad_id,
                sent.message_id,
                iso(now()),
            ),
        )

        c.execute(
            """
            UPDATE ads
            SET repeats_done=repeats_done + 1
            WHERE id=?
            """,
            (ad_id,),
        )

    return sent


async def delete_ad_posts(
    ad_id
):

    with db() as c:

        rows = c.execute(
            """
            SELECT message_id
            FROM ad_posts
            WHERE ad_id=?
            """,
            (ad_id,),
        ).fetchall()

    for row in rows:

        try:

            await bot.delete_message(
                CHANNEL_ID,
                row["message_id"],
            )

        except Exception as e:

            log.warning(
                "Post delete #%s: %s",
                ad_id,
                e,
            )

    with db() as c:

        c.execute(
            """
            DELETE FROM ad_posts
            WHERE ad_id=?
            """,
            (ad_id,),
        )


# ============================================================
# ADMIN IMAGE
# ============================================================

@dp.callback_query(
    F.data.regexp(r"^admin_add_image_\d+$")
)
async def admin_add_image(
    callback: types.CallbackQuery,
    state: FSMContext
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    ad_id = int(
        callback.data.split("_")[-1]
    )

    ad = get_ad(
        ad_id
    )

    if not ad:

        await callback.answer(
            "❌ E'lon topilmadi.",
            show_alert=True,
        )

        return

    await state.set_state(
        AdminImageForm.image
    )

    await state.update_data(
        ad_id=ad_id
    )

    await callback.message.answer(
        f"""
🖼 <b>#{ad_id}</b> e'lon uchun rasm yuboring.
""",
        parse_mode="HTML",
    )

    await callback.answer()


@dp.message(
    AdminImageForm.image,
    F.photo
)
async def admin_receive_image(
    message: types.Message,
    state: FSMContext
):

    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()

    ad_id = data.get(
        "ad_id"
    )

    if not ad_id:

        await state.clear()

        await message.answer(
            "❌ E'lon topilmadi."
        )

        return

    with db() as c:

        c.execute(
            """
            UPDATE ads
            SET image_file_id=?
            WHERE id=?
            """,
            (
                message.photo[-1].file_id,
                ad_id,
            ),
        )

    await state.clear()

    await send_ad_to_admin(
        ad_id
    )

    await message.answer(
        f"""
✅ #{ad_id} e'longa rasm qo'yildi.

Endi tasdiqlashingiz mumkin.
""",
        parse_mode="HTML",
    )


@dp.message(AdminImageForm.image)
async def admin_wrong_image(
    message: types.Message
):

    await message.answer(
        "🖼 Iltimos, rasm yuboring."
    )


# ============================================================
# APPROVE
# ============================================================

@dp.callback_query(
    F.data.regexp(r"^approve_\d+$")
)
async def approve_ad(
    callback: types.CallbackQuery
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    ad_id = int(
        callback.data.split("_")[1]
    )

    ad = get_ad(
        ad_id
    )

    if not ad:

        await callback.answer(
            "❌ E'lon topilmadi.",
            show_alert=True,
        )

        return

    if ad["status"] != "pending":

        await callback.answer(
            "⚠️ Bu e'lon allaqachon ko'rib chiqilgan.",
            show_alert=True,
        )

        return

    payment = latest_payment(
        ad_id
    )

    if ad["price"] > 0:

        if (
            not payment
            or
            payment["status"]
            != "receipt_received"
        ):

            await callback.answer(
                "❌ To'lov cheki hali kelmagan.",
                show_alert=True,
            )

            return

        with db() as c:

            c.execute(
                """
                UPDATE payments
                SET status='approved'
                WHERE id=?
                """,
                (payment["id"],),
            )

    # Birinchi post darhol chiqadi.
    try:

        await publish_ad(
            ad_id
        )

    except Exception as e:

        log.exception(
            "Kanalga chiqarish xatosi"
        )

        await callback.answer(
            "❌ Kanalga yuborib bo'lmadi. Bot kanalga ADMIN ekanini tekshiring.",
            show_alert=True,
        )

        return

    tariff = get_tariff(
        ad["tariff_id"]
    )

    if not tariff:

        await callback.answer(
            "❌ Tarif topilmadi.",
            show_alert=True,
        )

        return

    current = now()

    # Muhim:
    #
    # 1-post hozir chiqdi.
    # Keyingi post intervaldan keyin chiqadi.
    #
    # Oxirgi post ham o'z intervali tugagach o'chadi.
    #
    # Masalan:
    # 1 kun / 2 marta / 12 soat
    # 1-post 10:00
    # 2-post 22:00
    # 2-post 10:00 ertasi kuni o'chadi.
    #
    # Shuning uchun expire vaqtini:
    # postlar soni * interval
    # asosida hisoblaymiz.

    final_expire = (
        current
        +
        timedelta(
            hours=(
                tariff["posts"]
                *
                tariff["interval_hours"]
            )
        )
    )

    if tariff["posts"] > 1:

        next_post = (
            current
            +
            timedelta(
                hours=tariff["interval_hours"]
            )
        )

    else:

        next_post = None

    with db() as c:

        c.execute(
            """
            UPDATE ads
            SET status='published',
                expires_at=?,
                next_post_at=?
            WHERE id=?
            """,
            (
                iso(final_expire),
                iso(next_post),
                ad_id,
            ),
        )

    try:

        if callback.message.photo:

            await callback.message.edit_caption(
                caption=(
                    "✅ <b>TASDIQLANDI</b>\n\n"
                    "E'lon kanalga chiqarildi."
                ),
                parse_mode="HTML",
            )

        else:

            await callback.message.edit_text(
                (
                    "✅ <b>TASDIQLANDI</b>\n\n"
                    "E'lon kanalga chiqarildi."
                ),
                parse_mode="HTML",
            )

    except Exception:
        pass

    try:

        await bot.send_message(
            ad["telegram_id"],
            f"""
🎉 <b>E'loningiz tasdiqlandi!</b>

📢 E'lon kanalga chiqarildi.

📦 {esc(tariff['name'])}

🔄 {tariff['posts']} marta joylanadi.
""",
            parse_mode="HTML",
        )

    except Exception:
        pass

    await callback.answer(
        "✅ E'lon tasdiqlandi!"
    )


# ============================================================
# REJECT
# ============================================================

@dp.callback_query(
    F.data.regexp(r"^reject_\d+$")
)
async def reject_ad(
    callback: types.CallbackQuery,
    state: FSMContext
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    ad_id = int(
        callback.data.split("_")[1]
    )

    await state.set_state(
        RejectForm.reason
    )

    await state.update_data(
        ad_id=ad_id
    )

    await callback.message.answer(
        "❌ Rad etish sababini yozing."
    )

    await callback.answer()


@dp.message(RejectForm.reason)
async def reject_reason(
    message: types.Message,
    state: FSMContext
):

    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()

    ad = get_ad(
        data.get("ad_id")
    )

    if ad:

        with db() as c:

            c.execute(
                """
                UPDATE ads
                SET status='rejected'
                WHERE id=?
                """,
                (ad["id"],),
            )

            payment = latest_payment(
                ad["id"]
            )

            if payment:

                c.execute(
                    """
                    UPDATE payments
                    SET status='rejected'
                    WHERE id=?
                    """,
                    (payment["id"],),
                )

        try:

            await bot.send_message(
                ad["telegram_id"],
                f"""
❌ <b>E'loningiz rad etildi.</b>

Sabab:
{esc(message.text)}
""",
                parse_mode="HTML",
            )

        except Exception:
            pass

    await state.clear()

    await message.answer(
        "✅ E'lon rad etildi."
    )


# ============================================================
# ADMIN PANEL
# ============================================================

@dp.message(Command("admin"))
async def admin_panel(
    message: types.Message
):

    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "👨‍💼 <b>ADMIN PANEL</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(
    F.data == "admin_home"
)
async def admin_home(
    callback: types.CallbackQuery
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    await callback.message.edit_text(
        "👨‍💼 <b>ADMIN PANEL</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# ADMIN STATS
# ============================================================

@dp.callback_query(
    F.data == "admin_stats"
)
async def admin_stats(
    callback: types.CallbackQuery
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    with db() as c:

        users = c.execute(
            """
            SELECT COUNT(*) n
            FROM users
            """
        ).fetchone()["n"]

        ads = c.execute(
            """
            SELECT COUNT(*) n
            FROM ads
            """
        ).fetchone()["n"]

        active = c.execute(
            """
            SELECT COUNT(*) n
            FROM ads
            WHERE status='published'
            """
        ).fetchone()["n"]

        revenue = c.execute(
            """
            SELECT COALESCE(SUM(amount),0) n
            FROM payments
            WHERE status='approved'
            """
        ).fetchone()["n"]

        pending = c.execute(
            """
            SELECT COUNT(*) n
            FROM payments
            WHERE status='receipt_received'
            """
        ).fetchone()["n"]

    await callback.message.edit_text(
        f"""
📊 <b>STATISTIKA</b>

👥 Foydalanuvchilar:
<b>{users}</b>

📢 Jami e'lonlar:
<b>{ads}</b>

🟢 Faol e'lonlar:
<b>{active}</b>

⏳ Tekshirilayotgan to'lovlar:
<b>{pending}</b>

💰 Daromad:
<b>{money(revenue)} so'm</b>
""",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# ADMIN TARIFFS
# ============================================================

@dp.callback_query(
    F.data == "admin_tariffs"
)
async def admin_tariffs(
    callback: types.CallbackQuery
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    tariffs = get_tariffs()

    text = "💰 <b>TARIFLAR</b>\n\n"

    for i in range(1, 5):

        t = tariffs[i]

        text += (
            f"{i}. <b>{esc(t['name'])}</b>\n"
            f"💵 {money(t['price'])} so'm\n"
            f"🔄 {t['posts']} marta\n"
            f"⏱ Har {t['interval_hours']} soat\n"
            f"📅 {t['days']} kun\n\n"
        )

    await callback.message.edit_text(
        text,
        reply_markup=admin_tariff_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data.regexp(r"^edit_tariff_[1-4]$")
)
async def edit_tariff(
    callback: types.CallbackQuery,
    state: FSMContext
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    tariff_id = int(
        callback.data.split("_")[-1]
    )

    tariff = get_tariff(
        tariff_id
    )

    await state.set_state(
        TariffPriceForm.price
    )

    await state.update_data(
        tariff_id=tariff_id
    )

    await callback.message.answer(
        f"""
💰 <b>{esc(tariff['name'])}</b>

Hozirgi narx:
<b>{money(tariff['price'])} so'm</b>

Yangi narxni faqat raqam bilan yuboring.

Masalan:
25000
""",
        parse_mode="HTML",
    )

    await callback.answer()


@dp.message(
    TariffPriceForm.price
)
async def save_tariff_price(
    message: types.Message,
    state: FSMContext
):

    if message.from_user.id != ADMIN_ID:
        return

    try:

        price = int(
            (
                message.text or ""
            )
            .replace(" ", "")
            .replace(",", "")
        )

        if price < 0:
            raise ValueError

    except Exception:

        await message.answer(
            "❌ Narxni faqat raqam bilan yuboring."
        )

        return

    data = await state.get_data()

    update_tariff(
        data["tariff_id"],
        price=price,
    )

    await state.clear()

    await message.answer(
        "✅ Tarif narxi saqlandi."
    )

    await message.answer(
        "💰 <b>Tariflar</b>",
        reply_markup=admin_tariff_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# ADMIN ADS
# ============================================================

@dp.callback_query(
    F.data == "admin_ads"
)
async def admin_ads(
    callback: types.CallbackQuery
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    with db() as c:

        rows = c.execute(
            """
            SELECT *
            FROM ads
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()

    text = "📢 <b>E'LONLAR</b>\n\n"

    if not rows:

        text += "Hozircha e'lonlar yo'q."

    else:

        for ad in rows:

            text += (
                f"🆔 #{ad['id']}\n"
                f"📝 {esc(ad['title'])}\n"
                f"{status_text(ad['status'])}\n"
                f"🔄 {ad['repeats_done']}/"
                f"{ad['repeats_total']}\n"
            )

            if ad["status"] == "published":

                text += (
                    f"⏳ Keyingi: "
                    f"{remaining_text(ad['next_post_at'])}\n"
                )

                text += (
                    f"⌛ Tugashigacha: "
                    f"{remaining_text(ad['expires_at'])}\n"
                )

            text += "\n"

    await callback.message.edit_text(
        text,
        reply_markup=IK(
            inline_keyboard=[
                [
                    B(
                        text="⬅️ Admin panel",
                        callback_data="admin_home",
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# ADMIN PAYMENTS
# ============================================================

@dp.callback_query(
    F.data == "admin_payments"
)
async def admin_payments(
    callback: types.CallbackQuery
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    with db() as c:

        rows = c.execute(
            """
            SELECT *
            FROM payments
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()

    buttons = []

    for payment in rows:

        buttons.append(
            [
                B(
                    text=(
                        f"#{payment['id']} | "
                        f"{money(payment['amount'])} so'm | "
                        f"{payment['status']}"
                    ),
                    callback_data=(
                        f"payment_view_{payment['id']}"
                    ),
                )
            ]
        )

    buttons.append(
        [
            B(
                text="⬅️ Admin panel",
                callback_data="admin_home",
            )
        ]
    )

    await callback.message.edit_text(
        """
💳 <b>TO'LOVLAR</b>

Kerakli to'lovni tanlang.
""",
        reply_markup=IK(
            inline_keyboard=buttons
        ),
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data.regexp(r"^payment_view_\d+$")
)
async def payment_view(
    callback: types.CallbackQuery
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    payment_id = int(
        callback.data.split("_")[-1]
    )

    payment = get_payment(
        payment_id
    )

    if not payment:

        await callback.answer(
            "❌ Topilmadi.",
            show_alert=True,
        )

        return

    text = f"""
💳 <b>TO'LOV #{payment['id']}</b>

📢 E'lon:
#{payment['ad_id']}

👤 Telegram ID:
<code>{payment['telegram_id']}</code>

💰 {money(payment['amount'])} so'm

📌 Holat:
<b>{esc(payment['status'])}</b>
"""

    buttons = []

    if payment["receipt_file_id"]:

        buttons.append(
            [
                B(
                    text="👀 Chekni ko'rish",
                    callback_data=(
                        f"send_receipt_{payment['id']}"
                    ),
                )
            ]
        )

    buttons.append(
        [
            B(
                text="⬅️ To'lovlar",
                callback_data="admin_payments",
            )
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=IK(
            inline_keyboard=buttons
        ),
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data.regexp(r"^send_receipt_\d+$")
)
async def send_receipt(
    callback: types.CallbackQuery
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    payment_id = int(
        callback.data.split("_")[-1]
    )

    payment = get_payment(
        payment_id
    )

    if (
        payment
        and
        payment["receipt_file_id"]
    ):

        await bot.send_photo(
            ADMIN_ID,
            payment["receipt_file_id"],
            caption=(
                f"💳 To'lov #{payment['id']}\n"
                f"📢 E'lon #{payment['ad_id']}"
            ),
        )

    await callback.answer()


# ============================================================
# ADMIN USERS
# ============================================================

@dp.callback_query(
    F.data == "admin_users"
)
async def admin_users(
    callback: types.CallbackQuery
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    with db() as c:

        total = c.execute(
            """
            SELECT COUNT(*) n
            FROM users
            """
        ).fetchone()["n"]

        active = c.execute(
            """
            SELECT COUNT(*) n
            FROM users
            WHERE blocked=0
            """
        ).fetchone()["n"]

    await callback.message.edit_text(
        f"""
👥 <b>FOYDALANUVCHILAR</b>

Jami:
<b>{total}</b>

Faol:
<b>{active}</b>
""",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# BROADCAST
# ============================================================

@dp.callback_query(
    F.data == "admin_broadcast"
)
async def admin_broadcast(
    callback: types.CallbackQuery,
    state: FSMContext
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

        return

    await state.set_state(
        BroadcastForm.message
    )

    await callback.message.answer(
        """
📣 <b>Hammaga yuboriladigan xabarni yuboring.</b>

Matn yoki rasm yuborishingiz mumkin.
""",
        parse_mode="HTML",
    )

    await callback.answer()


@dp.message(
    BroadcastForm.message
)
async def broadcast(
    message: types.Message,
    state: FSMContext
):

    if message.from_user.id != ADMIN_ID:
        return

    with db() as c:

        users = c.execute(
            """
            SELECT telegram_id
            FROM users
            WHERE blocked=0
            """
        ).fetchall()

    success = 0
    failed = 0

    for user in users:

        try:

            if message.photo:

                await bot.send_photo(
                    user["telegram_id"],
                    message.photo[-1].file_id,
                    caption=(
                        message.caption or ""
                    ),
                )

            elif message.text:

                await bot.send_message(
                    user["telegram_id"],
                    message.text,
                )

            else:

                failed += 1
                continue

            success += 1

        except Exception as e:

            failed += 1

            if "bot was blocked" in str(e).lower():

                with db() as c:

                    c.execute(
                        """
                        UPDATE users
                        SET blocked=1
                        WHERE telegram_id=?
                        """,
                        (user["telegram_id"],),
                    )

    await state.clear()

    await message.answer(
        f"""
📣 <b>Yuborish tugadi.</b>

✅ Yuborildi:
{success}

❌ Yuborilmadi:
{failed}
""",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# SCHEDULER
# ============================================================

async def scheduler_loop():

    while True:

        try:

            current = now()

            # ------------------------------------------------
            # 1. RECEIPT TIMEOUT
            # ------------------------------------------------

            with db() as c:

                expired_payments = c.execute(
                    """
                    SELECT id, ad_id
                    FROM payments
                    WHERE status IN (
                        'waiting',
                        'paid'
                    )
                    AND expires_at IS NOT NULL
                    AND expires_at <= ?
                    """,
                    (iso(current),),
                ).fetchall()

            for payment in expired_payments:

                with db() as c:

                    c.execute(
                        """
                        UPDATE payments
                        SET status='expired'
                        WHERE id=?
                        """,
                        (payment["id"],),
                    )

                    c.execute(
                        """
                        UPDATE ads
                        SET status='cancelled'
                        WHERE id=?
                        AND status='pending'
                        """,
                        (payment["ad_id"],),
                    )

            # ------------------------------------------------
            # 2. EXPIRED ADS
            # ------------------------------------------------

            with db() as c:

                expired_ads = c.execute(
                    """
                    SELECT id, telegram_id
                    FROM ads
                    WHERE status='published'
                    AND expires_at IS NOT NULL
                    AND expires_at <= ?
                    """,
                    (iso(current),),
                ).fetchall()

            for ad in expired_ads:

                await delete_ad_posts(
                    ad["id"]
                )

                with db() as c:

                    c.execute(
                        """
                        UPDATE ads
                        SET status='expired',
                            next_post_at=NULL
                        WHERE id=?
                        """,
                        (ad["id"],),
                    )

                try:

                    await bot.send_message(
                        ad["telegram_id"],
                        f"""
⌛ <b>E'loningiz #{ad['id']} tugadi.</b>

Barcha joylangan postlar avtomatik o'chirildi.
""",
                        parse_mode="HTML",
                    )

                except Exception:
                    pass

            # ------------------------------------------------
            # 3. DUE REPOSTS
            # ------------------------------------------------

            with db() as c:

                due = c.execute(
                    """
                    SELECT id
                    FROM ads
                    WHERE status='published'
                    AND next_post_at IS NOT NULL
                    AND next_post_at <= ?
                    AND repeats_done < repeats_total
                    """,
                    (iso(current),),
                ).fetchall()

            for row in due:

                ad = get_ad(
                    row["id"]
                )

                if not ad:
                    continue

                if ad["repeats_done"] >= ad["repeats_total"]:
                    continue

                # --------------------------------------------
                # ESKI POSTNI O'CHIRISH
                # --------------------------------------------

                await delete_ad_posts(
                    ad["id"]
                )

                # --------------------------------------------
                # YANGI POST
                # --------------------------------------------

                try:

                    await publish_ad(
                        ad["id"]
                    )

                except Exception:

                    log.exception(
                        "Repost xatosi #%s",
                        ad["id"],
                    )

                    continue

                updated = get_ad(
                    ad["id"]
                )

                if not updated:
                    continue

                tariff = get_tariff(
                    updated["tariff_id"]
                )

                if not tariff:
                    continue

                # --------------------------------------------
                # KEYINGI POST
                # --------------------------------------------

                if (
                    updated["repeats_done"]
                    <
                    updated["repeats_total"]
                ):

                    next_time = (
                        current
                        +
                        timedelta(
                            hours=tariff[
                                "interval_hours"
                            ]
                        )
                    )

                    with db() as c:

                        c.execute(
                            """
                            UPDATE ads
                            SET next_post_at=?
                            WHERE id=?
                            """,
                            (
                                iso(next_time),
                                updated["id"],
                            ),
                        )

                else:

                    # Oxirgi post chiqdi.
                    #
                    # Oxirgi post ham intervaldan keyin
                    # avtomatik o'chiriladi.
                    #
                    # expires_at aynan shu vaqtga ko'chiriladi.

                    final_delete = (
                        current
                        +
                        timedelta(
                            hours=tariff[
                                "interval_hours"
                            ]
                        )
                    )

                    with db() as c:

                        c.execute(
                            """
                            UPDATE ads
                            SET next_post_at=NULL,
                                expires_at=?
                            WHERE id=?
                            """,
                            (
                                iso(final_delete),
                                updated["id"],
                            ),
                        )

        except Exception:

            log.exception(
                "Scheduler xatosi"
            )

        # Har 20 sekundda tekshiradi.
        await asyncio.sleep(20)


# ============================================================
# ERROR HANDLER
# ============================================================

@dp.errors()
async def global_error(
    event: types.ErrorEvent
):

    log.exception(
        "Unhandled Telegram update error: %s",
        event.exception,
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    init_db()

    asyncio.create_task(
        scheduler_loop()
    )

    log.info(
        "ISH BAZASI BOT ishga tushdi"
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except (
        KeyboardInterrupt,
        SystemExit,
    ):

        pass
