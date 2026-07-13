"""Google Forms APIによるフォーム情報と回答の取得。"""
import logging

logger = logging.getLogger(__name__)


def _service(credentials):
    from googleapiclient.discovery import build

    return build("forms", "v1", credentials=credentials, cache_discovery=False)


def get_form(credentials, form_id):
    """フォームの定義(タイトル・質問一覧)を取得する。"""
    return _service(credentials).forms().get(formId=form_id).execute()


def list_all_responses(credentials, form_id):
    """フォームの全回答をページングしながら取得する。"""
    service = _service(credentials)
    responses = []
    page_token = None
    while True:
        kwargs = {"formId": form_id, "pageSize": 100}
        if page_token:
            kwargs["pageToken"] = page_token
        result = service.forms().responses().list(**kwargs).execute()
        responses.extend(result.get("responses", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return responses
