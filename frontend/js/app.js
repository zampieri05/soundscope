"use strict";

const API_BASE_URL = "https://cj2v75mr48.execute-api.us-east-1.amazonaws.com";
const REQUEST_TIMEOUT_MS = 15000;
const PLACEHOLDER_IMAGE = "assets/artist-placeholder.svg";
const $ = (selector) => document.querySelector(selector);
const elements = {
  home: $("#inicio"), orb: $("#sound-orb"), form: $("#search-form"), input: $("#artist-input"), button: $("#search-button"), message: $("#form-message"),
  loading: $("#loading-state"), error: $("#error-state"), errorMessage: $("#error-message"), result: $("#result"), image: $("#artist-image"),
  name: $("#artist-name"), meta: $("#artist-meta"), formed: $("#artist-formed"), genre: $("#artist-genre"), country: $("#artist-country"), year: $("#artist-year"),
  biography: $("#artist-biography"), biographyWrap: $("#biography-wrap"), readMore: $("#read-more"), members: $("#artist-members"), membersSection: $("#integrantes"),
  membersNav: $("#members-nav"), albums: $("#artist-albums"), albumsSection: $("#discografia"), albumsNav: $("#albums-nav"), range: $("#timeline-range"),
  dataTrigger: $("#data-trigger"), dataPanel: $("#data-panel"), dataClose: $("#data-close"), backdrop: $("#panel-backdrop"), sourceIds: $("#source-ids"), sourceIdsWrap: $("#source-ids-wrap")
};
let requestInProgress = false;

function setState(state, message = "") {
  elements.loading.classList.toggle("is-hidden", state !== "loading");
  elements.error.classList.toggle("is-hidden", state !== "error");
  elements.result.classList.toggle("is-hidden", state !== "success");
  elements.home.classList.toggle("is-searching", state === "loading");
  elements.button.disabled = state === "loading";
  elements.input.setAttribute("aria-busy", String(state === "loading"));
  if (state === "error") elements.errorMessage.textContent = message;
}

function setFact(selector, node, value) {
  $(selector).classList.toggle("is-hidden", !value);
  node.textContent = value || "";
}

function renderArtist(payload) {
  if (!payload || typeof payload !== "object" || !payload.artist?.name) throw new Error("UNEXPECTED_RESPONSE");
  const artist = payload.artist;
  elements.name.textContent = artist.name;
  elements.meta.textContent = [artist.genre, artist.country].filter(Boolean).join("  •  ");
  elements.meta.classList.toggle("is-hidden", !elements.meta.textContent);
  elements.formed.textContent = artist.formed_year ? `Em atividade desde ${artist.formed_year}` : "";
  elements.formed.classList.toggle("is-hidden", !artist.formed_year);
  setFact("#genre-fact", elements.genre, artist.genre);
  setFact("#country-fact", elements.country, artist.country);
  setFact("#year-fact", elements.year, artist.formed_year);
  renderBiography(artist.biography);
  renderMembers(Array.isArray(artist.members) ? artist.members : []);
  renderAlbums(Array.isArray(artist.albums) ? artist.albums : []);
  renderSourceIds(artist.source_ids);
  elements.image.src = artist.image_url || PLACEHOLDER_IMAGE;
  elements.image.alt = artist.image_url ? `Foto de ${artist.name}` : `Imagem de ${artist.name} indisponível`;
  elements.image.onerror = () => { elements.image.onerror = null; elements.image.src = PLACEHOLDER_IMAGE; elements.image.alt = `Imagem de ${artist.name} indisponível`; };
  initializeReveal();
}

function renderBiography(value) {
  const text = typeof value === "string" ? value.trim() : "";
  elements.biography.textContent = text || "Ainda não há uma biografia disponível para este artista.";
  const isLong = text.length > 900;
  elements.biographyWrap.classList.toggle("is-collapsed", isLong);
  elements.readMore.classList.toggle("is-hidden", !isLong);
  elements.readMore.setAttribute("aria-expanded", "false");
  elements.readMore.innerHTML = "Ler mais <span>↓</span>";
}

function renderMembers(members) {
  const visible = members.length > 0;
  elements.membersSection.classList.toggle("is-hidden", !visible);
  elements.membersNav.classList.toggle("is-hidden", !visible);
  elements.members.replaceChildren(...members.map((member, index) => {
    const row = document.createElement("article"); row.className = "member";
    const number = document.createElement("span"); number.className = "member__number"; number.textContent = String(index + 1).padStart(2, "0");
    const name = document.createElement("h4"); name.textContent = member.name || "Nome indisponível";
    const role = document.createElement("p"); role.textContent = member.role || "Função não informada";
    row.append(number, name, role);
    if (typeof member.active === "boolean" || member.status) {
      const status = document.createElement("span"); status.className = "member__status";
      status.textContent = member.status || (member.active ? "Integrante atual" : "Ex-integrante"); row.append(status);
    }
    return row;
  }));
}

function albumPlaceholder(title) {
  const fallback = document.createElement("div"); fallback.className = "album__placeholder";
  const label = document.createElement("span"); label.textContent = "SoundScope / Arquivo";
  const name = document.createElement("strong"); name.textContent = title || "Lançamento sem título";
  fallback.append(label, name); return fallback;
}

function renderAlbums(albums) {
  const sorted = albums.map((album, index) => ({ album, index })).sort((a, b) => {
    const first = Number.parseInt(a.album.year, 10); const second = Number.parseInt(b.album.year, 10);
    if (Number.isNaN(first) && Number.isNaN(second)) return a.index - b.index;
    if (Number.isNaN(first)) return 1; if (Number.isNaN(second)) return -1;
    return first - second || a.index - b.index;
  }).map(({ album }) => album);
  const visible = sorted.length > 0;
  elements.albumsSection.classList.toggle("is-hidden", !visible);
  elements.albumsNav.classList.toggle("is-hidden", !visible);
  const years = sorted.map((album) => Number.parseInt(album.year, 10)).filter(Number.isFinite);
  elements.range.textContent = years.length ? `${Math.min(...years)} → ${Math.max(...years)}` : "Lançamentos em ordem cronológica";
  elements.albums.replaceChildren(...sorted.map((album) => {
    const card = document.createElement("article"); card.className = "album";
    const visual = document.createElement("div"); visual.className = "album__visual";
    const fallback = albumPlaceholder(album.title); visual.append(fallback);
    if (album.cover_url) {
      const image = document.createElement("img"); image.src = album.cover_url; image.alt = `Capa de ${album.title || "álbum sem título"}`; image.loading = "lazy"; image.decoding = "async";
      image.onload = () => fallback.remove(); image.onerror = () => image.remove(); visual.append(image);
    }
    const year = document.createElement("p"); year.className = "album__year"; year.textContent = album.year || "Ano não informado";
    const title = document.createElement("h4"); title.textContent = album.title || "Título não informado";
    card.append(visual, year, title); return card;
  }));
}

function renderSourceIds(sourceIds) {
  const entries = sourceIds && typeof sourceIds === "object" ? Object.entries(sourceIds).filter(([, value]) => value) : [];
  elements.sourceIdsWrap.classList.toggle("is-hidden", entries.length === 0);
  elements.sourceIds.textContent = entries.map(([source, id]) => `${source}: ${id}`).join("\n");
}

function friendlyError(error) {
  if (error.name === "AbortError") return "A busca demorou mais que o esperado. Verifique sua conexão e tente novamente.";
  if (error.message === "NOT_FOUND") return "Nenhum resultado corresponde a esse nome. Confira a escrita ou tente outro artista.";
  if (error.message === "UNEXPECTED_RESPONSE") return "O arquivo musical retornou uma resposta inesperada. Tente novamente em instantes.";
  return "O arquivo está temporariamente indisponível. Tente novamente em alguns instantes.";
}

async function searchArtist(artistName) {
  if (requestInProgress) return;
  requestInProgress = true; elements.message.textContent = ""; setState("loading");
  elements.loading.scrollIntoView({ behavior: "smooth", block: "start" });
  const controller = new AbortController(); const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}/artist/${encodeURIComponent(artistName)}`, { headers: { Accept: "application/json" }, signal: controller.signal });
    if (response.status === 404) throw new Error("NOT_FOUND");
    if (!response.ok) throw new Error(`HTTP_${response.status}`);
    renderArtist(await response.json()); setState("success");
    elements.result.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => elements.result.focus({ preventScroll: true }), 500);
  } catch (error) {
    setState("error", friendlyError(error)); elements.error.scrollIntoView({ behavior: "smooth", block: "center" });
  } finally {
    window.clearTimeout(timeoutId); requestInProgress = false; elements.button.disabled = false; elements.input.setAttribute("aria-busy", "false"); elements.home.classList.remove("is-searching");
  }
}

function focusSearch() { elements.home.scrollIntoView({ behavior: "smooth" }); window.setTimeout(() => elements.input.focus(), 350); }
function toggleDataPanel(force) {
  const open = typeof force === "boolean" ? force : !elements.dataPanel.classList.contains("is-open");
  elements.dataPanel.classList.toggle("is-open", open); elements.backdrop.classList.toggle("is-open", open);
  elements.dataPanel.setAttribute("aria-hidden", String(!open)); elements.dataTrigger.setAttribute("aria-expanded", String(open));
  if (open) elements.dataClose.focus(); else elements.dataTrigger.focus();
}
function initializeReveal() {
  const items = document.querySelectorAll(".reveal:not(.is-visible)");
  if (!window.IntersectionObserver) { items.forEach((item) => item.classList.add("is-visible")); return; }
  const observer = new IntersectionObserver((entries) => entries.forEach((entry) => { if (entry.isIntersecting) { entry.target.classList.add("is-visible"); observer.unobserve(entry.target); } }), { threshold: .08 });
  items.forEach((item) => observer.observe(item));
}

elements.form.addEventListener("submit", (event) => { event.preventDefault(); const name = elements.input.value.trim(); if (!name) { elements.message.textContent = "Digite o nome de um artista ou banda para começar."; elements.input.focus(); return; } searchArtist(name); });
elements.readMore.addEventListener("click", () => { const collapsed = elements.biographyWrap.classList.toggle("is-collapsed"); elements.readMore.setAttribute("aria-expanded", String(!collapsed)); elements.readMore.innerHTML = collapsed ? "Ler mais <span>↓</span>" : "Mostrar menos <span>↑</span>"; });
elements.dataTrigger.addEventListener("click", () => toggleDataPanel()); elements.dataClose.addEventListener("click", () => toggleDataPanel(false)); elements.backdrop.addEventListener("click", () => toggleDataPanel(false));
$("#nav-search").addEventListener("click", focusSearch); $("#new-search").addEventListener("click", focusSearch); $("#retry-search").addEventListener("click", focusSearch);
document.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); focusSearch(); } if (event.key === "Escape" && elements.dataPanel.classList.contains("is-open")) toggleDataPanel(false); });
if (window.matchMedia("(pointer:fine)").matches && !window.matchMedia("(prefers-reduced-motion:reduce)").matches) {
  elements.home.addEventListener("pointermove", (event) => { const x = (event.clientX / window.innerWidth - .5) * 18; const y = (event.clientY / window.innerHeight - .5) * 14; elements.orb.style.setProperty("--orb-x", `${x}px`); elements.orb.style.setProperty("--orb-y", `${y}px`); });
}
initializeReveal();
