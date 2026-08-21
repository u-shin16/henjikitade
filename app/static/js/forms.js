/**
 * フォーム管理画面のロジック。
 * フォームのURLを貼って登録する処理と、管理対象の有効/無効切り替え。
 */
(() => {
  const input = document.getElementById("form-url-input");
  const addBtn = document.getElementById("add-form-btn");
  const errorEl = document.getElementById("form-add-error");

  function showError(message) {
    errorEl.textContent = message || "";
    errorEl.hidden = !message;
  }

  async function addForm() {
    const url = input.value.trim();
    if (!url) {
      showError("フォームのURLを入力してください");
      input.focus();
      return;
    }

    showError("");
    addBtn.disabled = true;
    const result = await Api.post("/api/forms/add-by-url", { url });
    showToast(result.message, result.success ? "success" : "error");

    if (result.success) {
      input.value = "";
      setTimeout(() => window.location.reload(), 800);
      return;
    }

    // 貼り直してもらう必要があるため、理由は入力欄のそばにも残す
    showError(result.message);
    addBtn.disabled = false;
    input.focus();
  }

  addBtn.addEventListener("click", addForm);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addForm();
    }
  });
  input.addEventListener("input", () => showError(""));

  async function setActive(row, isActive, btn) {
    btn.disabled = true;
    const formId = row.dataset.formId;
    const result = await Api.post(
      `/api/forms/${encodeURIComponent(formId)}/active`,
      { is_active: isActive }
    );
    showToast(result.message, result.success ? "success" : "error");
    if (result.success) {
      setTimeout(() => window.location.reload(), 800);
    } else {
      btn.disabled = false;
    }
  }

  async function deleteForm(row, btn) {
    const title = row.dataset.formTitle || "このフォーム";
    const responseCount = Number(btn.dataset.responseCount || 0);
    // 保存済みの回答も一緒に消える。件数を見せてから確認する。
    const detail = responseCount
      ? `保存されている回答${responseCount}件も削除されます。`
      : "保存されているデータも削除されます。";
    if (!window.confirm(`「${title}」の登録を削除しますか？\n${detail}この操作は取り消せません。`)) {
      return;
    }

    btn.disabled = true;
    btn.textContent = "削除中…";
    const result = await Api.post(`/api/forms/${encodeURIComponent(row.dataset.formId)}/delete`);
    showToast(result.message, result.success ? "success" : "error");
    if (result.success) {
      setTimeout(() => window.location.reload(), 800);
      return;
    }
    btn.disabled = false;
    btn.textContent = "削除";
  }

  document.querySelectorAll(".delete-btn").forEach((btn) => {
    btn.addEventListener("click", () => deleteForm(btn.closest("tr"), btn));
  });

  document.querySelectorAll(".deactivate-btn").forEach((btn) => {
    btn.addEventListener("click", () => setActive(btn.closest("tr"), false, btn));
  });
  document.querySelectorAll(".reactivate-btn").forEach((btn) => {
    btn.addEventListener("click", () => setActive(btn.closest("tr"), true, btn));
  });
})();
