document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-auth-form]");
  const message = document.querySelector("[data-auth-message]");
  if (!form || !message) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = form.querySelector("button[type='submit']");
    const data = Object.fromEntries(new FormData(form).entries());
    const ui = window.PennywiseUI;
    if (data.age) data.age = Number(data.age);
    message.classList.remove("visible");
    ui.clearFieldErrors(form);
    ui.setButtonLoading(
      submitButton,
      true,
      form.dataset.authForm === "register" ? "Izveido kontu..." : "Piesakās...",
    );

    try {
      if (form.dataset.authForm === "register") {
        await window.PennywiseAPI.register(data);
      } else {
        await window.PennywiseAPI.login(data);
      }
      const requestedPage = new URLSearchParams(window.location.search).get("next");
      const safePage = /^[A-Za-z0-9_-]+\.html$/.test(requestedPage || "")
        ? requestedPage
        : "overview.html";
      window.location.replace(safePage);
    } catch (error) {
      const errors = error.payload?.errors;
      ui.showFieldErrors(form, errors || {});
      message.textContent = error.message;
      message.dataset.kind = "error";
      message.classList.add("visible");
      ui.setButtonLoading(submitButton, false);
    }
  });
});
