"""
tg_google_forms_bot.py
الإصدار النهائي بعد دمج كل التعديلات ✨
----------------------------------------
- يقبل الأسئلة من ملف txt أو نص مباشر.
- يطلب من المستخدم إدخال اسم الكويز.
- يعرض رابط viewform فقط.
"""

import os
import logging
import tempfile
import subprocess
from telegram import Update, BotCommand
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# إعداد التسجيل (Logs)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# توكن البوت
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "ضع_توكن_البوت_هنا"

# مسار سكربت إنشاء النموذج
SCRIPT_PATH = "google_forms_automator_fixed.py"


def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 أهلاً بك!\n"
        "أرسل لي الآن ملف الأسئلة (.txt)\n"
        "أو الصق الأسئلة مباشرة في الرسالة.\n\n"
        "كل سؤال يجب أن يكون مثل المثال التالي:\n"
        "سؤال: ما عاصمة مصر؟\n"
        "اختيارات: القاهرة | باريس | لندن\n"
        "إجابة: القاهرة\n"
        "نقاط: 1\n"
    )


def handle_message(update: Update, context: CallbackContext):
    """يتعامل مع الرسائل النصية (أسئلة منسوخة)"""
    text = update.message.text.strip()

    if not text:
        update.message.reply_text("⚠️ الرجاء إرسال نص الأسئلة أو ملف .txt.")
        return

    # طلب اسم الكويز
    update.message.reply_text("🎯 من فضلك أدخل اسم الكويز:")
    context.user_data["pending_questions"] = text
    context.user_data["awaiting_quiz_name"] = True


def handle_quiz_name(update: Update, context: CallbackContext):
    """يحصل على اسم الكويز ويبدأ الإنشاء"""
    quiz_name = update.message.text.strip()
    text = context.user_data.get("pending_questions")

    if not quiz_name:
        update.message.reply_text("⚠️ لا يمكن ترك الاسم فارغًا. حاول مرة أخرى:")
        return

    update.message.reply_text("⏳ جاري إنشاء النموذج، يرجى الانتظار قليلاً...")

    try:
        # حفظ الأسئلة في ملف مؤقت
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as temp:
            temp.write(text)
            temp_path = temp.name

        # استدعاء السكربت لإنشاء النموذج
        result = subprocess.run(
            ["python", SCRIPT_PATH, "--title", quiz_name, "--questions", temp_path],
            capture_output=True, text=True
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode == 0:
            update.message.reply_text("✅ تم إنشاء الكويز بنجاح!\n\n" + output)
        else:
            update.message.reply_text(f"❌ حدث خطأ أثناء الإنشاء:\n{error or output}")

    except Exception as e:
        update.message.reply_text(f"⚠️ حدث خطأ غير متوقع: {e}")

    finally:
        context.user_data.clear()
        if os.path.exists(temp_path):
            os.remove(temp_path)


def handle_document(update: Update, context: CallbackContext):
    """يتعامل مع الملفات المرسلة (txt)"""
    file = update.message.document

    if not file.file_name.endswith(".txt"):
        update.message.reply_text("⚠️ من فضلك أرسل ملف .txt فقط.")
        return

    # طلب اسم الكويز
    update.message.reply_text("🎯 من فضلك أدخل اسم الكويز:")
    context.user_data["file_id"] = file.file_id
    context.user_data["awaiting_quiz_name_file"] = True


def handle_quiz_name_file(update: Update, context: CallbackContext):
    """يستقبل اسم الكويز بعد إرسال ملف"""
    quiz_name = update.message.text.strip()
    file_id = context.user_data.get("file_id")

    if not quiz_name:
        update.message.reply_text("⚠️ لا يمكن ترك الاسم فارغًا. حاول مرة أخرى:")
        return

    update.message.reply_text("⏳ جاري إنشاء النموذج من الملف...")

    try:
        # تنزيل الملف المؤقت
        new_file = context.bot.get_file(file_id)
        temp_path = os.path.join(tempfile.gettempdir(), "questions.txt")
        new_file.download(temp_path)

        # تشغيل السكربت
        result = subprocess.run(
            ["python", SCRIPT_PATH, "--title", quiz_name, "--questions", temp_path],
            capture_output=True, text=True
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode == 0:
            update.message.reply_text("✅ تم إنشاء الكويز بنجاح!\n\n" + output)
        else:
            update.message.reply_text(f"❌ حدث خطأ أثناء الإنشاء:\n{error or output}")

    except Exception as e:
        update.message.reply_text(f"⚠️ حدث خطأ غير متوقع: {e}")

    finally:
        context.user_data.clear()
        if os.path.exists(temp_path):
            os.remove(temp_path)


def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))

    # استلام ملف txt
    dp.add_handler(MessageHandler(Filters.document.mime_type("text/plain"), handle_document))

    # استقبال اسم الكويز بعد إرسال ملف
    dp.add_handler(MessageHandler(
        Filters.text & Filters.chat_type.private & (Filters.regex(r"^.+$")),
        lambda u, c: handle_quiz_name_file(u, c) if c.user_data.get("awaiting_quiz_name_file")
        else handle_quiz_name(u, c) if c.user_data.get("awaiting_quiz_name")
        else handle_message(u, c)
    ))

    updater.start_polling()
    logger.info("Bot started successfully.")
    updater.idle()


if __name__ == "__main__":
    main()
