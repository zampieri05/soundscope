"use strict";
(function expose(root) {
  const PAGE_SIZE = 20;
  const CATEGORIES = Object.freeze(["Álbuns", "Ao Vivo", "Singles & EPs", "Demos", "Coletâneas", "Outros"]);
  function category(album) {
    const secondary = Array.isArray(album?.secondary_types) ? album.secondary_types : [];
    if (secondary.includes("Demo")) return "Demos";
    if (secondary.includes("Live")) return "Ao Vivo";
    if (secondary.includes("Compilation")) return "Coletâneas";
    if (album?.primary_type === "Single" || album?.primary_type === "EP") return "Singles & EPs";
    if (album?.primary_type === "Album") return "Álbuns";
    return "Outros";
  }
  function group(items) {
    const groups = Object.fromEntries(CATEGORIES.map((name) => [name, []]));
    for (const item of Array.isArray(items) ? items : []) groups[category(item)].push(item);
    return groups;
  }
  function defaultCategory(groups) {
    if (groups?.["Álbuns"]?.length) return "Álbuns";
    return CATEGORIES.find((name) => groups?.[name]?.length) || null;
  }
  function page(items, visibleCount, size = PAGE_SIZE) {
    return Array.isArray(items) ? items.slice(visibleCount, visibleCount + size) : [];
  }
  const api = Object.freeze({ PAGE_SIZE, CATEGORIES, category, group, defaultCategory, page });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.SoundScopeDiscography = api;
})(typeof window !== "undefined" ? window : globalThis);
