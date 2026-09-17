(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SoundScopeStoryMode = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";

  const DATE_PATTERN = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/;
  const MONTHS = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"];
  const text = (value) => typeof value === "string" && value.trim() ? value.trim() : "";
  function dateParts(value) {
    const match = text(value).match(DATE_PATTERN);
    if (!match) return null;
    const year = Number(match[1]); const month = match[2] ? Number(match[2]) : null; const day = match[3] ? Number(match[3]) : null;
    if (year < 1000 || year > 9999 || (month !== null && (month < 1 || month > 12)) || (day !== null && (day < 1 || day > 31))) return null;
    return { raw: match[0], year, month, day, precision: day ? "day" : month ? "month" : "year" };
  }
  function releaseDate(album) { return dateParts(album?.first_release_date) || dateParts(String(album?.year || "")); }
  function formatDate(value) {
    const date = dateParts(value); if (!date) return "";
    if (date.precision === "year") return String(date.year);
    if (date.precision === "month") return `${MONTHS[date.month - 1]} ${date.year}`;
    return `${String(date.day).padStart(2, "0")} ${MONTHS[date.month - 1]} ${date.year}`;
  }
  function albumId(album, index) { return text(album?.musicbrainz_release_group_id) || text(album?.album_id) || `record-${index + 1}`; }
  function normalizeArtist(input) {
    const source = input && typeof input === "object" ? input : {};
    const formed = dateParts(String(source.formed_year || ""));
    return {
      name: text(source.name), country: text(source.country), biography: text(source.biography), imageUrl: text(source.image_url),
      formedYear: formed?.precision === "year" ? String(formed.year) : "",
      members: (Array.isArray(source.members) ? source.members : []).map((member) => ({ name: text(member?.name), role: text(member?.role), active: typeof member?.active === "boolean" ? member.active : null })).filter((member) => member.name),
      albums: (Array.isArray(source.albums) ? source.albums : []).map((album, index) => ({
        id: albumId(album, index), albumId: text(album?.album_id), musicbrainzReleaseGroupId: text(album?.musicbrainz_release_group_id), title: text(album?.title),
        year: text(String(album?.year || "")), firstReleaseDate: text(album?.first_release_date), primaryType: text(album?.primary_type),
        secondaryTypes: Array.isArray(album?.secondary_types) ? album.secondary_types.filter((item) => typeof item === "string" && item.trim()).map((item) => item.trim()) : [], coverUrl: text(album?.cover_url), spotifyUrl: text(album?.spotify_url)
      })).filter((album) => album.title)
    };
  }
  function filterAlbums(albums, mode = "albums") {
    const dated = (Array.isArray(albums) ? albums : []).filter((album) => releaseDate({ first_release_date: album.firstReleaseDate, year: album.year }));
    return mode === "all" ? dated : dated.filter((album) => album.primaryType === "Album");
  }
  function buildTimeline(input, mode = "albums") {
    const artist = input?.albums && Object.prototype.hasOwnProperty.call(input, "formedYear") ? input : normalizeArtist(input);
    const events = [];
    if (artist.formedYear) events.push({ id: "formation", kind: "formation", date: artist.formedYear, year: artist.formedYear, title: artist.name, country: artist.country, sort: `${artist.formedYear}-00-00`, order: -1 });
    filterAlbums(artist.albums, mode).forEach((album, index) => {
      const date = releaseDate({ first_release_date: album.firstReleaseDate, year: album.year });
      events.push({ id: `release-${album.id}`, kind: "release", date: date.raw, year: String(date.year), title: album.title, album, sort: `${date.year}-${String(date.month || 0).padStart(2, "0")}-${String(date.day || 0).padStart(2, "0")}`, order: index });
    });
    return events.sort((a, b) => a.sort.localeCompare(b.sort) || a.order - b.order);
  }
  function createState(options = {}) {
    let state = { open: false, active: 0, mode: "albums", reducedMotion: Boolean(options.reducedMotion) };
    const get = () => ({ ...state }); const update = (patch) => { state = { ...state, ...patch }; options.onChange?.(get()); return get(); };
    return { get, open: () => update({ open: true, active: 0 }), close: () => update({ open: false }), activate: (active) => update({ active }), setMode: (mode) => update({ mode: mode === "all" ? "all" : "albums", active: 0 }) };
  }
  function node(tag, className, value) { const item = document.createElement(tag); if (className) item.className = className; if (value !== undefined) item.textContent = value; return item; }
  function renderRelease(event, index, onSpotify) {
    const section = node("article", `story-event story-event--release story-event--${index % 3}`); section.dataset.storyEvent = ""; section.dataset.year = event.year; section.id = `story-${event.id}`;
    section.append(node("span", "story-event__year", event.year));
    const copy = node("div", "story-event__copy"); copy.append(node("p", "story-label", event.album.primaryType || "REGISTRO"), node("h3", "", event.title));
    const date = node("p", "story-event__date", `Primeiro lançamento\n${formatDate(event.date)}`); copy.append(date);
    const visual = node("div", "story-event__cover"); const fallback = node("div", "story-cover-fallback"); fallback.append(node("small", "", "SoundScope / Arquivo"), node("strong", "", event.title)); visual.append(fallback);
    if (event.album.coverUrl) { const image = node("img"); image.src = event.album.coverUrl; image.alt = `Capa de ${event.title}`; image.loading = "lazy"; image.onerror = () => image.remove(); image.onload = () => fallback.remove(); visual.append(image); }
    if (event.album.spotifyUrl) { const link = node("a", "story-spotify", "Abrir álbum no Spotify ↗"); link.href = event.album.spotifyUrl; link.target = "_blank"; link.rel = "noopener noreferrer"; copy.append(link); }
    else if (onSpotify) { const button = node("button", "story-spotify", "Consultar no Spotify →"); const output = node("p", "story-spotify-status"); output.setAttribute("aria-live", "polite"); button.type = "button"; button.addEventListener("click", () => onSpotify(event.album, button, output)); copy.append(button, output); }
    section.append(copy, visual); return section;
  }
  function mount(container, options = {}) {
    if (!container) return null;
    const content = container.querySelector("[data-story-content]"); const closeButton = container.querySelector("[data-story-close]"); const progress = container.querySelector("[data-story-progress]");
    const state = createState({ reducedMotion: options.reducedMotion }); let artist = normalizeArtist({}); let opener = null; let observer = null;
    function setActive(index, event) { state.activate(index); const total = content.querySelectorAll("[data-story-event]").length; progress.textContent = `${String(index + 1).padStart(2, "0")} / ${String(total).padStart(2, "0")} · ${event?.year || "ARQUIVO"}`; }
    function observe() {
      observer?.disconnect(); const events = [...content.querySelectorAll("[data-story-event]")];
      if (!root.IntersectionObserver || state.get().reducedMotion) { events.forEach((item) => item.classList.add("is-active")); return; }
      observer = new root.IntersectionObserver((entries) => entries.forEach((entry) => { if (entry.isIntersecting) { events.forEach((item) => item.classList.toggle("is-active", item === entry.target)); setActive(events.indexOf(entry.target), entry.target.dataset); } }), { root: container, threshold: .55 });
      events.forEach((item) => observer.observe(item));
    }
    function render() {
      const events = buildTimeline(artist, state.get().mode); const intro = node("section", "story-intro"); intro.dataset.storyEvent = ""; intro.dataset.year = artist.formedYear || "";
      const title = node("h2", "", artist.name || "ARTISTA"); title.id = "story-mode-title";
      intro.append(node("p", "story-label", "STORY MODE / ARQUIVO 001"), title);
      if (artist.formedYear) intro.append(node("p", "story-intro__period", `${artist.formedYear} → PRESENTE`));
      intro.append(node("p", "story-intro__line", "Uma trajetória em registros.")); const begin = node("a", "story-begin", "Começar ↓"); begin.href = events.length ? `#story-${events[0].id}` : "#story-context"; intro.append(begin);
      const controls = node("div", "story-filters"); controls.setAttribute("role", "group"); controls.setAttribute("aria-label", "Filtrar registros"); controls.append(node("span", "", "VER:"));
      [["albums", "Álbuns"], ["all", "Todos os registros"]].forEach(([mode, label]) => { const button = node("button", "", label); button.type = "button"; button.setAttribute("aria-pressed", String(state.get().mode === mode)); button.addEventListener("click", () => { state.setMode(mode); render(); }); controls.append(button); });
      const timeline = node("div", "story-timeline"); timeline.append(...events.map((event, index) => event.kind === "release" ? renderRelease(event, index, options.onSpotify) : (() => { const section = node("article", "story-event story-event--formation"); section.dataset.storyEvent = ""; section.dataset.year = event.year; section.id = `story-${event.id}`; section.append(node("span", "story-event__year", event.year)); const copy = node("div", "story-event__copy"); copy.append(node("p", "story-label", "FORMAÇÃO"), node("h3", "", event.title)); if (event.country) copy.append(node("p", "story-event__date", event.country)); section.append(copy); return section; })()));
      const context = node("section", "story-context"); context.id = "story-context";
      if (artist.members.length) { const members = node("div", "story-context__block"); members.append(node("p", "story-label", "INTEGRANTES REGISTRADOS")); artist.members.forEach((member) => { const row = node("div", "story-member"); row.append(node("strong", "", member.name), node("span", "", member.role || "Função não informada")); members.append(row); }); context.append(members); }
      if (artist.biography) { const bio = node("div", "story-context__block"); bio.append(node("p", "story-label", "ARQUIVO / BIOGRAFIA"), node("p", "story-biography", artist.biography)); context.append(bio); }
      content.replaceChildren(intro, controls, timeline, context); observe(); setActive(0, intro.dataset);
    }
    function open(trigger) { opener = trigger || root.document?.activeElement; render(); container.classList.remove("is-hidden"); container.setAttribute("aria-hidden", "false"); trigger?.setAttribute("aria-expanded", "true"); document.body.classList.add("story-mode-open"); state.open(); container.scrollTop = 0; closeButton.focus(); }
    function close() { container.classList.add("is-hidden"); container.setAttribute("aria-hidden", "true"); document.body.classList.remove("story-mode-open"); opener?.setAttribute?.("aria-expanded", "false"); state.close(); opener?.focus?.(); }
    function keydown(event) { if (event.key === "Escape" && state.get().open) { event.preventDefault(); close(); } }
    closeButton.addEventListener("click", close); root.document?.addEventListener("keydown", keydown);
    return { setArtist(value) { artist = normalizeArtist(value); }, open, close, render, getState: state.get, destroy() { observer?.disconnect(); root.document?.removeEventListener("keydown", keydown); } };
  }
  return { dateParts, formatDate, normalizeArtist, filterAlbums, buildTimeline, createState, mount };
});
