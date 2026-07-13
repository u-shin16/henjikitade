/**
 * 受信箱画面のロジック。
 * 一覧取得・絞り込み・詳細表示・ステータス変更・重要マーク・メモ保存・手動同期を
 * すべてfetch APIで行い、ページ全体の再読み込みをしない。
 */
(() => {
  const STATUS_LABELS = {
    unhandled: "未対応",
    in_progress: "対応中",
    completed: "対応済み",
    on_hold: "保留",
  };

  const state = {
    box: "all",
    formId: null,
    query: "",
    dateFrom: "",
    dateTo: "",
    order: "desc",
    responses: [],
    forms: [],
    counts: {},
    selectedKey: null, // `${formId}/${responseId}`
    loading: false,
  };

  const el = {
    boxNav: document.getElementById("box-nav"),
    formNav: document.getElementById("form-nav"),
    inboxList: document.getElementById("inbox-list"),
    detailEmpty: document.getElementById("detail-empty"),
    detailContent: document.getElementById("detail-content"),
    searchInput: document.getElementById("search-input"),
    dateFrom: document.getElementById("date-from"),
    dateTo: document.getElementById("date-to"),
    orderSelect: document.getElementById("order-select"),
    clearFilters: document.getElementById("clear-filters"),
    syncBtn: document.getElementById("sync-btn"),
    lastSynced: document.getElementById("last-synced"),
    mainLayout: document.querySelector(".main-layout"),
  };

  // --- 一覧の取得と描画 ---

  function buildQueryParams() {
    const params = new URLSearchParams();
    if (state.formId) params.set("form_id", state.formId);
    if (state.box === "unread") params.set("read", "false");
    else if (state.box === "important") params.set("important", "true");
    else if (["unhandled", "in_progress", "completed", "on_hold"].includes(state.box)) {
      params.set("status", state.box);
    }
    if (state.query) params.set("q", state.query);
    if (state.dateFrom) params.set("date_from", state.dateFrom);
    if (state.dateTo) params.set("date_to", state.dateTo);
    params.set("order", state.order);
    return params;
  }

  async function loadInbox({ quiet = false } = {}) {
    if (state.loading) return;
    state.loading = true;
    if (!quiet) {
      el.inboxList.innerHTML = '<div class="empty-state">読み込み中...</div>';
    }
    const result = await Api.get(`/api/responses?${buildQueryParams()}`);
    state.loading = false;

    if (!result.success) {
      el.inboxList.innerHTML =
        `<div class="empty-state">${escapeHtml(result.message || "回答の取得に失敗しました")}</div>`;
      return;
    }

    state.responses = result.data.responses;
    state.counts = result.data.counts;
    state.forms = result.data.forms;
    renderCounts();
    renderFormNav();
    renderList();
    renderLastSynced();
  }

  function renderCounts() {
    const c = state.counts;
    const set = (id, value) => {
      const node = document.getElementById(id);
      if (node) node.textContent = value ?? 0;
    };
    set("count-all", c.total);
    set("count-unread", c.unread);
    set("count-unhandled", c.unhandled);
    set("count-in_progress", c.in_progress);
    set("count-completed", c.completed);
    set("count-on_hold", c.on_hold);
    set("count-important", c.important);
  }

  function renderFormNav() {
    el.formNav.innerHTML = state.forms.map((f) => `
      <li>
        <button class="nav-item ${state.formId === f.form_id ? "active" : ""}"
                data-form-id="${escapeHtml(f.form_id)}">
          <span class="nav-form-title">${escapeHtml(f.title)}</span>
          <span class="nav-count">${f.unread_count > 0 ? `未読${f.unread_count}` : f.response_count}</span>
        </button>
      </li>
    `).join("");
  }

  function renderLastSynced() {
    const times = state.forms.map((f) => f.last_synced_at).filter(Boolean).sort();
    el.lastSynced.textContent = times.length
      ? `最終同期: ${formatDateTime(times[times.length - 1])}`
      : "未同期";
  }

  function statusBadge(status) {
    return `<span class="badge badge-status badge-${escapeHtml(status)}">${escapeHtml(STATUS_LABELS[status] || status)}</span>`;
  }

  function renderList() {
    if (!state.responses.length) {
      el.inboxList.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><p>まだ回答は届いていません</p></div>';
      return;
    }
    el.inboxList.innerHTML = state.responses.map((r) => {
      const key = `${r.form_id}/${r.response_id}`;
      const name = r.respondent_name || "名前なし";
      return `
      <article class="inbox-item ${r.is_read ? "" : "unread"} ${state.selectedKey === key ? "selected" : ""}"
               data-key="${escapeHtml(key)}" data-form-id="${escapeHtml(r.form_id)}"
               data-response-id="${escapeHtml(r.response_id)}" tabindex="0" role="button">
        <div class="item-top">
          <span class="unread-dot" aria-hidden="true"></span>
          <span class="item-form">${escapeHtml(r.form_title)}</span>
          <span class="item-date">${formatDateTime(r.submitted_at)}</span>
        </div>
        <div class="item-middle">
          <span class="item-name">${escapeHtml(name)}</span>
          ${statusBadge(r.status)}
          ${r.is_important ? '<span class="item-star" title="重要">★</span>' : ""}
          ${r.has_memo ? '<span class="item-memo-icon" title="メモあり">📝</span>' : ""}
        </div>
        <div class="item-summary">${escapeHtml(r.summary_text)}</div>
      </article>`;
    }).join("");
  }

  // --- 詳細表示 ---

  async function openDetail(formId, responseId) {
    state.selectedKey = `${formId}/${responseId}`;
    renderList();
    el.mainLayout.classList.add("show-detail");
    el.detailEmpty.hidden = true;
    el.detailContent.hidden = false;
    el.detailContent.innerHTML = '<div class="empty-state">読み込み中...</div>';

    const result = await Api.get(
      `/api/responses/${encodeURIComponent(formId)}/${encodeURIComponent(responseId)}`
    );
    if (!result.success) {
      el.detailContent.innerHTML =
        `<div class="empty-state">${escapeHtml(result.message)}</div>`;
      return;
    }

    const d = result.data;
    // 詳細を開いた時点で既読になるため、一覧と件数を再取得する
    if (d.marked_read) {
      loadInbox({ quiet: true });
    }
    renderDetail(d);
  }

  function renderDetail(d) {
    const name = d.respondent_name || "名前なし";
    const email = d.respondent_email || "";
    const answersHtml = d.answers.map((a) => {
      const value = Array.isArray(a.answer)
        ? `<ul class="answer-list">${a.answer.map((v) => `<li>${escapeHtml(v)}</li>`).join("")}</ul>`
        : `<p>${escapeHtml(a.answer) || '<span class="muted">(未回答)</span>'}</p>`;
      return `
        <div class="qa-block">
          <div class="qa-question">${escapeHtml(a.question)}</div>
          <div class="qa-answer">${value}</div>
        </div>`;
    }).join("");

    const statusButtons = Object.entries(STATUS_LABELS).map(([value, label]) => `
      <button class="status-btn action-status-btn badge-${value} ${d.status === value ? "active" : ""}"
              data-status="${value}">${label}</button>
    `).join("");
    const importantLabel = d.is_important ? "重要を解除" : "重要にする";
    const importantState = d.is_important ? "現在: 重要" : "現在: 通常";
    const currentStatus = STATUS_LABELS[d.status] || d.status;
    const memoState = d.admin_memo ? "メモあり" : "未記入";

    el.detailContent.innerHTML = `
      <div class="detail-header">
        <button class="btn btn-ghost btn-sm detail-back" id="detail-back">← 一覧へ</button>
        <div class="detail-title-row">
          <div>
            <div class="detail-kicker">
              ${statusBadge(d.status)}
              <span class="read-chip">${d.is_read ? "既読" : "未読"}</span>
            </div>
            <h2 class="detail-form-title">${escapeHtml(d.form_title)}</h2>
          </div>
        </div>
        <div class="detail-meta">
          <div><span class="meta-label">日時</span>${formatDateTime(d.submitted_at)}</div>
          <div><span class="meta-label">回答者</span>${escapeHtml(name)}</div>
          <div><span class="meta-label">メール</span>${
            email
              ? `<a href="mailto:${escapeHtml(email)}">${escapeHtml(email)}</a>`
              : '<span class="muted">取得できません</span>'
          }</div>
        </div>
      </div>

      <div class="function-nav" role="tablist" aria-label="詳細機能">
        <button class="function-tab active" type="button" data-panel="answers-panel"
                aria-controls="answers-panel" aria-selected="true">
          <span class="function-tab-main">回答内容</span>
          <span class="function-tab-sub">質問と回答</span>
        </button>
        <button class="function-tab" type="button" data-panel="workflow-panel"
                aria-controls="workflow-panel" aria-selected="false">
          <span class="function-tab-main">対応する</span>
          <span class="function-tab-sub" id="status-tab-state">${escapeHtml(currentStatus)}</span>
        </button>
        <button class="function-tab" type="button" data-panel="memo-panel"
                aria-controls="memo-panel" aria-selected="false">
          <span class="function-tab-main">メモ</span>
          <span class="function-tab-sub" id="memo-tab-state">${memoState}</span>
        </button>
        <button class="function-tab" type="button" data-panel="form-panel"
                aria-controls="form-panel" aria-selected="false">
          <span class="function-tab-main">フォーム</span>
          <span class="function-tab-sub">リンク・回答ID</span>
        </button>
      </div>

      <div class="function-panels">
        <section class="function-panel active" id="answers-panel" data-panel-name="answers-panel">
          <h3>質問と回答</h3>
          ${answersHtml || '<p class="muted">回答内容がありません</p>'}
        </section>

        <section class="function-panel" id="workflow-panel" data-panel-name="workflow-panel" hidden>
          <h3>対応を変更</h3>
          <div class="detail-status-row" id="status-row-detail">${statusButtons}</div>
          <div class="important-row">
            <button class="action-btn important-action ${d.is_important ? "active" : ""}" id="important-btn"
                    type="button" title="重要マークを切り替え">
              <span class="action-main">${importantLabel}</span>
              <span class="action-sub">${importantState}</span>
            </button>
          </div>
        </section>

        <section class="function-panel" id="memo-panel" data-panel-name="memo-panel" hidden>
          <h3>管理者用メモ <span class="memo-note">(自分だけに表示されます)</span></h3>
          <textarea id="memo-input" rows="4"
            placeholder="例:7月15日に返信予定 / 不具合を確認中">${escapeHtml(d.admin_memo)}</textarea>
          <div class="memo-status" id="memo-status"></div>
        </section>

        <section class="function-panel" id="form-panel" data-panel-name="form-panel" hidden>
          <h3>フォーム情報</h3>
          <div class="form-action-panel">
            ${d.form_url
              ? `<a class="action-btn action-link" href="${escapeHtml(d.form_url)}" target="_blank" rel="noopener">
                   <span class="action-main">Googleフォームを開く</span>
                   <span class="action-sub">別タブで元フォームへ移動</span>
                 </a>`
              : '<span class="action-unavailable">フォームURLはありません</span>'}
            <div class="response-id-box">
              <span class="meta-label">回答ID</span>
              <span class="response-id-note">${escapeHtml(d.google_response_id)}</span>
            </div>
          </div>
        </section>
      </div>

      <div class="detail-footer">
        <span class="response-id-note">選択中: ${escapeHtml(name)} / ${formatDateTime(d.submitted_at)}</span>
      </div>
    `;

    bindDetailEvents(d);
  }

  function bindDetailEvents(d) {
    document.getElementById("detail-back").addEventListener("click", () => {
      el.mainLayout.classList.remove("show-detail");
    });

    document.querySelectorAll(".function-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        const panelId = tab.dataset.panel;
        document.querySelectorAll(".function-tab").forEach((node) => {
          const isActive = node === tab;
          node.classList.toggle("active", isActive);
          node.setAttribute("aria-selected", isActive ? "true" : "false");
        });
        document.querySelectorAll(".function-panel").forEach((panel) => {
          const isActive = panel.id === panelId;
          panel.hidden = !isActive;
          panel.classList.toggle("active", isActive);
        });
      });
    });

    // 対応状況の変更
    document.querySelectorAll("#status-row-detail .status-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const status = btn.dataset.status;
        if (status === d.status) return;
        const result = await Api.post(
          `/api/responses/${encodeURIComponent(d.form_id)}/${encodeURIComponent(d.response_id)}/status`,
          { status }
        );
        showToast(result.message, result.success ? "success" : "error");
        if (result.success) {
          d.status = status;
          document.querySelectorAll("#status-row-detail .status-btn").forEach((b) => {
            b.classList.toggle("active", b.dataset.status === status);
          });
          const headerBadge = document.querySelector(".detail-kicker .badge-status");
          if (headerBadge) {
            headerBadge.className = `badge badge-status badge-${status}`;
            headerBadge.textContent = STATUS_LABELS[status] || status;
          }
          const statusTabState = document.getElementById("status-tab-state");
          if (statusTabState) statusTabState.textContent = STATUS_LABELS[status] || status;
          loadInbox({ quiet: true });
        }
      });
    });

    // 重要マークの切り替え
    document.getElementById("important-btn").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      const next = !d.is_important;
      const result = await Api.post(
        `/api/responses/${encodeURIComponent(d.form_id)}/${encodeURIComponent(d.response_id)}/important`,
        { is_important: next }
      );
      showToast(result.message, result.success ? "success" : "error");
      if (result.success) {
        d.is_important = next;
        btn.classList.toggle("active", next);
        btn.querySelector(".action-main").textContent = next ? "重要を解除" : "重要にする";
        btn.querySelector(".action-sub").textContent = next ? "現在: 重要" : "現在: 通常";
        loadInbox({ quiet: true });
      }
    });

    // メモの自動保存(入力が止まってから保存する)
    const memoInput = document.getElementById("memo-input");
    const memoStatus = document.getElementById("memo-status");
    let memoTimer = null;
    memoInput.addEventListener("input", () => {
      memoStatus.textContent = "変更あり…";
      memoStatus.className = "memo-status";
      clearTimeout(memoTimer);
      memoTimer = setTimeout(async () => {
        memoStatus.textContent = "保存中…";
        const result = await Api.post(
          `/api/responses/${encodeURIComponent(d.form_id)}/${encodeURIComponent(d.response_id)}/memo`,
          { memo: memoInput.value }
        );
        if (result.success) {
          memoStatus.textContent = "保存しました";
          memoStatus.className = "memo-status saved";
          const memoTabState = document.getElementById("memo-tab-state");
          if (memoTabState) memoTabState.textContent = memoInput.value.trim() ? "メモあり" : "未記入";
          loadInbox({ quiet: true });
        } else {
          memoStatus.textContent = result.message || "保存に失敗しました";
          memoStatus.className = "memo-status error";
        }
      }, 800);
    });
  }

  // --- イベント登録 ---

  el.boxNav.addEventListener("click", (e) => {
    const btn = e.target.closest(".nav-item");
    if (!btn) return;
    state.box = btn.dataset.box;
    el.boxNav.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b === btn));
    loadInbox();
  });

  el.formNav.addEventListener("click", (e) => {
    const btn = e.target.closest(".nav-item");
    if (!btn) return;
    const formId = btn.dataset.formId;
    state.formId = state.formId === formId ? null : formId; // 再クリックで解除
    loadInbox();
  });

  el.inboxList.addEventListener("click", (e) => {
    const item = e.target.closest(".inbox-item");
    if (!item) return;
    openDetail(item.dataset.formId, item.dataset.responseId);
  });
  el.inboxList.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const item = e.target.closest(".inbox-item");
    if (!item) return;
    openDetail(item.dataset.formId, item.dataset.responseId);
  });

  let searchTimer = null;
  el.searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = el.searchInput.value.trim();
      loadInbox({ quiet: true });
    }, 300);
  });

  el.dateFrom.addEventListener("change", () => {
    state.dateFrom = el.dateFrom.value;
    loadInbox();
  });
  el.dateTo.addEventListener("change", () => {
    state.dateTo = el.dateTo.value;
    loadInbox();
  });
  el.orderSelect.addEventListener("change", () => {
    state.order = el.orderSelect.value;
    loadInbox();
  });

  el.clearFilters.addEventListener("click", () => {
    state.box = "all";
    state.formId = null;
    state.query = "";
    state.dateFrom = "";
    state.dateTo = "";
    state.order = "desc";
    el.searchInput.value = "";
    el.dateFrom.value = "";
    el.dateTo.value = "";
    el.orderSelect.value = "desc";
    el.boxNav.querySelectorAll(".nav-item").forEach((b) =>
      b.classList.toggle("active", b.dataset.box === "all"));
    loadInbox();
  });

  // 手動同期(連続クリック防止・進行状況表示)
  el.syncBtn.addEventListener("click", async () => {
    if (el.syncBtn.disabled) return;
    el.syncBtn.disabled = true;
    el.syncBtn.classList.add("syncing");
    el.syncBtn.querySelector(".sync-label").textContent = "回答を取得しています";

    const result = await Api.post("/api/sync");
    showToast(result.message, result.success ? "success" : "error", 5000);
    if (result.success) {
      await loadInbox({ quiet: true });
    } else if (result.data && result.data.need_login) {
      setTimeout(() => { window.location.href = "/login"; }, 1500);
    }

    el.syncBtn.disabled = false;
    el.syncBtn.classList.remove("syncing");
    el.syncBtn.querySelector(".sync-label").textContent = "回答を更新";
  });

  loadInbox();
})();
