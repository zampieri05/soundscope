(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SoundScopeSpotifyCatalog = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SEARCH_URL = "https://api.spotify.com/v1/search";
  const CACHE_KEY = "soundscope_spotify_album_matches_v1";
  const ARTIST_CATALOG_CACHE_KEY = "soundscope_spotify_artist_catalog_v1";
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

  function artistCandidateFromApi(artist) {
    return {
      name: artist?.name || "",
      spotifyId: artist?.id || "",
      spotifyUrl: artist?.external_urls?.spotify || "",
      followers: Number(artist?.followers?.total) || 0,
      popularity: Number(artist?.popularity) || 0,
      genres: Array.isArray(artist?.genres) ? artist.genres : []
    };
  }

  function matchArtist(artistName, candidates) {
    const wanted = normalize(artistName);
    const exact = (candidates || []).filter((item) =>
      item?.spotifyId && normalize(item.name) === wanted
    );
    if (!exact.length) {
      return { matched: false, confidence: "none", reason: "no_exact_match", artist: null };
    }
    if (exact.length === 1) {
      return { matched: true, confidence: "high", reason: "exact_artist_name", artist: exact[0] };
    }
    // Spotify Search is relevance-ranked. For homonyms, accept the first exact-name
    // candidate only when it has materially stronger audience evidence than #2.
    // This avoids arbitrary ties while still resolving established artists.
    const ranked = [...exact].sort((a, b) =>
      (Number(b.followers) || 0) - (Number(a.followers) || 0) ||
      (Number(b.popularity) || 0) - (Number(a.popularity) || 0)
    );
    const first = ranked[0], second = ranked[1];
    const firstFollowers = Number(first.followers) || 0;
    const secondFollowers = Number(second.followers) || 0;
    const followerLead = firstFollowers >= 1000 && firstFollowers >= Math.max(1, secondFollowers) * 3;
    const popularityLead = (Number(first.popularity) || 0) >= (Number(second.popularity) || 0) + 20;
    if (followerLead || popularityLead) {
      return { matched: true, confidence: "medium", reason: "exact_name_audience_lead", artist: first };
    }
    return { matched: false, confidence: "ambiguous", reason: "ambiguous_results", artist: null };
  }

  async function spotifyJson(url, accessToken, fetchApi, signal) {
    const response = await fetchApi(url, {
      headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" },
      signal
    });
    if (response.status === 401) throw new Error("SESSION_EXPIRED");
    if (response.status === 429) {
      const error = new Error("RATE_LIMITED");
      error.retryAfter = response.headers?.get?.("Retry-After") || null;
      throw error;
    }
    if (!response.ok) throw new Error("SPOTIFY_NETWORK_ERROR");
    try { return await response.json(); } catch (_) { throw new Error("SPOTIFY_NETWORK_ERROR"); }
  }

  async function searchArtists(artistName, accessToken, options = {}) {
    if (!accessToken) throw new Error("SPOTIFY_DISCONNECTED");
    const fetchApi = options.fetchApi || fetch;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeoutMs || REQUEST_TIMEOUT_MS);
    const url = new URL(SEARCH_URL);
    url.search = new URLSearchParams({ q: `artist:${artistName}`, type: "artist", limit: "10" });
    try {
      const data = await spotifyJson(url.toString(), accessToken, fetchApi, controller.signal);
      return (data?.artists?.items || []).filter(Boolean).map(artistCandidateFromApi);
    } catch (error) {
      if (error.name === "AbortError") throw new Error("SPOTIFY_TIMEOUT");
      throw error;
    } finally { clearTimeout(timer); }
  }

  function catalogAlbumFromApi(album) {
    const kind = normalize(album?.album_type);
    return {
      title: album?.name || "Título não informado",
      year: releaseYear(album?.release_date) ? String(releaseYear(album.release_date)) : null,
      album_id: album?.id ? `spotify:${album.id}` : null,
      musicbrainz_release_group_id: null,
      cover_url: album?.images?.[0]?.url || null,
      primary_type: kind === "single" ? "Single" : kind === "compilation" ? "Album" : "Album",
      secondary_types: kind === "compilation" ? ["Compilation"] : [],
      first_release_date: album?.release_date || null,
      spotify_url: album?.external_urls?.spotify || null
    };
  }

  async function fetchArtistCatalog(spotifyArtistId, accessToken, options = {}) {
    if (!accessToken) throw new Error("SPOTIFY_DISCONNECTED");
    if (!spotifyArtistId) throw new Error("SPOTIFY_ARTIST_REQUIRED");
    const fetchApi = options.fetchApi || fetch;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeoutMs || REQUEST_TIMEOUT_MS);
    const releases = [];
    let next = `https://api.spotify.com/v1/artists/${encodeURIComponent(spotifyArtistId)}/albums?` +
      new URLSearchParams({ include_groups: "album,single,compilation", limit: "10" });
    try {
      while (next) {
        const data = await spotifyJson(next, accessToken, fetchApi, controller.signal);
        releases.push(...(data?.items || []).filter(Boolean));
        next = data?.next || null;
      }
    } catch (error) {
      if (error.name === "AbortError") throw new Error("SPOTIFY_TIMEOUT");
      throw error;
    } finally { clearTimeout(timer); }
    const seen = new Set();
    return releases.map(catalogAlbumFromApi).filter((album) => {
      if (!album.album_id || seen.has(album.album_id)) return false;
      seen.add(album.album_id); return true;
    });
  }

  async function resolveArtistCatalog(artistName, accessToken, options = {}) {
    const storage = options.storage === undefined ? (typeof sessionStorage === "undefined" ? null : sessionStorage) : options.storage;
    const cacheKey = normalize(artistName);
    try {
      const cache = JSON.parse(storage?.getItem(ARTIST_CATALOG_CACHE_KEY) || "{}");
      if (cache[cacheKey]) return { ...cache[cacheKey], cached: true };
    } catch (_) { /* cache miss */ }
    const candidates = await searchArtists(artistName, accessToken, options);
    const match = matchArtist(artistName, candidates);
    if (!match.matched) return { ...match, albums: [], cached: false };
    const albums = await fetchArtistCatalog(match.artist.spotifyId, accessToken, options);
    const result = { ...match, albums, cached: false };
    if (storage) {
      try {
        const cache = JSON.parse(storage.getItem(ARTIST_CATALOG_CACHE_KEY) || "{}");
        cache[cacheKey] = { ...result, cached: false };
        storage.setItem(ARTIST_CATALOG_CACHE_KEY, JSON.stringify(cache));
      } catch (_) { /* cache failure must not affect catalog */ }
    }
    return result;
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

  return { SEARCH_URL, CACHE_KEY, ARTIST_CATALOG_CACHE_KEY, normalize, titleParts, candidateFromApi, scoreCandidate, matchAlbum, cacheId, lookupAlbum, searchAlbums, artistCandidateFromApi, matchArtist, searchArtists, catalogAlbumFromApi, fetchArtistCatalog, resolveArtistCatalog };
});
