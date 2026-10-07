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
)

# ============================================================
# ISH BAZASI BOT — YAKUNIY VERSIYA
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
CARD_HOLDER = os.getenv(
    "CARD_HOLDER",
    "Diyorbek Rustamov"
)

DB_PATH = os.getenv("DB_PATH", "bot.db")

RECEIPT_MINUTES = int(
    os.getenv("RECEIPT_MINUTES", "10")
)

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi. Railway Variables ga BOT_TOKEN kiriting."
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

log = logging.getLogger("ishbazasi")

bot = Bot(TOKEN)

dp = Dispatcher(
    storage=MemoryStorage()
)


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
        "price": 45000,
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
        "name": "VIP — 7 kun, har kuni 2 MARTA",
        "days": 7,
        "posts": 14,
        "interval_hours": 12,
        "price": 149000,
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
    return value.astimezone(
        timezone.utc
    ).isoformat()


def dt(value):
    if not value:
        return None

    return datetime.fromisoformat(value)


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

        existing = {
            row[1]
            for row in c.execute(
                "PRAGMA table_info(ads)"
            ).fetchall()
        }

        additions = {
            "tariff_id": "INTEGER DEFAULT 1",
            "repeats_total": "INTEGER DEFAULT 1",
            "repeats_done": "INTEGER DEFAULT 0",
            "interval_hours": "INTEGER DEFAULT 12",
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
                DO UPDATE SET

                    name=excluded.name,
                    days=excluded.days,
                    posts=excluded.posts,
                    interval_hours=excluded.interval_hours,
                    price=excluded.price,
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
# DATABASE FUNKSIYALAR
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

        if row:
            return row["id"]

    return None


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


def update_tariff_price(
    tariff_id,
    price
):

    with db() as c:

        c.execute(
            """
            UPDATE tariff_settings

            SET price=?

            WHERE id=?
            """,
            (
                price,
                tariff_id,
            ),
        )


def status_text(status):

    return {
        "pending": "⏳ Kutilmoqda",
        "published": "✅ Faol",
        "expired": "⌛ Tugagan",
        "rejected": "❌ Rad etilgan",
        "deleted": "🗑 O'chirilgan",
        "cancelled": "🚫 Bekor qilingan",
    }.get(
        status,
        status
    )


# ============================================================
# FOYDALANUVCHI MENYUSI
# ============================================================

def main_menu():

    return RK(
        keyboard=[
            [
                KB(
                    text="🚀 E'lon berish"
                )
            ],
            [
                KB(
                    text="📋 Mening e'lonlarim"
                )
            ],
            [
                KB(
                    text="📞 Admin bilan bog'lanish"
                )
            ],
        ],
        resize_keyboard=True,
    )


# ============================================================
# OBUNA
# ============================================================

def subscription_keyboard():

    return IK(
        inline_keyboard=[

            [
                B(
                    text="📢 Telegram kanalga obuna bo'lish — SHART!",
                    url=(
                        f"https://t.me/"
                        f"{REQUIRED_CHANNEL.lstrip('@')}"
                    ),
                )
            ],

            [
                B(
                    text="📸 Instagramga obuna bo'lish — SHART!",
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

Botdan foydalanish uchun quyidagi sahifalarga obuna bo'ling.

📢 Telegram — <b>MAJBURIY</b>
📸 Instagram — <b>MAJBURIY KO'RSATILADI</b>

⚠️ Instagram obunasi bot tomonidan tekshirilmaydi.

Telegram kanalga obuna bo'lgach:

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
# ADMIN MENYUSI
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

    for tariff_id in range(
        1,
        5
    ):

        tariff = tariffs[tariff_id]

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


def admin_tariff_keyboard():

    tariffs = get_tariffs()

    return IK(
        inline_keyboard=[

            [
                B(
                    text=(
                        f"1️⃣ "
                        f"{money(tariffs[1]['price'])} so'm"
                    ),
                    callback_data="edit_tariff_1",
                ),

                B(
                    text=(
                        f"2️⃣ "
                        f"{money(tariffs[2]['price'])} so'm"
                    ),
                    callback_data="edit_tariff_2",
                ),
            ],

            [
                B(
                    text=(
                        f"3️⃣ "
                        f"{money(tariffs[3]['price'])} so'm"
                    ),
                    callback_data="edit_tariff_3",
                ),

                B(
                    text=(
                        f"4️⃣ "
                        f"{money(tariffs[4]['price'])} so'm"
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

@dp.message(
    Command("start")
)
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
🎉 <b>Xush kelibsiz!</b>

🚀 Ishchi kerak bo'lsa,
shu bot orqali e'lon bering.
""",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )


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
            "✅ Telegram obunasi tasdiqlandi!",
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
            "❌ Avval Telegram kanalga obuna bo'ling!",
            show_alert=True,
        )


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
# MENING E'LONLARIM
# ============================================================

@dp.message(
    F.text == "📋 Mening e'lonlarim"
)
async def my_ads(
    message: types.Message
):

    if not await ensure_subscription(
        message
    ):
        return

    with db() as c:

        rows = c.execute(
            """
            SELECT *
            FROM ads

            WHERE telegram_id=?

            ORDER BY id DESC

            LIMIT 20
            """,
            (
                message.from_user.id,
            ),
        ).fetchall()

    if not rows:

        await message.answer(
            "📋 Sizda hali e'lon yo'q."
        )

        return

    result = [
        "📋 <b>Mening e'lonlarim</b>\n"
    ]

    for ad in rows:

        result.append(
            f"""
🆔 #{ad['id']}
📝 {esc(ad['title'])}

{status_text(ad['status'])}

🔄 {ad['repeats_done']}/"
            f"{ad['repeats_total']} marta
"""
        )

    await message.answer(
        "\n".join(result),
        parse_mode="HTML",
    )


# ============================================================
# E'LON BOSHLASH
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
📝 <b>E'lon sarlavhasini yozing.</b>

Masalan:
<i>Ofitsiantlar ishga taklif qilinadi</i>
""",
        parse_mode="HTML",
    )


@dp.message(
    AdForm.title
)
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


@dp.message(
    AdForm.location
)
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


@dp.message(
    AdForm.profession
)
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


@dp.message(
    AdForm.conditions
)
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


@dp.message(
    AdForm.contact
)
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

<b>⏭ O'tkazib yuborish</b>

tugmasini bosing.

⚠️ Rasm yubormasangiz,
e'lon admin paneliga rasmsiz keladi.
Admin keyin rasm qo'yadi.
""",
        reply_markup=image_skip_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# RASM
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


@dp.message(
    AdForm.image
)
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
# E'LON YARATISH
# ============================================================

def create_ad(
    telegram_id,
    data,
    tariff_data
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

                tariff_data["id"],
                tariff_data["days"],
                tariff_data["price"],

                tariff_data["posts"],
                tariff_data["interval_hours"],

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
# TARIF TANLASH
# ============================================================

@dp.callback_query(
    AdForm.tariff,
    F.data.regexp(
        r"^tariff_[1-4]$"
    )
)
async def choose_tariff(
    callback: types.CallbackQuery,
    state: FSMContext
):

    tariff_id = int(
        callback.data.split("_")[1]
    )

    selected = get_tariff(
        tariff_id
    )

    if not selected:

        await callback.answer(
            "❌ Tarif topilmadi.",
            show_alert=True,
        )

        return

    data = await state.get_data()

    selected = dict(selected)

    selected["id"] = tariff_id

    ad_id = create_ad(
        callback.from_user.id,
        data,
        selected,
    )

    payment_id = create_payment(
        ad_id,
        callback.from_user.id,
        selected["price"],
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
        "Railway Variables → CARD_NUMBER"
    )

    await callback.message.edit_text(
        f"""
💳 <b>TO'LOV</b>

📦 <b>{esc(selected['name'])}</b>

💰 <b>{money(selected['price'])} so'm</b>

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
# TO'LOV QILDIM
# ============================================================

@dp.callback_query(
    F.data.regexp(
        r"^paid_\d+$"
    )
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

    if dt(
        payment["expires_at"]
    ) < now():

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
                (
                    payment["ad_id"],
                ),
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

    await state.set_state(
        AdForm.receipt
    )

    await callback.message.answer(
        f"""
📸 <b>Endi to'lov chekini RASM qilib yuboring.</b>

⏰ Sizda {RECEIPT_MINUTES} daqiqa bor.
""",
        parse_mode="HTML",
    )

    await callback.answer(
        "✅ Endi chekni yuboring."
    )


# ============================================================
# CHEK QABUL QILISH
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

    payment = get_payment(
        payment_id
    )

    if (
        not payment
        or
        payment["telegram_id"]
        != message.from_user.id
    ):

        await state.clear()

        await message.answer(
            "❌ To'lov topilmadi."
        )

        return

    if dt(
        payment["expires_at"]
    ) < now():

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
                (
                    payment["ad_id"],
                ),
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


@dp.message(
    AdForm.receipt
)
async def receipt_not_photo(
    message: types.Message
):

    await message.answer(
        "📸 Chekni <b>rasm</b> qilib yuboring.",
        parse_mode="HTML",
    )


# ============================================================
# ADMINGA E'LON YUBORISH
# ============================================================

def admin_ad_text(ad):

    payment = latest_payment(
        ad["id"]
    )

    tariff_data = get_tariff(
        ad["tariff_id"]
    )

    if tariff_data:

        tariff_name = tariff_data[
            "name"
        ]

    else:

        tariff_name = (
            f"{ad['days']} kun"
        )

    if ad["image_file_id"]:

        image_text = "bor"

    else:

        image_text = (
            "yo'q — admin qo'yishi mumkin"
        )

    receipt_text = (
        "yuborilgan"
        if payment
        and payment["receipt_file_id"]
        else
        "yo'q"
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

🖼 Rasm: {image_text}

💳 Chek: {receipt_text}
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
                +
                text
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
# KANAL POSTI
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
            f'Telegram kanalimiz</a>'
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

    channel_text = build_channel_text(
        ad
    )

    if ad["image_file_id"]:

        sent = await bot.send_photo(
            CHANNEL_ID,
            ad["image_file_id"],
            caption=channel_text,
            parse_mode="HTML",
        )

    else:

        sent = await bot.send_message(
            CHANNEL_ID,
            channel_text,
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

            SET repeats_done =
                repeats_done + 1

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
                "Post o'chirish xatosi #%s: %s",
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
# ADMIN RASM QO'YISH
# ============================================================

@dp.callback_query(
    F.data.regexp(
        r"^admin_add_image_\d+$"
    )
)
async def admin_add_image(
    callback: types.CallbackQuery,
    state: FSMContext
):

    if (
        callback.from_user.id
        != ADMIN_ID
    ):

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
🖼 <b>#{ad_id}</b> e'lon uchun
rasmni yuboring.

Bot shu rasmni e'lon rasmi qilib qo'yadi.
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

    if (
        message.from_user.id
        != ADMIN_ID
    ):
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

            SET image_file_id=?,
                status='pending'

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

Endi <b>✅ Tasdiqlash</b>
tugmasini bosing.
""",
        parse_mode="HTML",
    )


@dp.message(
    AdminImageForm.image
)
async def admin_wrong_image(
    message: types.Message
):

    await message.answer(
        "🖼 Iltimos, rasm yuboring."
    )


# ============================================================
# E'LONNI TASDIQLASH
# ============================================================

@dp.callback_query(
    F.data.regexp(
        r"^approve_\d+$"
    )
)
async def approve_ad(
    callback: types.CallbackQuery
):

    if (
        callback.from_user.id
        != ADMIN_ID
    ):

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

    if ad["status"] not in (
        "pending",
    ):

        await callback.answer(
            "⚠️ Bu e'lon allaqachon ko'rib chiqilgan.",
            show_alert=True,
        )

        return

    if ad["price"] > 0:

        payment = latest_payment(
            ad_id
        )

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
                (
                    payment["id"],
                ),
            )

    try:

        await publish_ad(
            ad_id
        )

    except Exception:

        log.exception(
            "Kanalga chiqarish xatosi"
        )

        await callback.answer(
            """
❌ Kanalga yuborib bo'lmadi.

Bot kanalga ADMIN ekanini
tekshiring.
""",
            show_alert=True,
        )

        return

    selected = get_tariff(
        ad["tariff_id"]
    )

    if selected:

        expires_at = (
            now()
            +
            timedelta(
                days=selected["days"]
            )
        )

        if selected["posts"] > 1:

            next_post_at = (
                now()
                +
                timedelta(
                    hours=selected[
                        "interval_hours"
                    ]
                )
            )

        else:

            next_post_at = None

    else:

        expires_at = (
            now()
            +
            timedelta(
                days=1
            )
        )

        next_post_at = None

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
                iso(expires_at),
                (
                    iso(next_post_at)
                    if next_post_at
                    else None
                ),
                ad_id,
            ),
        )

    try:

        if callback.message.photo:

            await callback.message.edit_caption(
                caption="""
✅ <b>TASDIQLANDI</b>

E'lon kanalga chiqarildi.
""",
                parse_mode="HTML",
            )

        else:

            await callback.message.edit_text(
                """
✅ <b>TASDIQLANDI</b>

E'lon kanalga chiqarildi.
""",
                parse_mode="HTML",
            )

    except Exception:

        pass

    tariff_name = (
        selected["name"]
        if selected
        else
        "Tarif"
    )

    try:

        await bot.send_message(
            ad["telegram_id"],
            f"""
🎉 <b>E'loningiz tasdiqlandi!</b>

📢 E'lon kanalga chiqarildi.

📦 {esc(tariff_name)}
""",
            parse_mode="HTML",
        )

    except Exception:

        pass

    await callback.answer(
        "✅ E'lon tasdiqlandi!"
    )


# ============================================================
# RAD ETISH
# ============================================================

@dp.callback_query(
    F.data.regexp(
        r"^reject_\d+$"
    )
)
async def reject_ad(
    callback: types.CallbackQuery,
    state: FSMContext
):

    if (
        callback.from_user.id
        != ADMIN_ID
    ):

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


@dp.message(
    RejectForm.reason
)
async def reject_reason(
    message: types.Message,
    state: FSMContext
):

    if (
        message.from_user.id
        != ADMIN_ID
    ):
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
                (
                    ad["id"],
                ),
            )

        await bot.send_message(
            ad["telegram_id"],
            f"""
❌ <b>E'loningiz rad etildi.</b>

Sabab:
{esc(message.text)}
""",
            parse_mode="HTML",
        )

    await state.clear()

    await message.answer(
        "✅ E'lon rad etildi."
    )


# ============================================================
# ADMIN PANEL
# ============================================================

@dp.message(
    Command("admin")
)
async def admin_panel(
    message: types.Message
):

    if (
        message.from_user.id
        != ADMIN_ID
    ):
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

    if (
        callback.from_user.id
        != ADMIN_ID
    ):
        return await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

    await callback.message.edit_text(
        "👨‍💼 <b>ADMIN PANEL</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# STATISTIKA
# ============================================================

@dp.callback_query(
    F.data == "admin_stats"
)
async def admin_stats(
    callback: types.CallbackQuery
):

    if (
        callback.from_user.id
        != ADMIN_ID
    ):
        return await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

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

        approved_money = c.execute(
            """
            SELECT COALESCE(
                SUM(amount),
                0
            ) n

            FROM payments

            WHERE status='approved'
            """
        ).fetchone()["n"]

    await callback.message.edit_text(
        f"""
📊 <b>STATISTIKA</b>

👥 Foydalanuvchilar:
<b>{users}</b>

📢 Jami e'lonlar:
<b>{ads}</b>

✅ Faol e'lonlar:
<b>{active}</b>

💰 Tasdiqlangan to'lovlar:
<b>{money(approved_money)} so'm</b>
""",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# TARIFLAR
# ============================================================

@dp.callback_query(
    F.data == "admin_tariffs"
)
async def admin_tariffs(
    callback: types.CallbackQuery
):

    if (
        callback.from_user.id
        != ADMIN_ID
    ):
        return await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

    ts = get_tariffs()

    text = "💰 <b>TARIFLAR</b>\n\n"

    for i in range(
        1,
        5
    ):

        text += (
            f"{i}. "
            f"{esc(ts[i]['name'])}\n"
            f"💵 "
            f"<b>{money(ts[i]['price'])} so'm</b>\n\n"
        )

    await callback.message.edit_text(
        text,
        reply_markup=admin_tariff_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data.regexp(
        r"^edit_tariff_[1-4]$"
    )
)
async def edit_tariff(
    callback: types.CallbackQuery,
    state: FSMContext
):

    if (
        callback.from_user.id
        != ADMIN_ID
    ):
        return await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

    tariff_id = int(
        callback.data.split("_")[-1]
    )

    selected = get_tariff(
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
💰 <b>{esc(selected['name'])}</b>

Hozirgi narx:
<b>{money(selected['price'])} so'm</b>

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

    if (
        message.from_user.id
        != ADMIN_ID
    ):
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
            """
❌ Narxni faqat raqam bilan yuboring.

Masalan:
25000
"""
        )

        return

    data = await state.get_data()

    update_tariff_price(
        data["tariff_id"],
        price,
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
# E'LONLAR
# ============================================================

@dp.callback_query(
    F.data == "admin_ads"
)
async def admin_ads(
    callback: types.CallbackQuery
):

    if (
        callback.from_user.id
        != ADMIN_ID
    ):
        return await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

    with db() as c:

        rows = c.execute(
            """
            SELECT *
            FROM ads
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()

    if not rows:

        text = (
            "📢 Hozircha e'lonlar yo'q."
        )

    else:

        text = (
            "📢 <b>SO'NGGI E'LONLAR</b>\n\n"
        )

        for ad in rows:

            text += (
                f"🆔 #{ad['id']}\n"
                f"📝 {esc(ad['title'])}\n"
                f"{status_text(ad['status'])}\n"
                f"🔄 "
                f"{ad['repeats_done']}/"
                f"{ad['repeats_total']} marta\n\n"
            )

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
# TO'LOVLAR
# ============================================================

@dp.callback_query(
    F.data == "admin_payments"
)
async def admin_payments(
    callback: types.CallbackQuery
):

    if (
        callback.from_user.id
        != ADMIN_ID
    ):
        return await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

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
    F.data.regexp(
        r"^payment_view_\d+$"
    )
)
async def payment_view(
    callback: types.CallbackQuery
):

    if (
        callback.from_user.id
        != ADMIN_ID
    ):
        return await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

    payment_id = int(
        callback.data.split("_")[-1]
    )

    payment = get_payment(
        payment_id
    )

    if not payment:

        return await callback.answer(
            "❌ Topilmadi.",
            show_alert=True,
        )

    text = f"""
💳 <b>TO'LOV #{payment['id']}</b>

🆔 E'lon:
#{payment['ad_id']}

👤 Telegram ID:
<code>{payment['telegram_id']}</code>

💰 {money(payment['amount'])} so'm

📌 Holat:
{payment['status']}
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
    F.data.regexp(
        r"^send_receipt_\d+$"
    )
)
async def send_receipt(
    callback: types.CallbackQuery
):

    if (
        callback.from_user.id
        != ADMIN_ID
    ):
        return await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

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
# FOYDALANUVCHILAR
# ============================================================

@dp.callback_query(
    F.data == "admin_users"
)
async def admin_users(
    callback: types.CallbackQuery
):

    if (
        callback.from_user.id
        != ADMIN_ID
    ):
        return await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

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

    if (
        callback.from_user.id
        != ADMIN_ID
    ):
        return await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True,
        )

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

    if (
        message.from_user.id
        != ADMIN_ID
    ):
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
                        message.caption
                        or
                        ""
                    ),
                )

            else:

                await bot.send_message(
                    user["telegram_id"],
                    message.text or "",
                )

            success += 1

        except Exception:

            failed += 1

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
# AVTOMATIK REPOST / O'CHIRISH
# ============================================================

async def scheduler_loop():

    while True:

        try:

            current = now()

            with db() as c:

                expired = c.execute(
                    """
                    SELECT id, telegram_id
                    FROM ads

                    WHERE status='published'

                    AND expires_at IS NOT NULL

                    AND expires_at <= ?
                    """,
                    (
                        iso(current),
                    ),
                ).fetchall()

                due = c.execute(
                    """
                    SELECT id
                    FROM ads

                    WHERE status='published'

                    AND next_post_at IS NOT NULL

                    AND next_post_at <= ?

                    AND repeats_done < repeats_total
                    """,
                    (
                        iso(current),
                    ),
                ).fetchall()

            # MUDDATI TUGAGAN E'LONLAR

            for ad in expired:

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
                        (
                            ad["id"],
                        ),
                    )

                try:

                    await bot.send_message(
                        ad["telegram_id"],
                        f"""
⌛ <b>E'loningiz #{ad['id']} tugadi.</b>
""",
                        parse_mode="HTML",
                    )

                except Exception:

                    pass

            # NAVBATDAGI REPOSTLAR

            for row in due:

                ad = get_ad(
                    row["id"]
                )

                if not ad:
                    continue

                if (
                    ad["repeats_done"]
                    >=
                    ad["repeats_total"]
                ):
                    continue

                # Eski postni o'chiramiz.
                # Yangi post kanalga yuqoriga chiqadi.

                await delete_ad_posts(
                    ad["id"]
                )

                await publish_ad(
                    ad["id"]
                )

                updated = get_ad(
                    ad["id"]
                )

                selected = get_tariff(
                    updated["tariff_id"]
                )

                if (
                    updated["repeats_done"]
                    <
                    updated["repeats_total"]
                ):

                    hours = (
                        selected[
                            "interval_hours"
                        ]
                        if selected
                        else
                        updated[
                            "interval_hours"
                        ]
                    )

                    next_time = (
                        current
                        +
                        timedelta(
                            hours=hours
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

                    with db() as c:

                        c.execute(
                            """
                            UPDATE ads

                            SET next_post_at=NULL

                            WHERE id=?
                            """,
                            (
                                updated["id"],
                            ),
                        )

        except Exception:

            log.exception(
                "Scheduler xatosi"
            )

        await asyncio.sleep(
            20
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
