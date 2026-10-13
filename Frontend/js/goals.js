document.addEventListener("DOMContentLoaded", async () => {
  const user = await window.PennywiseAuth.ready;
  if (!user) return;

  const api = window.PennywiseAPI;
  const ui = window.PennywiseUI;
  const currency = user.currency || "EUR";
  document.querySelector("[data-goal-target-label]").textContent = `Mērķa summa (${currency})`;
  document.querySelector("[data-goal-current-label]").textContent = `Pašreizējā summa (${currency})`;
  const loading = document.querySelector("[data-goals-loading]");
  const content = document.querySelector("[data-goals-content]");
  const notice = document.querySelector("[data-page-notice]");
  const grid = document.querySelector("[data-goal-grid]");
  const empty = document.querySelector("[data-goal-empty]");
  const dialog = document.querySelector("[data-goal-dialog]");
  const form = document.querySelector("[data-goal-form]");
  const formMessage = document.querySelector("[data-form-message]");
  const amountDialog = document.querySelector("[data-amount-dialog]");
  const amountForm = document.querySelector("[data-amount-form]");
  const amountMessage = document.querySelector("[data-amount-message]");
  let goals = [];

  const money = (value) => new Intl.NumberFormat("lv-LV", {
    style: "currency", currency,
  }).format(Number(value || 0));

  function textElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    return element;
  }

  function statusLabel(status) {
    if (status === "complete") return "Pabeigts";
    if (status === "overdue" || status === "attention_needed") return "Jāpievērš uzmanība";
    if (status === "no_goals") return "Var sākt";
    return "Procesā";
  }

  function formatDate(value) {
    return new Date(`${value}T00:00:00`).toLocaleDateString("lv-LV", {
      day: "numeric", month: "short", year: "numeric",
    });
  }

  function showError(error) {
    notice.textContent = error.message;
    notice.dataset.kind = "error";
    notice.hidden = false;
  }

  function renderGoal(goal) {
    const card = document.createElement("article");
    card.className = `goal-card status-${goal.status}`;

    const header = document.createElement("div");
    header.className = "goal-card-head";
    const identity = document.createElement("div");
    identity.className = "goal-identity";
    identity.append(
      textElement("span", "goal-symbol", goal.name.charAt(0).toUpperCase()),
      textElement("h2", "", goal.name),
    );
    header.append(identity, textElement("span", "goal-status-badge", statusLabel(goal.status)));

    const amountLine = document.createElement("div");
    amountLine.className = "goal-amount-line";
    const current = document.createElement("div");
    current.append(textElement("strong", "", money(goal.converted_current_amount ?? goal.current_amount)), textElement("span", "", "uzkrāts"));
    const target = document.createElement("div");
    target.append(textElement("strong", "", money(goal.converted_target_amount ?? goal.target_amount)), textElement("span", "", "mērķis"));
    amountLine.append(current, target);

    const progressLabels = document.createElement("div");
    progressLabels.className = "goal-progress-labels";
    progressLabels.append(
      textElement("span", "", "Izpilde"),
      textElement("strong", "", `${Number(goal.percentage_complete).toLocaleString("lv-LV")}%`),
    );
    const progress = document.createElement("div");
    progress.className = "progress goal-progress";
    const bar = document.createElement("span");
    bar.style.width = `${Math.min(Number(goal.percentage_complete), 100)}%`;
    progress.append(bar);

    const details = document.createElement("dl");
    details.className = "goal-details";
    [
      ["Atlikusī summa", money(goal.converted_remaining_amount ?? goal.remaining_amount)],
      ["Ikmēneša iemaksa", money(goal.converted_monthly_contribution ?? goal.monthly_contribution)],
      ["Mērķa datums", formatDate(goal.deadline)],
    ].forEach(([label, value]) => {
      const item = document.createElement("div");
      item.append(textElement("dt", "", label), textElement("dd", "", value));
      details.append(item);
    });

    const actions = document.createElement("div");
    actions.className = "goal-actions";
    const update = textElement("button", "button button-primary", "Atjaunināt uzkrājumu");
    update.type = "button";
    update.dataset.updateGoalAmount = goal.savings_goals_id;
    const edit = textElement("button", "button button-secondary", "Rediģēt");
    edit.type = "button";
    edit.dataset.editGoal = goal.savings_goals_id;
    const remove = textElement("button", "button button-danger", "Dzēst");
    remove.type = "button";
    remove.dataset.deleteGoal = goal.savings_goals_id;
    actions.append(update, edit, remove);

    card.append(header, amountLine, progressLabels, progress, details, actions);
    return card;
  }

  function render(data) {
    goals = data.goals;
    document.querySelector("[data-goals-total-saved]").textContent = money(data.total_saved);
    document.querySelector("[data-goals-total-target]").textContent = `${money(data.total_target)} kopējais mērķis`;
    document.querySelector("[data-goals-progress]").textContent = `${Number(data.overall_progress).toLocaleString("lv-LV")}%`;
    document.querySelector("[data-goals-progress-bar]").style.width = `${Math.min(Number(data.overall_progress), 100)}%`;
    document.querySelector("[data-goals-status]").textContent = statusLabel(data.status);
    document.querySelector("[data-goals-count]").textContent = `Aktīvi: ${data.active_goal_count} no ${data.goal_count}`;
    grid.replaceChildren(...goals.map(renderGoal));
    grid.hidden = goals.length === 0;
    empty.hidden = goals.length !== 0;
  }

  async function loadGoals() {
    loading.hidden = false;
    content.hidden = true;
    try {
      const response = await api.getGoals();
      render(response.data);
      notice.hidden = true;
      content.hidden = false;
    } catch (error) {
      showError(error);
    } finally {
      loading.hidden = true;
    }
  }

  function todayText() {
    const date = new Date();
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
      .toISOString().slice(0, 10);
  }

  function openCreateDialog() {
    form.reset();
    form.elements.savings_goals_id.value = "";
    form.elements.current_amount.value = "0";
    form.elements.deadline.min = todayText();
    formMessage.classList.remove("visible");
    ui.clearFieldErrors(form);
    document.querySelector("[data-goal-dialog-title]").textContent = "Izveidot mērķi";
    dialog.showModal();
    form.elements.name.focus();
  }

  function openEditDialog(goalId) {
    const goal = goals.find((item) => String(item.savings_goals_id) === String(goalId));
    if (!goal) return;
    form.elements.savings_goals_id.value = goal.savings_goals_id;
    form.elements.name.value = goal.name;
    form.elements.target_amount.value = goal.converted_target_amount ?? goal.target_amount;
    form.elements.current_amount.value = goal.converted_current_amount ?? goal.current_amount;
    form.elements.deadline.value = goal.deadline;
    form.elements.deadline.min = goal.deadline < todayText() ? "" : todayText();
    formMessage.classList.remove("visible");
    ui.clearFieldErrors(form);
    document.querySelector("[data-goal-dialog-title]").textContent = "Rediģēt mērķi";
    dialog.showModal();
  }

  function openAmountDialog(goalId) {
    const goal = goals.find((item) => String(item.savings_goals_id) === String(goalId));
    if (!goal) return;
    amountForm.elements.savings_goals_id.value = goal.savings_goals_id;
    amountForm.elements.current_amount.value = goal.converted_current_amount ?? goal.current_amount;
    amountForm.elements.current_amount.max = goal.converted_target_amount ?? goal.target_amount;
    document.querySelector("[data-amount-dialog-title]").textContent = `Atjaunināt: ${goal.name}`;
    document.querySelector("[data-amount-helper]").textContent = `Mērķis: ${money(goal.converted_target_amount ?? goal.target_amount)}`;
    amountMessage.classList.remove("visible");
    ui.clearFieldErrors(amountForm);
    amountDialog.showModal();
    amountForm.elements.current_amount.focus();
  }

  document.querySelectorAll("[data-add-goal]").forEach((button) => {
    button.addEventListener("click", openCreateDialog);
  });
  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });
  document.querySelectorAll("[data-close-amount-dialog]").forEach((button) => {
    button.addEventListener("click", () => amountDialog.close());
  });

  grid.addEventListener("click", async (event) => {
    const edit = event.target.closest("[data-edit-goal]");
    const update = event.target.closest("[data-update-goal-amount]");
    const remove = event.target.closest("[data-delete-goal]");
    if (edit) openEditDialog(edit.dataset.editGoal);
    if (update) openAmountDialog(update.dataset.updateGoalAmount);
    if (remove && await ui.confirmAction({
      title: "Vai dzēst uzkrājuma mērķi?",
      message: "Mērķis un pašlaik uzkrātā summa tiks neatgriezeniski dzēsta.",
      confirmLabel: "Dzēst mērķi",
    })) {
      try {
        await api.deleteGoal(remove.dataset.deleteGoal);
        ui.toast("Uzkrājuma mērķis ir dzēsts.");
        await loadGoals();
      } catch (error) {
        showError(error);
      }
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const saveButton = document.querySelector("[data-save-goal]");
    const values = Object.fromEntries(new FormData(form).entries());
    const goalId = values.savings_goals_id;
    delete values.savings_goals_id;
    formMessage.classList.remove("visible");
    ui.clearFieldErrors(form);
    ui.setButtonLoading(saveButton, true, "Saglabā…");
    try {
      if (goalId) await api.updateGoal(goalId, values);
      else await api.createGoal(values);
      dialog.close();
      ui.toast(goalId ? "Uzkrājuma mērķis ir atjaunināts." : "Uzkrājuma mērķis ir izveidots.");
      await loadGoals();
    } catch (error) {
      ui.showFieldErrors(form, error.payload?.errors || {});
      formMessage.textContent = error.message;
      formMessage.classList.add("visible");
    } finally {
      ui.setButtonLoading(saveButton, false);
    }
  });

  amountForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const saveButton = document.querySelector("[data-save-amount]");
    const values = Object.fromEntries(new FormData(amountForm).entries());
    const goalId = values.savings_goals_id;
    delete values.savings_goals_id;
    amountMessage.classList.remove("visible");
    ui.clearFieldErrors(amountForm);
    ui.setButtonLoading(saveButton, true, "Atjaunina…");
    try {
      await api.updateGoal(goalId, values);
      amountDialog.close();
      ui.toast("Uzkrātā summa ir atjaunināta.");
      await loadGoals();
    } catch (error) {
      ui.showFieldErrors(amountForm, error.payload?.errors || {});
      amountMessage.textContent = error.message;
      amountMessage.classList.add("visible");
    } finally {
      ui.setButtonLoading(saveButton, false);
    }
  });

  await loadGoals();
});
