(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SoundScopeSpotifyOrbit = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const MAX_ARTISTS = 10;
  const VALID_RANGES = new Set(["short_term", "medium_term", "long_term"]);
  const POSITIONS = [[50,9],[73,17],[88,38],[82,68],[65,86],[39,88],[17,72],[11,43],[25,18],[50,27]];
  function safeUrl(value) { return typeof value === "string" && /^https:\/\/open\.spotify\.com\/artist\/[A-Za-z0-9]+(?:[/?#].*)?$/.test(value) ? value : ""; }
  function normalizeArtists(items) {
    return (Array.isArray(items) ? items : []).slice(0, MAX_ARTISTS).map((artist, index) => ({
      id: String(artist?.id || `orbit-${index + 1}`), name: String(artist?.name || "Artista não informado"),
      image: typeof artist?.image === "string" && /^https:\/\//.test(artist.image) ? artist.image : "",
      spotifyUrl: safeUrl(artist?.spotifyUrl), rank: index + 1
    }));
  }
  function calculateLayout(count) {
    const total = Math.max(0, Math.min(MAX_ARTISTS, Number.isFinite(count) ? Math.floor(count) : 0));
    return POSITIONS.slice(0, total).map(([x, y], index) => ({ x, y, scale: Number((1.08 - index * .025).toFixed(3)), drift: (index % 5) + 1 }));
  }
  function createState(options = {}) {
    let state = { range: "short_term", artists: [], selected: null, reducedMotion: Boolean(options.reducedMotion) };
    const notify = () => options.onChange?.({ ...state, artists: [...state.artists] });
    const snapshot = () => ({ ...state, artists: [...state.artists] });
    return {
      get: snapshot,
      setArtists(items) { state = { ...state, artists: normalizeArtists(items), selected: null }; notify(); return snapshot(); },
      setRange(range) { if (!VALID_RANGES.has(range)) throw new Error("INVALID_TIME_RANGE"); state = { ...state, range, selected: null }; notify(); return snapshot(); },
      select(id) { const selected = state.artists.find((artist) => artist.id === id) || null; state = { ...state, selected }; notify(); return selected; },
      explore() { if (state.selected) options.onExplore?.(state.selected); }
    };
  }
  function element(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; }
  function mount(container, options = {}) {
    if (!container) return null;
    const stage = container.querySelector("[data-orbit-stage]"); const panel = container.querySelector("[data-orbit-panel]");
    const status = container.querySelector("[data-orbit-status]"); const rangeLabel = container.querySelector("[data-orbit-range]");
    let controller;
    function render(state) {
      container.classList.toggle("is-reduced-motion", state.reducedMotion); rangeLabel.textContent = ({ short_term: "4 semanas", medium_term: "6 meses", long_term: "Longo prazo" })[state.range];
      stage.querySelectorAll(".orbit-node,.orbit-line").forEach((node) => node.remove());
      if (!state.artists.length) { status.textContent = "O Spotify não retornou artistas para este período."; panel.replaceChildren(); return; }
      status.textContent = ""; const layout = calculateLayout(state.artists.length);
      state.artists.forEach((artist, index) => {
        const line = element("i", "orbit-line"); const dx = layout[index].x - 50; const dy = layout[index].y - 50;
        line.style.setProperty("--length", `${Math.hypot(dx, dy)}%`); line.style.setProperty("--angle", `${Math.atan2(dy, dx) * 180 / Math.PI}deg`); stage.append(line);
        const button = element("button", "orbit-node"); button.type = "button"; button.dataset.artistId = artist.id; button.setAttribute("aria-label", `Selecionar ${artist.name}, posição ${artist.rank}`);
        button.setAttribute("aria-pressed", String(state.selected?.id === artist.id));
        button.style.setProperty("--x", `${layout[index].x}%`); button.style.setProperty("--y", `${layout[index].y}%`); button.style.setProperty("--scale", layout[index].scale); button.style.setProperty("--drift-duration", `${14 + layout[index].drift}s`);
        const visual = element("span", "orbit-node__visual");
        if (artist.image) { const image = element("img"); image.src = artist.image; image.alt = ""; image.loading = "lazy"; image.onerror = () => image.replaceWith(element("span", "orbit-node__fallback", artist.name.slice(0, 1))); visual.append(image); }
        else visual.append(element("span", "orbit-node__fallback", artist.name.slice(0, 1)));
        button.append(visual, element("span", "orbit-node__rank", `#${String(artist.rank).padStart(2, "0")}`), element("strong", "orbit-node__name", artist.name));
        button.addEventListener("click", () => controller.select(artist.id)); stage.append(button);
      });
      container.classList.toggle("has-selection", Boolean(state.selected));
      if (!state.selected) { panel.replaceChildren(element("p", "orbit-panel__hint", "Selecione um artista para aproximá-lo.")); return; }
      const artist = state.selected; const rank = element("p", "orbit-panel__rank", `#${String(artist.rank).padStart(2, "0")}`); const name = element("h4", "", artist.name);
      const copy = element("p", "", "Entre os artistas mais presentes na sua órbita neste período.");
      const actions = element("div", "orbit-panel__actions"); const explore = element("button", "", "Explorar no SoundScope →"); explore.type = "button"; explore.addEventListener("click", () => controller.explore()); actions.append(explore);
      if (artist.spotifyUrl) { const link = element("a", "", "Abrir no Spotify ↗"); link.href = artist.spotifyUrl; link.target = "_blank"; link.rel = "noopener noreferrer"; actions.append(link); }
      panel.replaceChildren(rank, name, copy, actions);
    }
    controller = createState({ reducedMotion: options.reducedMotion, onExplore: options.onExplore, onChange: render }); render(controller.get());
    return controller;
  }
  return { MAX_ARTISTS, VALID_RANGES, normalizeArtists, calculateLayout, createState, safeUrl, mount };
});
