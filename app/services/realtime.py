"""開いている受信箱へサーバー側イベントを配信する簡易ブローカー。"""
import queue
import threading

_lock = threading.Lock()
_subscribers = {}


def subscribe(user_id):
    q = queue.Queue(maxsize=20)
    with _lock:
        _subscribers.setdefault(user_id, set()).add(q)
    return q


def unsubscribe(user_id, q):
    with _lock:
        queues = _subscribers.get(user_id)
        if not queues:
            return
        queues.discard(q)
        if not queues:
            _subscribers.pop(user_id, None)


def publish(user_id, event):
    with _lock:
        queues = list(_subscribers.get(user_id, ()))

    for q in queues:
        try:
            q.put_nowait(event)
        except queue.Full:
            # 古い通知は捨てても、次のイベントや手動更新で一覧は整合する。
            pass
