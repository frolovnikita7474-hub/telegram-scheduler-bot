import logging
import threading
import os
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import Config
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = Config()
bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
db = Database("bot.db")

OFFSET = timedelta(hours=config.TIMEZONE_OFFSET)
TZ = timezone(OFFSET)

sessions = {}

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ только для администратора")
        return
    await message.answer("""
👋 <b>Бот запланированной публикации</b>

📋 <b>Команды:</b>
/schedule — запланировать пост (пошагово)
/now — моментальная публикация
/list — список запланированных постов
/delete [id] — удалить пост
/cancel — отменить текущее создание
""")

@dp.message(Command("schedule"))
async def cmd_schedule(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ только для администратора")
        return
    uid = message.from_user.id
    sessions[uid] = {}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data="date_today"),
         InlineKeyboardButton(text="📅 Завтра", callback_data="date_tomorrow")],
        [InlineKeyboardButton(text="📅 Послезавтра", callback_data="date_dayafter"),
         InlineKeyboardButton(text="✏️ Другая дата", callback_data="date_custom")],
    ])
    await message.answer("📆 <b>Выберите дату:</b>", reply_markup=kb)

@dp.callback_query(F.data.startswith("date_"))
async def cb_date(call: CallbackQuery):
    uid = call.from_user.id
    if uid not in sessions:
        await call.answer("❌ Сессия устарела, начните заново /schedule")
        return
    now = datetime.now(TZ)
    if call.data == "date_today":
        sessions[uid]["dt_local"] = now
        await ask_time(call)
    elif call.data == "date_tomorrow":
        sessions[uid]["dt_local"] = now + timedelta(days=1)
        await ask_time(call)
    elif call.data == "date_dayafter":
        sessions[uid]["dt_local"] = now + timedelta(days=2)
        await ask_time(call)
    elif call.data == "date_custom":
        sessions[uid]["waiting"] = "custom_date"
        await call.message.edit_text("📆 Введите дату в формате <code>ДД.ММ.ГГГГ</code>\nНапример: <code>15.06.2025</code>")

async def ask_time(call: CallbackQuery):
    uid = call.from_user.id
    sessions[uid]["waiting"] = "time"
    dt = sessions[uid]["dt_local"]
    await call.message.edit_text(f"✅ Дата: {dt.strftime('%d.%m.%Y')}\n\n🕐 Теперь введите <b>время</b> в формате <code>ЧЧ:ММ</code>")

@dp.message(Command("list"))
async def cmd_list(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ только для администратора")
        return
    posts = db.get_pending(message.from_user.id)
    if not posts:
        await message.answer("📭 Нет запланированных постов")
        return
    text = "📋 <b>Запланированные посты:</b>\n\n"
    for p in posts:
        dt = datetime.fromisoformat(p.scheduled_time)
        local = dt.replace(tzinfo=timezone.utc).astimezone(TZ)
        text += f"🆔 <code>{p.id}</code> — {local.strftime('%d.%m.%Y %H:%M')}\n"
        if p.content:
            text += f"   {p.content[:50]}...\n"
        text += "\n"
    await message.answer(text)

@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ только для администратора")
        return
    try:
        post_id = int(message.text.split()[1])
        db.delete_post(post_id)
        await message.answer(f"✅ Пост {post_id} удалён")
    except (IndexError, ValueError):
        await message.answer("⚠️ Использование: /delete [id]")

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message):
    uid = message.from_user.id
    sessions.pop(uid, None)
    await message.answer("❌ Отменено")

@dp.message(Command("now"))
async def cmd_now(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ только для администратора")
        return
    uid = message.from_user.id
    sessions[uid] = {"now": True, "waiting": "content"}
    await message.answer("📝 Отправьте текст или медиа для <b>моментальной</b> публикации:")

@dp.message()
async def handle_message(message: Message):
    uid = message.from_user.id
    if uid != config.ADMIN_ID:
        return
    if uid not in sessions:
        return
    s = sessions[uid]
    waiting = s.get("waiting")

    if waiting == "custom_date":
        if not message.text:
            await message.answer("❌ Отправьте дату текстом. Формат: ДД.ММ.ГГГГ")
            return
        try:
            dt_local = datetime.strptime(message.text.strip(), "%d.%m.%Y").replace(tzinfo=TZ)
        except ValueError:
            await message.answer("❌ Неверный формат. Используйте <code>ДД.ММ.ГГГГ</code>")
            return
        s["dt_local"] = dt_local
        s["waiting"] = "time"
        await message.answer(f"✅ Дата: {dt_local.strftime('%d.%m.%Y')}\n\n🕐 Теперь введите <b>время</b> в формате <code>ЧЧ:ММ</code>")
        return

    if waiting == "time":
        if not message.text:
            await message.answer("❌ Отправьте время текстом. Формат: ЧЧ:ММ")
            return
        try:
            t = datetime.strptime(message.text.strip(), "%H:%M")
            dt_local = s["dt_local"].replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        except ValueError:
            await message.answer("❌ Неверный формат. Используйте <code>ЧЧ:ММ</code>")
            return
        if dt_local <= datetime.now(TZ):
            dt_local += timedelta(days=1)
        s["dt"] = dt_local.astimezone(timezone.utc).replace(tzinfo=None)
        s["waiting"] = "content"
        tz_sign = "+" if config.TIMEZONE_OFFSET >= 0 else ""
        await message.answer(f"✅ Время: {dt_local.strftime('%d.%m.%Y %H:%M')} (UTC{tz_sign}{config.TIMEZONE_OFFSET})\n\n📝 Теперь отправьте текст поста (или <code>/skip</code> для пустого)")
        return

    if waiting == "content":
        content = (message.caption or message.text or "")
        content = "" if content == "/skip" else content
        file_id, file_type = None, None
        if message.photo:
            file_id = message.photo[-1].file_id
            file_type = "photo"
        elif message.video:
            file_id = message.video.file_id
            file_type = "video"
        elif message.document:
            file_id = message.document.file_id
            file_type = "document"
        if s.get("now"):
            try:
                if file_type == "photo":
                    await bot.send_photo(chat_id=config.CHANNEL_ID, photo=file_id, caption=content or "")
                elif file_type == "video":
                    await bot.send_video(chat_id=config.CHANNEL_ID, video=file_id, caption=content or "")
                elif file_type == "document":
                    await bot.send_document(chat_id=config.CHANNEL_ID, document=file_id, caption=content or "")
                else:
                    await bot.send_message(chat_id=config.CHANNEL_ID, text=content or "📌 Пост")
                await message.answer("✅ Опубликовано мгновенно!")
            except Exception as e:
                await message.answer(f"❌ Ошибка публикации: {e}")
            sessions.pop(uid, None)
            return
        dt = s["dt"]
        post_id = db.add_post(uid, content, file_id, file_type, dt)
        sessions.pop(uid, None)
        await message.answer(f"✅ Пост #{post_id} запланирован на {datetime.fromisoformat(str(dt)).strftime('%d.%m.%Y %H:%M')}")

async def publish_loop():
    await asyncio.sleep(5)
    while True:
        try:
            posts = db.get_due_posts()
            if posts:
                logger.info(f"Found {len(posts)} due post(s)")
            for post in posts:
                try:
                    if post.file_type == "photo" and post.file_id:
                        await bot.send_photo(chat_id=config.CHANNEL_ID, photo=post.file_id, caption=post.content or "")
                    elif post.file_type == "video" and post.file_id:
                        await bot.send_video(chat_id=config.CHANNEL_ID, video=post.file_id, caption=post.content or "")
                    elif post.file_type == "document" and post.file_id:
                        await bot.send_document(chat_id=config.CHANNEL_ID, document=post.file_id, caption=post.content or "")
                    else:
                        await bot.send_message(chat_id=config.CHANNEL_ID, text=post.content or "📌 Пост")
                    db.mark_post_sent(post.id)
                    logger.info(f"Published post {post.id}")
                except Exception as e:
                    logger.error(f"Failed to publish post {post.id}: {e}")
        except Exception as e:
            logger.error(f"Publish loop error: {e}")
        await asyncio.sleep(30)

def run_health_server():
    import http.server
    import socketserver
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        def log_message(self, *a):
            pass
    port = int(os.getenv("PORT", "10000"))
    with socketserver.TCPServer(("", port), Handler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

async def on_startup():
    await bot.set_my_commands([
        ("schedule", "Запланировать пост"),
        ("now", "Моментальная публикация"),
        ("list", "Список запланированных постов"),
        ("delete", "Удалить пост по ID"),
        ("cancel", "Отменить создание"),
    ])
    asyncio.create_task(publish_loop())
    logger.info("Publish loop started")

if __name__ == "__main__":
    logger.info("Bot starting...")
    dp.startup.register(on_startup)
    dp.run_polling(bot)