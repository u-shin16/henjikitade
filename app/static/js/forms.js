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

  document.querySelectorAll(".deactivate-btn").forEach((btn) => {
    btn.addEventListener("click", () => setActive(btn.closest("tr"), false, btn));
  });
  document.querySelectorAll(".reactivate-btn").forEach((btn) => {
    btn.addEventListener("click", () => setActive(btn.closest("tr"), true, btn));
  });
})();
