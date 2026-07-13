"""Google Drive APIによるGoogleフォーム一覧の取得。

drive.metadata.readonly スコープのみを使用し、
Googleフォーム(application/vnd.google-apps.form)だけを対象にする。
"""
import logging

logger = logging.getLogger(__name__)

FORM_MIME_TYPE = "application/vnd.google-apps.form"


def list_google_forms(credentials):
    """ユーザーが所有またはアクセスできるGoogleフォームの一覧を返す。"""
    from googleapiclient.discovery import build

    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    forms = []
    page_token = None
    while True:
        result = service.files().list(
            q=f"mimeType='{FORM_MIME_TYPE}' and trashed=false",
            fields="nextPageToken, files(id, name, modifiedTime, webViewLink)",
            orderBy="modifiedTime desc",
            pageSize=100,
            pageToken=page_token,
        ).execute()
        forms.extend(result.get("files", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return forms
