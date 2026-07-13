"""ManagedFormの集計値(response_count / unread_count / unhandled_count)の管理。

集計値はキャッシュとして扱い、ずれた場合は再計算で修正できるようにする。
"""
from datetime import datetime, time, timedelta, timezone

from app.constants import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_ON_HOLD,
    STATUS_UNHANDLED,
)


def recalculate_form_counts(form_repo, response_repo, user_id, form_id):
    """1フォーム分の集計値を回答データから数え直して保存する。"""
    counts = response_repo.count_for_form(user_id, form_id)
    form_repo.update_form(user_id, form_id, counts)
    return counts


def recalculate_all_counts(form_repo, response_repo, user_id):
    for form in form_repo.get_forms(user_id):
        recalculate_form_counts(form_repo, response_repo, user_id, form["form_id"])


def summarize_responses(responses):
    """回答一覧からサイドバー・ダッシュボード用の件数を集計する。"""
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.astimezone().date(), time.min).astimezone(timezone.utc)

    counts = {
        "total": len(responses),
        "unread": 0,
        "unhandled": 0,
        "in_progress": 0,
        "completed": 0,
        "on_hold": 0,
        "important": 0,
        "today": 0,
    }
    status_keys = {
        STATUS_UNHANDLED: "unhandled",
        STATUS_IN_PROGRESS: "in_progress",
        STATUS_COMPLETED: "completed",
        STATUS_ON_HOLD: "on_hold",
    }
    for r in responses:
        if not r.get("is_read"):
            counts["unread"] += 1
        key = status_keys.get(r.get("status"))
        if key:
            counts[key] += 1
        if r.get("is_important"):
            counts["important"] += 1
        submitted = r.get("submitted_at")
        if submitted is not None and submitted >= today_start:
            counts["today"] += 1
    return counts
