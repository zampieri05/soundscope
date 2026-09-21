"use strict";

/* SoundScope 2.2 · Global Search */
(() => {
  const form = document.querySelector("#search-form");
  const input = document.querySelector("#artist-input");
  if (!form || !input) return;

  const recentKey = "soundscope.recentArtists";
  const readRecent = () => {
    try { return JSON.parse(localStorage.getItem(recentKey) || "[]"); } catch (_) { return []; }
  };
  const saveRecent = (name) => {
    const next = [name, ...readRecent().filter((item) => item.toLowerCase() !== name.toLowerCase())].slice(0, 6);
    localStorage.setItem(recentKey, JSON.stringify(next));
  };

  const panel = document.createElement("div");
  panel.className = "quick-search";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Busca rápida");
  panel.innerHTML = '<div class="quick-search__box"><span>⌕</span><input type="search" placeholder="Busque qualquer artista..." aria-label="Busque qualquer artista"><kbd>ESC</kbd></div><div class="quick-search__recent"></div>';
  document.body.append(panel);
  const quickInput = panel.querySelector("input");
  const recent = panel.querySelector(".quick-search__recent");

  const renderRecent = () => {
    const items = readRecent();
    recent.replaceChildren();
    if (!items.length) return;
    const title = document.createElement("p"); title.textContent = "Vistos recentemente"; recent.append(title);
    items.forEach((name) => {
      const button = document.createElement("button"); button.type = "button"; button.textContent = name;
      button.addEventListener("click", () => go(name)); recent.append(button);
    });
  };
  const go = (name) => {
    const value = String(name || "").trim(); if (!value) return;
    saveRecent(value);
    location.href = `artist.html?artist=${encodeURIComponent(value)}`;
  };
  const open = () => { renderRecent(); panel.classList.add("is-open"); quickInput.value = ""; setTimeout(() => quickInput.focus(), 30); };
  const close = () => panel.classList.remove("is-open");

  form.addEventListener("submit", () => { const value = input.value.trim(); if (value) saveRecent(value); }, true);
  quickInput.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); go(quickInput.value); } });
  panel.addEventListener("click", (event) => { if (event.target === panel) close(); });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); open(); }
    if (event.key === "Escape") close();
  });
})();