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
  dataTrigger: $("#data-trigger"), dataPanel: $("#data-panel"), dataClose: $("#data-close"), backdrop: $("#panel-backdrop"), sourceIds: $("#source-ids"), sourceIdsWrap: $("#source-ids-wrap"), sourceNames: $("#source-names"), albumsLoadMore: $("#albums-load-more")
};
let requestInProgress = false;
let spotifySession = null;
let currentArtistName = "";

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
  currentArtistName = artist.name;
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
  renderSourceIds(artist.source_ids, payload.metadata?.sources);
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

const ALBUM_PAGE_SIZE = 20;
let pendingAlbums = [];
let visibleAlbumCount = 0;

function albumCategory(album) {
  return window.SoundScopeDiscography.category(album);
}

function createAlbumCard(album) {
  const card = document.createElement("article"); card.className = "album";
  const visual = document.createElement("div"); visual.className = "album__visual";
  const fallback = albumPlaceholder(album.title); visual.append(fallback);
  if (album.cover_url) {
    const image = document.createElement("img"); image.src = album.cover_url; image.alt = `Capa de ${album.title || "lançamento sem título"}`; image.loading = "lazy"; image.decoding = "async";
    image.onload = () => fallback.remove(); image.onerror = () => image.remove(); visual.append(image);
  }
  const year = document.createElement("p"); year.className = "album__year"; year.textContent = album.year || "Ano não informado";
  const title = document.createElement("h4"); title.textContent = album.title || "Título não informado";
  const type = document.createElement("p"); type.className = "album__type"; type.textContent = albumCategory(album);
  const spotifyResult = document.createElement("div"); spotifyResult.className = "album__spotify"; spotifyResult.setAttribute("aria-live", "polite");
  card.tabIndex = 0; card.setAttribute("role", "button"); card.setAttribute("aria-label", `${album.title || "Lançamento"}. Consultar no Spotify`);
  const select = () => lookupSpotifyAlbum(album, card, spotifyResult);
  card.addEventListener("click", select); card.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); } });
  card.append(visual, year, title, type, spotifyResult); return card;
}

function loadMoreAlbums() {
  const next = window.SoundScopeDiscography.page(pendingAlbums, visibleAlbumCount, ALBUM_PAGE_SIZE);
  elements.albums.append(...next.map(createAlbumCard));
  visibleAlbumCount += next.length;
  elements.albumsLoadMore.classList.toggle("is-hidden", visibleAlbumCount >= pendingAlbums.length);
  elements.albumsLoadMore.setAttribute("aria-label", `Carregar mais lançamentos. ${pendingAlbums.length - visibleAlbumCount} restantes`);
}

function renderAlbums(albums) {
  pendingAlbums = albums.map((album, index) => ({ album, index })).sort((a, b) => {
    const category = albumCategory(a.album).localeCompare(albumCategory(b.album), "pt-BR");
    const first = Number.parseInt(a.album.year, 10); const second = Number.parseInt(b.album.year, 10);
    return category || (Number.isNaN(first) ? 1 : Number.isNaN(second) ? -1 : first - second) || a.index - b.index;
  }).map(({ album }) => album);
  visibleAlbumCount = 0; elements.albums.replaceChildren();
  const visible = pendingAlbums.length > 0;
  elements.albumsSection.classList.toggle("is-hidden", !visible); elements.albumsNav.classList.toggle("is-hidden", !visible);
  const years = pendingAlbums.map((album) => Number.parseInt(album.year, 10)).filter(Number.isFinite);
  elements.range.textContent = years.length ? `${Math.min(...years)} → ${Math.max(...years)}` : "Lançamentos organizados por tipo";
  if (visible) loadMoreAlbums(); else elements.albumsLoadMore.classList.add("is-hidden");
}
async function lookupSpotifyAlbum(album, card, output) {
  if (card.dataset.spotifyState === "loading" || card.dataset.spotifyState === "done") return;
  if (!spotifySession) { output.textContent = "Conecte o Spotify para ouvir este álbum."; card.dataset.spotifyState = "disconnected"; return; }
  const spotify = window.SoundScopeSpotify;
  if (spotify.isExpired(spotifySession)) { spotify.disconnect(); window.SoundScopeSpotifyInsights?.clearCache(); spotifySession = null; renderSpotify("expired"); output.textContent = "Sua sessão do Spotify expirou."; return; }
  const catalog = window.SoundScopeSpotifyCatalog; if (!catalog) return;
  card.dataset.spotifyState = "loading"; output.textContent = "Consultando Spotify…";
  try {
    const result = await catalog.lookupAlbum({ artistName: currentArtistName, albumTitle: album.title, releaseYear: album.year }, spotifySession.accessToken);
    card.dataset.spotifyState = "done";
    if (!result.matched) { output.textContent = result.confidence === "ambiguous" ? "Correspondência não confirmada no Spotify." : "Álbum não encontrado no Spotify."; return; }
    const link = document.createElement("a"); link.href = result.album.spotifyUrl; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = "▶ Ouvir no Spotify ↗";
    link.addEventListener("click", (event) => event.stopPropagation()); output.replaceChildren(link);
  } catch (error) {
    card.dataset.spotifyState = "error";
    if (error.message === "SESSION_EXPIRED") { spotify.disconnect(); window.SoundScopeSpotifyInsights?.clearCache(); spotifySession = null; renderSpotify("expired"); output.textContent = "Sua sessão do Spotify expirou."; }
    else if (error.message === "RATE_LIMITED") output.textContent = "Spotify ocupado. Tente novamente em instantes.";
    else output.textContent = "Não foi possível consultar o Spotify. Tente novamente.";
  }
}

function renderSourceIds(sourceIds, sources) {
  const entries = sourceIds && typeof sourceIds === "object" ? Object.entries(sourceIds).filter(([, value]) => value) : [];
  elements.sourceIdsWrap.classList.toggle("is-hidden", entries.length === 0);
  const active = sources && typeof sources === "object" ? Object.entries(sources).filter(([, used]) => used).map(([name]) => name) : entries.map(([name]) => name);
  elements.sourceNames.textContent = active.join(" + ") || "Fonte não informada";
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
elements.albumsLoadMore.addEventListener("click", loadMoreAlbums);
elements.readMore.addEventListener("click", () => { const collapsed = elements.biographyWrap.classList.toggle("is-collapsed"); elements.readMore.setAttribute("aria-expanded", String(!collapsed)); elements.readMore.innerHTML = collapsed ? "Ler mais <span>↓</span>" : "Mostrar menos <span>↑</span>"; });
elements.dataTrigger.addEventListener("click", () => toggleDataPanel()); elements.dataClose.addEventListener("click", () => toggleDataPanel(false)); elements.backdrop.addEventListener("click", () => toggleDataPanel(false));
$("#nav-search").addEventListener("click", focusSearch); $("#new-search").addEventListener("click", focusSearch); $("#retry-search").addEventListener("click", focusSearch);
document.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); focusSearch(); } if (event.key === "Escape" && elements.dataPanel.classList.contains("is-open")) toggleDataPanel(false); });
if (window.matchMedia("(pointer:fine)").matches && !window.matchMedia("(prefers-reduced-motion:reduce)").matches) {
  elements.home.addEventListener("pointermove", (event) => { const x = (event.clientX / window.innerWidth - .5) * 18; const y = (event.clientY / window.innerHeight - .5) * 14; elements.orb.style.setProperty("--orb-x", `${x}px`); elements.orb.style.setProperty("--orb-y", `${y}px`); });
}
initializeReveal();

const spotifyElements = { connect: $("#spotify-connect"), disconnect: $("#spotify-disconnect"), status: $("#spotify-status"), insights: $("#meu-soundscope"), insightsNav: $("#insights-nav"), profile: $("#spotify-profile"), profileImage: $("#spotify-profile-image"), profileName: $("#spotify-profile-name"), insightsStatus: $("#insights-status"), artists: $("#top-artists"), tracks: $("#top-tracks") };
let insightsRequest = 0;

function rankingImage(src, alt) {
  if (!src) { const placeholder = document.createElement("span"); placeholder.className = "ranking__placeholder"; placeholder.setAttribute("aria-hidden", "true"); return placeholder; }
  const image = document.createElement("img"); image.src = src; image.alt = alt; image.loading = "lazy"; image.decoding = "async";
  image.onerror = () => image.replaceWith(rankingImage("", "")); return image;
}
function rankingLink(url, label) {
  const link = document.createElement("a"); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.setAttribute("aria-label", `${label} no Spotify`); link.textContent = "Abrir no Spotify ↗"; return link;
}
function renderTopArtists(items) {
  if (!items.length) { const empty = document.createElement("p"); empty.className = "ranking-empty"; empty.textContent = "O Spotify não retornou artistas para este período."; spotifyElements.artists.replaceChildren(empty); return; }
  spotifyElements.artists.replaceChildren(...items.map((artist, index) => {
    const row = document.createElement("article"); row.className = "ranking-row ranking-row--artist";
    const rank = document.createElement("span"); rank.className = "ranking__number"; rank.textContent = String(index + 1).padStart(2, "0");
    const name = document.createElement("h4"); name.textContent = artist.name; row.append(rank, rankingImage(artist.image, `Foto de ${artist.name}`), name);
    if (artist.spotifyUrl) row.append(rankingLink(artist.spotifyUrl, artist.name)); return row;
  }));
}
function renderTopTracks(items) {
  if (!items.length) { const empty = document.createElement("p"); empty.className = "ranking-empty"; empty.textContent = "O Spotify não retornou músicas para este período."; spotifyElements.tracks.replaceChildren(empty); return; }
  spotifyElements.tracks.replaceChildren(...items.map((track, index) => {
    const row = document.createElement("article"); row.className = "ranking-row";
    const rank = document.createElement("span"); rank.className = "ranking__number"; rank.textContent = String(index + 1).padStart(2, "0");
    const copy = document.createElement("div"); const name = document.createElement("h4"); name.textContent = track.name; const detail = document.createElement("p"); detail.textContent = `${track.artists.join(", ") || "Artista não informado"} · ${track.album}`; copy.append(name, detail);
    row.append(rank, rankingImage(track.image, `Capa de ${track.album}`), copy); if (track.spotifyUrl) row.append(rankingLink(track.spotifyUrl, track.name)); return row;
  }));
}
function insightsError(error) {
  if (error.message === "SPOTIFY_SCOPE_REQUIRED") return "Sua autorização precisa ser atualizada. Desconecte e conecte o Spotify novamente.";
  if (error.message === "RATE_LIMITED") return `O Spotify limitou as consultas. Tente novamente${error.retryAfter ? ` em cerca de ${error.retryAfter} segundos` : " mais tarde"}.`;
  if (error.message === "SESSION_EXPIRED") return "Sua sessão expirou. Conecte o Spotify novamente.";
  return "Não foi possível carregar seu universo musical. Verifique a conexão e tente novamente.";
}
async function loadInsights(timeRange = "short_term") {
  const insights = window.SoundScopeSpotifyInsights; if (!insights || !spotifySession) return;
  const request = ++insightsRequest; spotifyElements.insights.setAttribute("aria-busy", "true"); spotifyElements.insightsStatus.textContent = "Atualizando seu universo musical…";
  try {
    const [artists, tracks] = await Promise.all([insights.getTopArtists(timeRange, spotifySession.accessToken), insights.getTopTracks(timeRange, spotifySession.accessToken)]);
    if (request !== insightsRequest) return; renderTopArtists(artists.items); renderTopTracks(tracks.items); spotifyElements.insightsStatus.textContent = "";
  } catch (error) {
    if (request !== insightsRequest) return; spotifyElements.insightsStatus.textContent = insightsError(error);
    if (error.message === "SESSION_EXPIRED") { window.SoundScopeSpotify.disconnect(); window.SoundScopeSpotifyInsights?.clearCache(); spotifySession = null; renderSpotify("expired"); }
  } finally { if (request === insightsRequest) spotifyElements.insights.removeAttribute("aria-busy"); }
}
function renderInsightsProfile(session) {
  spotifyElements.profileName.textContent = session.user.displayName; spotifyElements.profile.classList.remove("is-hidden");
  spotifyElements.profile.toggleAttribute("href", Boolean(session.user.spotifyUrl)); if (session.user.spotifyUrl) spotifyElements.profile.href = session.user.spotifyUrl;
  spotifyElements.profileImage.classList.toggle("is-hidden", !session.user.image); if (session.user.image) { spotifyElements.profileImage.src = session.user.image; spotifyElements.profileImage.alt = `Foto de ${session.user.displayName}`; }
}
document.querySelectorAll(".period-selector button").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".period-selector button").forEach((item) => { const active = item === button; item.classList.toggle("is-active", active); item.setAttribute("aria-pressed", String(active)); }); loadInsights(button.dataset.range);
}));
function renderSpotify(state, session) {
  const connected = state === "connected";
  spotifyElements.connect.classList.toggle("is-hidden", connected); spotifyElements.disconnect.classList.toggle("is-hidden", !connected);
  spotifyElements.connect.disabled = state === "redirecting" || state === "processing";
  spotifyElements.connect.textContent = state === "redirecting" ? "Conectando..." : "Conectar Spotify";
  spotifyElements.status.textContent = connected ? `Spotify conectado · ${session.user.displayName}` : ({ processing: "Finalizando conexão...", expired: "Sua sessão do Spotify expirou. Conecte novamente.", error: "Não foi possível conectar ao Spotify." }[state] || "");
  spotifyElements.insights.classList.toggle("is-hidden", !connected); spotifyElements.insightsNav.classList.toggle("is-hidden", !connected);
  if (connected) { renderInsightsProfile(session); const active = document.querySelector(".period-selector button.is-active"); loadInsights(active?.dataset.range || "short_term"); }
}
async function initializeSpotify() {
  const spotify = window.SoundScopeSpotify; if (!spotify) return;
  let session = spotify.getSession();
  if (session && spotify.isExpired(session)) { spotify.disconnect(); window.SoundScopeSpotifyInsights?.clearCache(); renderSpotify("expired"); session = null; } else if (session) renderSpotify("connected", session);
  spotifySession = session;
  const callback = spotify.parseCallback(window.location.search);
  if (callback.code || callback.error || callback.state) { renderSpotify("processing"); try { session = await spotify.handleCallback(); spotifySession = session; renderSpotify("connected", session); } catch (_) { spotifySession = null; renderSpotify("error"); } }
  spotifyElements.connect.addEventListener("click", async () => { renderSpotify("redirecting"); try { await spotify.begin(); } catch (_) { renderSpotify("error"); } });
  spotifyElements.disconnect.addEventListener("click", () => { spotify.disconnect(); window.SoundScopeSpotifyInsights?.clearCache(); spotifySession = null; renderSpotify("disconnected"); document.querySelectorAll(".album__spotify").forEach((node) => { node.textContent = ""; delete node.parentElement.dataset.spotifyState; }); });
}
initializeSpotify();
