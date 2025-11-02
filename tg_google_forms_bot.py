import os, json

# حفظ بيانات Google من متغيرات البيئة (لأن Railway لا يحتفظ بملفات دائمة)
creds_env = os.environ.get("CREDENTIALS_JSON")
token_env = os.environ.get("TOKEN_JSON")

if creds_env:
    with open("credentials.json", "w", encoding="utf-8") as f:
        f.write(creds_env)

if token_env:
    with open("token.json", "w", encoding="utf-8") as f:
        f.write(token_env)

import logging
from functools import wraps
from tempfile import NamedTemporaryFile
from telegram import Update, BotCommand
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from google_forms_automator_fixed import (
    get_forms_service,
    create_form,
    load_questions_from_txt,
    update_form_with_requests,
    build_choice_question_item
)

BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def owner_only(func):
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        if OWNER_ID and update.effective_user.id != OWNER_ID:
            update.message.reply_text("❌ هذه الخاصية متاحة فقط لمالك البوت.")
            return
        return func(update, context, *args, **kwargs)
    return wrapped

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 مرحبًا!\n"
        "أرسل لي ملف الأسئلة (.txt) بنفس تنسيق الملف في Google Forms Automator وسأنشئ لك النموذج.\n\n"
        "/create - لإنشاء نموذج جديد\n"
        "/help - للمساعدة"
    )

def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("أرسل ملف نصي فيه الأسئلة بصيغة:\n"
                              "سؤال: ...\nاختيارات: ... | ...\nإجابة: ...\nنقاط: ...")

def create_handler(update: Update, context: CallbackContext):
    msg = update.message
    doc = msg.document
    if doc and doc.mime_type.startswith("text/"):
        file = doc.get_file()
        with NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            file.download(custom_path=tmp.name)
            questions_path = tmp.name
    else:
        update.message.reply_text("📎 أرسل ملف الأسئلة كـ .txt")
        return

    progress = update.message.reply_text("⏳ جاري إنشاء النموذج...")
    try:
        service = get_forms_service("credentials.json", "token.json")
        form = create_form(service, "Telegram Quiz", "تم إنشاؤه عبر بوت التليجرام")
        form_id = form["formId"]
        questions = load_questions_from_txt(questions_path)

        requests = [{"updateSettings": {"settings": {"quizSettings": {"isQuiz": True}},
                                        "updateMask": "quizSettings.isQuiz"}}]
        for q in questions:
            item = build_choice_question_item(q['title'], q['choices'], q['correct'], q['points'])
            requests.append(item)

        update_form_with_requests(service, form_id, requests)
        link = f"https://docs.google.com/forms/d/{form_id}/edit"
        progress.edit_text(f"✅ تم إنشاء النموذج!\n🔗 {link}")
    except Exception as e:
        logger.exception(e)
        progress.edit_text(f"❌ حدث خطأ: {e}")

def main():
    if not BOT_TOKEN:
        print("❌ ضع توكن البوت في متغير TG_BOT_TOKEN.")
        return
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_cmd))
    dp.add_handler(CommandHandler("create", create_handler))
    dp.add_handler(MessageHandler(Filters.document.mime_type("text/plain"), create_handler))
    updater.bot.set_my_commands([BotCommand("start", "ابدأ"), BotCommand("create", "إنشاء نموذج"), BotCommand("help", "مساعدة")])
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
