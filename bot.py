import os
import logging
import tempfile
import asyncio
import threading

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from telegram import Update
from telegram.error import Conflict, NetworkError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from config import BOT_TOKEN, ADMIN_ID
from processor import process_video, ProcessingError


logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
# حتى لا يظهر التوكن في السجلات
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

MAX_SIZE_MB = 20
MAX_DURATION_SEC = 20

processing_lock = asyncio.Semaphore(1)


# ---------- خادم ping لإبقاء الخدمة مستيقظة ----------

class Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def run_ping_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), Ping).serve_forever()


# ---------- مساعد لتعديل الرسالة بدون أن يسقط البوت ----------

async def safe_edit(message, text):
    try:
        await message.edit_text(text)
    except Exception:
        logger.warning("Could not edit status message")


# ---------- الأوامر ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحباً بك في بوت فصل الموسيقى 🎵\n\n"
        "أرسل فيديو وسأقوم بـ:\n"
        "1- إزالة الموسيقى والإبقاء على الكلام.\n"
        "2- استخراج الموسيقى بصيغة MP3.\n\n"
        f"الحد الأقصى: {MAX_DURATION_SEC} ثانية و{MAX_SIZE_MB} MB.\n"
        "انتظر حتى تنتهي المعالجة."
    )


async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Telegram ID: {update.effective_user.id}"
    )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    message = update.message

    if ADMIN_ID and user_id != ADMIN_ID:
        await message.reply_text("هذا البوت مخصص لصاحبه حالياً.")
        return

    media = message.video or message.document

    if not media:
        await message.reply_text("أرسل ملف فيديو من فضلك.")
        return

    if message.document and not (
        message.document.mime_type or ""
    ).startswith("video/"):
        await message.reply_text("الملف المرسل ليس فيديو.")
        return

    if media.file_size and media.file_size > MAX_SIZE_MB * 1024 * 1024:
        await message.reply_text(
            f"حجم الفيديو أكبر من {MAX_SIZE_MB} MB. أرسل فيديو أصغر."
        )
        return

    duration = getattr(media, "duration", None)
    if duration and duration > MAX_DURATION_SEC:
        await message.reply_text(
            f"الحد الأقصى لمدة الفيديو {MAX_DURATION_SEC} ثانية."
        )
        return

    status = await message.reply_text(
        "تم استلام الفيديو. انتظر قليلاً... ⏳"
    )

    async with processing_lock:

        try:
            with tempfile.TemporaryDirectory() as temp:

                work_dir = Path(temp)
                video_path = work_dir / "original.mp4"

                telegram_file = await media.get_file()
                await telegram_file.download_to_drive(
                    custom_path=video_path
                )

                await safe_edit(
                    status,
                    "جارٍ فصل الكلام عن الموسيقى... 🎧\n"
                    "قد يستغرق ذلك عدة دقائق."
                )

                clean_video, music_file = await asyncio.to_thread(
                    process_video,
                    video_path,
                    work_dir
                )

                await safe_edit(
                    status,
                    "اكتملت المعالجة! جارٍ إرسال الملفات..."
                )

                with open(clean_video, "rb") as file:
                    await message.reply_video(
                        video=file,
                        caption="🎬 الفيديو بعد إزالة الموسيقى",
                        read_timeout=120,
                        write_timeout=120
                    )

                with open(music_file, "rb") as file:
                    await message.reply_audio(
                        audio=file,
                        title="Extracted Music",
                        caption="🎵 الموسيقى المستخرجة",
                        read_timeout=120,
                        write_timeout=120
                    )

                await safe_edit(
                    status,
                    "تم إرسال الفيديو والموسيقى بنجاح! ✅"
                )

        except ProcessingError as error:
            # خطأ معروف: نعرض رسالته للمستخدم
            logger.warning("Processing error: %s", error)
            await safe_edit(status, f"⚠️ {error}")

        except Exception as error:
            # خطأ غير متوقع: التفاصيل في السجل، والمستخدم يرى رسالة قصيرة
            logger.exception("Video processing failed")
            await safe_edit(
                status,
                "حدث خطأ غير متوقع أثناء المعالجة.\n"
                "حاول مرة أخرى بفيديو أقصر.\n\n"
                f"التفاصيل: {str(error)[-300:]}"
            )


# ---------- معالج الأخطاء العام ----------

async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error

    if isinstance(error, Conflict):
        logger.warning(
            "409 Conflict: نسخة أخرى من البوت تعمل بنفس التوكن."
        )
        return

    if isinstance(error, NetworkError):
        logger.warning("Network error: %s", error)
        return

    logger.error("Unhandled error", exc_info=error)


def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", get_id))

    app.add_handler(
        MessageHandler(
            filters.VIDEO | filters.Document.VIDEO,
            handle_video
        )
    )

    app.add_error_handler(error_handler)

    threading.Thread(target=run_ping_server, daemon=True).start()

    print("Telegram Music Bot is running...")

    # drop_pending_updates: لا يعالج فيديوهات قديمة بعد إعادة التشغيل
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
