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

# إعداد التسجيل (Logs)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# التوكن
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "ضع_توكن_البوت_هنا"

# مسار السكربت الأساسي
SCRIPT_PATH = "google_forms_automator_fixed.py"


# --------------------------- دالة موحدة لإرسال الرسائل ---------------------------
def send_message(chat_id, context: CallbackContext, text: str):
    """
    إرسال أي رسالة مع زر إنشاء كويز جديد دائمًا.
    يعمل مع الضغط على الزر أو أي رسالة نصية.
    """
    keyboard = [[InlineKeyboardButton("🪄 إنشاء كويز جديد", callback_data="create_quiz")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


def send_welcome_message(update_or_context, context: CallbackContext):
    """رسالة الترحيب"""
    welcome_message = (
        "👋 أهلاً بك!\n"
        "أرسل لي الآن ملف الأسئلة (.txt)\n"
        "أو الصق الأسئلة مباشرة في الرسالة.\n\n"
        "كل سؤال يجب أن يكون مثل المثال التالي:\n"
        "سؤال: ما عاصمة مصر؟\n"
        "اختيارات: القاهرة | باريس | لندن\n"
        "إجابة: القاهرة\n"
        "نقاط: 1"
    )

    if isinstance(update_or_context, Update):
        chat_id = update_or_context.effective_chat.id
    else:
        chat_id = update_or_context  # إذا تم تمرير chat_id مباشرة

    send_message(chat_id, context, welcome_message)


# --------------------------- المرحلة 1: الترحيب ---------------------------
def start(update: Update, context: CallbackContext):
    """رسالة الترحيب عند /start"""
    context.user_data.clear()
    send_welcome_message(update, context)
    context.user_data["step"] = "awaiting_questions"


def button_handler(update: Update, context: CallbackContext):
    """معالجة الضغط على زر Inline"""
    query = update.callback_query
    query.answer()  # يجب دائمًا الرد على callback_query

    # مسح بيانات المستخدم
    context.user_data.clear()

    # إرسال رسالة بدء كويز جديد
    send_message(query.effective_chat.id, context, "🎯 من فضلك أرسل ملف الأسئلة (.txt) أو الصق الأسئلة مباشرة:")
    context.user_data["step"] = "awaiting_questions"


# --------------------------- المرحلة 2: استلام الأسئلة ---------------------------
def handle_document(update: Update, context: CallbackContext):
    """عند إرسال ملف .txt"""
    if context.user_data.get("step") != "awaiting_questions":
        send_message(update.effective_chat.id, context, "⚠️ اضغط على زر 🪄 لإنشاء كويز جديد أولاً.")
        return

    file = update.message.document
    if not file.file_name.endswith(".txt"):
        send_message(update.effective_chat.id, context, "⚠️ من فضلك أرسل ملف .txt فقط.")
        return

    context.user_data["file_id"] = file.file_id
    context.user_data["step"] = "awaiting_quiz_name"
    send_message(update.effective_chat.id, context, "🎯 من فضلك أدخل اسم الكويز:")


def handle_text(update: Update, context: CallbackContext):
    """عند إرسال الأسئلة نصيًا أو إدخال اسم الكويز"""
    step = context.user_data.get("step")

    if step == "awaiting_questions":
        text = update.message.text.strip()
        if not text:
            send_message(update.effective_chat.id, context, "⚠️ الرجاء إرسال نص الأسئلة أو ملف .txt.")
            return
        context.user_data["questions_text"] = text
        context.user_data["step"] = "awaiting_quiz_name"
        send_message(update.effective_chat.id, context, "🎯 من فضلك أدخل اسم الكويز:")
        return

    elif step == "awaiting_quiz_name":
        quiz_name = update.message.text.strip()
        if not quiz_name:
            send_message(update.effective_chat.id, context, "⚠️ لا يمكن ترك الاسم فارغًا، حاول مرة أخرى:")
            return
        context.user_data["quiz_name"] = quiz_name
        start_quiz_creation(update, context)
        return

    else:
        send_message(update.effective_chat.id, context, "⚠️ اضغط على زر 🪄 لإنشاء كويز جديد أولاً.")


# --------------------------- المرحلة 3: الإنشاء ---------------------------
def start_quiz_creation(update: Update, context: CallbackContext):
    """إنشاء النموذج"""
    quiz_name = context.user_data.get("quiz_name")
    text = context.user_data.get("questions_text")
    file_id = context.user_data.get("file_id")

    send_message(update.effective_chat.id, context, "⏳ جاري إنشاء النموذج، يرجى الانتظار قليلاً...")

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
            send_message(update.effective_chat.id, context, "⚠️ لم يتم العثور على الأسئلة.")
            return

        result = subprocess.run(
            ["python", SCRIPT_PATH, "--title", quiz_name, "--questions", temp_path],
            capture_output=True, text=True
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode == 0:
            send_message(update.effective_chat.id, context, "✅ تم إنشاء الكويز بنجاح!\n\n" + output)
        else:
            send_message(update.effective_chat.id, context, f"❌ حدث خطأ أثناء الإنشاء:\n{error or output}")

    except Exception as e:
        send_message(update.effective_chat.id, context, f"⚠️ حدث خطأ غير متوقع: {e}")

    finally:
        context.user_data.clear()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# --------------------------- المرحلة 4: التشغيل ---------------------------
def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    # الأوامر
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))

    # استقبال ملف txt
    dp.add_handler(MessageHandler(Filters.document.mime_type("text/plain"), handle_document))

    # استقبال الرسائل النصية
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    updater.start_polling()
    logger.info("✅ Bot started and waiting for messages.")
    updater.idle()


if __name__ == "__main__":
    main()
