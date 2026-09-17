(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SoundScopeSpotifyHistory = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const API_URL = "https://api.spotify.com/v1/me/player/recently-played";
  const CACHE_KEY = "soundscope_spotify_history_v1";
  const CACHE_TTL_MS = 45000;
  const REQUEST_TIMEOUT_MS = 8000;
  let pending = null;

  function safeUrl(value) { return typeof value === "string" && /^https:\/\//.test(value) ? value : ""; }
  function normalizeItem(item) {
    const playedAt = String(item?.played_at || "");
    if (!playedAt || Number.isNaN(Date.parse(playedAt)) || !item?.track) return null;
    const track = item.track;
    return {
      playedAt,
      name: String(track.name || "Música não informada"),
      artists: Array.isArray(track.artists) ? track.artists.map((artist) => String(artist?.name || "")).filter(Boolean) : [],
      album: String(track.album?.name || "Álbum não informado"),
      image: Array.isArray(track.album?.images) ? safeUrl(track.album.images.find((image) => image?.url)?.url) : "",
      spotifyUrl: safeUrl(track.external_urls?.spotify)
    };
  }
  function normalizeResponse(data) {
    return (Array.isArray(data?.items) ? data.items : []).map(normalizeItem).filter(Boolean)
      .sort((first, second) => Date.parse(second.playedAt) - Date.parse(first.playedAt));
  }
  function readCache(storage, now = Date.now()) {
    try {
      const cached = JSON.parse(storage?.getItem(CACHE_KEY));
      if (!cached || !Array.isArray(cached.items) || !Number.isFinite(cached.savedAt) || now - cached.savedAt >= CACHE_TTL_MS) return null;
      return cached.items;
    } catch (_) { return null; }
  }
  function writeCache(storage, items, now = Date.now()) {
    try { storage?.setItem(CACHE_KEY, JSON.stringify({ savedAt: now, items })); } catch (_) { /* Personal history remains usable without storage. */ }
  }
  function clearCache(storage = typeof sessionStorage === "undefined" ? null : sessionStorage) {
    try { storage?.removeItem(CACHE_KEY); } catch (_) { /* The cache is disposable. */ }
  }
  function spotifyError(code, retryAfter) { const error = new Error(code); if (retryAfter) error.retryAfter = retryAfter; return error; }

  async function requestHistory(accessToken, options, storage) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), options.timeoutMs || REQUEST_TIMEOUT_MS);
    const url = new URL(API_URL); url.search = new URLSearchParams({ limit: String(options.limit || 20) });
    try {
      const response = await (options.fetchApi || fetch)(url.toString(), { headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" }, signal: controller.signal });
      if (response.status === 401) throw new Error("SESSION_EXPIRED");
      if (response.status === 403) throw new Error("SPOTIFY_SCOPE_REQUIRED");
      if (response.status === 429) throw spotifyError("RATE_LIMITED", response.headers?.get?.("Retry-After"));
      if (!response.ok) throw new Error("SPOTIFY_NETWORK_ERROR");
      let data; try { data = await response.json(); } catch (_) { throw new Error("SPOTIFY_NETWORK_ERROR"); }
      const items = normalizeResponse(data); writeCache(storage, items, options.now?.() ?? Date.now());
      return { items, cached: false };
    } catch (error) {
      if (error.name === "AbortError") throw new Error("SPOTIFY_TIMEOUT");
      if (["SESSION_EXPIRED", "SPOTIFY_SCOPE_REQUIRED", "RATE_LIMITED", "SPOTIFY_NETWORK_ERROR"].includes(error.message)) throw error;
      throw new Error("SPOTIFY_NETWORK_ERROR");
    } finally { clearTimeout(timeoutId); }
  }
  function getRecentlyPlayed(accessToken, options = {}) {
    if (!accessToken) return Promise.reject(new Error("SPOTIFY_DISCONNECTED"));
    const storage = options.storage === undefined ? (typeof sessionStorage === "undefined" ? null : sessionStorage) : options.storage;
    const now = options.now?.() ?? Date.now();
    if (options.forceRefresh) clearCache(storage);
    else { const cached = readCache(storage, now); if (cached) return Promise.resolve({ items: cached, cached: true }); }
    if (pending) return pending;
    pending = requestHistory(accessToken, options, storage).finally(() => { pending = null; });
    return pending;
  }

  function localDateKey(date) { return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`; }
  function formatDay(date, options = {}) {
    const now = options.now ? new Date(options.now) : new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const difference = Math.round((Date.UTC(day.getFullYear(), day.getMonth(), day.getDate()) - Date.UTC(start.getFullYear(), start.getMonth(), start.getDate())) / 86400000);
    if (difference === 0 || difference === -1) return new Intl.RelativeTimeFormat(options.locale, { numeric: "auto" }).format(difference, "day").toLocaleUpperCase(options.locale);
    return new Intl.DateTimeFormat(options.locale, { day: "numeric", month: "long", year: day.getFullYear() === start.getFullYear() ? undefined : "numeric" }).format(day).toLocaleUpperCase(options.locale);
  }
  function groupByLocalDate(items, options = {}) {
    const groups = [];
    items.forEach((item) => {
      const date = new Date(item.playedAt); const key = localDateKey(date);
      let group = groups[groups.length - 1];
      if (!group || group.key !== key) { group = { key, label: formatDay(date, options), items: [] }; groups.push(group); }
      group.items.push({ ...item, time: new Intl.DateTimeFormat(options.locale, { hour: "2-digit", minute: "2-digit" }).format(date) });
    });
    return groups;
  }

  return { API_URL, CACHE_KEY, CACHE_TTL_MS, normalizeItem, normalizeResponse, readCache, clearCache, getRecentlyPlayed, formatDay, groupByLocalDate };
});
