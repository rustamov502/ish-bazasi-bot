import asyncio
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
# SOZLAMALAR
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = 8451295149
ADMIN_CONTACT = os.getenv("ADMIN_CONTACT", "@rustamovvvll")

# E'lonlar chiqadigan kanal
CHANNEL_ID = os.getenv("CHANNEL_ID", "@Ishbazasi")

# Majburiy Telegram kanal
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@Ishbazasi")

# Instagram — faqat ko'rsatamiz, tekshirmaymiz
INSTAGRAM_USERNAME = "ishbazasi"
INSTAGRAM_URL = "https://instagram.com/ishbazasi"

# Karta ma'lumoti Railway Variables'dan olinadi
CARD_NUMBER = os.getenv("CARD_NUMBER", "")
CARD_HOLDER = os.getenv("CARD_HOLDER", "Diyorbek Rustamov")

DB_PATH = os.getenv("DB_PATH", "bot.db")

# Chek yuborish uchun ajratilgan vaqt
RECEIPT_MINUTES = 10

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

log = logging.getLogger(__name__)

bot = Bot(TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ============================================================
# DATABASE
# ============================================================

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.now(timezone.utc)


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
                user_id INTEGER NOT NULL,

                title TEXT,
                location TEXT NOT NULL,
                profession TEXT NOT NULL,
                conditions TEXT NOT NULL,
                contact TEXT NOT NULL,

                image_file_id TEXT,

                days INTEGER NOT NULL,
                price INTEGER NOT NULL,
                lifetime INTEGER DEFAULT 0,

                status TEXT DEFAULT 'pending',

                channel_message_id INTEGER,
                expires_at TEXT,
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
            """
        )


# ============================================================
# USERLAR
# ============================================================

def register_user(user: types.User):
    t = now().isoformat()

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
                t,
                t,
            ),
        )


def get_user_db_id(telegram_id):
    with db() as c:
        row = c.execute(
            "SELECT id FROM users WHERE telegram_id=?",
            (telegram_id,),
        ).fetchone()

        return row["id"] if row else None


def get_ad(ad_id):
    with db() as c:
        return c.execute(
            "SELECT * FROM ads WHERE id=?",
            (ad_id,),
        ).fetchone()


def get_payment(payment_id):
    with db() as c:
        return c.execute(
            "SELECT * FROM payments WHERE id=?",
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


def update_ad_status(ad_id, status):
    with db() as c:
        c.execute(
            "UPDATE ads SET status=? WHERE id=?",
            (status, ad_id),
        )


def update_payment_status(payment_id, status):
    with db() as c:
        c.execute(
            "UPDATE payments SET status=? WHERE id=?",
            (status, payment_id),
        )


# ============================================================
# TUGMALAR
# ============================================================

def main_menu():
    return RK(
        keyboard=[
            [KB(text="🚀 E'lon berish")],
            [KB(text="📋 Mening e'lonlarim")],
            [KB(text="📞 Admin bilan bog'lanish")],
        ],
        resize_keyboard=True,
    )


def subscription_keyboard():
    return IK(
        inline_keyboard=[
            [
                B(
                    text="📢 Telegram kanalga obuna bo'lish",
                    url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}",
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
                    text="✅ Tekshirish",
                    callback_data="check_subscription",
                )
            ],
        ]
    )


def admin_keyboard():
    return IK(
        inline_keyboard=[
            [
                B(text="📊 Statistika", callback_data="admin_stats"),
                B(text="📢 E'lonlar", callback_data="admin_ads"),
            ],
            [
                B(text="💳 To'lovlar", callback_data="admin_payments"),
                B(text="👥 Foydalanuvchilar", callback_data="admin_users"),
            ],
            [
                B(text="📣 Hammaga xabar", callback_data="admin_broadcast"),
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


# ============================================================
# OBUNANI TEKSHIRISH
# ============================================================

async def telegram_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(
            chat_id=REQUIRED_CHANNEL,
            user_id=user_id,
        )

        return member.status not in ("left", "kicked")

    except Exception as e:
        log.error("Obuna tekshirish xatosi: %s", e)
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


class RejectForm(StatesGroup):
    reason = State()


class BroadcastForm(StatesGroup):
    message = State()


# ============================================================
# TARIFLAR
# ============================================================

TARIFFS = {
    1: {
        "days": 1,
        "price": 0,
        "name": "1 kun — BIRINCHI MARTA BEPUL",
        "lifetime": 0,
    },

    2: {
        "days": 2,
        "price": 10000,
        "name": "2 kun — 10 000 so'm",
        "lifetime": 0,
    },

    3: {
        "days": 3,
        "price": 15000,
        "name": "3 kun — 15 000 so'm",
        "lifetime": 0,
    },

    4: {
        "days": 0,
        "price": 30000,
        "name": "♾ Umrbod — 30 000 so'm",
        "lifetime": 1,
    },
}


def tariff_keyboard():
    return IK(
        inline_keyboard=[
            [
                B(
                    text="🆓 1 kun — 1 MARTA BEPUL",
                    callback_data="tariff_1",
                )
            ],
            [
                B(
                    text="🟡 2 kun — 10 000 so'm",
                    callback_data="tariff_2",
                )
            ],
            [
                B(
                    text="🟠 3 kun — 15 000 so'm",
                    callback_data="tariff_3",
                )
            ],
            [
                B(
                    text="♾ Umrbod — 30 000 so'm",
                    callback_data="tariff_4",
                )
            ],
        ]
    )


def has_used_free_ad(telegram_id):
    with db() as c:
        row = c.execute(
            """
            SELECT COUNT(*) AS n
            FROM ads
            WHERE telegram_id=?
            AND days=1
            AND price=0
            AND status NOT IN ('cancelled', 'rejected')
            """,
            (telegram_id,),
        ).fetchone()

        return row["n"] > 0


# ============================================================
# START
# ============================================================

@dp.message(Command("start"))
async def start(message: types.Message):
    register_user(message.from_user)

    if not await telegram_subscribed(message.from_user.id):
        await message.answer(
            """
👋 Assalomu alaykum!

🚀 <b>Ish Bazasi</b> botiga xush kelibsiz.

Botdan foydalanish uchun:

📢 Telegram kanalimizga obuna bo'ling — <b>SHART</b>

📸 Instagram sahifamizga obuna bo'ling — <b>SHART</b>

Instagram obunasi bot tomonidan tekshirilmaydi.
""",
            reply_markup=subscription_keyboard(),
            parse_mode="HTML",
        )
        return

    await message.answer(
        """
🎉 <b>Xush kelibsiz!</b>

🚀 Ishchi kerak bo'lsa, shu bot orqali e'lon bering.

📢 Tasdiqlangan e'lonlar kanalga chiqariladi.
⏰ Tanlangan muddat tugagach avtomatik o'chiriladi.
""",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "check_subscription")
async def check_subscription(callback: types.CallbackQuery):

    if await telegram_subscribed(callback.from_user.id):

        await callback.answer(
            "✅ Telegram obunangiz tasdiqlandi!",
            show_alert=True,
        )

        await callback.message.answer(
            "🚀 Endi botdan foydalanishingiz mumkin.",
            reply_markup=main_menu(),
        )

    else:

        await callback.answer(
            "❌ Avval Telegram kanalga obuna bo'ling!",
            show_alert=True,
        )


# ============================================================
# ADMIN CONTACT
# ============================================================

@dp.message(F.text == "📞 Admin bilan bog'lanish")
async def admin_contact(message: types.Message):

    await message.answer(
        f"""
📞 <b>Admin bilan bog'lanish</b>

👨‍💼 Admin: {ADMIN_CONTACT}

Savol yoki muammo bo'lsa, admin bilan bog'lanishingiz mumkin.
""",
        parse_mode="HTML",
    )


# ============================================================
# E'LON BOSHLASH
# ============================================================

@dp.message(F.text == "🚀 E'lon berish")
async def start_ad(message: types.Message, state: FSMContext):

    register_user(message.from_user)

    if not await telegram_subscribed(message.from_user.id):

        await message.answer(
            "❌ Avval Telegram kanalga obuna bo'ling.",
            reply_markup=subscription_keyboard(),
        )

        return

    await state.set_state(AdForm.title)

    await message.answer(
        """
📝 <b>E'lon sarlavhasini yozing.</b>

Masalan:
<i>Ofitsiantlar ishga taklif qilinadi</i>
""",
        parse_mode="HTML",
    )


@dp.message(AdForm.title)
async def ad_title(message: types.Message, state: FSMContext):

    await state.update_data(title=message.text.strip())

    await state.set_state(AdForm.location)

    await message.answer(
        "📍 <b>Ish joyi qayerda?</b>\n\nMasalan: Toshkent, Chilonzor",
        parse_mode="HTML",
    )


@dp.message(AdForm.location)
async def ad_location(message: types.Message, state: FSMContext):

    await state.update_data(location=message.text.strip())

    await state.set_state(AdForm.profession)

    await message.answer(
        "💼 <b>Qanday ishchi kerak?</b>\n\nMasalan: Ofitsiant",
        parse_mode="HTML",
    )


@dp.message(AdForm.profession)
async def ad_profession(message: types.Message, state: FSMContext):

    await state.update_data(profession=message.text.strip())

    await state.set_state(AdForm.conditions)

    await message.answer(
        """
📋 <b>Ish haqida batafsil ma'lumot yozing.</b>

Maosh, ish vaqti, talablar va boshqa ma'lumotlarni yozing.
""",
        parse_mode="HTML",
    )


@dp.message(AdForm.conditions)
async def ad_conditions(message: types.Message, state: FSMContext):

    await state.update_data(conditions=message.text.strip())

    await state.set_state(AdForm.contact)

    await message.answer(
        """
📞 <b>Aloqa ma'lumotini yuboring.</b>

Telefon raqami yoki Telegram username.
""",
        parse_mode="HTML",
    )


@dp.message(AdForm.contact)
async def ad_contact(message: types.Message, state: FSMContext):

    await state.update_data(contact=message.text.strip())

    await state.set_state(AdForm.image)

    await message.answer(
        """
🖼 <b>E'lon uchun rasm yuboring.</b>

Ish joyi, kompaniya yoki vakansiyaga mos rasm yuborishingiz mumkin.

Agar rasm bo'lmasa, pastdagi tugmani bosib o'tkazib yuboring.
""",
        reply_markup=image_skip_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# RASM
# ============================================================

@dp.message(AdForm.image, F.photo)
async def ad_image(message: types.Message, state: FSMContext):

    photo = message.photo[-1]

    await state.update_data(
        image_file_id=photo.file_id
    )

    await state.set_state(AdForm.tariff)

    await message.answer(
        "💰 <b>E'lon muddatini tanlang:</b>",
        reply_markup=tariff_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(AdForm.image, F.data == "skip_image")
async def skip_image(callback: types.CallbackQuery, state: FSMContext):

    # Rasm berilmasa None qoladi.
    # Kanalga keyin chiroyli fallback reklama matni yuboriladi.

    await state.update_data(
        image_file_id=None
    )

    await state.set_state(AdForm.tariff)

    await callback.message.edit_text(
        "💰 <b>E'lon muddatini tanlang:</b>",
        reply_markup=tariff_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


@dp.message(AdForm.image)
async def wrong_image(message: types.Message):

    await message.answer(
        "🖼 Iltimos, rasm yuboring yoki ⏭ O'tkazib yuborish tugmasini bosing.",
        reply_markup=image_skip_keyboard(),
    )


# ============================================================
# E'LON YARATISH
# ============================================================

def create_ad(telegram_id, data, tariff):

    user_id = get_user_db_id(telegram_id)

    with db() as c:

        cursor = c.execute(
            """
            INSERT INTO ads (
                telegram_id,
                user_id,
                title,
                location,
                profession,
                conditions,
                contact,
                image_file_id,
                days,
                price,
                lifetime,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                telegram_id,
                user_id,
                data.get("title", ""),
                data["location"],
                data["profession"],
                data["conditions"],
                data["contact"],
                data.get("image_file_id"),
                tariff["days"],
                tariff["price"],
                tariff["lifetime"],
                now().isoformat(),
            ),
        )

        return cursor.lastrowid


def create_payment(ad_id, telegram_id, amount):

    expires = now() + timedelta(minutes=RECEIPT_MINUTES)

    with db() as c:

        cursor = c.execute(
            """
            INSERT INTO payments (
                ad_id,
                telegram_id,
                amount,
                status,
                expires_at,
                created_at
            )
            VALUES (?, ?, ?, 'waiting', ?, ?)
            """,
            (
                ad_id,
                telegram_id,
                amount,
                expires.isoformat(),
                now().isoformat(),
            ),
        )

        return cursor.lastrowid


# ============================================================
# TARIF TANLASH
# ============================================================

@dp.callback_query(
    AdForm.tariff,
    F.data.regexp(r"^tariff_[1-4]$")
)
async def choose_tariff(
    callback: types.CallbackQuery,
    state: FSMContext,
):

    tariff_id = int(callback.data.split("_")[1])

    tariff = TARIFFS[tariff_id]

    data = await state.get_data()

    # 1 kunlik bepul faqat birinchi marta
    if tariff_id == 1 and has_used_free_ad(callback.from_user.id):

        await callback.answer(
            "❌ Siz 1 kunlik bepul e'lon imkoniyatidan foydalanib bo'lgansiz.",
            show_alert=True,
        )

        return

    ad_id = create_ad(
        callback.from_user.id,
        data,
        tariff,
    )

    # BEPUL
    if tariff["price"] == 0:

        await state.clear()

        await send_ad_to_admin(ad_id)

        await callback.message.edit_text(
            """
✅ <b>E'lon tayyor!</b>

👨‍💼 E'lon admin tasdig'iga yuborildi.

Tasdiqlangandan keyin avtomatik kanalga chiqariladi.
""",
            parse_mode="HTML",
        )

        await callback.answer()
        return

    # PULLIK
    payment_id = create_payment(
        ad_id,
        callback.from_user.id,
        tariff["price"],
    )

    await state.update_data(
        ad_id=ad_id,
        payment_id=payment_id,
    )

    await state.set_state(AdForm.receipt)

    card = CARD_NUMBER or "KARTA RAQAMI RAILWAY VARIABLES'DA KIRITILADI"

    if tariff["lifetime"]:
        duration_text = "♾ <b>UMRBOD</b>"
    else:
        duration_text = f"⏰ <b>{tariff['days']} kun</b>"

    await callback.message.edit_text(
        f"""
💳 <b>TO'LOV</b>

📦 Tarif: {tariff['name']}
{duration_text}

💰 <b>Summa: {tariff['price']:,} so'm</b>

💳 Karta:
<code>{card}</code>

👤 Karta egasi:
<b>{CARD_HOLDER}</b>

To'lovni amalga oshirgach:

👇 <b>“💳 To'lov qildim”</b> tugmasini bosing.
""",
        reply_markup=IK(
            inline_keyboard=[
                [
                    B(
                        text="💳 To'lov qildim",
                        callback_data=f"paid_{payment_id}",
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

@dp.callback_query(F.data.regexp(r"^paid_\d+$"))
async def paid(
    callback: types.CallbackQuery,
    state: FSMContext,
):

    payment_id = int(callback.data.split("_")[1])

    payment = get_payment(payment_id)

    if not payment:

        await callback.answer(
            "❌ To'lov topilmadi.",
            show_alert=True,
        )

        return

    if payment["telegram_id"] != callback.from_user.id:

        await callback.answer(
            "❌ Bu to'lov sizga tegishli emas.",
            show_alert=True,
        )

        return

    if payment["status"] != "waiting":

        await callback.answer(
            "❌ Bu to'lov allaqachon yuborilgan.",
            show_alert=True,
        )

        return

    expires = datetime.fromisoformat(
        payment["expires_at"]
    )

    if now() > expires:

        update_payment_status(
            payment_id,
            "expired",
        )

        update_ad_status(
            payment["ad_id"],
            "cancelled",
        )

        await state.clear()

        await callback.message.edit_text(
            "❌ Chek yuborish vaqti tugagan. Iltimos, e'lonni qaytadan yarating."
        )

        return

    await callback.message.answer(
        """
📸 <b>Endi to'lov chekini yuboring.</b>

Chekni RASM ko'rinishida yuboring.

⏰ Chekni 10 daqiqa ichida yuboring.
""",
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# CHEK QABUL QILISH
# ============================================================

@dp.message(AdForm.receipt, F.photo)
async def receive_receipt(
    message: types.Message,
    state: FSMContext,
):

    data = await state.get_data()

    payment_id = data.get("payment_id")

    payment = get_payment(payment_id)

    if not payment:

        await message.answer(
            "❌ To'lov topilmadi. E'lonni qaytadan boshlang."
        )

        await state.clear()
        return

    expires = datetime.fromisoformat(
        payment["expires_at"]
    )

    if now() > expires:

        update_payment_status(
            payment_id,
            "expired",
        )

        update_ad_status(
            payment["ad_id"],
            "cancelled",
        )

        await state.clear()

        await message.answer(
            "❌ Chek yuborish vaqti tugagan."
        )

        return

    receipt_file_id = message.photo[-1].file_id

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

👨‍💼 Admin tekshiradi.

Tasdiqlangandan keyin e'loningiz kanalga avtomatik chiqariladi.
""",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )


@dp.message(AdForm.receipt)
async def receipt_not_photo(message: types.Message):

    await message.answer(
        "📸 Iltimos, to'lov chekini rasm qilib yuboring."
    )


# ============================================================
# ADMINGA E'LON YUBORISH
# ============================================================

async def send_ad_to_admin(ad_id):

    ad = get_ad(ad_id)

    if not ad:
        return

    payment = latest_payment(ad_id)

    username = "username yo'q"

    try:
        user = await bot.get_chat(ad["telegram_id"])

        if user.username:
            username = f"@{user.username}"

    except Exception:
        pass

    tariff_name = (
        "♾ Umrbod"
        if ad["lifetime"]
        else f"{ad['days']} kun"
    )

    text = f"""
📥 <b>YANGI E'LON</b>

🆔 E'lon ID: <code>#{ad['id']}</code>

👤 Foydalanuvchi: {username}
🆔 Telegram ID: <code>{ad['telegram_id']}</code>

📝 <b>Sarlavha:</b>
{ad['title']}

📍 <b>Manzil:</b>
{ad['location']}

💼 <b>Ish:</b>
{ad['profession']}

📋 <b>Batafsil:</b>
{ad['conditions']}

📞 <b>Aloqa:</b>
{ad['contact']}

⏰ <b>Tarif:</b> {tariff_name}
💰 <b>Summa:</b> {ad['price']:,} so'm
"""

    keyboard = IK(
        inline_keyboard=[
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
        ]
    )

    if payment and payment["receipt_file_id"]:

        await bot.send_photo(
            ADMIN_ID,
            payment["receipt_file_id"],
            caption="💳 <b>TO'LOV CHEKI</b>\n\n" + text,
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
# ADMIN TASDIQLASH
# ============================================================

@dp.callback_query(F.data.regexp(r"^approve_\d+$"))
async def approve_ad(callback: types.CallbackQuery):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Sizda ruxsat yo'q.",
            show_alert=True,
        )

        return

    ad_id = int(
        callback.data.split("_")[1]
    )

    ad = get_ad(ad_id)

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

    payment = latest_payment(ad_id)

    # Pullik e'lon uchun chek shart
    if ad["price"] > 0:

        if not payment or payment["status"] != "receipt_received":

            await callback.answer(
                "❌ To'lov cheki hali kelmagan.",
                show_alert=True,
            )

            return

        update_payment_status(
            payment["id"],
            "approved",
        )

    # Kanalga chiqarish
    channel_text = f"""
🟢 <b>{ad['title']}</b>

📍 <b>Manzil:</b> {ad['location']}

💼 <b>Ish:</b> {ad['profession']}

💰 <b>Ma'lumot:</b>
{ad['conditions']}

📞 <b>Aloqa:</b> {ad['contact']}

🆔 E'lon: <code>#{ad['id']}</code>
"""

    if ad["lifetime"]:

        channel_text += "\n♾ <b>Amal qilish muddati: UMRBOD</b>"

    else:

        channel_text += (
            f"\n⏰ <b>Amal qilish muddati: "
            f"{ad['days']} kun</b>"
        )

    try:

        # Foydalanuvchi rasm bergan bo'lsa
        if ad["image_file_id"]:

            sent = await bot.send_photo(
                CHANNEL_ID,
                ad["image_file_id"],
                caption=channel_text,
                parse_mode="HTML",
            )

        else:

            # Rasm berilmasa, bizning standart reklama
            # kartochkamiz o'rniga chiroyli branded matn.
            fallback_text = (
                "📢 <b>ISH BAZASI</b>\n"
                "🔎 Ish topish va ishchi topish uchun qulay platforma\n\n"
                + channel_text
            )

            sent = await bot.send_message(
                CHANNEL_ID,
                fallback_text,
                parse_mode="HTML",
            )

    except Exception as e:

        log.exception("Kanalga chiqarishda xato")

        await callback.answer(
            "❌ Bot kanalga post yubora olmayapti. "
            "Bot kanalga admin ekanini tekshiring.",
            show_alert=True,
        )

        return

    # Muddati
    if ad["lifetime"]:

        expires_at = None

    else:

        expires_at = (
            now() + timedelta(days=ad["days"])
        ).isoformat()

    with db() as c:

        c.execute(
            """
            UPDATE ads

            SET status='published',
                channel_message_id=?,
                expires_at=?

            WHERE id=?
            """,
            (
                sent.message_id,
                expires_at,
                ad_id,
            ),
        )

    # Adminga xabar
    try:

        if callback.message.photo:

            await callback.message.edit_caption(
                caption="✅ <b>TASDIQLANDI</b>\n\n"
                        "E'lon kanalga chiqarildi.",
                parse_mode="HTML",
            )

        else:

            await callback.message.edit_text(
                "✅ <b>TASDIQLANDI</b>\n\n"
                "E'lon kanalga chiqarildi.",
                parse_mode="HTML",
            )

    except Exception:
        pass

    # Foydalanuvchiga xabar
    try:

        await bot.send_message(
            ad["telegram_id"],
            f"""
🎉 <b>E'loningiz tasdiqlandi!</b>

🆔 E'lon: #{ad_id}

📢 E'lon kanalga chiqarildi.

Rahmat! ❤️
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

@dp.callback_query(F.data.regexp(r"^reject_\d+$"))
async def reject_ad(
    callback: types.CallbackQuery,
    state: FSMContext,
):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ Sizda ruxsat yo'q.",
            show_alert=True,
        )

        return

    ad_id = int(
        callback.data.split("_")[1]
    )

    ad = get_ad(ad_id)

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

    await state.update_data(
        reject_ad_id=ad_id
    )

    await state.set_state(
        RejectForm.reason
    )

    await callback.message.answer(
        f"""
❌ <b>#{ad_id} e'lonni rad etish</b>

Rad etish sababini yozing.

Masalan:
<i>To'lov cheki tasdiqlanmadi.</i>
""",
        parse_mode="HTML",
    )

    await callback.answer()


@dp.message(RejectForm.reason)
async def reject_reason(
    message: types.Message,
    state: FSMContext,
):

    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()

    ad_id = data.get("reject_ad_id")

    reason = message.text.strip()

    ad = get_ad(ad_id)

    if not ad:

        await state.clear()

        await message.answer(
            "❌ E'lon topilmadi."
        )

        return

    update_ad_status(
        ad_id,
        "rejected",
    )

    payment = latest_payment(ad_id)

    if payment:

        update_payment_status(
            payment["id"],
            "rejected",
        )

    try:

        await bot.send_message(
            ad["telegram_id"],
            f"""
❌ <b>E'loningiz rad etildi.</b>

🆔 E'lon: #{ad_id}

📋 <b>Sabab:</b>
{reason}

Savollar bo'lsa:
{ADMIN_CONTACT}
""",
            parse_mode="HTML",
        )

    except Exception:
        pass

    await state.clear()

    await message.answer(
        f"❌ #{ad_id} e'lon rad etildi.\n\nSabab foydalanuvchiga yuborildi."
    )


# ============================================================
# MENING E'LONLARIM
# ============================================================

@dp.message(F.text == "📋 Mening e'lonlarim")
async def my_ads(message: types.Message):

    with db() as c:

        rows = c.execute(
            """
            SELECT *
            FROM ads
            WHERE telegram_id=?
            ORDER BY id DESC
            LIMIT 20
            """,
            (message.from_user.id,),
        ).fetchall()

    if not rows:

        await message.answer(
            "📋 Sizda hozircha e'lonlar yo'q."
        )

        return

    status_names = {
        "pending": "⏳ Kutilmoqda",
        "published": "✅ Kanalda",
        "rejected": "❌ Rad etilgan",
        "expired": "⌛ Muddati tugagan",
        "cancelled": "🚫 Bekor qilingan",
        "deleted": "🗑 O'chirilgan",
    }

    text = "📋 <b>MENING E'LONLARIM</b>\n\n"

    for ad in rows:

        status = status_names.get(
            ad["status"],
            ad["status"],
        )

        text += (
            f"🆔 <b>#{ad['id']}</b>\n"
            f"📝 {ad['title']}\n"
            f"📍 {ad['location']}\n"
            f"📌 {status}\n\n"
        )

    await message.answer(
        text,
        parse_mode="HTML",
    )


# ============================================================
# ADMIN PANEL
# ============================================================

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        """
👨‍💼 <b>ISH BAZASI — ADMIN PANEL</b>

Kerakli bo'limni tanlang:
""",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# ADMIN STATISTIKA
# ============================================================

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):

    if callback.from_user.id != ADMIN_ID:
        return

    with db() as c:

        users = c.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        ads = c.execute(
            "SELECT COUNT(*) FROM ads"
        ).fetchone()[0]

        published = c.execute(
            """
            SELECT COUNT(*)
            FROM ads
            WHERE status='published'
            """
        ).fetchone()[0]

        pending = c.execute(
            """
            SELECT COUNT(*)
            FROM ads
            WHERE status='pending'
            """
        ).fetchone()[0]

        rejected = c.execute(
            """
            SELECT COUNT(*)
            FROM ads
            WHERE status='rejected'
            """
        ).fetchone()[0]

        revenue = c.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM payments
            WHERE status='approved'
            """
        ).fetchone()[0]

    await callback.message.edit_text(
        f"""
📊 <b>STATISTIKA</b>

👥 Foydalanuvchilar: <b>{users}</b>

📢 Jami e'lonlar: <b>{ads}</b>

✅ Kanalda: <b>{published}</b>

⏳ Kutilayotgan: <b>{pending}</b>

❌ Rad etilgan: <b>{rejected}</b>

💰 Tushum: <b>{revenue:,} so'm</b>
""",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# ADMIN E'LONLAR
# ============================================================

@dp.callback_query(F.data == "admin_ads")
async def admin_ads(callback: types.CallbackQuery):

    if callback.from_user.id != ADMIN_ID:
        return

    with db() as c:

        rows = c.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM ads
            GROUP BY status
            """
        ).fetchall()

    if not rows:

        text = "📢 Hozircha e'lonlar yo'q."

    else:

        text = "📢 <b>E'LONLAR</b>\n\n"

        for row in rows:

            text += (
                f"• {row['status']}: "
                f"{row['count']} ta\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# ADMIN TO'LOVLAR
# ============================================================

@dp.callback_query(F.data == "admin_payments")
async def admin_payments(callback: types.CallbackQuery):

    if callback.from_user.id != ADMIN_ID:
        return

    with db() as c:

        total = c.execute(
            """
            SELECT COALESCE(SUM(amount),0)
            FROM payments
            WHERE status='approved'
            """
        ).fetchone()[0]

        waiting = c.execute(
            """
            SELECT COUNT(*)
            FROM payments
            WHERE status='receipt_received'
            """
        ).fetchone()[0]

        all_payments = c.execute(
            """
            SELECT COUNT(*)
            FROM payments
            """
        ).fetchone()[0]

    await callback.message.edit_text(
        f"""
💳 <b>TO'LOVLAR</b>

💰 Tasdiqlangan tushum:
<b>{total:,} so'm</b>

📸 Tekshirilayotgan cheklar:
<b>{waiting}</b>

🧾 Jami to'lovlar:
<b>{all_payments}</b>

To'lovlarni tasdiqlash/rad etish
chek kelganida avtomatik admin chatida chiqadi.
""",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# ADMIN FOYDALANUVCHILAR
# ============================================================

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):

    if callback.from_user.id != ADMIN_ID:
        return

    with db() as c:

        total = c.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        active_ads = c.execute(
            """
            SELECT COUNT(*)
            FROM ads
            WHERE status='published'
            """
        ).fetchone()[0]

    await callback.message.edit_text(
        f"""
👥 <b>FOYDALANUVCHILAR</b>

Jami foydalanuvchilar:
<b>{total}</b>

Hozir kanalda turgan e'lonlar:
<b>{active_ads}</b>
""",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# BROADCAST
# ============================================================

@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(
    callback: types.CallbackQuery,
    state: FSMContext,
):

    if callback.from_user.id != ADMIN_ID:
        return

    await state.set_state(
        BroadcastForm.message
    )

    await callback.message.answer(
        """
📣 <b>HAMMAGA XABAR</b>

Yubormoqchi bo'lgan xabaringizni yozing.

Bekor qilish:
<code>/cancel</code>
""",
        parse_mode="HTML",
    )

    await callback.answer()


@dp.message(BroadcastForm.message)
async def broadcast_message(
    message: types.Message,
    state: FSMContext,
):

    if message.from_user.id != ADMIN_ID:
        return

    if message.text == "/cancel":

        await state.clear()

        await message.answer(
            "❌ Bekor qilindi."
        )

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

            await bot.send_message(
                user["telegram_id"],
                message.text,
            )

            success += 1

        except Exception:

            failed += 1

        await asyncio.sleep(0.05)

    await state.clear()

    await message.answer(
        f"""
✅ <b>Xabar yuborildi!</b>

📨 Yetkazildi: {success}

❌ Yetkazilmadi: {failed}
""",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# ============================================================
# CANCEL
# ============================================================

@dp.message(Command("cancel"))
async def cancel(
    message: types.Message,
    state: FSMContext,
):

    await state.clear()

    await message.answer(
        "❌ Amal bekor qilindi.",
        reply_markup=main_menu(),
    )


# ============================================================
# AVTOMATIK MUDDAT NAZORATI
# ============================================================

async def expiration_worker():

    while True:

        try:

            with db() as c:

                expired_ads = c.execute(
                    """
                    SELECT *
                    FROM ads
                    WHERE status='published'
                    AND lifetime=0
                    AND expires_at IS NOT NULL
                    AND expires_at <= ?
                    """,
                    (now().isoformat(),),
                ).fetchall()

            for ad in expired_ads:

                try:

                    if ad["channel_message_id"]:

                        await bot.delete_message(
                            chat_id=CHANNEL_ID,
                            message_id=ad["channel_message_id"],
                        )

                except Exception as e:

                    log.warning(
                        "E'lonni o'chirish xatosi #%s: %s",
                        ad["id"],
                        e,
                    )

                update_ad_status(
                    ad["id"],
                    "expired",
                )

                try:

                    await bot.send_message(
                        ad["telegram_id"],
                        f"""
⌛ <b>E'loningizning muddati tugadi.</b>

🆔 E'lon: #{ad['id']}

E'lon kanaldan avtomatik olib tashlandi.
""",
                        parse_mode="HTML",
                    )

                except Exception:
                    pass

            # Muddati o'tgan to'lovlar
            with db() as c:

                expired_payments = c.execute(
                    """
                    SELECT *
                    FROM payments
                    WHERE status='waiting'
                    AND expires_at <= ?
                    """,
                    (now().isoformat(),),
                ).fetchall()

            for payment in expired_payments:

                update_payment_status(
                    payment["id"],
                    "expired",
                )

                update_ad_status(
                    payment["ad_id"],
                    "cancelled",
                )

        except Exception:

            log.exception(
                "Expiration worker xatosi"
            )

        await asyncio.sleep(30)


# ============================================================
# START BOT
# ============================================================

async def main():

    init_db()

    # Eski webhook bo'lsa olib tashlaydi
    await bot.delete_webhook(
        drop_pending_updates=True
    )

    worker = asyncio.create_task(
        expiration_worker()
    )

    try:

        log.info("Bot ishga tushmoqda...")

        await dp.start_polling(bot)

    finally:

        worker.cancel()

        try:
            await worker
        except asyncio.CancelledError:
            pass

        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
