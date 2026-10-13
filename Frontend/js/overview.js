document.addEventListener("DOMContentLoaded", async () => {
  const user = await window.PennywiseAuth.ready;
  if (!user) return;

  const api = window.PennywiseAPI;
  const i18n = window.PennywiseI18n;
  const currency = user.currency || "EUR";
  const monthInput = document.querySelector("[data-overview-month]");
  const notice = document.querySelector("[data-page-notice]");
  const loading = document.querySelector("[data-overview-loading]");
  const content = document.querySelector("[data-overview-content]");
  const notifications = document.querySelector("[data-overview-notifications]");
  const now = new Date();
  const redirectedFromAdmin = new URLSearchParams(window.location.search).get("notice") === "admin";
  monthInput.value = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 7);
  const money = (value) => new Intl.NumberFormat("lv-LV", {
    style: "currency", currency,
  }).format(Number(value || 0));

  function textElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    return element;
  }

  function showError(message) {
    notice.textContent = message;
    notice.dataset.kind = "error";
    notice.hidden = false;
  }

  function changeText(value, subject) {
    const number = Number(value);
    if (number === 0) return `${subject} nav mainījušies salīdzinājumā ar iepriekšējo mēnesi`;
    const direction = number > 0 ? "pieauguši" : "samazinājušies";
    return `${subject} ${direction} par ${Math.abs(number).toLocaleString("lv-LV", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}% salīdzinājumā ar iepriekšējo mēnesi`;
  }

  function renderTrend(trend) {
    const chart = document.querySelector("[data-trend-chart]");
    chart.replaceChildren();
    const maximum = Math.max(1, ...trend.flatMap((item) => [Number(item.income), Number(item.expenses)]));
    trend.forEach((item) => {
      const group = document.createElement("div");
      group.className = "trend-group";
      const bars = document.createElement("div");
      bars.className = "trend-bars";
      const income = document.createElement("span");
      income.className = "trend-income";
      income.style.height = `${Math.max(Number(item.income) / maximum * 100, 2)}%`;
      income.title = `Ienākumi: ${money(item.income)}`;
      const expenses = document.createElement("span");
      expenses.className = "trend-expense";
      expenses.style.height = `${Math.max(Number(item.expenses) / maximum * 100, 2)}%`;
      expenses.title = `Izdevumi: ${money(item.expenses)}`;
      bars.append(income, expenses);
      const label = new Date(`${item.month}-01T00:00:00`).toLocaleDateString("lv-LV", { month: "short" });
      group.append(bars, textElement("small", "", label));
      chart.append(group);
    });
  }

  function renderBudgets(budget) {
    document.querySelector("[data-budget-remaining]").textContent = money(budget.remaining);
    document.querySelector("[data-budget-limit]").textContent = money(budget.total_limit);
    document.querySelector("[data-budget-used]").textContent = `${Number(budget.percentage_used).toLocaleString("lv-LV")}% izmantoti šomēnes`;
    const bar = document.querySelector("[data-budget-progress]");
    bar.style.width = `${Math.min(Number(budget.percentage_used), 100)}%`;
    bar.dataset.status = budget.status;

    notifications.replaceChildren();
    (budget.notifications || []).forEach((notification) => {
      const category = budget.categories.find((entry) => entry.category_id === notification.category_id);
      const name = i18n.categoryTitle(category?.category || "Kategorija");
      const message = notification.type === "danger"
        ? `Kategorijas “${name}” budžets ir pārsniegts.`
        : `Kategorijas “${name}” budžets tuvojas limitam.`;
      const item = textElement("div", "budget-notification", message);
      item.dataset.kind = notification.type;
      notifications.append(item);
    });

    const list = document.querySelector("[data-overview-budgets]");
    list.replaceChildren();
    budget.categories.slice(0, 4).forEach((category) => {
      const row = document.createElement("div");
      row.className = "overview-budget-row";
      const labels = document.createElement("div");
      labels.append(
        textElement("span", "", i18n.categoryTitle(category.category)),
        textElement("strong", "", `${category.percentage_used}%`),
      );
      const progress = document.createElement("div");
      progress.className = "progress";
      const inner = document.createElement("span");
      inner.style.width = `${Math.min(Number(category.percentage_used), 100)}%`;
      progress.append(inner);
      row.append(labels, progress);
      list.append(row);
    });
    if (!budget.categories.length) {
      list.append(textElement("p", "muted compact-copy", "Vēl nav izveidots neviens kategorijas budžets."));
    }
  }

  function renderRecent(transactions) {
    const rows = document.querySelector("[data-recent-rows]");
    const table = document.querySelector("[data-recent-table]");
    const empty = document.querySelector("[data-recent-empty]");
    rows.replaceChildren();
    transactions.forEach((transaction) => {
      const row = document.createElement("tr");
      [
        new Date(`${transaction.date}T00:00:00`).toLocaleDateString("lv-LV"),
        transaction.description,
        i18n.categoryTitle(transaction.category),
      ].forEach((value) => row.append(textElement("td", "", value)));
      const amount = textElement(
        "td",
        `money-value ${transaction.type}`,
        `${transaction.type === "income" ? "+" : "−"}${money(transaction.converted_amount ?? transaction.amount)}`,
      );
      row.append(amount);
      rows.append(row);
    });
    table.hidden = transactions.length === 0;
    empty.hidden = transactions.length !== 0;
  }

  function render(data) {
    document.querySelector("[data-available-balance]").textContent = money(data.available_balance);
    document.querySelector("[data-month-income]").textContent = money(data.current_month_income);
    document.querySelector("[data-month-spending]").textContent = money(data.current_month_spending);
    document.querySelector("[data-month-saved]").textContent = money(data.saved_amount);
    document.querySelector("[data-net-flow]").textContent = `Neto naudas plūsma ${money(data.net_cash_flow)}`;
    document.querySelector("[data-income-change]").textContent = changeText(data.income_percentage_change, "Ienākumi");
    document.querySelector("[data-expense-change]").textContent = changeText(data.expense_percentage_change, "Izdevumi");
    renderTrend(data.spending_trend);
    renderBudgets(data.current_budget);
    renderRecent(data.recent_transactions);
  }

  async function loadOverview() {
    loading.hidden = false;
    content.hidden = true;
    try {
      const response = await api.getOverview(monthInput.value);
      render(response.data);
      content.hidden = false;
      if (redirectedFromAdmin) {
        showError("Nepieciešamas administratora piekļuves tiesības.");
      } else {
        notice.hidden = true;
      }
    } catch (error) {
      showError(error.message);
    } finally {
      loading.hidden = true;
    }
  }

  monthInput.addEventListener("change", loadOverview);
  await loadOverview();
});
