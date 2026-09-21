"use strict";
(() => {
  const $ = (s) => document.querySelector(s);
  const modal = $("#account-modal"), entry = $("#account-entry"), status = $("#account-status");
  if (!modal || !entry) return;
  const tabs = [...modal.querySelectorAll("[data-account-tab]")];
  const login = $("#account-login-form"), signup = $("#account-signup-form");
  const setTab = (name) => {
    tabs.forEach((b) => b.classList.toggle("is-active", b.dataset.accountTab === name));
    login?.classList.toggle("is-hidden", name !== "login");
    signup?.classList.toggle("is-hidden", name !== "signup");
    if (status) status.textContent = "";
  };
  const open = () => { document.documentElement.classList.add("account-open"); modal.classList.remove("is-hidden"); document.documentElement.style.overflow = "hidden"; requestAnimationFrame(() => modal.querySelector("input")?.focus({ preventScroll: true })); };
  const close = () => { modal.classList.add("is-hidden"); document.documentElement.classList.remove("account-open"); document.documentElement.style.overflow = ""; entry.focus({ preventScroll: true }); };
  entry.addEventListener("click", open);
  modal.querySelectorAll("[data-account-provider]").forEach((button) => button.addEventListener("click", () => { const provider = button.dataset.accountProvider; status.textContent = `${provider}: interface pronta. Vamos ativar o OAuth assim que o Cognito e as credenciais do provedor forem configurados.`; }));
  modal.querySelectorAll("[data-account-close]").forEach((el) => el.addEventListener("click", close));
  tabs.forEach((b) => b.addEventListener("click", () => setTab(b.dataset.accountTab)));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal.classList.contains("is-hidden")) close(); });
  const pending = (e) => {
    e.preventDefault();
    if (!e.currentTarget.reportValidity()) return;
    status.textContent = "Interface pronta. A autenticação segura será conectada ao Amazon Cognito na próxima etapa.";
  };
  login?.addEventListener("submit", pending);
  signup?.addEventListener("submit", pending);
})();
