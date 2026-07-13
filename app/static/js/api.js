/**
 * fetch APIの共通ラッパー。
 * すべてのAPIレスポンスは {success, message, data} 形式のJSONを想定する。
 */
const Api = {
  async request(url, { method = "GET", body = null } = {}) {
    const headers = { "Accept": "application/json" };
    if (method !== "GET") {
      const token = document.querySelector('meta[name="csrf-token"]');
      if (token) headers["X-CSRFToken"] = token.content;
      headers["Content-Type"] = "application/json";
    }
    let res;
    try {
      res = await fetch(url, {
        method,
        headers,
        body: body != null ? JSON.stringify(body) : null,
        credentials: "same-origin",
      });
    } catch (e) {
      return { success: false, message: "通信に失敗しました。接続を確認してください" };
    }

    if (res.status === 401) {
      window.location.href = "/login";
      return { success: false, message: "ログインが必要です" };
    }

    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      data = null;
    }
    if (!data || typeof data.success === "undefined") {
      return { success: false, message: "サーバーからの応答を読み取れませんでした" };
    }
    return data;
  },

  get(url) {
    return Api.request(url);
  },

  post(url, body) {
    return Api.request(url, { method: "POST", body: body || {} });
  },
};

/** HTMLエスケープ(XSS対策)。動的な文字列は必ずこれを通して描画する。 */
function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/** 画面右下に操作結果のトーストを表示する。 */
function showToast(message, type = "info", duration = 3500) {
  const container = document.getElementById("toast-container");
  if (!container || !message) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("show"));
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

/** ISO文字列の日時を「2026/07/13 10:30」形式へ整形する。 */
function formatDateTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "-";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
