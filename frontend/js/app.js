"use strict";

const API_BASE_URL = "https://cj2v75mr48.execute-api.us-east-1.amazonaws.com";
const REQUEST_TIMEOUT_MS = 15000;
const PLACEHOLDER_IMAGE = "assets/artist-placeholder.svg";

const elements = {
  form: document.querySelector("#search-form"), input: document.querySelector("#artist-input"),
  button: document.querySelector("#search-button"), formMessage: document.querySelector("#form-message"),
  loading: document.querySelector("#loading-state"), error: document.querySelector("#error-state"),
  errorMessage: document.querySelector("#error-message"), result: document.querySelector("#result"),
  image: document.querySelector("#artist-image"), name: document.querySelector("#artist-name"),
  genre: document.querySelector("#artist-genre"), country: document.querySelector("#artist-country"),
  year: document.querySelector("#artist-year"), biography: document.querySelector("#artist-biography"),
  badges: document.querySelector("#source-badges")
  , members: document.querySelector("#artist-members"), membersSection: document.querySelector("#members-section"),
  albums: document.querySelector("#artist-albums"), albumsSection: document.querySelector("#albums-section")
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

function getSources(data) {
  const sourceText = String(data.metadata?.source || "").toLowerCase();
  const ids = data.artist?.source_ids || {};
  const sources = [];
  if (sourceText.includes("theaudiodb") || ids.theaudiodb) sources.push("TheAudioDB");
  if (sourceText.includes("musicbrainz") || ids.musicbrainz) sources.push("MusicBrainz");
  return sources.length ? sources : ["SoundScope"];
}

function renderArtist(data) {
  if (!data || typeof data !== "object" || !data.artist || !data.artist.name) throw new Error("UNEXPECTED_RESPONSE");
  const artist = data.artist;
  elements.name.textContent = artist.name;
  elements.genre.textContent = artist.genre || "Não informado";
  elements.country.textContent = artist.country || "Não informado";
  elements.year.textContent = artist.formed_year || "Não informado";
  elements.biography.textContent = artist.biography || "Biografia não disponível no momento.";
  elements.image.src = artist.image_url || PLACEHOLDER_IMAGE;
  elements.image.alt = artist.image_url ? `Imagem de ${artist.name}` : `Imagem de ${artist.name} não disponível`;
  elements.image.onerror = () => { elements.image.onerror = null; elements.image.src = PLACEHOLDER_IMAGE; elements.image.alt = `Imagem de ${artist.name} não disponível`; };
  elements.badges.replaceChildren(...getSources(data).map((source) => { const badge = document.createElement("span"); badge.className = "source-badge"; badge.textContent = source; return badge; }));
  renderMembers(Array.isArray(artist.members) ? artist.members : []);
  renderAlbums(Array.isArray(artist.albums) ? artist.albums : []);
}

function renderMembers(members) {
  elements.membersSection.classList.toggle("is-hidden", members.length === 0);
  elements.members.replaceChildren(...members.map((member) => {
    const card = document.createElement("article");
    const name = document.createElement("h4"); name.textContent = member.name || "Nome não informado"; card.append(name);
    if (member.role) { const role = document.createElement("p"); role.textContent = member.role; card.append(role); }
    return card;
  }));
}

function renderAlbums(albums) {
  elements.albumsSection.classList.toggle("is-hidden", albums.length === 0);
  elements.albums.replaceChildren(...albums.map((album) => {
    const card = document.createElement("article"); card.className = "album";
    const visual = document.createElement("div"); visual.className = "album__visual";
    const image = document.createElement("img"); image.src = album.cover_url || PLACEHOLDER_IMAGE; image.alt = album.cover_url ? `Capa de ${album.title}` : `Capa de ${album.title} não disponível`; image.loading = "lazy";
    image.onerror = () => { image.onerror = null; image.src = PLACEHOLDER_IMAGE; };
    const title = document.createElement("h4"); title.textContent = album.title || "Título não informado";
    const year = document.createElement("p"); year.textContent = album.year || "Ano não informado";
    visual.append(image); card.append(visual, title, year); return card;
  }));
}

function friendlyError(error) {
  if (error.name === "AbortError") return "A consulta demorou mais que o esperado. Verifique sua conexão e tente novamente.";
  if (error.message === "NOT_FOUND") return "Não encontramos esse artista. Confira o nome e tente outra busca.";
  if (error.message === "UNEXPECTED_RESPONSE") return "Recebemos uma resposta inesperada. Tente novamente em instantes.";
  return "Não foi possível consultar os dados agora. Tente novamente.";
}

async function searchArtist(artistName) {
  if (requestInProgress) return;
  requestInProgress = true;
  elements.formMessage.textContent = "";
  setState("loading");
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}/artist/${encodeURIComponent(artistName)}`, { headers: { Accept: "application/json" }, signal: controller.signal });
    if (response.status === 404) throw new Error("NOT_FOUND");
    if (!response.ok) throw new Error(`HTTP_${response.status}`);
    const data = await response.json();
    renderArtist(data);
    setState("success");
    window.setTimeout(() => elements.result.scrollIntoView({ behavior: "smooth", block: "center" }), 100);
  } catch (error) {
    setState("error", friendlyError(error));
  } finally {
    window.clearTimeout(timeoutId);
    requestInProgress = false;
    elements.button.disabled = false;
    elements.form.classList.remove("is-loading");
    elements.input.setAttribute("aria-busy", "false");
  }
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  const artistName = elements.input.value.trim();
  if (!artistName) { elements.formMessage.textContent = "Digite o nome de um artista para pesquisar."; elements.input.focus(); return; }
  searchArtist(artistName);
});
