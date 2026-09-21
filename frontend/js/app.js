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
  membersNav: $("#members-nav"), albums: $("#artist-albums"), albumsSection: $("#discografia"), albumsNav: $("#albums-nav"), range: $("#timeline-range"), albumFilters: $("#discography-filters"),
  dataTrigger: $("#data-trigger"), dataPanel: $("#data-panel"), dataClose: $("#data-close"), backdrop: $("#panel-backdrop"), sourceIds: $("#source-ids"), sourceIdsWrap: $("#source-ids-wrap"), sourceNames: $("#source-names"), albumsLoadMore: $("#albums-load-more"), storyOpen: $("#story-mode-open"), storyMode: $("#story-mode")
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
  storyController?.setArtist(artist);
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
let albumGroups = {};
let activeAlbumCategory = null;

function albumCategory(album) {
  return window.SoundScopeDiscography.category(album);
}

function createAlbumCard(album) {
  const card = document.createElement("article"); card.className = "album";
  const visual = document.createElement("div"); visual.className = "album__visual";
  const fallback = albumPlaceholder(album.title); visual.append(fallback);
  const coverUrl = album.cover_url || (album.musicbrainz_release_group_id
    ? `${API_BASE_URL}/cover/${encodeURIComponent(album.musicbrainz_release_group_id)}`
    : "");
  if (coverUrl) {
    const image = document.createElement("img"); image.src = coverUrl; image.alt = `Capa de ${album.title || "lançamento sem título"}`; image.loading = "lazy"; image.decoding = "async";
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
  const sorted = albums.map((album, index) => ({ album, index })).sort((a, b) => {
    const first = Number.parseInt(a.album.year, 10); const second = Number.parseInt(b.album.year, 10);
    return (Number.isNaN(first) ? 1 : Number.isNaN(second) ? -1 : first - second) || a.index - b.index;
  }).map(({ album }) => album);
  albumGroups = window.SoundScopeDiscography.group(sorted);
  activeAlbumCategory = window.SoundScopeDiscography.defaultCategory(albumGroups);
  const visible = sorted.length > 0;
  elements.albumsSection.classList.toggle("is-hidden", !visible); elements.albumsNav.classList.toggle("is-hidden", !visible);
  elements.albumFilters.replaceChildren(...window.SoundScopeDiscography.CATEGORIES.filter((name) => albumGroups[name].length).map((name) => {
    const button = document.createElement("button"); button.type = "button"; button.className = "discography-filter"; button.setAttribute("role", "tab"); button.dataset.category = name;
    button.append(document.createTextNode(`${name} `)); const count = document.createElement("span"); count.textContent = albumGroups[name].length; button.append(count);
    button.addEventListener("click", () => selectAlbumCategory(name)); return button;
  }));
  if (visible) selectAlbumCategory(activeAlbumCategory); else { elements.albums.replaceChildren(); elements.albumsLoadMore.classList.add("is-hidden"); }
}
function selectAlbumCategory(name) {
  activeAlbumCategory = name; pendingAlbums = albumGroups[name] || []; visibleAlbumCount = 0;
  elements.albums.classList.remove("is-switching"); void elements.albums.offsetWidth; elements.albums.classList.add("is-switching"); elements.albums.replaceChildren();
  [...elements.albumFilters.children].forEach((button) => { const selected = button.dataset.category === name; button.classList.toggle("is-active", selected); button.setAttribute("aria-selected", String(selected)); });
  const years = pendingAlbums.map((album) => Number.parseInt(album.year, 10)).filter(Number.isFinite);
  elements.range.textContent = years.length ? `${name} · ${Math.min(...years)} → ${Math.max(...years)}` : name;
  loadMoreAlbums();
}
async function lookupSpotifyAlbum(album, card, output) {
  if (card.dataset.spotifyState === "loading" || card.dataset.spotifyState === "done") return;
  if (!spotifySession) { output.textContent = "Conecte o Spotify para ouvir este álbum."; card.dataset.spotifyState = "disconnected"; return; }
  const spotify = window.SoundScopeSpotify;
  if (spotify.isExpired(spotifySession)) { spotify.disconnect(); window.SoundScopeSpotifyInsights?.clearCache(); window.SoundScopeSpotifyHistory?.clearCache(); spotifySession = null; renderSpotify("expired"); output.textContent = "Sua sessão do Spotify expirou."; return; }
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
    if (error.message === "SESSION_EXPIRED") { spotify.disconnect(); window.SoundScopeSpotifyInsights?.clearCache(); window.SoundScopeSpotifyHistory?.clearCache(); spotifySession = null; renderSpotify("expired"); output.textContent = "Sua sessão do Spotify expirou."; }
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
  if (!document.body.classList.contains("artist-route")) { window.location.href = `artist.html?artist=${encodeURIComponent(artistName)}`; return; }
  if (requestInProgress) return;
  requestInProgress = true; elements.message.textContent = ""; setState("loading");
  elements.loading.scrollIntoView({ behavior: "smooth", block: "start" });
  const controller = new AbortController(); const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}/artist/${encodeURIComponent(artistName)}`, { headers: { Accept: "application/json" }, signal: controller.signal });
    if (response.status === 404) throw new Error("NOT_FOUND");
    if (!response.ok) throw new Error(`HTTP_${response.status}`);
    renderArtist(await response.json()); setState("success");
    document.body.classList.add("artist-page-open");
    history.replaceState({ soundScopeArtist: artistName }, "", `artist.html?artist=${encodeURIComponent(artistName)}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
    window.setTimeout(() => elements.result.focus({ preventScroll: true }), 500);
  } catch (error) {
    setState("error", friendlyError(error)); elements.error.scrollIntoView({ behavior: "smooth", block: "center" });
  } finally {
    window.clearTimeout(timeoutId); requestInProgress = false; elements.button.disabled = false; elements.input.setAttribute("aria-busy", "false"); elements.home.classList.remove("is-searching");
  }
}

function focusSearch() { window.location.href = "index.html"; }
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
const initialArtist = new URLSearchParams(location.search).get("artist");
if (document.body.classList.contains("artist-route")) { if (initialArtist) { elements.input.value = initialArtist; window.setTimeout(() => searchArtist(initialArtist), 0); } else { window.location.replace("index.html"); } }

/* SoundScope Motion Director v4 */
(function initializeMotionDirector() {
  const reduced = window.matchMedia("(prefers-reduced-motion:reduce)").matches;
  if (reduced) return;
  document.documentElement.classList.add("motion-v4");

  const finePointer = window.matchMedia("(pointer:fine)").matches;
  if (finePointer) {
    document.addEventListener("pointermove", (event) => {
      document.documentElement.style.setProperty("--cursor-x", `${event.clientX}px`);
      document.documentElement.style.setProperty("--cursor-y", `${event.clientY}px`);
    }, { passive: true });

    document.addEventListener("pointermove", (event) => {
      const card = event.target.closest(".album");
      if (!card) return;
      const rect = card.getBoundingClientRect();
      const rx = ((event.clientY - rect.top) / rect.height - .5) * -8;
      const ry = ((event.clientX - rect.left) / rect.width - .5) * 10;
      card.style.setProperty("--tilt-x", `${rx.toFixed(2)}deg`);
      card.style.setProperty("--tilt-y", `${ry.toFixed(2)}deg`);
      card.style.setProperty("--glow-x", `${((event.clientX - rect.left) / rect.width * 100).toFixed(1)}%`);
      card.style.setProperty("--glow-y", `${((event.clientY - rect.top) / rect.height * 100).toFixed(1)}%`);
    }, { passive: true });
    document.addEventListener("pointerout", (event) => {
      const card = event.target.closest(".album");
      if (card && !card.contains(event.relatedTarget)) {
        card.style.removeProperty("--tilt-x"); card.style.removeProperty("--tilt-y");
      }
    });
  }

  const progress = document.createElement("div");
  progress.className = "motion-progress"; progress.setAttribute("aria-hidden", "true");
  document.body.append(progress);
  let ticking = false;
  const updateScroll = () => {
    const max = Math.max(1, document.documentElement.scrollHeight - innerHeight);
    progress.style.transform = `scaleX(${Math.min(1, scrollY / max)})`;
    document.documentElement.style.setProperty("--scroll-y", `${scrollY}px`);
    ticking = false;
  };
  addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(updateScroll); } }, { passive: true });
  updateScroll();

  document.addEventListener("click", (event) => {
    const target = event.target.closest("button,.album,.brand");
    if (!target) return;
    const ripple = document.createElement("span");
    ripple.className = "motion-ripple"; ripple.style.left = `${event.clientX}px`; ripple.style.top = `${event.clientY}px`;
    document.body.append(ripple); ripple.addEventListener("animationend", () => ripple.remove(), { once: true });
  });
})();

const storyController = window.SoundScopeStoryMode?.mount(elements.storyMode, {
  reducedMotion: window.matchMedia("(prefers-reduced-motion:reduce)").matches,
  onSpotify: (album, button, output) => lookupSpotifyAlbum({ title: album.title, year: album.year }, button, output)
});
elements.storyOpen.addEventListener("click", () => storyController?.open(elements.storyOpen));

const spotifyElements = { connect: $("#spotify-connect"), disconnect: $("#spotify-disconnect"), status: $("#spotify-status"), insights: $("#meu-soundscope"), insightsNav: $("#insights-nav"), profile: $("#spotify-profile"), profileImage: $("#spotify-profile-image"), profileName: $("#spotify-profile-name"), insightsStatus: $("#insights-status"), artists: $("#top-artists"), tracks: $("#top-tracks"), history: $("#spotify-history"), historyStatus: $("#history-status"), historyRefresh: $("#history-refresh"), orbit: $("#minha-orbita"), orbitEnter: $("#orbit-enter"), orbitClose: $("#orbit-close"), orbitShare: $("#orbit-share"), orbitShareOpen: $("#orbit-share-open") };
let insightsRequest = 0;
let historyRequest = 0;
const orbitController = window.SoundScopeSpotifyOrbit?.mount(spotifyElements.orbit, {
  reducedMotion: window.matchMedia("(prefers-reduced-motion:reduce)").matches,
  onExplore: (artist) => { elements.input.value = artist.name; searchArtist(artist.name); }
});
const orbitShareController = window.SoundScopeOrbitShare?.mount(spotifyElements.orbitShare, {
  navigator: window.navigator,
  logoUrl: "assets/soundscope-logo.png",
  iconUrl: "assets/soundscope-icon-512.png"
});

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
function renderHistory(items) {
  if (!items.length) { const empty = document.createElement("p"); empty.className = "ranking-empty"; empty.textContent = "Nenhuma reprodução recente foi retornada pelo Spotify."; spotifyElements.history.replaceChildren(empty); return; }
  const history = window.SoundScopeSpotifyHistory;
  spotifyElements.history.replaceChildren(...history.groupByLocalDate(items).map((group) => {
    const section = document.createElement("section"); section.className = "history-day";
    const heading = document.createElement("h4"); heading.textContent = group.label; section.append(heading);
    group.items.forEach((item) => {
      const row = document.createElement("article"); row.className = "history-row";
      const time = document.createElement("time"); time.dateTime = item.playedAt; time.textContent = item.time;
      const visual = rankingImage(item.image, item.image ? `Capa de ${item.album}` : "");
      const copy = document.createElement("div"); const name = document.createElement("h5"); name.textContent = item.name;
      const detail = document.createElement("p"); detail.textContent = `${item.artists.join(", ") || "Artista não informado"} · ${item.album}`; copy.append(name, detail);
      row.append(time, visual, copy); if (item.spotifyUrl) row.append(rankingLink(item.spotifyUrl, item.name)); section.append(row);
    }); return section;
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
    if (request !== insightsRequest) return; renderTopArtists(artists.items); renderTopTracks(tracks.items); orbitController?.setRange(timeRange); orbitController?.setArtists(artists.items); spotifyElements.insightsStatus.textContent = "";
  } catch (error) {
    if (request !== insightsRequest) return; spotifyElements.insightsStatus.textContent = insightsError(error);
    if (error.message === "SESSION_EXPIRED") { window.SoundScopeSpotify.disconnect(); window.SoundScopeSpotifyInsights?.clearCache(); window.SoundScopeSpotifyHistory?.clearCache(); spotifySession = null; renderSpotify("expired"); }
  } finally { if (request === insightsRequest) spotifyElements.insights.removeAttribute("aria-busy"); }
}
function historyError(error) {
  if (error.message === "SPOTIFY_DISCONNECTED") return "Conecte o Spotify para consultar suas últimas escutas.";
  if (error.message === "SESSION_EXPIRED") return "Sua sessão expirou. Conecte o Spotify novamente.";
  if (error.message === "SPOTIFY_SCOPE_REQUIRED") return "Esta sessão não possui a permissão de histórico. Desconecte e conecte o Spotify novamente.";
  if (error.message === "RATE_LIMITED") return `O Spotify limitou a consulta. Tente novamente${error.retryAfter ? ` em cerca de ${error.retryAfter} segundos` : " mais tarde"}.`;
  if (error.message === "SPOTIFY_TIMEOUT") return "O Spotify demorou mais que o esperado. Tente atualizar novamente.";
  return "Não foi possível carregar as últimas escutas. Verifique sua conexão e tente novamente.";
}
async function loadHistory(forceRefresh = false) {
  const history = window.SoundScopeSpotifyHistory;
  if (!history || !spotifySession) { spotifyElements.historyStatus.textContent = historyError(new Error("SPOTIFY_DISCONNECTED")); return; }
  const request = ++historyRequest; spotifyElements.historyRefresh.disabled = true; spotifyElements.history.setAttribute("aria-busy", "true"); spotifyElements.historyStatus.textContent = "Carregando últimas escutas…";
  try {
    const result = await history.getRecentlyPlayed(spotifySession.accessToken, { forceRefresh });
    if (request !== historyRequest) return; renderHistory(result.items); spotifyElements.historyStatus.textContent = "";
  } catch (error) {
    if (request !== historyRequest) return; spotifyElements.historyStatus.textContent = historyError(error);
    if (error.message === "SESSION_EXPIRED") { window.SoundScopeSpotify.disconnect(); window.SoundScopeSpotifyInsights?.clearCache(); history.clearCache(); spotifySession = null; renderSpotify("expired"); }
  } finally { if (request === historyRequest) { spotifyElements.history.removeAttribute("aria-busy"); spotifyElements.historyRefresh.disabled = false; } }
}
function renderInsightsProfile(session) {
  spotifyElements.profileName.textContent = session.user.displayName; spotifyElements.profile.classList.remove("is-hidden");
  spotifyElements.profile.toggleAttribute("href", Boolean(session.user.spotifyUrl)); if (session.user.spotifyUrl) spotifyElements.profile.href = session.user.spotifyUrl;
  spotifyElements.profileImage.classList.toggle("is-hidden", !session.user.image); if (session.user.image) { spotifyElements.profileImage.src = session.user.image; spotifyElements.profileImage.alt = `Foto de ${session.user.displayName}`; }
}
document.querySelectorAll(".period-selector button").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".period-selector button").forEach((item) => { const active = item === button; item.classList.toggle("is-active", active); item.setAttribute("aria-pressed", String(active)); }); loadInsights(button.dataset.range);
}));
spotifyElements.orbitEnter.addEventListener("click", () => { spotifyElements.orbit.classList.remove("is-hidden"); spotifyElements.orbitEnter.setAttribute("aria-expanded", "true"); spotifyElements.orbit.scrollIntoView({ behavior: "smooth", block: "start" }); });
spotifyElements.orbitClose.addEventListener("click", () => { spotifyElements.orbit.classList.add("is-hidden"); spotifyElements.orbitEnter.setAttribute("aria-expanded", "false"); spotifyElements.orbitEnter.focus(); });
spotifyElements.orbitShareOpen.addEventListener("click", () => orbitShareController?.open(orbitController?.get().artists || [], spotifyElements.orbitShareOpen));
spotifyElements.historyRefresh.addEventListener("click", () => loadHistory(true));
function renderSpotify(state, session) {
  const connected = state === "connected";
  spotifyElements.connect.classList.toggle("is-hidden", connected); spotifyElements.disconnect.classList.toggle("is-hidden", !connected);
  spotifyElements.connect.disabled = state === "redirecting" || state === "processing";
  const connectLabel = state === "redirecting" ? "Conectando..." : "Conectar com Spotify";
  spotifyElements.connect.querySelector("span").textContent = connectLabel;
  spotifyElements.status.textContent = connected ? `Spotify conectado · ${session.user.displayName}` : ({ processing: "Finalizando conexão...", expired: "Sua sessão do Spotify expirou. Conecte novamente.", error: "Não foi possível conectar ao Spotify." }[state] || "");
  spotifyElements.insights.classList.toggle("is-hidden", !connected); spotifyElements.insightsNav.classList.toggle("is-hidden", !connected);
  if (connected) { renderInsightsProfile(session); const active = document.querySelector(".period-selector button.is-active"); loadInsights(active?.dataset.range || "short_term"); loadHistory(); }
}
async function initializeSpotify() {
  const spotify = window.SoundScopeSpotify; if (!spotify) return;
  let session = spotify.getSession();
  spotifySession = session;
  if (session && spotify.isExpired(session)) { spotify.disconnect(); window.SoundScopeSpotifyInsights?.clearCache(); window.SoundScopeSpotifyHistory?.clearCache(); spotifySession = null; renderSpotify("expired"); session = null; } else if (session) renderSpotify("connected", session);
  const callback = spotify.parseCallback(window.location.search);
  if (callback.code || callback.error || callback.state) { renderSpotify("processing"); try { session = await spotify.handleCallback(); spotifySession = session; renderSpotify("connected", session); } catch (_) { spotifySession = null; renderSpotify("error"); } }
  spotifyElements.connect.addEventListener("click", async () => { renderSpotify("redirecting"); try { await spotify.begin(); } catch (_) { renderSpotify("error"); } });
  spotifyElements.disconnect.addEventListener("click", () => { spotify.disconnect(); window.SoundScopeSpotifyInsights?.clearCache(); window.SoundScopeSpotifyHistory?.clearCache(); spotifySession = null; renderSpotify("disconnected"); document.querySelectorAll(".album__spotify").forEach((node) => { node.textContent = ""; delete node.parentElement.dataset.spotifyState; }); });
}
initializeSpotify();
