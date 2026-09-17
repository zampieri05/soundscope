"use strict";
(function expose(root) {
  const PAGE_SIZE = 20;
  function category(album) {
    const secondary = Array.isArray(album?.secondary_types) ? album.secondary_types : [];
    if (secondary.includes("Live")) return "Ao vivo";
    if (secondary.includes("Compilation")) return "Compilação";
    return ({ Album: "Álbum", EP: "EP", Single: "Single", Broadcast: "Broadcast" })[album?.primary_type] || "Outro";
  }
  function page(items, visibleCount, size = PAGE_SIZE) {
    return Array.isArray(items) ? items.slice(visibleCount, visibleCount + size) : [];
  }
  const api = Object.freeze({ PAGE_SIZE, category, page });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.SoundScopeDiscography = api;
})(typeof window !== "undefined" ? window : globalThis);
