"""
google_forms_automator_fixed.py (إصدار نهائي)
=============================================
- إصلاح مشكلة ترتيب التحديثات: يتم تفعيل وضع الاختبار (isQuiz=True) أولاً قبل إضافة الأسئلة.
- إضافة سؤال تفاعلي في البداية لاسم الكويز (إذا لم يُمرر بالوسائط).
- في النهاية، طباعة رابط النموذج (Form link) بجانب الـ Form ID.
- استمرار الاعتماد على ملف نصي للأسئلة بنفس التنسيق السابق.

تنسيق ملف questions.txt:
-------------------------
سؤال: ما هي عاصمة مصر؟
اختيارات: القاهرة | الإسكندرية | الأقصر | أسوان
إجابة: القاهرة
نقاط: 2

سؤال: أي من اللغات التالية لغة برمجة؟
اختيارات: HTML | Python | CSS | Markdown
إجابة: Python
نقاط: 1
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

def sanitize_text(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", str(s))

def get_forms_service(credentials_file: str = CREDENTIALS_FILE, token_file: str = TOKEN_FILE):
    creds = None
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            logger.info("Loaded credentials from %s", token_file)
        except Exception as e:
            logger.warning("Failed reading token file: %s", e)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("Refreshed credentials using refresh token")
            except Exception as e:
                logger.warning("Failed to refresh credentials: %s", e)
                creds = None
        if not creds:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(f"Credentials file not found: {credentials_file}")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
            logger.info("Saved new token to %s", token_file)

    service = build('forms', 'v1', credentials=creds)
    return service

def create_form(service, title: str, description: str = "") -> Dict[str, Any]:
    body = {'info': {'title': sanitize_text(title), 'documentTitle': sanitize_text(title)}}
    if description:
        body['info']['description'] = sanitize_text(description)

    try:
        logger.info("Creating form: %s", title)
        created = service.forms().create(body=body).execute()
        return created
    except HttpError as e:
        _log_http_error(e, "creating form")
        raise

def build_choice_question_item(title: str, choices: List[str], correct_answer: str = None, points: int = 0) -> Dict[str, Any]:
    title = sanitize_text(title)
    sanitized_choices = [sanitize_text(c) for c in choices]
    choice_objects = [{'value': c} for c in sanitized_choices]

    question_obj = {
        'question': {
            'required': False,
            'choiceQuestion': {
                'type': 'RADIO',
                'options': choice_objects
            }
        }
    }

    if correct_answer is not None:
        try:
            idx = sanitized_choices.index(sanitize_text(correct_answer))
            question_obj['question']['grading'] = {
                'pointValue': int(points) if points else 0,
                'correctAnswers': {
                    'answers': [{'value': sanitized_choices[idx]}]
                }
            }
        except ValueError:
            logger.warning("Correct answer '%s' not found in choices for question '%s'", correct_answer, title)

    return {
        'createItem': {
            'item': {
                'title': title,
                'questionItem': question_obj
            },
            'location': {'index': 0}
        }
    }

def update_form_with_requests(service, form_id: str, requests: List[Dict[str, Any]]):
    if not requests:
        logger.info("No requests to apply for form %s", form_id)
        return None
    try:
        resp = service.forms().batchUpdate(formId=form_id, body={'requests': requests}).execute()
        logger.info("batchUpdate applied successfully to form %s", form_id)
        return resp
    except HttpError as e:
        _log_http_error(e, f"batchUpdate on form {form_id}")
        raise

def _log_http_error(e: HttpError, context_msg: str = ""):
    logger.error("HttpError while %s: %s", context_msg, e)
    try:
        content = e.content.decode() if isinstance(e.content, (bytes, bytearray)) else str(e.content)
        parsed = json.loads(content)
        logger.error("Error details: %s", json.dumps(parsed, indent=2, ensure_ascii=False))
    except Exception:
        logger.warning("Could not parse HttpError content: %s", getattr(e, 'content', None))

def load_questions_from_txt(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Questions file not found: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    blocks = re.split(r'\n\s*\n+', content)
    questions = []

    for block in blocks:
        q = {'title': None, 'choices': [], 'correct': None, 'points': 0}
        for line in block.splitlines():
            line = line.strip()
            if line.startswith('سؤال:'):
                q['title'] = line.replace('سؤال:', '').strip()
            elif line.startswith('اختيارات:'):
                opts = line.replace('اختيارات:', '').strip()
                q['choices'] = [opt.strip() for opt in opts.split('|') if opt.strip()]
            elif line.startswith('إجابة:'):
                q['correct'] = line.replace('إجابة:', '').strip() or None
            elif line.startswith('نقاط:'):
                val = line.replace('نقاط:', '').strip()
                q['points'] = int(val) if val.isdigit() else 0
        if q['title'] and q['choices']:
            questions.append(q)
    return questions

def main():
    parser = argparse.ArgumentParser(description='إنشاء Google Form من ملف نصي للأسئلة')
    parser.add_argument('--title', '-t', default='', help='عنوان النموذج')
    parser.add_argument('--description', '-d', default='', help='وصف النموذج')
    parser.add_argument('--questions', '-q', default='questions.txt', help='ملف الأسئلة النصي')
    args = parser.parse_args()

    # إن لم يتم تمرير العنوان كوسيط، اطلبه من المستخدم
    if not args.title:
        args.title = input("أدخل اسم الكويز: ").strip() or "نموذج جديد"

    service = get_forms_service()
    created = create_form(service, args.title, args.description)
    form_id = created.get('formId')

    if not form_id:
        logger.error("لم يتم الحصول على formId من Google API")
        return

    # تحميل الأسئلة
    questions = load_questions_from_txt(args.questions)

    # ترتيب الطلبات: فعّل isQuiz أولاً، ثم الأسئلة، ثم الوصف
    requests = []

    # 1️⃣ تفعيل وضع الكويز
    requests.append({
        "updateSettings": {
            "settings": {"quizSettings": {"isQuiz": True}},
            "updateMask": "quizSettings.isQuiz"
        }
    })

    # 2️⃣ إضافة الأسئلة
    for q in questions:
        item = build_choice_question_item(q['title'], q['choices'], q['correct'], q['points'])
        requests.append(item)

    # 3️⃣ إضافة الوصف (اختياري)
    if args.description:
        requests.append({
            "updateFormInfo": {
                "info": {"description": sanitize_text(args.description)},
                "updateMask": "description"
            }
        })

    try:
        update_form_with_requests(service, form_id, requests)
    except Exception as e:
        logger.exception("فشل في تطبيق التحديثات: %s", e)
        return

    form_url = created.get('responderUri') or f"https://docs.google.com/forms/d/{form_id}/edit"

    logger.info("تم إنشاء الكويز بنجاح!")
    print("\n✅ تم إنشاء كويز جديد بنجاح!")
    print("📄 الاسم:", args.title)
    print("🆔 Form ID:", form_id)
    print("🔗 رابط النموذج:", form_url)

if __name__ == '__main__':
    main()
