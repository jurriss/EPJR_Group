document.addEventListener("DOMContentLoaded", async () => {
  const form = document.querySelector("[data-profile-form]");
  const message = document.querySelector("[data-profile-message]");
  const deleteButton = document.querySelector("[data-delete-account]");
  const loading = document.querySelector("[data-profile-loading]");
  const content = document.querySelector("[data-profile-content]");
  if (!form) return;

  await window.PennywiseAuth.ready;
  let response;
  try {
    response = await window.PennywiseAPI.getProfile();
  } catch (error) {
    message.textContent = error.message;
    message.dataset.kind = "error";
    message.hidden = false;
    loading.hidden = true;
    return;
  }

  const user = response.data.user;
  let savedCurrency = user.currency;
  for (const field of ["username", "email", "first_name", "last_name", "age", "currency"]) {
    if (form.elements[field]) form.elements[field].value = user[field] ?? "";
  }
  loading.hidden = true;
  content.hidden = false;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = form.querySelector("button[type='submit']");
    const data = Object.fromEntries(new FormData(form).entries());
    const ui = window.PennywiseUI;
    data.age = Number(data.age);
    ui.clearFieldErrors(form);
    ui.setButtonLoading(submitButton, true, "Saglabā…");
    try {
      const result = await window.PennywiseAPI.updateProfile(data);
      ui.toast(result.message);
      message.hidden = true;
      if (result.data.user.currency !== savedCurrency) {
        savedCurrency = result.data.user.currency;
        window.location.reload();
      }
    } catch (error) {
      ui.showFieldErrors(form, error.payload?.errors || {});
      message.textContent = error.message;
      message.dataset.kind = "error";
      message.hidden = false;
    } finally {
      ui.setButtonLoading(submitButton, false);
    }
  });

  deleteButton?.addEventListener("click", async () => {
    const confirmed = await window.PennywiseUI.confirmAction({
      title: "Vai dzēst savu Pennywise kontu?",
      message: "Tavs profils un visi ar to saistītie finanšu dati tiks neatgriezeniski dzēsti. Šo darbību nevar atsaukt.",
      confirmLabel: "Dzēst kontu",
    });
    if (!confirmed) return;
    window.PennywiseUI.setButtonLoading(deleteButton, true, "Dzēš…");
    try {
      await window.PennywiseAPI.deleteAccount();
      window.location.replace("register.html");
    } catch (error) {
      message.textContent = error.message;
      message.dataset.kind = "error";
      message.hidden = false;
      window.PennywiseUI.setButtonLoading(deleteButton, false);
    }
  });
});
