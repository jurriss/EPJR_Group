document.addEventListener("DOMContentLoaded", async () => {
  const user = await window.PennywiseAuth.ready;
  if (!user) return;

  const api = window.PennywiseAPI;
  const ui = window.PennywiseUI;
  const i18n = window.PennywiseI18n;
  const currency = user.currency || "EUR";
  document.querySelector("[data-budget-amount-label]").textContent = `Mēneša limits (${currency})`;
  const monthInput = document.querySelector("[data-budget-month]");
  const grid = document.querySelector("[data-budget-grid]");
  const empty = document.querySelector("[data-budget-empty]");
  const dialog = document.querySelector("[data-budget-dialog]");
  const form = document.querySelector("[data-budget-form]");
  const formMessage = document.querySelector("[data-form-message]");
  const pageNotice = document.querySelector("[data-page-notice]");
  const notifications = document.querySelector("[data-budget-notifications]");
  const loading = document.querySelector("[data-budgets-loading]");
  const content = document.querySelector("[data-budgets-content]");
  let budgets = [];

  const now = new Date();
  monthInput.value = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 7);
  const money = (value) => new Intl.NumberFormat("lv-LV", {
    style: "currency", currency,
  }).format(Number(value || 0));

  function showNotice(message, kind = "error") {
    pageNotice.textContent = message;
    pageNotice.dataset.kind = kind;
    pageNotice.hidden = false;
  }

  function showFormError(error) {
    ui.showFieldErrors(form, error.payload?.errors || {});
    formMessage.textContent = error.message;
    formMessage.classList.add("visible");
  }

  function statusLabel(status) {
    if (status === "exceeded") return "Limits pārsniegts";
    if (status === "warning") return "Tuvojas limitam";
    return "Atbilst plānam";
  }

  function textElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    return element;
  }

  function render(data) {
    budgets = data.categories;
    document.querySelector("[data-total-limit]").textContent = money(data.total_limit);
    document.querySelector("[data-total-spent]").textContent = money(data.amount_spent);
    document.querySelector("[data-total-remaining]").textContent = money(data.remaining);
    document.querySelector("[data-budget-percentage]").textContent = `${Number(data.percentage_used).toLocaleString("lv-LV", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}% izmantoti`;
    document.querySelector("[data-budget-status]").textContent = statusLabel(data.status);
    const [year, month] = monthInput.value.split("-").map(Number);
    const today = new Date();
    const selectedIndex = year * 12 + month;
    const currentIndex = today.getFullYear() * 12 + today.getMonth() + 1;
    const lastDay = new Date(year, month, 0).getDate();
    const daysRemaining = selectedIndex < currentIndex
      ? 0
      : selectedIndex > currentIndex ? lastDay : Math.max(lastDay - today.getDate(), 0);
    document.querySelector("[data-days-remaining]").textContent = String(daysRemaining);
    document.querySelector("[data-budget-count]").textContent = budgets.length === 0
      ? "0 budžetu"
      : `${budgets.length} ${budgets.length === 1 ? "budžets" : "budžeti"}`;
    notifications.replaceChildren();
    (data.notifications || []).forEach((notification) => {
      const category = budgets.find((entry) => entry.category_id === notification.category_id);
      const name = i18n.categoryTitle(category?.category || "Kategorija");
      const message = notification.type === "danger"
        ? `Kategorijas “${name}” budžets ir pārsniegts.`
        : `Kategorijas “${name}” budžets tuvojas limitam.`;
      const item = textElement("div", "budget-notification", message);
      item.dataset.kind = notification.type;
      notifications.append(item);
    });
    grid.replaceChildren();

    budgets.forEach((budget) => {
      const card = document.createElement("article");
      card.className = `budget-card status-${budget.status}`;
      const header = document.createElement("div");
      header.className = "budget-card-head";
      const heading = document.createElement("div");
      heading.append(
        textElement("h3", "", i18n.categoryTitle(budget.category)),
        textElement("span", "budget-status", statusLabel(budget.status)),
      );
      const actions = document.createElement("div");
      actions.className = "table-actions";
      const edit = textElement("button", "button button-quiet", "Rediģēt");
      edit.type = "button";
      edit.dataset.editBudget = budget.expense_id;
      const remove = textElement("button", "button button-danger", "Dzēst");
      remove.type = "button";
      remove.dataset.deleteBudget = budget.expense_id;
      actions.append(edit, remove);
      header.append(heading, actions);

      const amounts = document.createElement("div");
      amounts.className = "budget-amounts";
      const spent = document.createElement("div");
      spent.append(textElement("strong", "", money(budget.spent)), textElement("span", "", "iztērēts"));
      const limit = document.createElement("div");
      limit.append(textElement("strong", "", money(budget.limit)), textElement("span", "", "limits"));
      amounts.append(spent, limit);

      const progress = document.createElement("div");
      progress.className = "progress";
      const bar = document.createElement("span");
      bar.style.width = `${Math.min(Number(budget.percentage_used), 100)}%`;
      progress.append(bar);
      const foot = textElement(
        "p", "budget-card-foot",
        `${Number(budget.percentage_used).toLocaleString("lv-LV", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}% izmantoti · atlikums ${money(budget.remaining)}`,
      );
      card.append(header, amounts, progress, foot);
      grid.append(card);
    });
    empty.hidden = budgets.length !== 0;
  }

  async function loadBudgets() {
    loading.hidden = false;
    content.hidden = true;
    try {
      const response = await api.getBudgets(monthInput.value);
      render(response.data);
      pageNotice.hidden = true;
      content.hidden = false;
    } catch (error) {
      showNotice(error.message);
    } finally {
      loading.hidden = true;
    }
  }

  function openCreateDialog() {
    form.reset();
    form.elements.expense_id.value = "";
    document.querySelector("[data-budget-dialog-title]").textContent = "Izveidot budžetu";
    formMessage.classList.remove("visible");
    ui.clearFieldErrors(form);
    dialog.showModal();
  }

  function openEditDialog(expenseId) {
    const budget = budgets.find((item) => String(item.expense_id) === String(expenseId));
    if (!budget) return;
    form.elements.expense_id.value = budget.expense_id;
    form.elements.category_id.value = budget.category_id;
    form.elements.amount.value = budget.limit;
    document.querySelector("[data-budget-dialog-title]").textContent = "Rediģēt budžetu";
    formMessage.classList.remove("visible");
    ui.clearFieldErrors(form);
    dialog.showModal();
  }

  try {
    const categoryResponse = await api.getCategories("expense");
    const categorySelect = document.querySelector("[data-budget-category]");
    categoryResponse.data.categories.forEach((category) => {
      categorySelect.add(new Option(i18n.categoryTitle(category.title), category.category_id));
    });
    await loadBudgets();
  } catch (error) {
    showNotice(error.message);
  }

  monthInput.addEventListener("change", loadBudgets);
  document.querySelector("[data-add-budget]").addEventListener("click", openCreateDialog);
  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });

  grid.addEventListener("click", async (event) => {
    const edit = event.target.closest("[data-edit-budget]");
    const remove = event.target.closest("[data-delete-budget]");
    if (edit) openEditDialog(edit.dataset.editBudget);
    if (remove && await ui.confirmAction({
      title: "Dzēst mēneša budžetu?",
      message: "Kategorijas limits tiks dzēsts. Esošie darījumi paliks nemainīti.",
      confirmLabel: "Dzēst budžetu",
    })) {
      try {
        await api.deleteBudget(remove.dataset.deleteBudget);
        ui.toast("Budžets veiksmīgi dzēsts.");
        await loadBudgets();
      } catch (error) { showNotice(error.message); }
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const saveButton = document.querySelector("[data-save-budget]");
    const values = Object.fromEntries(new FormData(form).entries());
    const expenseId = values.expense_id;
    delete values.expense_id;
    ui.setButtonLoading(saveButton, true, "Saglabā...");
    formMessage.classList.remove("visible");
    ui.clearFieldErrors(form);
    try {
      if (expenseId) await api.updateBudget(expenseId, values);
      else await api.createBudget(values);
      dialog.close();
      ui.toast(expenseId ? "Budžets veiksmīgi atjaunināts." : "Budžets veiksmīgi izveidots.");
      await loadBudgets();
    } catch (error) {
      showFormError(error);
    } finally {
      ui.setButtonLoading(saveButton, false);
    }
  });
});
