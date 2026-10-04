import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

# --- SOZLAMALAR ---
TOKEN = "8974822891:AAHxBHtgefeSjS5xMVhFvUch4ajUS7mjNQQ"  # BotFather tokeningiz
ADMIN_ID = 8451295149                                    # Sizning ID raqamingiz
CHANNEL_ID = "@Ishbazasi"                                # E'lonlar boradigan kanal
REQUIRED_CHANNELS = ["@Ishbazasi"]                       # Majburiy obuna kanali
ADMIN_CONTACT = "@rustamovvvll"                          # Sizning username'ingiz

# --- KARTA MA'LUMOTLARI ---
CARD_NUMBER = "4198130044564523"
CARD_HOLDER = "Rustamov Diyorbek"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

USERS_DB = set()


class AdForm(StatesGroup):
  location = State()
  profession = State()
  conditions = State()
  contact = State()
  duration = State()
  waiting_for_receipt = State()


async def check_subscriptions(user_id: int) -> bool:
  for channel in REQUIRED_CHANNELS:
    try:
      member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
      if member.status in ["left", "kicked"]:
        return False
    except Exception:
      return False
  return True


def get_sub_keyboard():
  keyboard = []
  for ch in REQUIRED_CHANNELS:
    keyboard.append([InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{ch.lstrip('@')}")])
  keyboard.append([InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")])
  return InlineKeyboardMarkup(inline_keyboard=keyboard)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
  USERS_DB.add(message.from_user.id)
  if not await check_subscriptions(message.from_user.id):
    await message.answer(
        "Assalomu alaykum! Botdan foydalanish uchun avval quyidagi kanalimizga obuna bo'ling:",
        reply_markup=get_sub_keyboard(),
    )
    return
  await show_main_menu(message)


@dp.message(F.text.lower().in_(["salom", "assalomu alaykum"]))
async def greeting(message: types.Message):
  await cmd_start(message)


async def show_main_menu(message: types.Message):
  keyboard = ReplyKeyboardMarkup(
      keyboard=[
          [KeyboardButton(text="🚀 E'lon berish (Ishchi kerak)")],
          [KeyboardButton(text="📞 Admin bilan bog'lanish")],
      ],
      resize_keyboard=True,
  )
  await message.answer("Xush kelibsiz! Kerakli tugmani tanlang:", reply_markup=keyboard)


@dp.callback_query(F.data == "check_sub")
async def process_check_sub(callback: types.CallbackQuery):
  if await check_subscriptions(callback.from_user.id):
    await callback.message.delete()
    await show_main_menu(callback.message)
  else:
    await callback.answer("Siz hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)


@dp.message(F.text == "📞 Admin bilan bog'lanish")
async def contact_admin(message: types.Message):
  await message.answer(f"Agar botda biron kamchilik yoki savol bo'lsa, adminga yozing: {ADMIN_CONTACT}")


@dp.message(F.text == "🚀 E'lon berish (Ishchi kerak)")
async def start_ad(message: types.Message, state: FSMContext):
  if not await check_subscriptions(message.from_user.id):
    await message.answer("Avval kanalga obuna bo'ling!", reply_markup=get_sub_keyboard())
    return
  await state.set_state(AdForm.location)
  await message.answer("📍 Ish joyi qayerda? (Masalan: Buxoro shahar, Markaziy bozor):")


@dp.message(AdForm.location)
async def process_location(message: types.Message, state: FSMContext):
  await state.update_data(location=message.text)
  await state.set_state(AdForm.profession)
  await message.answer("🛠 Qanday mutaxassis / ishchi kerak? (Masalan: Ofitsiant, Novvoy):")


@dp.message(AdForm.profession)
async def process_profession(message: types.Message, state: FSMContext):
  await state.update_data(profession=message.text)
  await state.set_state(AdForm.conditions)
  await message.answer("📋 Talablar va shartlar qanday? (Ish vaqti, maosh va hokazo):")


@dp.message(AdForm.conditions)
async def process_conditions(message: types.Message, state: FSMContext):
  await state.update_data(conditions=message.text)
  await state.set_state(AdForm.contact)
  await message.answer("📞 Aloqa uchun telefon raqamingiz yoki Username'ingiz:")


@dp.message(AdForm.contact)
async def process_contact(message: types.Message, state: FSMContext):
  await state.update_data(contact=message.text)
  await state.set_state(AdForm.duration)

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🟢 1 kunlik — Bepul", callback_data="dur_1")],
          [InlineKeyboardButton(text="🟡 2 kunlik — 15 000 so'm", callback_data="dur_2")],
          [InlineKeyboardButton(text="🟠 3 kunlik — 30 000 so'm", callback_data="dur_3")],
          [InlineKeyboardButton(text="⭐ 1 haftalik VIP — 45 000 so'm", callback_data="dur_7")],
      ]
  )
  await message.answer("⏱ E'lon muddatini tanlang:", reply_markup=keyboard)


@dp.callback_query(AdForm.duration, F.data.startswith("dur_"))
async def process_duration(callback: types.CallbackQuery, state: FSMContext):
  days = int(callback.data.split("_")[1])
  await state.update_data(days=days)

  if days == 1:
    # Bepul tarif - to'g'ridan to'g'ri adminga yuboramiz
    data = await state.get_data()
    await state.clear()
    await send_ad_to_admin(callback.bot, callback.from_user.id, data, None, 1)
    await callback.message.edit_text("✅ E'loningiz bepul tarifat asosida adminga yuborildi!")
  else:
    # Pullik tarif - karta ma'lumotlarini chiqaramiz
    prices = {2: "15 000 so'm", 3: "30 000 so'm", 7: "45 000 so'm"}
    text = (
        f"💳 **To'lov qilish uchun ma'lumotlar:**\n\n"
        f"Karta raqami: `{CARD_NUMBER}`\n"
        f"Karta egasi: {CARD_HOLDER}\n"
        f"Summa: {prices[days]}\n\n"
        f"Pulni o'tkazib, quyidagi tugmani bosing va chek (skrinshot) yuboring."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💳 To'lov qildim", callback_data="pay_done")]]
    )
    await state.set_state(AdForm.waiting_for_receipt)
    await callback.message.edit_text(text, reply_markup=kb)


@dp.callback_query(AdForm.waiting_for_receipt, F.data == "pay_done")
async def pay_done_clicked(callback: types.CallbackQuery, state: FSMContext):
  await callback.message.answer(
      "📸 Iltimos, amalga oshirilgan to'lov chekini (skrinshotini) rasm ko'rinishida yuboring:"
  )
  await callback.answer()


@dp.message(AdForm.waiting_for_receipt, F.photo)
async def receive_receipt(message: types.Message, state: FSMContext):
  photo_id = message.photo[-1].file_id
  data = await state.get_data()
  await state.clear()

  await send_ad_to_admin(message.bot, message.from_user.id, data, photo_id, data["days"])
  await message.answer("✅ To'lov chekingiz va e'loningiz adminga yuborildi! Tekshiruvdan so'ng kanalga chiqariladi.")


async def send_ad_to_admin(bot_obj, user_id, data, photo_id, days):
  tariff_name = (
      "1 kunlik (Bepul)"
      if days == 1
      else f"{days} kunlik" if days != 7 else "1 haftalik VIP (Doimiy)"
  )

  admin_text = (
      f"📥 **Yangi e'lon va to'lov!**\n\n"
      f"📍 Manzil: {data['location']}\n"
      f"🛠 Mutaxassis: {data['profession']}\n"
      f"📋 Shartlar: {data['conditions']}\n"
      f"📞 Aloqa: {data['contact']}\n"
      f"⏱ Tarifi: {tariff_name}\n"
      f"👤 Yuboruvchi ID: {user_id}"
  )

  approve_keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"app_{days}_{user_id}"),
              InlineKeyboardButton(text="❌ Rad etish", callback_data="rej"),
          ]
      ]
  )

  if photo_id:
    await bot_obj.send_photo(ADMIN_ID, photo=photo_id, caption=admin_text, reply_markup=approve_keyboard)
  else:
    await bot_obj.send_message(ADMIN_ID, admin_text, reply_markup=approve_keyboard)


@dp.callback_query(F.data.startswith("app_"))
async def approve_ad(callback: types.CallbackQuery):
  _, days_str, author_id = callback.data.split("_")
  days = int(days_str)

  msg = callback.message
  caption = msg.caption or msg.text
  lines = caption.split("\n")
  
  loc, prof, cond, cont = "", "", "", ""
  for line in lines:
    if line.startswith("📍 Manzil: "):
      loc = line.replace("📍 Manzil: ", "")
    elif line.startswith("🛠 Mutaxassis: "):
      prof = line.replace("🛠 Mutaxassis: ", "")
    elif line.startswith("📋 Shartlar: "):
      cond = line.replace("📋 Shartlar: ", "")
    elif line.startswith("📞 Aloqa: "):
      cont = line.replace("📞 Aloqa: ", "")

  vip_badge = "⭐ [VIP E'LON]\n\n" if days == 7 else ""
  channel_text = (
      f"{vip_badge}📌 **BO'SH ISH O'RNI (Vakansiya)**\n\n"
      f"📍 **Manzil:** {loc}\n"
      f"🛠 **Mutaxassis:** {prof}\n"
      f"📋 **Shartlar:** {cond}\n\n"
      f"📞 **Aloqa:** {cont}\n\n"
      f"🔍 *Kanalimiz:* {CHANNEL_ID}"
  )

  contact_btn = InlineKeyboardMarkup(
      inline_keyboard=[[InlineKeyboardButton(text="💬 Bog'lanish", url=f"https://t.me/{cont.lstrip('@')}" if '@' in cont else "https://t.me/")]]
  )

  sent_msg = await bot.send_message(CHANNEL_ID, channel_text, reply_markup=contact_btn)
  await callback.message.edit_caption(caption=f"✅ E'lon tasdiqlandi va kanalga chiqarildi!\n\n{caption}" if callback.message.photo else "✅ E'lon tasdiqlandi va kanalga chiqarildi!")

  if days in [1, 2, 3]:
    seconds = days * 86400
    asyncio.create_task(delete_ad_after_delay(sent_msg.chat.id, sent_msg.message_id, seconds))


async def delete_ad_after_delay(chat_id, message_id, delay):
  await asyncio.sleep(delay)
  try:
    await bot.delete_message(chat_id=chat_id, message_id=message_id)
  except Exception:
    pass


@dp.callback_query(F.data == "rej")
async def reject_ad(callback: types.CallbackQuery):
  if callback.message.photo:
    await callback.message.edit_caption(caption="❌ E'lon va to'lov rad etildi.")
  else:
    await callback.message.edit_text("❌ E'lon va to'lov rad etildi.")


@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats")]
      ]
  )
  await message.answer("Salom, Admin! Kerakli bo'limni tanlang:", reply_markup=keyboard)


@dp.callback_query(F.data == "adm_stats", F.from_user.id == ADMIN_ID)
async def adm_stats(callback: types.CallbackQuery):
  await callback.message.edit_text(f"📊 Bot foydalanuvchilari soni: {len(USERS_DB)} ta")


async def main():
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
