import asyncio, os, sqlite3, logging
from datetime import datetime, timezone, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as IK, KeyboardButton as KB, ReplyKeyboardMarkup as RK
from redis.asyncio import Redis

TOKEN=os.getenv('BOT_TOKEN')
ADMIN_ID=8451295149
CHANNEL_ID=os.getenv('CHANNEL_ID','@Ishbazasi')
ADMIN_CONTACT=os.getenv('ADMIN_CONTACT','@rustamovvvll')
CARD_NUMBER=os.getenv('CARD_NUMBER','')
CARD_HOLDER=os.getenv('CARD_HOLDER','Rustamov Diyorbek')
REDIS_URL=os.getenv('REDIS_URL','redis://localhost:6379/0')
DB_PATH=os.getenv('DB_PATH','bot.db')
RECEIPT_MINUTES=5
if not TOKEN: raise RuntimeError('BOT_TOKEN topilmadi')
logging.basicConfig(level=logging.INFO)
log=logging.getLogger(__name__)
redis=Redis.from_url(REDIS_URL,decode_responses=False)
dp=Dispatcher(storage=RedisStorage(redis=redis)); bot=Bot(TOKEN)

def con():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c
def now(): return datetime.now(timezone.utc)
def init():
    with con() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_id INTEGER UNIQUE,username TEXT,first_name TEXT,created_at TEXT,last_seen TEXT,blocked INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS ads(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_id INTEGER,user_id INTEGER,location TEXT,profession TEXT,conditions TEXT,contact TEXT,days INTEGER,price INTEGER,vip INTEGER DEFAULT 0,status TEXT DEFAULT 'pending',channel_message_id INTEGER,expires_at TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,ad_id INTEGER,telegram_id INTEGER,amount INTEGER,status TEXT DEFAULT 'waiting',receipt_file_id TEXT,expires_at TEXT,created_at TEXT);''')
def reg(u):
    t=now().isoformat()
    with con() as c:c.execute('''INSERT INTO users(telegram_id,username,first_name,created_at,last_seen) VALUES(?,?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,last_seen=excluded.last_seen''',(u.id,u.username,u.first_name,t,t))
def uid(tid):
    with con() as c:
        r=c.execute('SELECT id FROM users WHERE telegram_id=?',(tid,)).fetchone(); return r['id']
def adget(i):
    with con() as c:return c.execute('SELECT * FROM ads WHERE id=?',(i,)).fetchone()
def payget(i):
    with con() as c:return c.execute('SELECT * FROM payments WHERE id=?',(i,)).fetchone()
def latestpay(aid):
    with con() as c:return c.execute('SELECT * FROM payments WHERE ad_id=? ORDER BY id DESC LIMIT 1',(aid,)).fetchone()
def status_ad(i,s):
    with con() as c:c.execute('UPDATE ads SET status=? WHERE id=?',(s,i))
def status_pay(i,s):
    with con() as c:c.execute('UPDATE payments SET status=? WHERE id=?',(s,i))

def menu():return RK(keyboard=[[KB(text="🚀 E'lon berish")],[KB(text='📞 Admin bilan bog\'lanish')],[KB(text='👤 Mening ID raqamim')]],resize_keyboard=True)
def subkb():return IK(inline_keyboard=[[B(text='📢 Kanalga obuna bo\'lish',url='https://t.me/Ishbazasi')],[B(text='✅ Obunani tekshirish',callback_data='sub')]])
def adminkb():return IK(inline_keyboard=[[B(text='📊 Statistika',callback_data='astats'),B(text="📋 E'lonlar",callback_data='aads')],[B(text="💰 To'lovlar",callback_data='apay'),B(text='👥 Foydalanuvchilar',callback_data='ausers')],[B(text='📣 Hammaga xabar',callback_data='abroadcast'),B(text='⚙️ Tariflar',callback_data='atariffs')],[B(text="🗑 E'lonni o'chirish",callback_data='adelete')]])
def tariffkb():return IK(inline_keyboard=[[B(text='🟢 1 kun — BEPUL',callback_data='t1')],[B(text="🟡 2 kun — 15 000 so'm",callback_data='t2')],[B(text="🟠 3 kun — 30 000 so'm",callback_data='t3')],[B(text='⭐ VIP — 45 000 so\'m 🔥 SKIDKA',callback_data='t7')]])
async def subscribed(tid):
    try:return (await bot.get_chat_member(CHANNEL_ID,tid)).status not in ('left','kicked')
    except Exception:return False

class Ad(StatesGroup):loc=State();job=State();conditions=State();contact=State();tariff=State();receipt=State()
class Broadcast(StatesGroup):text=State()
class Delete(StatesGroup):aid=State()

@dp.message(Command('start'))
async def start(m:types.Message):
    reg(m.from_user)
    if not await subscribed(m.from_user.id):return await m.answer('Botdan foydalanish uchun avval kanalga obuna bo\'ling.',reply_markup=subkb())
    await m.answer('Assalomu alaykum! 👋\nIsh bazasi botiga xush kelibsiz.',reply_markup=menu())
@dp.callback_query(F.data=='sub')
async def sub(c:types.CallbackQuery):
    if await subscribed(c.from_user.id):await c.message.edit_text('✅ Obuna tasdiqlandi!');await c.message.answer('Botdan foydalanishingiz mumkin.',reply_markup=menu())
    else:await c.answer('❌ Hali obuna bo\'lmagansiz.',show_alert=True)
@dp.message(F.text=='👤 Mening ID raqamim')
async def myid(m):reg(m.from_user);await m.answer(f'👤 Botdagi ID: <code>{uid(m.from_user.id)}</code>\nTelegram ID: <code>{m.from_user.id}</code>',parse_mode='HTML')
@dp.message(F.text=='📞 Admin bilan bog\'lanish')
async def contact(m):await m.answer(f'📞 Admin: {ADMIN_CONTACT}')

@dp.message(F.text=="🚀 E'lon berish")
async def begin(m,state:FSMContext):
    reg(m.from_user)
    if not await subscribed(m.from_user.id):return await m.answer('Avval kanalga obuna bo\'ling.',reply_markup=subkb())
    await state.set_state(Ad.loc);await m.answer('📍 Ish joyi qayerda?')
@dp.message(Ad.loc)
async def loc(m,state):await state.update_data(location=m.text.strip());await state.set_state(Ad.job);await m.answer('🛠 Qanday ishchi kerak?')
@dp.message(Ad.job)
async def job(m,state):await state.update_data(profession=m.text.strip());await state.set_state(Ad.conditions);await m.answer('📋 Talablar, maosh va ish vaqti?')
@dp.message(Ad.conditions)
async def cond(m,state):await state.update_data(conditions=m.text.strip());await state.set_state(Ad.contact);await m.answer('📞 Aloqa: telefon yoki Telegram username')
@dp.message(Ad.contact)
async def cont(m,state):
    await state.update_data(contact=m.text.strip());await state.set_state(Ad.tariff)
    await m.answer("💰 Tarifni tanlang:\n⭐ VIP 45 000 so'm — umrbod kanalda qoladi.",reply_markup=tariffkb())

T={1:(0,0,'1 kunlik'),2:(15000,0,'2 kunlik'),3:(30000,0,'3 kunlik'),7:(45000,1,'VIP UMRBOD')}
def create_ad(tid,d,days,price,vip):
    with con() as c:
        x=c.execute('INSERT INTO ads(telegram_id,user_id,location,profession,conditions,contact,days,price,vip,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(tid,uid(tid),d['location'],d['profession'],d['conditions'],d['contact'],days,price,vip,now().isoformat()));return x.lastrowid
def create_pay(aid,tid,amount):
    ex=now()+timedelta(minutes=RECEIPT_MINUTES)
    with con() as c:x=c.execute('INSERT INTO payments(ad_id,telegram_id,amount,expires_at,created_at) VALUES(?,?,?,?,?)',(aid,tid,amount,ex.isoformat(),now().isoformat()));return x.lastrowid

@dp.callback_query(Ad.tariff,F.data.regexp(r'^t[1237]$'))
async def tariff(c,state:FSMContext):
    days=int(c.data[1:]);price,vip,name=T[days];d=await state.get_data();aid=create_ad(c.from_user.id,d,days,price,vip)
    if not price:
        await state.clear();await send_admin(aid);return await c.message.edit_text('✅ E\'lon adminga yuborildi. Tasdiqlangach kanalga chiqadi.')
    pid=create_pay(aid,c.from_user.id,price);await state.update_data(payment_id=pid);await state.set_state(Ad.receipt)
    card=CARD_NUMBER or 'KARTA RAQAMI HOSTINGDA KIRITILADI'
    desc=('⭐ <b>VIP UMRBOD</b>\n<s>70 000</s> → <b>45 000 so\'m</b> 🔥 SKIDKA\nE\'lon avtomatik o\'chirilmaydi.' if vip else f'⏱ <b>{days} kunlik</b> — {price:,} so\'m\nE\'lon {days} kundan keyin o\'chadi.')
    await c.message.edit_text(f'{desc}\n\n💳 Karta: <code>{card}</code>\n👤 Egasi: {CARD_HOLDER}\n\n⏰ Chekni {RECEIPT_MINUTES} daqiqa ichida yuboring.',reply_markup=IK(inline_keyboard=[[B(text='💳 To\'lov qildim',callback_data=f'paid{pid}')]]),parse_mode='HTML')
@dp.callback_query(F.data.regexp(r'^paid\d+$'))
async def paid(c,state:FSMContext):
    pid=int(c.data[4:]);d=await state.get_data();p=payget(pid)
    if not p or d.get('payment_id')!=pid:return await c.answer('❌ To\'lov sessiyasi topilmadi.',show_alert=True)
    if now()>datetime.fromisoformat(p['expires_at']):status_pay(pid,'expired');status_ad(p['ad_id'],'cancelled');await state.clear();return await c.message.edit_text('❌ 5 daqiqa tugadi. Tarifni qaytadan tanlang.')
    await c.message.answer('📸 Chekni rasm qilib yuboring. Sizda 5 daqiqa bor.');await c.answer()
@dp.message(Ad.receipt,F.photo)
async def receipt(m,state):
    d=await state.get_data();p=payget(d.get('payment_id'))
    if not p:return await m.answer('❌ To\'lov topilmadi.')
    if now()>datetime.fromisoformat(p['expires_at']):status_pay(p['id'],'expired');status_ad(p['ad_id'],'cancelled');await state.clear();return await m.answer('❌ 5 daqiqa tugadi.')
    with con() as c:c.execute("UPDATE payments SET receipt_file_id=?,status='receipt_received' WHERE id=?",(m.photo[-1].file_id,p['id']))
    await state.clear();await send_admin(p['ad_id']);await m.answer('✅ Chek qabul qilindi. Admin tekshiradi.')
@dp.message(Ad.receipt)
async def receipt_text(m):await m.answer('📸 Iltimos, chekni rasm qilib yuboring.')

async def send_admin(aid):
    a=adget(aid);p=latestpay(aid)
    text=(f"📥 <b>YANGI E'LON</b>\n\n🆔 Ariza ID: <code>{a['id']}</code>\n👤 Foydalanuvchi ID: <code>{a['user_id']}</code>\n📱 Telegram ID: <code>{a['telegram_id']}</code>\n\n📍 <b>Manzil:</b> {a['location']}\n🛠 <b>Ish:</b> {a['profession']}\n📋 <b>Shartlar:</b> {a['conditions']}\n📞 <b>Aloqa:</b> {a['contact']}\n⏱ <b>Tarif:</b> {T[a['days']][2]}\n💰 <b>Summa:</b> {a['price']:,} so'm")
    kb=IK(inline_keyboard=[[B(text='✅ Tasdiqlash',callback_data=f'yes{aid}'),B(text='❌ Rad etish',callback_data=f'no{aid}')]])
    if p and p['receipt_file_id']:await bot.send_photo(ADMIN_ID,p['receipt_file_id'],caption=text,reply_markup=kb,parse_mode='HTML')
    else:await bot.send_message(ADMIN_ID,text,reply_markup=kb,parse_mode='HTML')
@dp.callback_query(F.data.regexp(r'^yes\d+$'))
async def approve(c):
    if c.from_user.id!=ADMIN_ID:return await c.answer('❌ Ruxsat yo\'q.',show_alert=True)
    aid=int(c.data[3:]);a=adget(aid)
    if not a or a['status']!='pending':return await c.answer('Bu e\'lon allaqachon ko\'rib chiqilgan.',show_alert=True)
    p=latestpay(aid)
    if a['price'] and (not p or p['status']!='receipt_received'):return await c.answer('❌ Chek topilmadi.',show_alert=True)
    if p:status_pay(p['id'],'approved')
    text=('⭐ <b>VIP UMRBOD E\'LON</b>\n\n' if a['vip'] else '')+f"📌 <b>BO'SH ISH O'RNI</b>\n\n📍 <b>Manzil:</b> {a['location']}\n🛠 <b>Ish:</b> {a['profession']}\n📋 <b>Shartlar:</b> {a['conditions']}\n📞 <b>Aloqa:</b> {a['contact']}"
    u=a['contact'].strip();url=f'https://t.me/{u[1:]}' if u.startswith('@') else 'https://t.me/'
    try:s=await bot.send_message(CHANNEL_ID,text,reply_markup=IK(inline_keyboard=[[B(text='💬 Bog\'lanish',url=url)]]),parse_mode='HTML')
    except Exception:return await c.answer('❌ Bot kanalga admin qilinmagan yoki kanal sozlamasida xato.',show_alert=True)
    ex=None if a['vip'] else (now()+timedelta(days=a['days'])).isoformat()
    with con() as x:x.execute("UPDATE ads SET status='published',channel_message_id=?,expires_at=? WHERE id=?",(s.message_id,ex,aid))
    if c.message.photo:await c.message.edit_caption(caption='✅ Tasdiqlandi va kanalga chiqarildi.')
    else:await c.message.edit_text('✅ Tasdiqlandi va kanalga chiqarildi.')
    await c.answer()
@dp.callback_query(F.data.regexp(r'^no\d+$'))
async def reject(c):
    if c.from_user.id!=ADMIN_ID:return await c.answer('❌ Ruxsat yo\'q.',show_alert=True)
    aid=int(c.data[2:]);a=adget(aid)
    if not a:return await c.answer('Topilmadi.',show_alert=True)
    status_ad(aid,'rejected');p=latestpay(aid)
    if p:status_pay(p['id'],'rejected')
    if c.message.photo:await c.message.edit_caption(caption='❌ E\'lon rad etildi.')
    else:await c.message.edit_text('❌ E\'lon rad etildi.')
    await c.answer()

@dp.message(Command('admin'))
async def admin(m):
    if m.from_user.id==ADMIN_ID:await m.answer('👨‍💼 <b>ADMIN PANEL</b>',reply_markup=adminkb(),parse_mode='HTML')
@dp.callback_query(F.data=='astats')
async def astats(c):
    if c.from_user.id!=ADMIN_ID:return
    with con() as x:
        u=x.execute('SELECT COUNT(*) FROM users').fetchone()[0];a=x.execute('SELECT COUNT(*) FROM ads').fetchone()[0];pub=x.execute("SELECT COUNT(*) FROM ads WHERE status='published'").fetchone()[0];pend=x.execute("SELECT COUNT(*) FROM ads WHERE status='pending'").fetchone()[0];rev=x.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='approved'").fetchone()[0]
    await c.message.edit_text(f'📊 <b>STATISTIKA</b>\n\n👥 Foydalanuvchilar: {u}\n📢 Jami e\'lonlar: {a}\n✅ Kanalda: {pub}\n⏳ Kutilmoqda: {pend}\n💰 Tushum: {rev:,} so\'m',reply_markup=adminkb(),parse_mode='HTML')
@dp.callback_query(F.data=='aads')
async def aads(c):
    if c.from_user.id!=ADMIN_ID:return
    with con() as x:r=x.execute('SELECT status,COUNT(*) n FROM ads GROUP BY status').fetchall()
    await c.message.edit_text('📋 <b>E\'LONLAR</b>\n\n'+'\n'.join(f"• {z['status']}: {z['n']} ta" for z in r) or 'Hozircha yo\'q',reply_markup=adminkb(),parse_mode='HTML')
@dp.callback_query(F.data=='apay')
async def apay(c):
    if c.from_user.id!=ADMIN_ID:return
    with con() as x:rev=x.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='approved'").fetchone()[0];w=x.execute("SELECT COUNT(*) FROM payments WHERE status='receipt_received'").fetchone()[0]
    await c.message.edit_text(f"💰 <b>TO'LOVLAR</b>\n\n✅ Tushum: {rev:,} so'm\n📸 Tekshirilayotgan cheklar: {w} ta",reply_markup=adminkb(),parse_mode='HTML')
@dp.callback_query(F.data=='ausers')
async def ausers(c):
    if c.from_user.id!=ADMIN_ID:return
    with con() as x:n=x.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    await c.message.edit_text(f'👥 <b>FOYDALANUVCHILAR</b>\n\nJami: {n}\nHar bir foydalanuvchiga bot ID beradi.',reply_markup=adminkb(),parse_mode='HTML')
@dp.callback_query(F.data=='atariffs')
async def atariffs(c):
    if c.from_user.id!=ADMIN_ID:return
    await c.message.edit_text("⚙️ <b>TARIFLAR</b>\n\n🟢 1 kun — Bepul\n🟡 2 kun — 15 000 so'm\n🟠 3 kun — 30 000 so'm\n⭐ VIP UMRBOD — <s>70 000</s> → <b>45 000 so'm</b>",reply_markup=adminkb(),parse_mode='HTML')
@dp.callback_query(F.data=='abroadcast')
async def broadcast_start(c,state):
    if c.from_user.id!=ADMIN_ID:return
    await state.set_state(Broadcast.text);await c.message.answer('📣 Hamma foydalanuvchiga yuboriladigan xabarni yozing. /cancel');await c.answer()
@dp.message(Broadcast.text)
async def broadcast(m,state):
    if m.from_user.id!=ADMIN_ID:return
    if m.text=='/cancel':await state.clear();return await m.answer('Bekor qilindi.')
    with con() as x:users=x.execute('SELECT telegram_id FROM users WHERE blocked=0').fetchall()
    ok=bad=0
    for u in users:
        try:await bot.send_message(u['telegram_id'],m.text);ok+=1
        except Exception:bad+=1
        await asyncio.sleep(.04)
    await state.clear();await m.answer(f'✅ Yuborildi: {ok}\n❌ Yetkazilmadi: {bad}')
@dp.callback_query(F.data=='adelete')
async def delete_start(c,state):
    if c.from_user.id!=ADMIN_ID:return
    await state.set_state(Delete.aid);await c.message.answer('🗑 O\'chirish uchun e\'lon ID raqamini yuboring. /cancel');await c.answer()
@dp.message(Delete.aid)
async def delete_ad(m,state):
    if m.from_user.id!=ADMIN_ID:return
    if m.text=='/cancel':await state.clear();return await m.answer('Bekor qilindi.')
    try:aid=int(m.text)
    except:return await m.answer('Faqat ID raqamini yozing.')
    a=adget(aid)
    if not a:return await m.answer('❌ Topilmadi.')
    if a['channel_message_id']:
        try:await bot.delete_message(CHANNEL_ID,a['channel_message_id'])
        except Exception:pass
    status_ad(aid,'deleted');await state.clear();await m.answer(f'✅ #{aid} o\'chirildi.')
@dp.message(Command('cancel'))
async def cancel(m,state):await state.clear();await m.answer('❌ Bekor qilindi.',reply_markup=menu())

async def workers():
    while True:
        try:
            with con() as x:ads=x.execute("SELECT * FROM ads WHERE status='published' AND vip=0 AND expires_at IS NOT NULL AND expires_at<=?",(now().isoformat(),)).fetchall()
            for a in ads:
                try:await bot.delete_message(CHANNEL_ID,a['channel_message_id'])
                except Exception:pass
                status_ad(a['id'],'expired')
            with con() as x:pays=x.execute("SELECT * FROM payments WHERE status='waiting' AND expires_at<=?",(now().isoformat(),)).fetchall()
            for p in pays:status_pay(p['id'],'expired');status_ad(p['ad_id'],'cancelled')
        except Exception:log.exception('Worker xatosi')
        await asyncio.sleep(30)

async def main():
    init();await bot.delete_webhook(drop_pending_updates=True);w=asyncio.create_task(workers())
    try:await dp.start_polling(bot)
    finally:w.cancel();await redis.close();await bot.session.close()
if __name__=='__main__':asyncio.run(main())
