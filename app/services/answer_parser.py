"""Google Forms APIの回答データを、アプリ内で扱う形式へ変換する。

フォームごとに質問名が異なるため、特定の質問名に依存せず、
質問タイトルのキーワードから名前・メールアドレス・本文を推測する。
該当する質問が見つからなくてもエラーにしない。
"""
import re
from datetime import datetime, timezone

SUMMARY_LENGTH = 100

NAME_KEYWORDS = ["お名前", "氏名", "名前", "おなまえ", "name", "ニックネーム"]
EMAIL_KEYWORDS = ["メールアドレス", "メール", "email", "e-mail", "mail", "連絡先"]
BODY_KEYWORDS = [
    "お問い合わせ内容", "お問い合わせ", "問い合わせ", "ご意見", "フィードバック",
    "ご要望", "メッセージ", "本文", "内容", "詳細", "ご感想", "感想",
]

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def build_question_map(form_data):
    """Forms APIのフォーム定義から {questionId: (順序, 質問タイトル)} を作る。"""
    question_map = {}
    order = 0
    for item in form_data.get("items", []):
        title = item.get("title") or "無題の質問"
        question_item = item.get("questionItem")
        if question_item:
            question = question_item.get("question", {})
            question_id = question.get("questionId")
            if question_id:
                question_map[question_id] = (order, title)
                order += 1
            continue
        # 質問グループ(グリッド等)にも対応する
        group = item.get("questionGroupItem")
        if group:
            for question in group.get("questions", []):
                question_id = question.get("questionId")
                row_title = (question.get("rowQuestion") or {}).get("title") or ""
                label = f"{title} - {row_title}" if row_title else title
                if question_id:
                    question_map[question_id] = (order, label)
                    order += 1
    return question_map


def _extract_answer_value(answer):
    """回答形式(テキスト・複数選択・ファイル等)ごとに値を取り出す。"""
    text_answers = answer.get("textAnswers")
    if text_answers:
        values = [a.get("value", "") for a in text_answers.get("answers", [])]
        return values[0] if len(values) == 1 else values

    file_answers = answer.get("fileUploadAnswers")
    if file_answers:
        values = [a.get("fileName", "アップロードファイル") for a in file_answers.get("answers", [])]
        return values[0] if len(values) == 1 else values

    grade = answer.get("grade")
    if grade is not None:
        return "正解" if grade.get("correct") else "不正解"

    return ""


def _answer_to_text(value):
    if isinstance(value, list):
        return "、".join(str(v) for v in value)
    return str(value or "")


def _match_keywords(title, keywords):
    lowered = (title or "").lower()
    return any(k.lower() in lowered for k in keywords)


def parse_submitted_at(api_response):
    """createTime / lastSubmittedTime をFirestore Timestamp互換のdatetimeへ変換する。"""
    raw = api_response.get("lastSubmittedTime") or api_response.get("createTime")
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def parse_response(question_map, api_response):
    """Forms APIの1回答を、Firestoreへ保存するdictへ変換する。"""
    answers = {}
    ordered = []
    for question_id, answer in (api_response.get("answers") or {}).items():
        order, title = question_map.get(question_id, (9999, "削除された質問"))
        value = _extract_answer_value(answer)
        answers[question_id] = {
            "question_id": question_id,
            "question": title,
            "answer": value,
            "order": order,
        }
        ordered.append((order, title, value))
    ordered.sort(key=lambda x: x[0])

    respondent_name = ""
    respondent_email = api_response.get("respondentEmail") or ""
    body = ""

    for _, title, value in ordered:
        text = _answer_to_text(value)
        if not respondent_name and _match_keywords(title, NAME_KEYWORDS):
            respondent_name = text
        if not respondent_email and _match_keywords(title, EMAIL_KEYWORDS):
            match = EMAIL_PATTERN.search(text)
            respondent_email = match.group(0) if match else text
        if not body and _match_keywords(title, BODY_KEYWORDS):
            body = text

    # メールアドレスらしき回答が見つからない場合、全回答から探す
    if not respondent_email:
        for _, _, value in ordered:
            match = EMAIL_PATTERN.search(_answer_to_text(value))
            if match:
                respondent_email = match.group(0)
                break

    # 本文が推測できない場合は、名前・メール以外の最初の回答を本文にする
    if not body:
        for _, title, value in ordered:
            if _match_keywords(title, NAME_KEYWORDS) or _match_keywords(title, EMAIL_KEYWORDS):
                continue
            text = _answer_to_text(value)
            if text:
                body = text
                break
    if not body and ordered:
        body = _answer_to_text(ordered[0][2])

    search_parts = [respondent_name, respondent_email]
    for _, title, value in ordered:
        search_parts.append(title)
        search_parts.append(_answer_to_text(value))
    search_text = " ".join(p for p in search_parts if p).lower()

    return {
        "respondent_name": respondent_name,
        "respondent_email": respondent_email,
        "summary_text": body[:SUMMARY_LENGTH],
        "search_text": search_text,
        "submitted_at": parse_submitted_at(api_response),
        "answers": answers,
    }
