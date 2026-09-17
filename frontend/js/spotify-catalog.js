(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SoundScopeSpotifyCatalog = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SEARCH_URL = "https://api.spotify.com/v1/search";
  const CACHE_KEY = "soundscope_spotify_album_matches_v1";
  const REQUEST_TIMEOUT_MS = 8000;
  const EDITION_WORDS = "deluxe|remaster(?:ed)?|anniversary|expanded|special|bonus|collector(?:'s)?|legacy|super deluxe";
  const pending = new Map();

  function normalize(value) {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
      .replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ").trim().replace(/\s+/g, " ");
  }

  function titleParts(value) {
    const normalized = normalize(value);
    const editionPattern = new RegExp(`(?:^|\\s)(?:${EDITION_WORDS})(?:\\s+edition)?(?:\\s|$)`);
    const base = normalized
      .replace(/\s+\d{2,4}\s+remaster(?:ed)?(?:\s+edition)?$/, "")
      .replace(new RegExp(`\\s+(?:${EDITION_WORDS})(?:\\s+edition)?(?:\\s+version)?(?:\\s+\\d{2,4})?.*$`), "")
      .trim();
    return { normalized, base: base || normalized, isEdition: editionPattern.test(normalized) };
  }

  function releaseYear(value) {
    const match = String(value || "").match(/^\d{4}/);
    return match ? Number(match[0]) : null;
  }

  function candidateFromApi(album) {
    return {
      artist: Array.isArray(album?.artists) ? album.artists.map((item) => item.name).filter(Boolean) : [],
      title: album?.name || "",
      releaseDate: album?.release_date || "",
      type: album?.album_type || album?.type || "",
      spotifyId: album?.id || "",
      spotifyUrl: album?.external_urls?.spotify || ""
    };
  }

  function scoreCandidate(input, candidate) {
    const wantedArtist = normalize(input.artistName);
    const artists = (Array.isArray(candidate.artist) ? candidate.artist : [candidate.artist]).map(normalize);
    if (!wantedArtist || !artists.includes(wantedArtist)) return null;
    const wantedTitle = titleParts(input.albumTitle);
    const foundTitle = titleParts(candidate.title);
    if (!wantedTitle.normalized || wantedTitle.base !== foundTitle.base) return null;
    if (!candidate.spotifyId || !/^https:\/\/open\.spotify\.com\/album\//.test(candidate.spotifyUrl)) return null;

    let score = 40;
    score += wantedTitle.normalized === foundTitle.normalized ? 45 : 35;
    const wantedYear = releaseYear(input.releaseYear);
    const foundYear = releaseYear(candidate.releaseDate);
    if (wantedYear && foundYear) {
      const difference = Math.abs(wantedYear - foundYear);
      if (difference > 1) return null;
      score += difference === 0 ? 10 : 5;
    }
    if (normalize(candidate.type) === "album") score += 5;
    if (!wantedTitle.isEdition && foundTitle.isEdition) score -= 3;
    return score;
  }

  function matchAlbum(input, candidates) {
    const ranked = (candidates || []).map((album) => ({ album, score: scoreCandidate(input, album) }))
      .filter((item) => item.score !== null).sort((a, b) => b.score - a.score || a.album.spotifyId.localeCompare(b.album.spotifyId));
    if (!ranked.length || ranked[0].score < 80) return { matched: false, confidence: "none", reason: "no_confident_match", album: null };
    if (ranked[1] && ranked[0].score - ranked[1].score <= 3 && ranked[0].album.spotifyId !== ranked[1].album.spotifyId) {
      return { matched: false, confidence: "ambiguous", reason: "ambiguous_results", album: null };
    }
    return { matched: true, confidence: ranked[0].score >= 95 ? "high" : "medium", reason: "artist_title_year", album: ranked[0].album };
  }

  function cacheId(input) { return [normalize(input.artistName), normalize(input.albumTitle), releaseYear(input.releaseYear) || ""].join("|"); }
  function readCache(storage, key) {
    try { const cache = JSON.parse(storage?.getItem(CACHE_KEY) || "{}"); return Object.prototype.hasOwnProperty.call(cache, key) ? cache[key] : null; } catch (_) { return null; }
  }
  function writeCache(storage, key, value) {
    if (!storage) return;
    try { const cache = JSON.parse(storage.getItem(CACHE_KEY) || "{}"); cache[key] = value; storage.setItem(CACHE_KEY, JSON.stringify(cache)); } catch (_) { /* Cache failure must not affect the catalog. */ }
  }

  async function searchAlbums(input, accessToken, options = {}) {
    if (!accessToken) throw new Error("SPOTIFY_DISCONNECTED");
    const fetchApi = options.fetchApi || fetch;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeoutMs || REQUEST_TIMEOUT_MS);
    const query = `album:${input.albumTitle} artist:${input.artistName}`;
    const url = new URL(SEARCH_URL); url.search = new URLSearchParams({ q: query, type: "album", limit: "10" });
    try {
      const response = await fetchApi(url.toString(), { headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" }, signal: controller.signal });
      if (response.status === 401) throw new Error("SESSION_EXPIRED");
      if (response.status === 429) { const error = new Error("RATE_LIMITED"); error.retryAfter = response.headers?.get?.("Retry-After") || null; throw error; }
      if (!response.ok) throw new Error("SPOTIFY_NETWORK_ERROR");
      let data; try { data = await response.json(); } catch (_) { throw new Error("SPOTIFY_NETWORK_ERROR"); }
      return (data?.albums?.items || []).filter(Boolean).map(candidateFromApi);
    } catch (error) {
      if (error.name === "AbortError") throw new Error("SPOTIFY_TIMEOUT");
      throw error;
    } finally { clearTimeout(timer); }
  }

  async function lookupAlbum(input, accessToken, options = {}) {
    const storage = options.storage === undefined ? (typeof sessionStorage === "undefined" ? null : sessionStorage) : options.storage;
    const key = cacheId(input); const cached = readCache(storage, key);
    if (cached) return { ...cached, cached: true };
    if (pending.has(key)) return pending.get(key);
    const request = searchAlbums(input, accessToken, options).then((candidates) => {
      const result = matchAlbum(input, candidates); writeCache(storage, key, result); return { ...result, cached: false };
    }).finally(() => pending.delete(key));
    pending.set(key, request); return request;
  }

  return { SEARCH_URL, CACHE_KEY, normalize, titleParts, candidateFromApi, scoreCandidate, matchAlbum, cacheId, lookupAlbum, searchAlbums };
});
