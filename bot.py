import logging
import threading
import time
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = Config()
bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
db = Database("bot.db")
scheduler = BackgroundScheduler()

def parse_time(time_str: str) -> Optional[datetime]:
    offset = timedelta(hours=config.TIMEZONE_OFFSET)
    tz = timezone(offset)
    now_local = datetime.now(tz)
    formats = [
        ("%d.%m.%Y %H:%M", "15.06.2025 14:30"),
        ("%d.%m.%Y %H:%M:%S", "15.06.2025 14:30:00"),
        ("%Y-%m-%d %H:%M", "2025-06-15 14:30"),
        ("%H:%M", "14:30"),
    ]
    for fmt, example in formats:
        try:
            dt_naive = datetime.strptime(time_str.strip(), fmt)
            if fmt == "%H:%M":
                dt_local = now_local.replace(hour=dt_naive.hour, minute=dt_naive.minute, second=0, microsecond=0)
            else:
                dt_local = dt_naive.replace(tzinfo=tz)
            if fmt == "%H:%M" and dt_local <= now_local:
                dt_local += timedelta(days=1)
            dt_utc = dt_local.astimezone(timezone.utc).replace(tzinfo=None)
            return dt_utc
        except ValueError:
            continue
    return None

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ только для администратора")
        return
    await message.answer("""
👋 <b>Бот запланированной публикации</b>

📋 <b>Команды:</b>
/schedule [время] — запланировать пост
/list — список запланированных постов
/delete [id] — удалить пост
/cancel — отменить текущее создание

📌 <b>Формат времени:</b>
• 14:30 (сегодня)
• 15.06.2025 14:30
• 2025-06-15 14:30
""")

waiting_for_time = {}

@dp.message(Command("schedule"))
async def cmd_schedule(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ только для администратора")
        return
    await message.answer("🕐 Отправьте время публикации\nформат: <code>DD.MM.YYYY HH:MM</code>")
    waiting_for_time[message.from_user.id] = "time"

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
        text += f"🆔 <code>{p.id}</code> — {dt.strftime('%d.%m.%Y %H:%M')}\n"
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
    if uid in waiting_for_time:
        del waiting_for_time[uid]
    await message.answer("❌ Отменено")

@dp.message()
async def handle_message(message: Message):
    uid = message.from_user.id
    if uid != config.ADMIN_ID:
        return
    if uid not in waiting_for_time:
        return
    state = waiting_for_time[uid]
    if state == "time":
        if not message.text:
            await message.answer("❌ Отправьте время текстом. Формат: DD.MM.YYYY HH:MM")
            return
        dt = parse_time(message.text)
        if not dt:
            await message.answer("❌ Неверный формат времени. Попробуйте: DD.MM.YYYY HH:MM")
            return
        waiting_for_time[uid] = ("content", dt)
        await message.answer(f"✅ Время: {dt.strftime('%d.%m.%Y %H:%M')}\n\n📝 Теперь отправьте текст поста (или /skip для пустого)")
    elif state[0] == "content":
        dt = state[1]
        content = message.text if message.text != "/skip" else ""
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
        post_id = db.add_post(uid, content, file_id, file_type, dt)
        del waiting_for_time[uid]
        await message.answer(f"✅ Пост #{post_id} запланирован на {dt.strftime('%d.%m.%Y %H:%M')}")

def publish_scheduled():
    posts = db.get_due_posts()
    for post in posts:
        try:
            if post.file_type == "photo" and post.file_id:
                from aiogram.types import InputMediaPhoto
                media = [InputMediaPhoto(media=post.file_id, caption=post.content or "")]
                import asyncio
                asyncio.run(bot.send_media_group(chat_id=config.CHANNEL_ID, media=media))
            elif post.file_type == "video" and post.file_id:
                import asyncio
                asyncio.run(bot.send_video(chat_id=config.CHANNEL_ID, video=post.file_id, caption=post.content or ""))
            elif post.file_type == "document" and post.file_id:
                import asyncio
                asyncio.run(bot.send_document(chat_id=config.CHANNEL_ID, document=post.file_id, caption=post.content or ""))
            else:
                import asyncio
                asyncio.run(bot.send_message(chat_id=config.CHANNEL_ID, text=post.content or "📌 Пост"))
            db.mark_post_sent(post.id)
            logger.info(f"Published post {post.id}")
        except Exception as e:
            logger.error(f"Failed to publish post {post.id}: {e}")

scheduler.add_job(publish_scheduled, "interval", seconds=30)
scheduler.start()

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

import threading
threading.Thread(target=run_health_server, daemon=True).start()

if __name__ == "__main__":
    logger.info("Bot starting...")
    dp.run_polling(bot)