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
# ISH BAZASI BOT
# aiogram 3.x
#
# ASOSIY QOIDALAR:
# 1) Telegram kanalga majburiy obuna tekshiriladi.
# 2) Instagram tugmasi ko'rsatiladi, lekin Instagram obunasi tekshirilmaydi.
# 3) 1 kunlik bepul tarif har bir foydalanuvchiga faqat 1 marta.
# 4) E'lon uzunligiga limit qo'yilmaydi. Har bir e'lonni admin tasdiqlaydi/rad etadi.
# 5) To'lov -> chek -> admin tekshiruvi -> tasdiq/rad.
# 6) Admin panelda e'lonlarni ko'rish va kanal postini o'chirish mumkin.
# 7) 1/2/3 kunlik e'lonlar muddati tugaganda avtomatik o'chadi.
# 8) Umrbod e'lon avtomatik o'chirilmaydi.
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = 8451295149
ADMIN_CONTACT = os.getenv("ADMIN_CONTACT", "@rustamovvvll")

# E'lonlar chiqadigan kanal.
CHANNEL_ID = os.getenv("CHANNEL_ID", "@Ishbazasi")

# Majburiy Telegram kanal.
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@Ishbazasi")

# Instagram faqat ko'rsatiladi, obunasi bot tomonidan tekshirilmaydi.
INSTAGRAM_USERNAME = "ishbazasi"
INSTAGRAM_URL = "https://instagram.com/ishbazasi"

# Railway Variables.
CARD_NUMBER = os.getenv("CARD_NUMBER", "")
CARD_HOLDER = os.getenv("CARD_HOLDER", "Diyorbek Rustamov")

DB_PATH = os.getenv("DB_PATH", "bot.db")

# Pullik tarif tanlangandan keyin chek yuborish uchun vaqt.
RECEIPT_MINUTES = 10

# Admin e'lonlar ro'yxatida bir sahifada nechta e'lon.
ADMIN_PAGE_SIZE = 8

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi. Railway Variables ga BOT_TOKEN kiriting.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

log = logging.getLogger(__name__)

bot = Bot(TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ============================================================
# YORDAMCHI FUNKSIYALAR
# ============================================================

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.now(timezone.utc)


def esc(value):
    """User yozgan matnni Telegram HTML formatini buzmaydigan qiladi."""
    return html.escape(str(value or ""))


def channel_username():
    value = CHANNEL_ID.strip()
    if value.startswith("@"):
        return value[1:]
    return ""


def channel_url():
    username = channel_username()
    return f"https://t.me/{username}" if username else None


def short_status(status):
    return {
        "pending": "⏳ Kutilmoqda",
        "published": "✅ Kanalda",
        "rejected": "❌ Rad etilgan",
        "expired": "⌛ Muddati tugagan",
        "cancelled": "🚫 Bekor qilingan",
        "deleted": "🗑 O'chirilgan",
    }.get(status, status)


# ============================================================
# DATABASE
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
                    text="📢 Telegram kanalga obuna bo'lish — SHART!",
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
                    text="✅ Obunani tekshirish",
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


def admin_ads_filter_keyboard():
    return IK(
        inline_keyboard=[
            [
                B(text="⏳ Kutilayotgan", callback_data="admin_list_pending_0"),
                B(text="✅ Kanalda", callback_data="admin_list_published_0"),
            ],
            [
                B(text="❌ Rad etilgan", callback_data="admin_list_rejected_0"),
                B(text="⌛ Tugagan", callback_data="admin_list_expired_0"),
            ],
            [
                B(text="🗑 O'chirilgan", callback_data="admin_list_deleted_0"),
            ],
            [
                B(text="⬅️ Admin panel", callback_data="admin_home"),
            ],
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
        log.error("Telegram obuna tekshirish xatosi: %s", e)
        return False


async def ensure_subscription(message: types.Message) -> bool:
    if await telegram_subscribed(message.from_user.id):
        return True

    await message.answer(
        """
❌ <b>Majburiy obuna kerak!</b>

Botdan foydalanish uchun Telegram kanalimizga obuna bo'lishingiz shart.

📢 Telegram kanal — <b>SHART</b>
📸 Instagram — <b>SHART</b>

Instagram obunasi bot tomonidan tekshirilmaydi.
""",
        reply_markup=subscription_keyboard(),
        parse_mode="HTML",
    )
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


def has_used_free_ad(telegram_id):
    """
    Faqat 1 marta bepul.
    Bekor qilingan yoki rad etilgan bepul e'lon qayta bepul olish
    imkonini bermaydi, chunki bepul imkoniyat bir marta ishlatilgan hisoblanadi.
    """
    with db() as c:
        row = c.execute(
            """
            SELECT COUNT(*) AS n
            FROM ads
            WHERE telegram_id=?
              AND days=1
              AND price=0
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

📢 Telegram kanalimizga obuna bo'lish — <b>SHART</b>
📸 Instagram sahifamizga obuna bo'lish — <b>SHART</b>

Instagram obunasi bot tomonidan tekshirilmaydi.

Pastdagi tugmalar orqali obuna bo'ling va
<b>✅ Obunani tekshirish</b>ni bosing.
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

👨‍💼 Har bir e'lon admin tomonidan ko'rib chiqiladi.
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

@dp.message(F.text == "📞 Admin bilan bog'lanish")
async def admin_contact(message: types.Message):
    await message.answer(
        f"""
📞 <b>Admin bilan bog'lanish</b>

👨‍💼 Admin: {esc(ADMIN_CONTACT)}

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

    if not await ensure_subscription(message):
        return

    await state.clear()
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
    text = (message.text or "").strip()

    if not text:
        await message.answer("❌ Sarlavha bo'sh bo'lmasin.")
        return

    await state.update_data(title=text)
    await state.set_state(AdForm.location)

    await message.answer(
        "📍 <b>Ish joyi qayerda?</b>\n\nMasalan: Toshkent, Chilonzor",
        parse_mode="HTML",
    )


@dp.message(AdForm.location)
async def ad_location(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()

    if not text:
        await message.answer("❌ Manzilni yozing.")
        return

    await state.update_data(location=text)
    await state.set_state(AdForm.profession)

    await message.answer(
        "💼 <b>Qanday ishchi kerak?</b>\n\nMasalan: Ofitsiant",
        parse_mode="HTML",
    )


@dp.message(AdForm.profession)
async def ad_profession(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()

    if not text:
        await message.answer("❌ Ish turini yozing.")
        return

    await state.update_data(profession=text)
    await state.set_state(AdForm.conditions)

    await message.answer(
        """
📋 <b>Ish haqida batafsil ma'lumot yozing.</b>

Maosh, ish vaqti, talablar va boshqa ma'lumotlarni yozing.

ℹ️ <b>Maxsus uzunlik limiti yo'q.</b>
Admin e'lonni ko'rib chiqadi va tasdiqlaydi yoki rad etadi.
""",
        parse_mode="HTML",
    )


@dp.message(AdForm.conditions)
async def ad_conditions(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()

    if not text:
        await message.answer("❌ Batafsil ma'lumotni yozing.")
        return

    await state.update_data(conditions=text)
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
    text = (message.text or "").strip()

    if not text:
        await message.answer("❌ Aloqa ma'lumotini yozing.")
        return

    await state.update_data(contact=text)
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

    await state.update_data(image_file_id=photo.file_id)
    await state.set_state(AdForm.tariff)

    await message.answer(
        "💰 <b>E'lon muddatini tanlang:</b>\n\n"
        "🆓 1 kunlik bepul tarif faqat bir marta beriladi.",
        reply_markup=tariff_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(AdForm.image, F.data == "skip_image")
async def skip_image(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(image_file_id=None)
    await state.set_state(AdForm.tariff)

    await callback.message.edit_text(
        "💰 <b>E'lon muddatini tanlang:</b>\n\n"
        "🆓 1 kunlik bepul tarif faqat bir marta beriladi.",
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

    # 1 kunlik bepul faqat birinchi marta.
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

    # ========================================================
    # BEPUL
    # ========================================================

    if tariff["price"] == 0:
        await state.clear()

        await send_ad_to_admin(ad_id)

        await callback.message.edit_text(
            """
✅ <b>E'lon tayyor!</b>

👨‍💼 E'lon admin tasdig'iga yuborildi.

Admin ma'qullasa avtomatik kanalga chiqariladi.
""",
            parse_mode="HTML",
        )

        await callback.answer()
        return

    # ========================================================
    # PULLIK
    # ========================================================

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

📦 Tarif: {esc(tariff['name'])}
{duration_text}

💰 <b>Summa: {tariff['price']:,} so'm</b>

💳 Karta:
<code>{esc(card)}</code>

👤 Karta egasi:
<b>{esc(CARD_HOLDER)}</b>

To'lovni amalga oshirgach:

👇 <b>“💳 To'lov qildim”</b> tugmasini bosing.

⏰ Chekni {RECEIPT_MINUTES} daqiqa ichida yuboring.
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

    if payment["status"] == "receipt_received":
        await callback.answer(
            "⏳ Chekingiz allaqachon yuborilgan. Admin tekshiradi.",
            show_alert=True,
        )
        return

    if payment["status"] != "waiting":
        await callback.answer(
            "❌ Bu to'lov sessiyasi faol emas.",
            show_alert=True,
        )
        return

    expires = datetime.fromisoformat(payment["expires_at"])

    if now() > expires:
        update_payment_status(payment_id, "expired")
        update_ad_status(payment["ad_id"], "cancelled")
        await state.clear()

        await callback.message.edit_text(
            "❌ Chek yuborish vaqti tugagan. Iltimos, e'lonni qaytadan yarating."
        )
        await callback.answer()
        return

    # To'lov jarayoni "paid" bosqichiga o'tadi.
    update_payment_status(payment_id, "paid")

    await state.update_data(
        ad_id=payment["ad_id"],
        payment_id=payment_id,
    )
    await state.set_state(AdForm.receipt)

    await callback.message.answer(
        f"""
📸 <b>Endi to'lov chekini yuboring.</b>

Chekni <b>RASM</b> ko'rinishida yuboring.

⏰ Sizda {RECEIPT_MINUTES} daqiqa bor.
""",
        parse_mode="HTML",
    )

    await callback.answer("✅ To'lov bosqichi qabul qilindi.")


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

    if payment["telegram_id"] != message.from_user.id:
        await message.answer("❌ Bu to'lov sizga tegishli emas.")
        return

    if payment["status"] not in ("paid", "waiting"):
        await message.answer(
            "❌ Bu to'lov sessiyasi faol emas."
        )
        await state.clear()
        return

    expires = datetime.fromisoformat(payment["expires_at"])

    if now() > expires:
        update_payment_status(payment_id, "expired")
        update_ad_status(payment["ad_id"], "cancelled")
        await state.clear()

        await message.answer(
            "❌ Chek yuborish vaqti tugagan. E'lon bekor qilindi."
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

    await send_ad_to_admin(payment["ad_id"])

    await message.answer(
        """
✅ <b>Chek qabul qilindi!</b>

👨‍💼 Admin to'lov va e'lonni tekshiradi.

Tasdiqlangandan keyin e'lon avtomatik kanalga chiqariladi.
""",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )


@dp.message(AdForm.receipt)
async def receipt_not_photo(message: types.Message):
    await message.answer(
        "📸 Iltimos, to'lov chekini <b>rasm</b> qilib yuboring.",
        parse_mode="HTML",
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

👤 Foydalanuvchi: {esc(username)}
🆔 Telegram ID: <code>{ad['telegram_id']}</code>

📝 <b>Sarlavha:</b>
{esc(ad['title'])}

📍 <b>Manzil:</b>
{esc(ad['location'])}

💼 <b>Ish:</b>
{esc(ad['profession'])}

📋 <b>Batafsil:</b>
{esc(ad['conditions'])}

📞 <b>Aloqa:</b>
{esc(ad['contact'])}

⏰ <b>Tarif:</b> {esc(tariff_name)}
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
# KANALGA E'LON CHIQARISH
# ============================================================

def build_channel_text(ad):
    text = f"""
🟢 <b>{esc(ad['title'])}</b>

📍 <b>Manzil:</b> {esc(ad['location'])}

💼 <b>Ish:</b> {esc(ad['profession'])}

📋 <b>Ma'lumot:</b>
{esc(ad['conditions'])}

📞 <b>Aloqa:</b> {esc(ad['contact'])}

🆔 E'lon: <code>#{ad['id']}</code>
"""

    if ad["lifetime"]:
        text += "\n♾ <b>Amal qilish muddati: UMRBOD</b>"
    else:
        text += (
            f"\n⏰ <b>Amal qilish muddati: "
            f"{ad['days']} kun</b>"
        )

    return text


async def publish_ad_to_channel(ad):
    channel_text = build_channel_text(ad)

    if ad["image_file_id"]:
        return await bot.send_photo(
            CHANNEL_ID,
            ad["image_file_id"],
            caption=channel_text,
            parse_mode="HTML",
        )

    fallback_text = (
        "📢 <b>ISH BAZASI</b>\n"
        "🔎 Ish topish va ishchi topish uchun qulay platforma\n\n"
        + channel_text
    )

    return await bot.send_message(
        CHANNEL_ID,
        fallback_text,
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

    ad_id = int(callback.data.split("_")[1])
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

    # Pullik e'lon uchun chek shart.
    if ad["price"] > 0:
        if not payment or payment["status"] != "receipt_received":
            await callback.answer(
                "❌ To'lov cheki hali kelmagan.",
                show_alert=True,
            )
            return

        update_payment_status(payment["id"], "approved")

    try:
        sent = await publish_ad_to_channel(ad)

    except Exception:
        log.exception("Kanalga chiqarishda xato")

        await callback.answer(
            "❌ Bot kanalga post yubora olmayapti. "
            "Bot kanalga admin ekanini va post yuborish/o'chirish huquqlarini tekshiring.",
            show_alert=True,
        )
        return

    # Muddati.
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

    # Admindagi xabarni yangilash.
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
                "✅ <b>TASDIQLANDI</b>\n\n"
                "E'lon kanalga chiqarildi.",
                parse_mode="HTML",
            )
    except Exception:
        pass

    # Foydalanuvchiga xabar.
    try:
        link_text = ""
        url = channel_url()
        if url:
            link_text = f"\n\n🔗 <a href=\"{url}\">Kanalga o'tish</a>"

        await bot.send_message(
            ad["telegram_id"],
            f"""
🎉 <b>E'loningiz tasdiqlandi!</b>

🆔 E'lon: #{ad_id}

📢 E'lon kanalga chiqarildi.{link_text}

Rahmat! ❤️
""",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.answer("✅ E'lon tasdiqlandi!")


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

    ad_id = int(callback.data.split("_")[1])
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

    await state.update_data(reject_ad_id=ad_id)
    await state.set_state(RejectForm.reason)

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

    reason = (message.text or "").strip()

    if not reason:
        await message.answer("❌ Rad etish sababini yozing.")
        return

    data = await state.get_data()
    ad_id = data.get("reject_ad_id")

    ad = get_ad(ad_id)

    if not ad:
        await state.clear()
        await message.answer("❌ E'lon topilmadi.")
        return

    update_ad_status(ad_id, "rejected")

    payment = latest_payment(ad_id)

    if payment and payment["status"] in (
        "waiting",
        "paid",
        "receipt_received",
    ):
        update_payment_status(payment["id"], "rejected")

    try:
        await bot.send_message(
            ad["telegram_id"],
            f"""
❌ <b>E'loningiz rad etildi.</b>

🆔 E'lon: #{ad_id}

📋 <b>Sabab:</b>
{esc(reason)}

Savollar bo'lsa:
{esc(ADMIN_CONTACT)}
""",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await state.clear()

    await message.answer(
        f"❌ #{ad_id} e'lon rad etildi.\n\n"
        "Sabab foydalanuvchiga yuborildi.",
        reply_markup=main_menu(),
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

    text = "📋 <b>MENING E'LONLARIM</b>\n\n"

    for ad in rows:
        text += (
            f"🆔 <b>#{ad['id']}</b>\n"
            f"📝 {esc(ad['title'])}\n"
            f"📍 {esc(ad['location'])}\n"
            f"📌 {short_status(ad['status'])}\n\n"
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


@dp.callback_query(F.data == "admin_home")
async def admin_home(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    await callback.message.edit_text(
        """
👨‍💼 <b>ISH BAZASI — ADMIN PANEL</b>

Kerakli bo'limni tanlang:
""",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


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
            "SELECT COUNT(*) FROM ads WHERE status='published'"
        ).fetchone()[0]

        pending = c.execute(
            "SELECT COUNT(*) FROM ads WHERE status='pending'"
        ).fetchone()[0]

        rejected = c.execute(
            "SELECT COUNT(*) FROM ads WHERE status='rejected'"
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

💰 Tasdiqlangan tushum: <b>{revenue:,} so'm</b>
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

    await callback.message.edit_text(
        "📢 <b>E'LONLAR BOSHQARUVI</b>\n\nBo'limni tanlang:",
        reply_markup=admin_ads_filter_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data.regexp(r"^admin_list_(pending|published|rejected|expired|deleted)_\d+$")
)
async def admin_list_ads(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    parts = callback.data.split("_")
    status = parts[2]
    page = int(parts[3])

    offset = page * ADMIN_PAGE_SIZE

    with db() as c:
        rows = c.execute(
            """
            SELECT *
            FROM ads
            WHERE status=?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (status, ADMIN_PAGE_SIZE, offset),
        ).fetchall()

        total = c.execute(
            """
            SELECT COUNT(*)
            FROM ads
            WHERE status=?
            """,
            (status,),
        ).fetchone()[0]

    if not rows:
        await callback.message.edit_text(
            f"📢 <b>{short_status(status)}</b>\n\n"
            "Hozircha e'lon yo'q.",
            reply_markup=admin_ads_filter_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    text = (
        f"📢 <b>{short_status(status)}</b>\n\n"
        f"Jami: <b>{total}</b>\n\n"
    )

    buttons = []

    for ad in rows:
        text += (
            f"🆔 <b>#{ad['id']}</b> — "
            f"{esc(ad['title'])}\n"
            f"📍 {esc(ad['location'])}\n\n"
        )

        if status == "published":
            buttons.append(
                [
                    B(
                        text=f"🗑 #{ad['id']} o'chirish",
                        callback_data=f"admin_delete_ad_{ad['id']}",
                    )
                ]
            )

    nav = []

    if page > 0:
        nav.append(
            B(
                text="⬅️ Oldingi",
                callback_data=f"admin_list_{status}_{page - 1}",
            )
        )

    if offset + len(rows) < total:
        nav.append(
            B(
                text="Keyingi ➡️",
                callback_data=f"admin_list_{status}_{page + 1}",
            )
        )

    if nav:
        buttons.append(nav)

    buttons.append(
        [
            B(
                text="⬅️ E'lonlar bo'limi",
                callback_data="admin_ads",
            )
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=IK(inline_keyboard=buttons),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# ADMIN E'LONNI KANALDAN O'CHIRISH
# ============================================================

@dp.callback_query(F.data.regexp(r"^admin_delete_ad_\d+$"))
async def admin_delete_ad(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "❌ Sizda ruxsat yo'q.",
            show_alert=True,
        )
        return

    ad_id = int(callback.data.split("_")[-1])
    ad = get_ad(ad_id)

    if not ad:
        await callback.answer(
            "❌ E'lon topilmadi.",
            show_alert=True,
        )
        return

    if ad["status"] != "published":
        await callback.answer(
            "⚠️ Bu e'lon hozir kanal statusida emas.",
            show_alert=True,
        )
        return

    delete_error = None

    try:
        if ad["channel_message_id"]:
            await bot.delete_message(
                chat_id=CHANNEL_ID,
                message_id=ad["channel_message_id"],
            )
    except Exception as e:
        delete_error = str(e)
        log.warning(
            "Admin kanal postini o'chirishda xato #%s: %s",
            ad_id,
            e,
        )

    # Telegramda o'chirish muvaffaqiyatli bo'lmasa ham,
    # statusni o'zboshimchalik bilan deleted qilmaymiz.
    if delete_error:
        await callback.answer(
            "❌ Kanal postini o'chirib bo'lmadi. Botning admin huquqlarini tekshiring.",
            show_alert=True,
        )
        return

    update_ad_status(ad_id, "deleted")

    try:
        await bot.send_message(
            ad["telegram_id"],
            f"""
🗑 <b>E'loningiz kanaldan olib tashlandi.</b>

🆔 E'lon: #{ad_id}

Admin tomonidan o'chirildi.
""",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.answer(
        "✅ E'lon kanaldan o'chirildi.",
        show_alert=True,
    )

    # Ro'yxatni yangilash.
    with db() as c:
        rows = c.execute(
            """
            SELECT *
            FROM ads
            WHERE status='published'
            ORDER BY id DESC
            LIMIT ?
            """,
            (ADMIN_PAGE_SIZE,),
        ).fetchall()

        total = c.execute(
            "SELECT COUNT(*) FROM ads WHERE status='published'"
        ).fetchone()[0]

    if not rows:
        await callback.message.edit_text(
            "📢 <b>✅ Kanalda</b>\n\nHozircha e'lon yo'q.",
            reply_markup=admin_ads_filter_keyboard(),
            parse_mode="HTML",
        )
        return

    text = f"📢 <b>✅ Kanalda</b>\n\nJami: <b>{total}</b>\n\n"
    buttons = []

    for item in rows:
        text += (
            f"🆔 <b>#{item['id']}</b> — {esc(item['title'])}\n"
            f"📍 {esc(item['location'])}\n\n"
        )
        buttons.append(
            [
                B(
                    text=f"🗑 #{item['id']} o'chirish",
                    callback_data=f"admin_delete_ad_{item['id']}",
                )
            ]
        )

    buttons.append(
        [B(text="⬅️ E'lonlar bo'limi", callback_data="admin_ads")]
    )

    await callback.message.edit_text(
        text,
        reply_markup=IK(inline_keyboard=buttons),
        parse_mode="HTML",
    )


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
            WHERE status IN ('paid', 'receipt_received')
            """
        ).fetchone()[0]

        all_payments = c.execute(
            "SELECT COUNT(*) FROM payments"
        ).fetchone()[0]

        approved = c.execute(
            "SELECT COUNT(*) FROM payments WHERE status='approved'"
        ).fetchone()[0]

        rejected = c.execute(
            "SELECT COUNT(*) FROM payments WHERE status='rejected'"
        ).fetchone()[0]

        expired = c.execute(
            "SELECT COUNT(*) FROM payments WHERE status='expired'"
        ).fetchone()[0]

    await callback.message.edit_text(
        f"""
💳 <b>TO'LOVLAR</b>

💰 Tasdiqlangan tushum:
<b>{total:,} so'm</b>

📸 Tekshirilayotgan:
<b>{waiting}</b>

✅ Tasdiqlangan to'lovlar:
<b>{approved}</b>

❌ Rad etilgan:
<b>{rejected}</b>

⌛ Muddati tugagan:
<b>{expired}</b>

🧾 Jami to'lovlar:
<b>{all_payments}</b>

To'lov cheki kelganda admin chatida
avtomatik tekshirish uchun chiqadi.
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

        blocked = c.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE blocked=1
            """
        ).fetchone()[0]

    await callback.message.edit_text(
        f"""
👥 <b>FOYDALANUVCHILAR</b>

Jami foydalanuvchilar:
<b>{total}</b>

Hozir kanalda turgan e'lonlar:
<b>{active_ads}</b>

🚫 Bloklangan foydalanuvchilar:
<b>{blocked}</b>
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

    await state.set_state(BroadcastForm.message)

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
        await message.answer("❌ Bekor qilindi.")
        return

    text_to_send = message.text or ""

    if not text_to_send:
        await message.answer(
            "❌ Faqat matnli xabar yuboring yoki /cancel bosing."
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
                text_to_send,
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
            # ------------------------------------------------
            # Muddati tugagan e'lonlar
            # ------------------------------------------------
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
                        "E'lonni avtomatik o'chirish xatosi #%s: %s",
                        ad["id"],
                        e,
                    )

                update_ad_status(ad["id"], "expired")

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

            # ------------------------------------------------
            # Muddati o'tgan to'lovlar
            # waiting va paid holatlari.
            # receipt_received esa chek kelgan hisoblanadi
            # va admin uni ko'rib chiqadi.
            # ------------------------------------------------
            with db() as c:
                expired_payments = c.execute(
                    """
                    SELECT *
                    FROM payments
                    WHERE status IN ('waiting', 'paid')
                      AND expires_at <= ?
                    """,
                    (now().isoformat(),),
                ).fetchall()

            for payment in expired_payments:
                update_payment_status(
                    payment["id"],
                    "expired",
                )

                ad = get_ad(payment["ad_id"])

                if ad and ad["status"] == "pending":
                    update_ad_status(
                        payment["ad_id"],
                        "cancelled",
                    )

                try:
                    await bot.send_message(
                        payment["telegram_id"],
                        f"""
⌛ <b>To'lov vaqti tugadi.</b>

🆔 E'lon: #{payment['ad_id']}

Chek o'z vaqtida yuborilmagani uchun
e'lon bekor qilindi.
""",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        except Exception:
            log.exception("Expiration worker xatosi")

        await asyncio.sleep(30)


# ============================================================
# START BOT
# ============================================================

async def main():
    init_db()

    # Eski webhook bo'lsa olib tashlaydi.
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
