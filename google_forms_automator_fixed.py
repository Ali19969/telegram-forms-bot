"""
google_forms_automator_fixed.py
الإصدار الذكي (يدعم متغيرات البيئة في Railway) ✅
-------------------------------------------------
- إذا لم يجد credentials.json أو token.json في النظام،
  يقوم بإنشائهما من متغيرات البيئة CREDENTIALS_JSON و TOKEN_JSON.
"""

import os
import json
import logging
import argparse
import re
from typing import List, Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/forms.body"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def ensure_credentials_files():
    """يتحقق من وجود ملفات Google API أو إنشائها من متغيرات البيئة"""
    # credentials.json
    if not os.path.exists(CREDENTIALS_FILE):
        env_data = os.getenv("CREDENTIALS_JSON")
        if env_data:
            try:
                with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
                    f.write(env_data)
                logger.info("✅ تم إنشاء credentials.json من متغير البيئة.")
            except Exception as e:
                logger.error("⚠️ فشل إنشاء credentials.json: %s", e)
        else:
            logger.warning("⚠️ لم يتم العثور على CREDENTIALS_JSON في المتغيرات.")

    # token.json
    if not os.path.exists(TOKEN_FILE):
        env_token = os.getenv("TOKEN_JSON")
        if env_token:
            try:
                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    f.write(env_token)
                logger.info("✅ تم إنشاء token.json من متغير البيئة.")
            except Exception as e:
                logger.error("⚠️ فشل إنشاء token.json: %s", e)


def sanitize_text(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", str(s))


def get_forms_service():
    """تجهيز خدمة Google Forms"""
    ensure_credentials_files()

    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            logger.info("Loaded credentials from token file.")
        except Exception as e:
            logger.warning("Error loading token: %s", e)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError("ملف credentials.json مفقود.")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())
            logger.info("Saved new token.")
    return build("forms", "v1", credentials=creds)


# 🔽 بقية الكود كما في آخر إصدار (نفس المميزات السابقة) 🔽

def create_form(service, title, description=None):
    body = {"info": {"title": sanitize_text(title)}}
    logger.info("Creating form: %s", title)
    created = service.forms().create(body=body).execute()
    if description:
        try:
            service.forms().batchUpdate(
                formId=created["formId"],
                body={
                    "requests": [
                        {
                            "updateFormInfo": {
                                "info": {"description": sanitize_text(description)},
                                "updateMask": "description",
                            }
                        }
                    ]
                },
            ).execute()
            logger.info("Description added successfully.")
        except Exception as e:
            logger.warning("Failed to add description: %s", e)
    return created


def build_choice_question_item(title: str, choices: List[str], correct_answer: str = None, points: int = 0):
    title = sanitize_text(title)
    sanitized_choices = [sanitize_text(c) for c in choices]
    choice_objects = [{"value": c} for c in sanitized_choices]
    question_obj = {
        "question": {
            "required": False,
            "choiceQuestion": {"type": "RADIO", "options": choice_objects}
        }
    }
    if correct_answer:
        try:
            idx = sanitized_choices.index(sanitize_text(correct_answer))
            question_obj["question"]["grading"] = {
                "pointValue": int(points) if points else 0,
                "correctAnswers": {"answers": [{"value": sanitized_choices[idx]}]}
            }
        except ValueError:
            logger.warning("الإجابة '%s' غير موجودة ضمن الخيارات للسؤال '%s'", correct_answer, title)
    return {
        "createItem": {
            "item": {"title": title, "questionItem": question_obj},
            "location": {"index": 0}
        }
    }


def update_form_with_requests(service, form_id: str, requests: List[Dict[str, Any]]):
    if not requests:
        return None
    try:
        resp = service.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()
        logger.info("batchUpdate applied successfully to form %s", form_id)
        return resp
    except HttpError as e:
        logger.error("HttpError: %s", e)
        raise


def parse_questions_from_text(content: str) -> List[Dict[str, Any]]:
    blocks = re.split(r"\n\s*\n+", content.strip())
    questions = []
    for block in blocks:
        q = {"title": None, "choices": [], "correct": None, "points": 0}
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("سؤال:"):
                q["title"] = line.replace("سؤال:", "").strip()
            elif line.startswith("اختيارات:"):
                opts = line.replace("اختيارات:", "").strip()
                q["choices"] = [opt.strip() for opt in opts.split("|") if opt.strip()]
            elif line.startswith("إجابة:"):
                q["correct"] = line.replace("إجابة:", "").strip() or None
            elif line.startswith("نقاط:"):
                val = line.replace("نقاط:", "").strip()
                q["points"] = int(val) if val.isdigit() else 0
        if q["title"] and q["choices"]:
            questions.append(q)
    return questions


def load_questions(path_or_text: str, from_file: bool = True) -> List[Dict[str, Any]]:
    if from_file:
        if not os.path.exists(path_or_text):
            raise FileNotFoundError(f"ملف الأسئلة غير موجود: {path_or_text}")
        with open(path_or_text, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = path_or_text
    return parse_questions_from_text(content)


def ask_for_quiz_name() -> str:
    while True:
        title = input("🎯 أدخل اسم الكويز: ").strip()
        if title:
            return title
        print("⚠️ لا يمكن ترك الاسم فارغًا، حاول مرة أخرى.")


def main():
    parser = argparse.ArgumentParser(description="إنشاء Google Form من ملف أو نص للأسئلة")
    parser.add_argument("--title", "-t", default="", help="عنوان النموذج")
    parser.add_argument("--description", "-d", default="", help="وصف النموذج")
    parser.add_argument("--questions", "-q", default="", help="ملف الأسئلة (txt)")
    parser.add_argument("--text", "-x", default="", help="نص الأسئلة مباشرة")
    args = parser.parse_args()

    if not args.title:
        args.title = ask_for_quiz_name()

    service = get_forms_service()
    form = create_form(service, args.title, args.description)
    form_id = form["formId"]

    requests = [{
        "updateSettings": {
            "settings": {"quizSettings": {"isQuiz": True}},
            "updateMask": "quizSettings.isQuiz"
        }
    }]

    if args.text:
        questions = load_questions(args.text, from_file=False)
    else:
        qfile = args.questions or "questions.txt"
        questions = load_questions(qfile, from_file=True)

    for q in questions:
        item = build_choice_question_item(q["title"], q["choices"], q["correct"], q["points"])
        requests.append(item)

    update_form_with_requests(service, form_id, requests)

    form_url = form.get("responderUri")
    if not form_url:
        form_url = f"https://docs.google.com/forms/d/e/{form_id}/viewform"

    print("\n✅ تم إنشاء النموذج بنجاح!")
    print("📄 اسم الكويز:", args.title)
    print("🔗 رابط العرض:", form_url)


if __name__ == "__main__":
    main()
