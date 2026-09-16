"use strict";

const API_BASE_URL = "https://cj2v75mr48.execute-api.us-east-1.amazonaws.com";
const REQUEST_TIMEOUT_MS = 15000;
const PLACEHOLDER_IMAGE = "assets/artist-placeholder.svg";
const ACCENTS = [[168,137,255],[106,158,194],[192,116,133],[192,142,91],[104,165,143],[149,128,182]];

const $ = (selector) => document.querySelector(selector);
const elements = {
  form: $("#search-form"), input: $("#artist-input"), button: $("#search-button"), formMessage: $("#form-message"),
  loading: $("#loading-state"), error: $("#error-state"), errorMessage: $("#error-message"), result: $("#result"),
  image: $("#artist-image"), name: $("#artist-name"), meta: $("#artist-meta"), formed: $("#artist-formed"),
  genre: $("#artist-genre"), country: $("#artist-country"), year: $("#artist-year"), biography: $("#artist-biography"),
  biographyWrap: $("#biography-wrap"), readMore: $("#read-more"), members: $("#artist-members"),
  membersSection: $("#members-section"), membersNav: $("#members-nav"), albums: $("#artist-albums"),
  albumsSection: $("#albums-section"), albumsNav: $("#albums-nav")
};
let requestInProgress = false;

function setState(state, message = "") {
  elements.loading.classList.toggle("is-hidden", state !== "loading");
  elements.error.classList.toggle("is-hidden", state !== "error");
  elements.result.classList.toggle("is-hidden", state !== "success");
  elements.form.classList.toggle("is-loading", state === "loading");
  elements.button.disabled = state === "loading";
  elements.input.setAttribute("aria-busy", String(state === "loading"));
  if (state === "error") elements.errorMessage.textContent = message;
}

function setAccent(name) {
  const hash = [...name].reduce((value, character) => ((value << 5) - value + character.charCodeAt(0)) | 0, 0);
  const color = ACCENTS[Math.abs(hash) % ACCENTS.length];
  document.documentElement.style.setProperty("--accent", `rgb(${color.join(",")})`);
  document.documentElement.style.setProperty("--accent-rgb", color.join(","));
}

function setFact(id, element, value) {
  $(id).classList.toggle("is-hidden", !value);
  element.textContent = value || "";
}

function renderArtist(data) {
  if (!data || typeof data !== "object" || !data.artist || !data.artist.name) throw new Error("UNEXPECTED_RESPONSE");
  const artist = data.artist;
  setAccent(artist.name);
  elements.name.textContent = artist.name;
  elements.meta.textContent = [artist.genre, artist.country].filter(Boolean).join("  •  ");
  elements.meta.classList.toggle("is-hidden", !elements.meta.textContent);
  elements.formed.textContent = artist.formed_year ? `Formed ${artist.formed_year}` : "";
  elements.formed.classList.toggle("is-hidden", !artist.formed_year);
  setFact("#genre-fact", elements.genre, artist.genre);
  setFact("#country-fact", elements.country, artist.country);
  setFact("#year-fact", elements.year, artist.formed_year);
  renderBiography(artist.biography);
  elements.image.src = artist.image_url || PLACEHOLDER_IMAGE;
  elements.image.alt = artist.image_url ? `${artist.name}, artist photograph` : `${artist.name} artwork unavailable`;
  elements.image.onerror = () => { elements.image.onerror = null; elements.image.src = PLACEHOLDER_IMAGE; elements.image.alt = `${artist.name} artwork unavailable`; };
  renderMembers(Array.isArray(artist.members) ? artist.members : []);
  renderAlbums(Array.isArray(artist.albums) ? artist.albums : []);
  initializeReveal();
}

function renderBiography(biography) {
  const text = typeof biography === "string" ? biography.trim() : "";
  elements.biography.textContent = text || "A biography for this artist is not available yet.";
  const isLong = text.length > 900;
  elements.biographyWrap.classList.toggle("is-collapsed", isLong);
  elements.readMore.classList.toggle("is-hidden", !isLong);
  elements.readMore.setAttribute("aria-expanded", "false");
  elements.readMore.innerHTML = "Read more <span>↓</span>";
}

function renderMembers(members) {
  const visible = members.length > 0;
  elements.membersSection.classList.toggle("is-hidden", !visible);
  elements.membersNav.classList.toggle("is-hidden", !visible);
  elements.members.replaceChildren(...members.map((member, index) => {
    const card = document.createElement("article"); card.className = "member";
    const number = document.createElement("span"); number.className = "member__number"; number.textContent = String(index + 1).padStart(2, "0");
    const name = document.createElement("h4"); name.textContent = member.name || "Name unavailable";
    const role = document.createElement("p"); role.textContent = member.role || "Role not listed";
    card.append(number, name, role);
    if (typeof member.active === "boolean" || member.status) {
      const status = document.createElement("span"); status.className = "member__status";
      status.textContent = member.status || (member.active ? "Current member" : "Past member"); card.append(status);
    }
    return card;
  }));
}

function albumPlaceholder(title) {
  const fallback = document.createElement("div"); fallback.className = "album__placeholder";
  const brand = document.createElement("span"); brand.textContent = "SoundScope";
  const name = document.createElement("strong"); name.textContent = title || "Untitled release";
  fallback.append(brand, name); return fallback;
}

function renderAlbums(albums) {
  const sorted = albums.map((album, index) => ({ album, index })).sort((a, b) => {
    const first = Number.parseInt(a.album.year, 10); const second = Number.parseInt(b.album.year, 10);
    if (Number.isNaN(first) && Number.isNaN(second)) return a.index - b.index;
    if (Number.isNaN(first)) return 1; if (Number.isNaN(second)) return -1; return first - second || a.index - b.index;
  }).map(({ album }) => album);
  const visible = sorted.length > 0;
  elements.albumsSection.classList.toggle("is-hidden", !visible);
  elements.albumsNav.classList.toggle("is-hidden", !visible);
  elements.albums.replaceChildren(...sorted.map((album) => {
    const card = document.createElement("article"); card.className = "album";
    const visual = document.createElement("div"); visual.className = "album__visual";
    const fallback = albumPlaceholder(album.title); visual.append(fallback);
    if (album.cover_url) {
      const image = document.createElement("img"); image.src = album.cover_url; image.alt = `Cover of ${album.title || "untitled release"}`; image.loading = "lazy"; image.decoding = "async";
      image.onload = () => fallback.remove(); image.onerror = () => image.remove(); visual.append(image);
    }
    const title = document.createElement("h4"); title.textContent = album.title || "Title unavailable";
    const year = document.createElement("p"); year.textContent = album.year || "Year unavailable";
    card.append(visual, title, year); return card;
  }));
}

function friendlyError(error) {
  if (error.name === "AbortError") return "The request took longer than expected. Check your connection and try again.";
  if (error.message === "NOT_FOUND") return "No artist matched that name. Check the spelling or try a different search.";
  if (error.message === "UNEXPECTED_RESPONSE") return "The music archive returned an unexpected response. Please try again shortly.";
  return "The archive is temporarily unavailable. Please try again in a moment.";
}

async function searchArtist(artistName) {
  if (requestInProgress) return;
  requestInProgress = true; elements.formMessage.textContent = ""; setState("loading");
  elements.loading.scrollIntoView({ behavior: "smooth", block: "start" });
  const controller = new AbortController(); const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}/artist/${encodeURIComponent(artistName)}`, { headers: { Accept: "application/json" }, signal: controller.signal });
    if (response.status === 404) throw new Error("NOT_FOUND");
    if (!response.ok) throw new Error(`HTTP_${response.status}`);
    renderArtist(await response.json()); setState("success");
    window.setTimeout(() => elements.result.focus({ preventScroll: true }), 350);
  } catch (error) { setState("error", friendlyError(error)); elements.error.scrollIntoView({ behavior: "smooth", block: "center" }); }
  finally { window.clearTimeout(timeoutId); requestInProgress = false; elements.button.disabled = false; elements.form.classList.remove("is-loading"); elements.input.setAttribute("aria-busy", "false"); }
}

function focusSearch() { $("#top").scrollIntoView({ behavior: "smooth" }); window.setTimeout(() => elements.input.focus(), 350); }
function initializeReveal() {
  const items = document.querySelectorAll(".reveal:not(.is-visible)");
  if (!("IntersectionObserver" in window)) { items.forEach((item) => item.classList.add("is-visible")); return; }
  const observer = new IntersectionObserver((entries) => entries.forEach((entry) => { if (entry.isIntersecting) { entry.target.classList.add("is-visible"); observer.unobserve(entry.target); } }), { threshold: .08 });
  items.forEach((item) => observer.observe(item));
}

elements.form.addEventListener("submit", (event) => { event.preventDefault(); const name = elements.input.value.trim(); if (!name) { elements.formMessage.textContent = "Enter an artist or band name to begin."; elements.input.focus(); return; } searchArtist(name); });
elements.readMore.addEventListener("click", () => { const collapsed = elements.biographyWrap.classList.toggle("is-collapsed"); elements.readMore.setAttribute("aria-expanded", String(!collapsed)); elements.readMore.innerHTML = collapsed ? "Read more <span>↓</span>" : "Show less <span>↑</span>"; });
$("#nav-search").addEventListener("click", focusSearch); $("#new-search").addEventListener("click", focusSearch); $("#retry-search").addEventListener("click", focusSearch);
document.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); focusSearch(); } });
initializeReveal();
