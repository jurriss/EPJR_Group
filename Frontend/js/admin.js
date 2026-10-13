document.addEventListener("DOMContentLoaded", async () => {
  const usersBody = document.querySelector("[data-users-body]");
  const categoriesBody = document.querySelector("[data-categories-body]");
  const categoryForm = document.querySelector("[data-category-form]");
  const notice = document.querySelector("[data-admin-notice]");
  const ui = window.PennywiseUI;

  const currentUser = await window.PennywiseAuth.ready;
  if (!currentUser || currentUser.role !== "admin") return;

  function showNotice(message, kind = "success") {
    if (kind === "success") {
      notice.hidden = true;
      ui.toast(message);
      return;
    }
    notice.textContent = message;
    notice.dataset.kind = kind;
    notice.hidden = false;
  }

  function textElement(tag, text, className = "") {
    const element = document.createElement(tag);
    element.textContent = text ?? "";
    if (className) element.className = className;
    return element;
  }

  function emptyTableRow(columnCount, message) {
    const row = document.createElement("tr");
    const cell = textElement("td", message);
    cell.colSpan = columnCount;
    row.append(cell);
    return row;
  }

  function actionButton(label, dataAttribute, className) {
    const button = textElement("button", label, className);
    button.type = "button";
    button.setAttribute(dataAttribute, "");
    return button;
  }

  async function loadStatistics() {
    const response = await window.PennywiseAPI.getAdminStatistics();
    const statistics = response.data.statistics;
    document.querySelectorAll("[data-statistic]").forEach((element) => {
      element.textContent = statistics[element.dataset.statistic] ?? "0";
    });
  }

  async function loadUsers() {
    const response = await window.PennywiseAPI.getAdminUsers();
    const users = response.data.users;
    usersBody.replaceChildren();
    if (!users.length) {
      usersBody.append(emptyTableRow(4, "Lietotāji nav atrasti."));
      return;
    }
    users.forEach((user) => {
      const row = document.createElement("tr");
      row.dataset.userId = user.user_id;

      const account = document.createElement("td");
      account.append(textElement("strong", user.username), textElement("span", user.email));
      const name = textElement("td", `${user.first_name} ${user.last_name}`);

      const roleCell = document.createElement("td");
      const roleSelect = document.createElement("select");
      roleSelect.className = "compact-select";
      roleSelect.dataset.userRole = "";
      roleSelect.setAttribute("aria-label", `Lietotāja ${user.username} loma`);
      const userOption = new Option("Lietotājs", "user");
      const adminOption = new Option("Administrators", "admin");
      userOption.selected = user.role === "user";
      adminOption.selected = user.role === "admin";
      roleSelect.add(userOption);
      roleSelect.add(adminOption);
      roleCell.append(roleSelect);

      const actions = document.createElement("td");
      actions.className = "table-actions";
      actions.append(
        actionButton("Saglabāt", "data-save-user", "button button-quiet"),
        actionButton("Dzēst", "data-delete-user", "button button-danger"),
      );
      row.append(account, name, roleCell, actions);
      usersBody.append(row);
    });
  }

  async function loadCategories() {
    const response = await window.PennywiseAPI.getCategories();
    const categories = response.data.categories;
    categoriesBody.replaceChildren();
    if (!categories.length) {
      categoriesBody.append(emptyTableRow(3, "Kategorijas nav atrastas."));
      return;
    }
    categories.forEach((category) => {
      const row = document.createElement("tr");
      row.dataset.categoryId = category.category_id;
      row.dataset.categoryType = category.type || "expense";
      const title = document.createElement("td");
      title.append(textElement("strong", window.PennywiseI18n.categoryTitle(category.title)));
      const type = textElement("td", category.type === "income" ? "Ienākumi" : "Izdevumi");
      const actions = document.createElement("td");
      actions.className = "table-actions";
      actions.append(
        actionButton("Rediģēt", "data-edit-category", "button button-quiet"),
        actionButton("Dzēst", "data-delete-category", "button button-danger"),
      );
      row.append(title, type, actions);
      categoriesBody.append(row);
    });
  }

  usersBody?.addEventListener("click", async (event) => {
    const row = event.target.closest("[data-user-id]");
    if (!row) return;
    const userId = Number(row.dataset.userId);
    try {
      if (event.target.matches("[data-save-user]")) {
        const button = event.target;
        const role = row.querySelector("[data-user-role]").value;
        ui.setButtonLoading(button, true, "Saglabā…");
        try {
          const response = await window.PennywiseAPI.updateAdminUser(userId, { role });
          showNotice(response.message);
        } finally {
          ui.setButtonLoading(button, false);
        }
      }
      if (event.target.matches("[data-delete-user]")) {
        if (!await ui.confirmAction({
          title: "Vai dzēst šo lietotāju?",
          message: "Konts un visi tā finanšu dati tiks neatgriezeniski dzēsti.",
          confirmLabel: "Dzēst lietotāju",
        })) return;
        const response = await window.PennywiseAPI.deleteAdminUser(userId);
        showNotice(response.message);
        await Promise.all([loadUsers(), loadStatistics()]);
      }
    } catch (error) {
      showNotice(error.message, "error");
    }
  });

  categoriesBody?.addEventListener("click", async (event) => {
    const row = event.target.closest("[data-category-id]");
    if (!row) return;
    const categoryId = Number(row.dataset.categoryId);
    try {
      if (event.target.matches("[data-edit-category]")) {
        const currentTitle = row.querySelector("strong").textContent;
        const title = await ui.promptAction({
          title: "Rediģēt kategoriju",
          label: "Kategorijas nosaukums",
          value: currentTitle,
          confirmLabel: "Saglabāt kategoriju",
        });
        if (!title || title === currentTitle) return;
        const response = await window.PennywiseAPI.updateCategory(categoryId, {
          title,
          type: row.dataset.categoryType,
        });
        showNotice(response.message);
        await loadCategories();
      }
      if (event.target.matches("[data-delete-category]")) {
        if (!await ui.confirmAction({
          title: "Vai dzēst kategoriju?",
          message: "To var izdarīt tikai tad, ja kategorija netiek izmantota nevienā darījumā vai budžetā.",
          confirmLabel: "Dzēst kategoriju",
        })) return;
        const response = await window.PennywiseAPI.deleteCategory(categoryId);
        showNotice(response.message);
        await Promise.all([loadCategories(), loadStatistics()]);
      }
    } catch (error) {
      showNotice(error.message, "error");
    }
  });

  categoryForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const titleInput = categoryForm.elements.title;
    const submitButton = categoryForm.querySelector("button[type='submit']");
    ui.clearFieldErrors(categoryForm);
    ui.setButtonLoading(submitButton, true, "Pievieno…");
    try {
      const response = await window.PennywiseAPI.createCategory({
        title: titleInput.value,
        type: categoryForm.elements.type.value,
      });
      titleInput.value = "";
      showNotice(response.message);
      await Promise.all([loadCategories(), loadStatistics()]);
    } catch (error) {
      ui.showFieldErrors(categoryForm, error.payload?.errors || {});
      showNotice(error.message, "error");
    } finally {
      ui.setButtonLoading(submitButton, false);
    }
  });

  try {
    await Promise.all([loadStatistics(), loadUsers(), loadCategories()]);
  } catch (error) {
    showNotice(error.message, "error");
  }
});
