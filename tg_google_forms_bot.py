import os
import logging
import tempfile
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    CallbackQueryHandler,
)

# إعداد التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "ضع_توكن_البوت_هنا"
SCRIPT_PATH = "google_forms_automator_fixed.py"


# --------------------------- دالة إرسال رسالة مع زر إنشاء كويز ---------------------------
def send_message(chat_id: int, context: CallbackContext, text: str):
    """إرسال أي رسالة مع زر إنشاء كويز جديد دائمًا"""
    keyboard = [[InlineKeyboardButton("🪄 إنشاء كويز جديد", callback_data="create_quiz")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="Markdown")


# --------------------------- دالة إرسال رابط الكويز ---------------------------
def send_quiz_link(chat_id: int, context: CallbackContext, quiz_url: str):
    """إرسال رسالة نجاح تحتوي على رابط الكويز + زر فتح + زر إنشاء كويز جديد"""
    text = (
        "✅ *تم إنشاء الكويز بنجاح!*\n\n"
        f"🔗 رابط الكويز: `{quiz_url}`\n\n"
        "اضغط على الزر أدناه لفتحه مباشرة أو انسخ الرابط أعلاه.\n\n"
        "🖊️ تم التطوير بواسطة: ADEl EL-GAWAD"
    )
    
    keyboard = [
        [InlineKeyboardButton("فتح الكويز 🎯", url=quiz_url)],
        [InlineKeyboardButton("🪄 إنشاء كويز جديد", callback_data="create_quiz")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="Markdown")


# --------------------------- رسالة /help ---------------------------
def send_help_text(chat_id: int, context: CallbackContext):
    help_text = (
        "*ℹ️ تعليمات البوت لإرسال الأسئلة:*\n\n"
        "1️⃣ أرسل لي **ملف الأسئلة بصيغة .txt** أو الصق الأسئلة مباشرة.\n"
        "2️⃣ كل سؤال يجب أن يكون بالشكل التالي:\n"
        "   سؤال: ما عاصمة مصر؟\n"
        "   اختيارات: القاهرة | باريس | لندن\n"
        "   إجابة: القاهرة\n"
        "   نقاط: 1\n\n"
        "💡 يمكنك الضغط على الزر 🪄 لإنشاء كويز جديد في أي وقت.\n\n"
        "🖊️ تم التطوير بواسطة: ADEl EL-GAWAD"
    )
    send_message(chat_id, context, help_text)


# --------------------------- الأوامر ---------------------------
def start(update: Update, context: CallbackContext):
    context.user_data.clear()
    chat_id = update.effective_chat.id
    send_help_text(chat_id, context)
    context.user_data["step"] = "awaiting_questions"


def help_command(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    send_help_text(chat_id, context)


def create_command(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    context.user_data.clear()
    send_message(chat_id, context, "🎯 من فضلك أرسل ملف الأسئلة (.txt) أو الصق الأسئلة مباشرة:")
    context.user_data["step"] = "awaiting_questions"


def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    context.user_data.clear()
    chat_id = query.message.chat.id
    send_message(chat_id, context, "🎯 من فضلك أرسل ملف الأسئلة (.txt) أو الصق الأسئلة مباشرة:")
    context.user_data["step"] = "awaiting_questions"


# --------------------------- استقبال الملفات والنصوص ---------------------------
def handle_document(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if context.user_data.get("step") != "awaiting_questions":
        send_message(chat_id, context, "⚠️ اضغط على زر 🪄 لإنشاء كويز جديد أولاً.")
        return

    file = update.message.document
    if not file.file_name.endswith(".txt"):
        send_message(chat_id, context, "⚠️ من فضلك أرسل ملف .txt فقط.")
        return

    context.user_data["file_id"] = file.file_id
    context.user_data["step"] = "awaiting_quiz_name"
    send_message(chat_id, context, "🎯 من فضلك أدخل اسم الكويز:")


def handle_text(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    step = context.user_data.get("step")

    if step == "awaiting_questions":
        text = update.message.text.strip()
        if not text:
            send_message(chat_id, context, "⚠️ الرجاء إرسال نص الأسئلة أو ملف .txt.")
            return
        context.user_data["questions_text"] = text
        context.user_data["step"] = "awaiting_quiz_name"
        send_message(chat_id, context, "🎯 من فضلك أدخل اسم الكويز:")
        return

    elif step == "awaiting_quiz_name":
        quiz_name = update.message.text.strip()
        if not quiz_name:
            send_message(chat_id, context, "⚠️ لا يمكن ترك الاسم فارغًا، حاول مرة أخرى:")
            return
        context.user_data["quiz_name"] = quiz_name
        start_quiz_creation(update, context)
        return

    else:
        send_message(chat_id, context, "⚠️ اضغط على زر 🪄 لإنشاء كويز جديد أولاً.")


# --------------------------- إنشاء الكويز ---------------------------
def start_quiz_creation(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    quiz_name = context.user_data.get("quiz_name")
    text = context.user_data.get("questions_text")
    file_id = context.user_data.get("file_id")

    send_message(chat_id, context, "⏳ جاري إنشاء النموذج، يرجى الانتظار قليلاً...")

    temp_path = None
    try:
        if text:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as temp:
                temp.write(text)
                temp_path = temp.name
        elif file_id:
            file = context.bot.get_file(file_id)
            temp_path = os.path.join(tempfile.gettempdir(), "questions.txt")
            file.download(temp_path)
        else:
            send_message(chat_id, context, "⚠️ لم يتم العثور على الأسئلة.")
            return

        result = subprocess.run(
            ["python", SCRIPT_PATH, "--title", quiz_name, "--questions", temp_path],
            capture_output=True, text=True
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode == 0:
            # نفترض أن آخر سطر من stdout هو رابط الكويز
            quiz_url = output.splitlines()[-1].strip()
            send_quiz_link(chat_id, context, quiz_url)
        else:
            send_message(chat_id, context, f"❌ حدث خطأ أثناء الإنشاء:\n{error or output}")

    except Exception as e:
        send_message(chat_id, context, f"⚠️ حدث خطأ غير متوقع: {e}")

    finally:
        context.user_data.clear()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# --------------------------- تشغيل البوت ---------------------------
def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("create", create_command))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.document.mime_type("text/plain"), handle_document))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    updater.start_polling()
    logger.info("✅ Bot started and waiting for messages.")
    updater.idle()


if __name__ == "__main__":
    main()
