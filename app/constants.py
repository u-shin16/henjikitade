STATUS_UNHANDLED = "unhandled"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_ON_HOLD = "on_hold"

STATUSES = [
    STATUS_UNHANDLED,
    STATUS_IN_PROGRESS,
    STATUS_COMPLETED,
    STATUS_ON_HOLD,
]

STATUS_LABELS = {
    STATUS_UNHANDLED: "未対応",
    STATUS_IN_PROGRESS: "対応中",
    STATUS_COMPLETED: "対応済み",
    STATUS_ON_HOLD: "保留",
}

APP_NAME = "返事きたで"
APP_DESCRIPTION = "複数のGoogleフォームに届いた問い合わせを、一括確認・対応管理できるWebアプリ"

ADMIN_MEMO_MAX_LENGTH = 2000
