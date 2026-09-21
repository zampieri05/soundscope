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
  panel.innerHTML = '<div class="quick-search__box"><span>⌕</span><input type="search" placeholder="Busque qualquer artista..." aria-label="Busque qualquer artista"><kbd>ESC</kbd></div><div class="quick-search__suggestions" role="listbox"></div><div class="quick-search__recent"></div>';
  document.body.append(panel);
  const quickInput = panel.querySelector("input");
  const recent = panel.querySelector(".quick-search__recent");
  const suggestions = panel.querySelector(".quick-search__suggestions");
  let searchTimer = 0;
  let searchController = null;

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
  const renderSuggestions = (items) => {
    suggestions.replaceChildren();
    items.forEach((artist) => {
      const button = document.createElement("button"); button.type = "button"; button.className = "quick-search__result"; button.setAttribute("role", "option");
      const avatar = document.createElement("span"); avatar.className = "quick-search__avatar"; avatar.textContent = (artist.name || "?").slice(0, 1).toUpperCase();
      const copy = document.createElement("span"); const name = document.createElement("strong"); name.textContent = artist.name;
      const detail = document.createElement("small"); detail.textContent = [artist.type, artist.country, artist.disambiguation].filter(Boolean).join(" · ") || "Artista";
      copy.append(name, detail); button.append(avatar, copy);
      button.addEventListener("click", () => go(artist.name)); suggestions.append(button);
    });
  };
  const suggest = (query) => {
    clearTimeout(searchTimer); searchController?.abort();
    const value = query.trim(); if (value.length < 2) { suggestions.replaceChildren(); renderRecent(); return; }
    recent.replaceChildren();
    searchTimer = setTimeout(async () => {
      searchController = new AbortController();
      try {
        const url = "https://cj2v75mr48.execute-api.us-east-1.amazonaws.com/artist/" + encodeURIComponent(value) + "?suggest=1";
        const response = await fetch(url, { signal: searchController.signal, headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("SEARCH_FAILED");
        const data = await response.json();
        renderSuggestions((data.artists || []).filter((artist) => artist.name).slice(0, 6));
      } catch (error) { if (error.name !== "AbortError") suggestions.replaceChildren(); }
    }, 320);
  };
  const open = () => { suggestions.replaceChildren(); renderRecent(); panel.classList.add("is-open"); quickInput.value = ""; setTimeout(() => quickInput.focus(), 30); };
  const close = () => panel.classList.remove("is-open");

  form.addEventListener("submit", () => { const value = input.value.trim(); if (value) saveRecent(value); }, true);
  quickInput.addEventListener("input", () => suggest(quickInput.value));
  quickInput.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); go(quickInput.value); } });
  panel.addEventListener("click", (event) => { if (event.target === panel) close(); });
  const loadRabbitHole = async () => {
    if (!document.body.classList.contains("artist-route")) return;
    const artistName = new URLSearchParams(location.search).get("artist");
    const result = document.querySelector("#result");
    if (!artistName || !result) return;
    const section = document.createElement("section");
    section.className = "rabbit-hole";
    section.innerHTML = '<div class="rabbit-hole__heading"><p>Rabbit Hole</p><h2>Continue explorando</h2><span>Conexões documentadas pelo MusicBrainz</span></div><div class="rabbit-hole__grid" aria-live="polite"></div>';
    result.append(section);
    const grid = section.querySelector(".rabbit-hole__grid");
    try {
      const response = await fetch("https://cj2v75mr48.execute-api.us-east-1.amazonaws.com/artist/" + encodeURIComponent(artistName) + "?related=1");
      if (!response.ok) throw new Error("RELATED_FAILED");
      const data = await response.json();
      const artists = Array.isArray(data.artists) ? data.artists : [];
      if (!artists.length) { section.remove(); return; }
      artists.forEach((artist, index) => {
        const card = document.createElement("button"); card.type = "button"; card.className = "rabbit-hole__card";
        const number = document.createElement("span"); number.className = "rabbit-hole__number"; number.textContent = String(index + 1).padStart(2, "0");
        const copy = document.createElement("span"); const name = document.createElement("strong"); name.textContent = artist.name;
        const relation = document.createElement("small"); relation.textContent = artist.relation ? "Conexão: " + artist.relation : "Conexão MusicBrainz";
        copy.append(name, relation); const arrow = document.createElement("span"); arrow.textContent = "↗";
        card.append(number, copy, arrow); card.addEventListener("click", () => go(artist.name)); grid.append(card);
      });
    } catch (_) { section.remove(); }
  };
  loadRabbitHole();

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); open(); }
    if (event.key === "Escape") close();
  });
})();