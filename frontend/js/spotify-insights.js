(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SoundScopeSpotifyInsights = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const API_URL = "https://api.spotify.com/v1/me/top";
  const CACHE_PREFIX = "soundscope_spotify_insights_v1";
  const VALID_TYPES = new Set(["artists", "tracks"]);
  const VALID_RANGES = new Set(["short_term", "medium_term", "long_term"]);

  function safeUrl(value) { return typeof value === "string" && /^https:\/\//.test(value) ? value : ""; }
  function firstImage(images) { return Array.isArray(images) ? safeUrl(images.find((image) => image?.url)?.url) : ""; }
  function normalizeArtist(artist) {
    return { id: String(artist?.id || ""), name: String(artist?.name || "Artista não informado"), image: firstImage(artist?.images), spotifyUrl: safeUrl(artist?.external_urls?.spotify) };
  }
  function normalizeTrack(track) {
    return { id: String(track?.id || ""), name: String(track?.name || "Música não informada"), artists: Array.isArray(track?.artists) ? track.artists.map((artist) => String(artist?.name || "")).filter(Boolean) : [], album: String(track?.album?.name || "Álbum não informado"), image: firstImage(track?.album?.images), spotifyUrl: safeUrl(track?.external_urls?.spotify) };
  }
  function cacheKey(type, timeRange) { return `${CACHE_PREFIX}:top-${type}:${timeRange}`; }
  function readCache(storage, key) { try { const value = JSON.parse(storage?.getItem(key)); return Array.isArray(value) ? value : null; } catch (_) { return null; } }
  function writeCache(storage, key, value) { try { storage?.setItem(key, JSON.stringify(value)); } catch (_) { /* Insights remain usable when storage is unavailable. */ } }
  function clearCache(storage = typeof sessionStorage === "undefined" ? null : sessionStorage) {
    try { VALID_TYPES.forEach((type) => VALID_RANGES.forEach((range) => storage?.removeItem(cacheKey(type, range)))); } catch (_) { /* Cache is disposable. */ }
  }
  function spotifyError(code, retryAfter) { const error = new Error(code); if (retryAfter) error.retryAfter = retryAfter; return error; }

  async function getTop(type, timeRange, accessToken, options = {}) {
    if (!VALID_TYPES.has(type)) throw new Error("INVALID_TYPE");
    if (!VALID_RANGES.has(timeRange)) throw new Error("INVALID_TIME_RANGE");
    if (!accessToken) throw new Error("SPOTIFY_DISCONNECTED");
    const storage = options.storage === undefined ? (typeof sessionStorage === "undefined" ? null : sessionStorage) : options.storage;
    const key = cacheKey(type, timeRange); const cached = readCache(storage, key);
    if (cached) return { items: cached, cached: true };
    const url = new URL(`${API_URL}/${type}`); url.search = new URLSearchParams({ time_range: timeRange, limit: String(options.limit || 10) });
    let response;
    try { response = await (options.fetchApi || fetch)(url.toString(), { headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" } }); }
    catch (_) { throw new Error("SPOTIFY_NETWORK_ERROR"); }
    if (response.status === 401) throw new Error("SESSION_EXPIRED");
    if (response.status === 403) throw new Error("SPOTIFY_SCOPE_REQUIRED");
    if (response.status === 429) throw spotifyError("RATE_LIMITED", response.headers?.get?.("Retry-After"));
    if (!response.ok) throw new Error("SPOTIFY_NETWORK_ERROR");
    let data; try { data = await response.json(); } catch (_) { throw new Error("SPOTIFY_NETWORK_ERROR"); }
    const normalizer = type === "artists" ? normalizeArtist : normalizeTrack;
    const items = Array.isArray(data?.items) ? data.items.filter(Boolean).map(normalizer) : [];
    writeCache(storage, key, items);
    return { items, cached: false };
  }

  function getTopArtists(timeRange, accessToken, options) { return getTop("artists", timeRange, accessToken, options); }
  function getTopTracks(timeRange, accessToken, options) { return getTop("tracks", timeRange, accessToken, options); }
  return { API_URL, CACHE_PREFIX, VALID_RANGES, cacheKey, clearCache, normalizeArtist, normalizeTrack, getTop, getTopArtists, getTopTracks };
});
