"""
google_forms_automator_fixed.py
الإصدار النهائي الكامل ✅
----------------------------------------------
- إنشاء Google Form بالعنوان فقط.
- ثم إضافة الوصف والأسئلة عبر batchUpdate.
- إصلاح دعم الاستدعاء من بوت التيليجرام (3 وسائط).
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

# إعداد الصلاحيات
SCOPES = ["https://www.googleapis.com/auth/forms.body"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

# إعداد السجلات
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def sanitize_text(s: str) -> str:
    """تنظيف النص من رموز غير صالحة"""
    if s is None:
        return ""
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", str(s))


def get_forms_service(credentials_file=CREDENTIALS_FILE, token_file=TOKEN_FILE):
    """تجهيز خدمة Google Forms"""
    creds = None
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            logger.info("Loaded credentials from token file.")
        except Exception as e:
            logger.warning("Error loading token: %s", e)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError("ملف credentials.json مفقود.")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_file, "w") as token:
                token.write(creds.to_json())
            logger.info("Saved new token.")
    return build("forms", "v1", credentials=creds)


def create_form(service, title, description=None):
    """
    إنشاء نموذج جديد بعنوان فقط (الوصف يُضاف لاحقًا عبر batchUpdate)
    يقبل 3 وسائط لتوافقه مع بوت التيليجرام.
    """
    body = {"info": {"title": sanitize_text(title)}}
    logger.info("Creating form: %s", title)
    created = service.forms().create(body=body).execute()

    # إضافة الوصف لاحقاً
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
    """إنشاء كائن يمثل سؤال اختيار من متعدد"""
    title = sanitize_text(title)
    sanitized_choices = [sanitize_text(c) for c in choices]
    choice_objects = [{"value": c} for c in sanitized_choices]

    question_obj = {
        "question": {
            "required": False,
            "choiceQuestion": {
                "type": "RADIO",
                "options": choice_objects
            }
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
            "item": {
                "title": title,
                "questionItem": question_obj
            },
            "location": {"index": 0}
        }
    }


def update_form_with_requests(service, form_id: str, requests: List[Dict[str, Any]]):
    """إرسال التحديثات (مثل الأسئلة والإعدادات) إلى النموذج"""
    if not requests:
        return None
    try:
        resp = service.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()
        logger.info("batchUpdate applied successfully to form %s", form_id)
        return resp
    except HttpError as e:
        logger.error("HttpError: %s", e)
        raise


def load_questions_from_txt(path: str) -> List[Dict[str, Any]]:
    """تحميل الأسئلة من ملف نصي"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"ملف الأسئلة غير موجود: {path}")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    blocks = re.split(r"\n\s*\n+", content)
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


def main():
    """البرنامج الرئيسي"""
    parser = argparse.ArgumentParser(description="إنشاء Google Form من ملف نصي للأسئلة")
    parser.add_argument("--title", "-t", default="", help="عنوان النموذج")
    parser.add_argument("--description", "-d", default="", help="وصف النموذج")
    parser.add_argument("--questions", "-q", default="questions.txt", help="ملف الأسئلة")
    args = parser.parse_args()

    if not args.title:
        args.title = input("أدخل اسم الكويز: ").strip() or "نموذج جديد"

    service = get_forms_service()
    form = create_form(service, args.title, args.description)
    form_id = form["formId"]

    # إعداد النموذج كاختبار
    requests = [{
        "updateSettings": {
            "settings": {"quizSettings": {"isQuiz": True}},
            "updateMask": "quizSettings.isQuiz"
        }
    }]

    # تحميل الأسئلة وإضافتها
    questions = load_questions_from_txt(args.questions)
    for q in questions:
        item = build_choice_question_item(q["title"], q["choices"], q["correct"], q["points"])
        requests.append(item)

    update_form_with_requests(service, form_id, requests)

    form_url = f"https://docs.google.com/forms/d/{form_id}/edit"
    print("\n✅ تم إنشاء النموذج بنجاح!")
    print("📄 العنوان:", args.title)
    print("🔗 الرابط:", form_url)


if __name__ == "__main__":
    main()
