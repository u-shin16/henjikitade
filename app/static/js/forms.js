/**
 * フォーム管理画面のロジック。
 * チェックボックスで選択したフォームの一括追加と、管理対象の有効/無効切り替え。
 */
(() => {
  const addBtn = document.getElementById("add-selected-btn");
  const selectedCount = document.getElementById("selected-count");

  function updateSelection() {
    const checked = document.querySelectorAll(".form-check:checked");
    addBtn.disabled = checked.length === 0;
    selectedCount.textContent = checked.length
      ? `${checked.length}件を追加します`
      : "追加するフォームを選択してください";
  }

  document.querySelectorAll(".form-check").forEach((cb) => {
    cb.addEventListener("change", updateSelection);
  });

  addBtn.addEventListener("click", async () => {
    const forms = [...document.querySelectorAll(".form-check:checked")].map((cb) => {
      const row = cb.closest("[data-form-id]");
      return { id: row.dataset.formId, title: row.dataset.formTitle };
    });
    if (!forms.length) return;

    addBtn.disabled = true;
    const result = await Api.post("/api/forms/manage", { forms });
    showToast(result.message, result.success ? "success" : "error");
    if (result.success) {
      setTimeout(() => window.location.reload(), 800);
    } else {
      addBtn.disabled = false;
    }
  });

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

  updateSelection();
})();
