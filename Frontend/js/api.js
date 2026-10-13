(function () {
  "use strict";

  async function request(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });

    const payload = await response.json().catch(() => ({
      success: false,
      message: "Serveris atgrieza nenolasāmu atbildi.",
    }));

    if (!response.ok) {
      const error = new Error(payload.message || "Pieprasījumu neizdevās izpildīt.");
      error.status = response.status;
      error.payload = payload;
      if (response.status === 401 && document.body.hasAttribute("data-auth-required")) {
        const nextPage = encodeURIComponent(window.location.pathname.split("/").pop() || "overview.html");
        window.location.replace(`login.html?next=${nextPage}`);
      }
      throw error;
    }

    return payload;
  }

  function setStatus(element, state, label) {
    if (!element) return;
    element.dataset.state = state;
    const labelElement = element.querySelector("[data-status-label]");
    if (labelElement) labelElement.textContent = label;
  }

  function toast(message, kind = "success") {
    let region = document.querySelector("[data-toast-region]");
    if (!region) {
      region = document.createElement("div");
      region.className = "toast-region";
      region.dataset.toastRegion = "";
      region.setAttribute("aria-live", "polite");
      region.setAttribute("aria-label", "Paziņojumi");
      document.body.append(region);
    }
    const item = document.createElement("div");
    item.className = `toast toast-${kind}`;
    item.setAttribute("role", kind === "error" ? "alert" : "status");
    const text = document.createElement("span");
    text.textContent = message;
    const close = document.createElement("button");
    close.type = "button";
    close.setAttribute("aria-label", "Aizvērt paziņojumu");
    close.textContent = "×";
    close.addEventListener("click", () => item.remove());
    item.append(text, close);
    region.append(item);
    window.setTimeout(() => item.remove(), 5000);
  }

  function clearFieldErrors(form) {
    form.querySelectorAll(".field-error").forEach((element) => element.remove());
    form.querySelectorAll("[aria-invalid='true']").forEach((field) => {
      field.removeAttribute("aria-invalid");
      field.removeAttribute("aria-describedby");
    });
  }

  function showFieldErrors(form, errors = {}) {
    clearFieldErrors(form);
    Object.entries(errors).forEach(([name, message]) => {
      const field = form.elements[name];
      if (!field) return;
      const error = document.createElement("small");
      const id = `${form.dataset.formId || "form"}-${name}-error`;
      error.id = id;
      error.className = "field-error";
      error.textContent = message;
      field.setAttribute("aria-invalid", "true");
      field.setAttribute("aria-describedby", id);
      field.closest(".field")?.append(error);
    });
  }

  function setButtonLoading(button, loading, loadingLabel = "Saglabā...") {
    if (!button) return;
    if (loading) {
      button.dataset.originalLabel = button.textContent;
      button.textContent = loadingLabel;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
    } else {
      button.textContent = button.dataset.originalLabel || button.textContent;
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }

  function confirmAction({ title, message, confirmLabel = "Dzēst" }) {
    return new Promise((resolve) => {
      const dialog = document.createElement("dialog");
      dialog.className = "modal confirm-modal";
      const card = document.createElement("div");
      card.className = "modal-card";
      const heading = document.createElement("h2");
      heading.textContent = title;
      const copy = document.createElement("p");
      copy.className = "muted";
      copy.textContent = message;
      const actions = document.createElement("div");
      actions.className = "form-actions modal-actions";
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "button button-secondary";
      cancel.textContent = "Atcelt";
      const confirm = document.createElement("button");
      confirm.type = "button";
      confirm.className = "button button-danger";
      confirm.textContent = confirmLabel;
      actions.append(cancel, confirm);
      card.append(heading, copy, actions);
      dialog.append(card);
      document.body.append(dialog);
      let accepted = false;
      cancel.addEventListener("click", () => dialog.close());
      confirm.addEventListener("click", () => { accepted = true; dialog.close(); });
      dialog.addEventListener("close", () => { dialog.remove(); resolve(accepted); }, { once: true });
      dialog.showModal();
      cancel.focus();
    });
  }

  function promptAction({ title, label, value = "", confirmLabel = "Saglabāt" }) {
    return new Promise((resolve) => {
      const dialog = document.createElement("dialog");
      dialog.className = "modal confirm-modal";
      const form = document.createElement("form");
      form.className = "modal-card";
      const heading = document.createElement("h2");
      heading.textContent = title;
      const field = document.createElement("div");
      field.className = "field prompt-field";
      const fieldLabel = document.createElement("label");
      fieldLabel.textContent = label;
      const input = document.createElement("input");
      input.value = value;
      input.required = true;
      input.maxLength = 60;
      fieldLabel.htmlFor = "prompt-action-input";
      input.id = "prompt-action-input";
      field.append(fieldLabel, input);
      const actions = document.createElement("div");
      actions.className = "form-actions modal-actions";
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "button button-secondary";
      cancel.textContent = "Atcelt";
      const confirm = document.createElement("button");
      confirm.type = "submit";
      confirm.className = "button button-primary";
      confirm.textContent = confirmLabel;
      actions.append(cancel, confirm);
      form.append(heading, field, actions);
      dialog.append(form);
      document.body.append(dialog);
      let result = null;
      cancel.addEventListener("click", () => dialog.close());
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        result = input.value.trim();
        if (result) dialog.close();
      });
      dialog.addEventListener("close", () => { dialog.remove(); resolve(result); }, { once: true });
      dialog.showModal();
      input.focus();
      input.select();
    });
  }

  function withQuery(path, parameters = {}) {
    const query = new URLSearchParams();
    Object.entries(parameters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, value);
    });
    const suffix = query.toString();
    return suffix ? `${path}?${suffix}` : path;
  }

  function initializeShell() {
    document.querySelectorAll("[data-current-year]").forEach((element) => {
      element.textContent = new Date().getFullYear();
    });

    const menuButtons = document.querySelectorAll("[data-menu-toggle]");
    const closeNavigation = () => {
      document.body.classList.remove("nav-open");
      menuButtons.forEach((button) => button.setAttribute("aria-expanded", "false"));
    };
    if (document.querySelector(".sidebar")) {
      const scrim = document.createElement("button");
      scrim.type = "button";
      scrim.className = "nav-scrim";
      scrim.setAttribute("aria-label", "Aizvērt izvēlni");
      scrim.addEventListener("click", closeNavigation);
      document.body.append(scrim);
    }
    menuButtons.forEach((button) => {
      button.setAttribute("aria-expanded", "false");
      button.addEventListener("click", () => {
        document.body.classList.toggle("nav-open");
        button.setAttribute("aria-expanded", String(document.body.classList.contains("nav-open")));
      });
    });
    document.querySelectorAll(".side-nav a").forEach((link) => {
      link.addEventListener("click", closeNavigation);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeNavigation();
    });

    document.querySelectorAll("[data-logout]").forEach((button) => {
      button.addEventListener("click", async () => {
        setButtonLoading(button, true, "Izrakstās...");
        try {
          await window.PennywiseAPI.logout();
        } catch (error) {
          // A missing or expired session has the same destination.
        }
        window.location.replace("login.html");
      });
    });
  }

  async function initializeAuthentication() {
    const requiresAuthentication = document.body.hasAttribute("data-auth-required");
    const requiresAdministrator = document.body.hasAttribute("data-admin-required");
    const isGuestPage = document.body.hasAttribute("data-auth-guest");
    if (!requiresAuthentication && !requiresAdministrator && !isGuestPage) return null;

    try {
      const response = await window.PennywiseAPI.getMe();
      const user = response.data.user;
      if (isGuestPage) {
        window.location.replace("overview.html");
        return user;
      }
      if (requiresAdministrator && user.role !== "admin") {
        window.location.replace("overview.html?notice=admin");
        return null;
      }
      document.querySelectorAll("[data-user-name]").forEach((element) => {
        element.textContent = user.first_name || user.username;
      });
      document.querySelectorAll("[data-user-full-name]").forEach((element) => {
        element.textContent = `${user.first_name} ${user.last_name}`.trim() || user.username;
      });
      document.querySelectorAll("[data-user-currency]").forEach((element) => {
        element.textContent = `${user.currency} konts`;
      });
      document.querySelectorAll("[data-user-initial]").forEach((element) => {
        element.textContent = (user.first_name || user.username || "P").charAt(0).toUpperCase();
      });
      document.querySelectorAll("[data-admin-link]").forEach((element) => {
        element.hidden = user.role !== "admin";
      });
      document.body.classList.remove("auth-pending");
      return user;
    } catch (error) {
      if (isGuestPage) return null;
      const nextPage = encodeURIComponent(window.location.pathname.split("/").pop() || "overview.html");
      window.location.replace(`login.html?next=${nextPage}`);
      return null;
    }
  }

  window.PennywiseAPI = {
    request,
    getHealth: () => request("/api/health"),
    getDatabaseHealth: () => request("/api/health/database"),
    register: (data) => request("/api/auth/register", { method: "POST", body: JSON.stringify(data) }),
    login: (data) => request("/api/auth/login", { method: "POST", body: JSON.stringify(data) }),
    logout: () => request("/api/auth/logout", { method: "POST" }),
    getMe: () => request("/api/auth/me"),
    getProfile: () => request("/api/users/me"),
    updateProfile: (data) => request("/api/users/me", { method: "PUT", body: JSON.stringify(data) }),
    deleteAccount: () => request("/api/users/me", { method: "DELETE" }),
    getCategories: (type) => request(withQuery("/api/categories", { type })),
    createCategory: (data) => request("/api/categories", { method: "POST", body: JSON.stringify(data) }),
    updateCategory: (id, data) => request(`/api/categories/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    deleteCategory: (id) => request(`/api/categories/${id}`, { method: "DELETE" }),
    getIncome: () => request("/api/income"),
    createIncome: (data) => request("/api/income", { method: "POST", body: JSON.stringify(data) }),
    updateIncome: (id, data) => request(`/api/income/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    deleteIncome: (id) => request(`/api/income/${id}`, { method: "DELETE" }),
    getTransactions: (parameters) => request(withQuery("/api/transactions", parameters)),
    getTransaction: (id) => request(`/api/transactions/${id}`),
    createTransaction: (data) => request("/api/transactions", { method: "POST", body: JSON.stringify(data) }),
    updateTransaction: (id, data) => request(`/api/transactions/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    deleteTransaction: (id) => request(`/api/transactions/${id}`, { method: "DELETE" }),
    getBudgets: (month) => request(withQuery("/api/expenses", { month })),
    createBudget: (data) => request("/api/expenses", { method: "POST", body: JSON.stringify(data) }),
    updateBudget: (id, data) => request(`/api/expenses/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    deleteBudget: (id) => request(`/api/expenses/${id}`, { method: "DELETE" }),
    getOverview: (month) => request(withQuery("/api/overview", { month })),
    getGoals: () => request("/api/savings-goals"),
    getGoal: (id) => request(`/api/savings-goals/${id}`),
    createGoal: (data) => request("/api/savings-goals", { method: "POST", body: JSON.stringify(data) }),
    updateGoal: (id, data) => request(`/api/savings-goals/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    deleteGoal: (id) => request(`/api/savings-goals/${id}`, { method: "DELETE" }),
    getAdminUsers: () => request("/api/admin/users"),
    updateAdminUser: (id, data) => request(`/api/admin/users/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    deleteAdminUser: (id) => request(`/api/admin/users/${id}`, { method: "DELETE" }),
    getAdminStatistics: () => request("/api/admin/statistics"),
  };
  window.PennywiseUI = {
    setStatus,
    toast,
    clearFieldErrors,
    showFieldErrors,
    setButtonLoading,
    confirmAction,
    promptAction,
  };
  const categoryTranslations = {
    "Food & coffee": "Ēdiens un kafija",
    Transport: "Transports",
    Education: "Izglītība",
    "Fun & social": "Izklaide un atpūta",
    Subscriptions: "Abonementi",
    Groceries: "Pārtikas preces",
    Housing: "Mājoklis",
    "Unknown category": "Nezināma kategorija",
  };
  window.PennywiseI18n = {
    categoryTitle: (title) => categoryTranslations[title] || title,
  };
  window.PennywiseAuth = { ready: null };

  document.addEventListener("DOMContentLoaded", () => {
    initializeShell();
    window.PennywiseAuth.ready = initializeAuthentication();
  });
})();
