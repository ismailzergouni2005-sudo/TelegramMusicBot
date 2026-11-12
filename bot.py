
import logging
import tempfile
import asyncio

from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from config import BOT_TOKEN, ADMIN_ID
from processor import process_video


logging.basicConfig(
    logging.getLogger("httpx").setLevel(logging.WARNING)
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

processing_lock = asyncio.Semaphore(1)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "مرحباً بك في بوت فصل الموسيقى 🎵\n\n"
        "أرسل فيديو وسأقوم بـ:\n"
        "1- إزالة الموسيقى والإبقاء على الكلام.\n"
        "2- استخراج الموسيقى بصيغة MP3.\n\n"
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

    if media.file_size and media.file_size > 20 * 1024 * 1024:
        await message.reply_text(
            "حجم الفيديو أكبر من 20 MB. أرسل فيديو أصغر."
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

                await status.edit_text(
                    "جارٍ فصل الكلام عن الموسيقى بالذكاء الاصطناعي... 🎧"
                )

                clean_video, music_file = await asyncio.to_thread(
                    process_video,
                    video_path,
                    work_dir
                )

                await status.edit_text(
                    "اكتملت المعالجة! جارٍ إرسال الملفات..."
                )

                with open(clean_video, "rb") as file:
                    await message.reply_video(
                        video=file,
                        caption="🎬 الفيديو بعد إزالة الموسيقى"
                    )

                with open(music_file, "rb") as file:
                    await message.reply_audio(
                        audio=file,
                        title="Extracted Music",
                        caption="🎵 الموسيقى المستخرجة"
                    )

                await status.edit_text(
                    "تم إرسال الفيديو والموسيقى بنجاح! ✅"
                )

        except Exception as error:
            logger.exception("Video processing failed")

            await status.edit_text(
                "حدث خطأ أثناء معالجة الفيديو.\n"
                "تأكد من صلاحية الفيديو وحاول مجدداً.\n\n"
                f"تفاصيل الخطأ: {str(error)[:500]}"
            )


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

    print("Telegram Music Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
