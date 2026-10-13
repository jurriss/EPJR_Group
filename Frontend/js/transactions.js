document.addEventListener("DOMContentLoaded", async () => {
  const user = await window.PennywiseAuth.ready;
  if (!user) return;

  const api = window.PennywiseAPI;
  const ui = window.PennywiseUI;
  const i18n = window.PennywiseI18n;
  const filters = document.querySelector("[data-transaction-filters]");
  const rows = document.querySelector("[data-transaction-rows]");
  const tableRegion = document.querySelector("[data-table-region]");
  const empty = document.querySelector("[data-transaction-empty]");
  const pagination = document.querySelector("[data-pagination]");
  const dialog = document.querySelector("[data-transaction-dialog]");
  const form = document.querySelector("[data-transaction-form]");
  const formMessage = document.querySelector("[data-form-message]");
  const pageNotice = document.querySelector("[data-page-notice]");
  const loading = document.querySelector("[data-transactions-loading]");
  const currency = user.currency || "EUR";
  document.querySelector("[data-transaction-amount-label]").textContent = `Summa (${currency})`;
  let page = 1;
  let totalPages = 0;
  let searchTimer;
  let categories = [];

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

  function addCell(row, text, className) {
    const cell = document.createElement("td");
    cell.textContent = text;
    if (className) cell.className = className;
    row.append(cell);
    return cell;
  }

  function renderTransactions(transactions) {
    rows.replaceChildren();
    transactions.forEach((transaction) => {
      const row = document.createElement("tr");
      addCell(row, new Date(`${transaction.date}T00:00:00`).toLocaleDateString("lv-LV"));
      addCell(row, transaction.description);
      addCell(row, i18n.categoryTitle(transaction.category));
      const amountCell = addCell(
        row,
        `${transaction.type === "income" ? "+" : "−"}${money(transaction.converted_amount ?? transaction.amount)}`,
        `money-value ${transaction.type}`,
      );
      amountCell.dataset.label = transaction.type === "income" ? "Ienākumi" : "Izdevumi";
      amountCell.setAttribute(
        "aria-label",
        `${transaction.type === "income" ? "Ienākumi" : "Izdevumi"}: ${money(transaction.converted_amount ?? transaction.amount)}`,
      );
      const actions = document.createElement("td");
      actions.className = "table-actions table-actions-nowrap";
      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "button button-quiet";
      edit.textContent = "Rediģēt";
      edit.dataset.editTransaction = transaction.transaction_id;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "button button-danger";
      remove.textContent = "Dzēst";
      remove.dataset.deleteTransaction = transaction.transaction_id;
      actions.append(edit, remove);
      row.append(actions);
      rows.append(row);
    });
    tableRegion.hidden = transactions.length === 0;
    empty.hidden = transactions.length !== 0;
  }

  function currentParameters() {
    return Object.fromEntries(new FormData(filters).entries());
  }

  async function loadTransactions() {
    loading.hidden = false;
    tableRegion.hidden = true;
    empty.hidden = true;
    try {
      const response = await api.getTransactions({ ...currentParameters(), page, limit: 10 });
      const data = response.data;
      pageNotice.hidden = true;
      totalPages = data.pagination.total_pages;
      renderTransactions(data.transactions);
      pagination.hidden = totalPages <= 1;
      document.querySelector("[data-page-label]").textContent = `${page}. lapa no ${totalPages || 1}`;
      document.querySelector("[data-page-previous]").disabled = page <= 1;
      document.querySelector("[data-page-next]").disabled = page >= totalPages;
    } catch (error) {
      showNotice(error.message);
      pagination.hidden = true;
    } finally {
      loading.hidden = true;
    }
  }

  async function loadSummary() {
    try {
      const { data } = await api.getOverview(filters.elements.month.value || undefined);
      document.querySelector("[data-month-income]").textContent = money(data.current_month_income);
      document.querySelector("[data-month-spending]").textContent = money(data.current_month_spending);
      document.querySelector("[data-month-net]").textContent = money(data.net_cash_flow);
    } catch (error) {
      showNotice(error.message);
    }
  }

  function fillFilterCategories(type = "") {
    const filterSelect = document.querySelector("[data-filter-category]");
    const selected = filterSelect.value;
    filterSelect.replaceChildren(new Option("Visas kategorijas", ""));
    categories
      .filter((category) => !type || category.type === type)
      .forEach((category) => {
        filterSelect.add(new Option(i18n.categoryTitle(category.title), category.category_id));
      });
    if ([...filterSelect.options].some((option) => option.value === selected)) {
      filterSelect.value = selected;
    }
  }

  function fillFormCategories(type, selected = "") {
    const formSelect = document.querySelector("[data-form-category]");
    formSelect.replaceChildren(new Option("Izvēlieties kategoriju", ""));
    categories
      .filter((category) => category.type === type)
      .forEach((category) => {
        formSelect.add(new Option(i18n.categoryTitle(category.title), category.category_id));
      });
    formSelect.value = String(selected || "");
  }

  function openCreateDialog() {
    form.reset();
    form.elements.transaction_id.value = "";
    form.elements.type.value = "expense";
    fillFormCategories("expense");
    const now = new Date();
    form.elements.date.value = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
      .toISOString().slice(0, 10);
    formMessage.classList.remove("visible");
    ui.clearFieldErrors(form);
    document.querySelector("[data-dialog-title]").textContent = "Pievienot darījumu";
    dialog.showModal();
  }

  async function openEditDialog(transactionId) {
    try {
      const { data } = await api.getTransaction(transactionId);
      const transaction = data.transaction;
      form.elements.transaction_id.value = transaction.transaction_id;
      form.elements.type.value = transaction.type;
      form.elements.amount.value = transaction.converted_amount ?? transaction.amount;
      form.elements.description.value = transaction.description;
      fillFormCategories(transaction.type, transaction.category_id);
      form.elements.date.value = transaction.date;
      formMessage.classList.remove("visible");
      ui.clearFieldErrors(form);
      document.querySelector("[data-dialog-title]").textContent = "Rediģēt darījumu";
      dialog.showModal();
    } catch (error) {
      showNotice(error.message);
    }
  }

  try {
    const categoryResponse = await api.getCategories();
    categories = categoryResponse.data.categories;
    fillFilterCategories();
    fillFormCategories("expense");
    await Promise.all([loadTransactions(), loadSummary()]);
  } catch (error) {
    showNotice(error.message);
  }

  filters.addEventListener("input", (event) => {
    if (event.target.name !== "search") return;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { page = 1; loadTransactions(); }, 250);
  });
  filters.addEventListener("change", (event) => {
    if (event.target.name === "type") fillFilterCategories(event.target.value);
    page = 1;
    loadTransactions();
    if (event.target.name === "month") loadSummary();
  });
  filters.addEventListener("submit", (event) => event.preventDefault());
  document.querySelector("[data-clear-filters]").addEventListener("click", () => {
    filters.reset(); page = 1; loadTransactions(); loadSummary();
  });
  document.querySelector("[data-page-previous]").addEventListener("click", () => {
    if (page > 1) { page -= 1; loadTransactions(); }
  });
  document.querySelector("[data-page-next]").addEventListener("click", () => {
    if (page < totalPages) { page += 1; loadTransactions(); }
  });
  document.querySelector("[data-add-transaction]").addEventListener("click", openCreateDialog);
  form.elements.type.addEventListener("change", () => {
    fillFormCategories(form.elements.type.value);
  });
  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });

  rows.addEventListener("click", async (event) => {
    const edit = event.target.closest("[data-edit-transaction]");
    const remove = event.target.closest("[data-delete-transaction]");
    if (edit) openEditDialog(edit.dataset.editTransaction);
    if (remove && await ui.confirmAction({
      title: "Dzēst darījumu?",
      message: "Darījums tiks neatgriezeniski dzēsts no tavas finanšu vēstures.",
      confirmLabel: "Dzēst darījumu",
    })) {
      try {
        await api.deleteTransaction(remove.dataset.deleteTransaction);
        ui.toast("Darījums veiksmīgi dzēsts.");
        await Promise.all([loadTransactions(), loadSummary()]);
      } catch (error) { showNotice(error.message); }
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const saveButton = document.querySelector("[data-save-transaction]");
    const values = Object.fromEntries(new FormData(form).entries());
    const transactionId = values.transaction_id;
    delete values.transaction_id;
    ui.setButtonLoading(saveButton, true, "Saglabā...");
    formMessage.classList.remove("visible");
    ui.clearFieldErrors(form);
    try {
      if (transactionId) await api.updateTransaction(transactionId, values);
      else await api.createTransaction(values);
      dialog.close();
      ui.toast(transactionId ? "Darījums veiksmīgi atjaunināts." : "Darījums veiksmīgi pievienots.");
      page = 1;
      await Promise.all([loadTransactions(), loadSummary()]);
    } catch (error) {
      showFormError(error);
    } finally {
      ui.setButtonLoading(saveButton, false);
    }
  });
});
