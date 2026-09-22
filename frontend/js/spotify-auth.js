(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SoundScopeSpotify = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const SPOTIFY_CONFIG = Object.freeze({ clientId: "9761def5856640cfa578814d94806c02", redirectUri: `${location.origin}${location.pathname.includes("/preview-v2/") ? "/preview-v2/index.html" : "/"}`, authorizeUrl: "https://accounts.spotify.com/authorize", tokenUrl: "https://accounts.spotify.com/api/token", profileUrl: "https://api.spotify.com/v1/me", scopes: Object.freeze(["user-top-read", "user-read-recently-played"]) });
  const KEYS = { verifier: "spotify_pkce_verifier", state: "spotify_oauth_state", session: "spotify_session" };
  const PERSISTENT_SESSION_KEY = "soundscope_spotify_session";
  function base64Url(bytes) { let binary = ""; bytes.forEach((byte) => { binary += String.fromCharCode(byte); }); const encoded = typeof btoa === "function" ? btoa(binary) : Buffer.from(bytes).toString("base64"); return encoded.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
  function randomString(length, cryptoApi = globalThis.crypto) { if (!cryptoApi?.getRandomValues) throw new Error("CRYPTO_UNAVAILABLE"); const bytes = new Uint8Array(length); cryptoApi.getRandomValues(bytes); return base64Url(bytes); }
  async function createChallenge(verifier, cryptoApi = globalThis.crypto) { if (!cryptoApi?.subtle) throw new Error("CRYPTO_UNAVAILABLE"); return base64Url(new Uint8Array(await cryptoApi.subtle.digest("SHA-256", new TextEncoder().encode(verifier)))); }
  function statesMatch(expected, returned) { return Boolean(expected && returned && expected === returned); }
  function parseCallback(search) { const p = new URLSearchParams(search); return { code: p.get("code"), state: p.get("state"), error: p.get("error"), errorDescription: p.get("error_description") }; }
  function isExpired(session, now = Date.now()) { return !session?.accessToken || !session.expiresAt || now >= session.expiresAt; }
  function clearCallbackUrl() { const url = new URL(location.href); ["code", "state", "error", "error_description"].forEach((key) => url.searchParams.delete(key)); history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}`); }
  function clearTemporary(storage) { storage.removeItem(KEYS.verifier); storage.removeItem(KEYS.state); }
  async function begin(storage = sessionStorage, locationApi = location) { const verifier = randomString(64); const state = randomString(32); const challenge = await createChallenge(verifier); storage.setItem(KEYS.verifier, verifier); storage.setItem(KEYS.state, state); const params = new URLSearchParams({ client_id: SPOTIFY_CONFIG.clientId, response_type: "code", redirect_uri: SPOTIFY_CONFIG.redirectUri, scope: SPOTIFY_CONFIG.scopes.join(" "), code_challenge_method: "S256", code_challenge: challenge, state }); locationApi.assign(`${SPOTIFY_CONFIG.authorizeUrl}?${params}`); }
  async function jsonResponse(response) { try { return await response.json(); } catch (_) { throw new Error("INVALID_JSON"); } }
  async function exchange(code, verifier, fetchApi = fetch) { const body = new URLSearchParams({ client_id: SPOTIFY_CONFIG.clientId, grant_type: "authorization_code", code, redirect_uri: SPOTIFY_CONFIG.redirectUri, code_verifier: verifier }); const response = await fetchApi(SPOTIFY_CONFIG.tokenUrl, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body }); const data = await jsonResponse(response); if (!response.ok || !data.access_token) throw new Error("TOKEN_ERROR"); return data; }
  async function profile(accessToken, fetchApi = fetch) { const response = await fetchApi(SPOTIFY_CONFIG.profileUrl, { headers: { Authorization: `Bearer ${accessToken}` } }); if (response.status === 401) throw new Error("SESSION_EXPIRED"); const data = await jsonResponse(response); if (!response.ok || !data.id) throw new Error("PROFILE_ERROR"); return data; }
  async function handleCallback(storage = sessionStorage, fetchApi = fetch) { const callback = parseCallback(location.search); if (!callback.code && !callback.error && !callback.state) return null; const expected = storage.getItem(KEYS.state); /* OAuth callbacks share query parameter names. Ignore callbacks that belong to SoundScope Accounts or another provider instead of consuming their code/state. */ if (!expected || !statesMatch(expected, callback.state)) return null; clearCallbackUrl(); if (callback.error) { clearTemporary(storage); throw new Error(callback.error === "access_denied" ? "ACCESS_DENIED" : "OAUTH_ERROR"); } const verifier = storage.getItem(KEYS.verifier); if (!callback.code) { clearTemporary(storage); throw new Error("MISSING_CODE"); } if (!verifier) { clearTemporary(storage); throw new Error("MISSING_VERIFIER"); } try { const token = await exchange(callback.code, verifier, fetchApi); const user = await profile(token.access_token, fetchApi); const session = { accessToken: token.access_token, expiresAt: Date.now() + Number(token.expires_in) * 1000, user: { id: user.id, displayName: user.display_name || "Usuário", image: user.images?.[0]?.url || "", spotifyUrl: user.external_urls?.spotify || "" } }; storage.setItem(KEYS.session, JSON.stringify(session)); try { localStorage.setItem(PERSISTENT_SESSION_KEY, JSON.stringify(session)); } catch (_) {} return session; } finally { clearTemporary(storage); } }
  function getSession(storage = sessionStorage) {
    try {
      const session = JSON.parse(storage.getItem(KEYS.session));
      if (session?.accessToken) return session;
    } catch (_) { storage.removeItem(KEYS.session); }
    try {
      const persistent = JSON.parse(localStorage.getItem(PERSISTENT_SESSION_KEY));
      if (persistent?.accessToken) {
        storage.setItem(KEYS.session, JSON.stringify(persistent));
        return persistent;
      }
    } catch (_) { try { localStorage.removeItem(PERSISTENT_SESSION_KEY); } catch (_) {} }
    return null;
  }
  function disconnect(storage = sessionStorage) { clearTemporary(storage); storage.removeItem(KEYS.session); try { localStorage.removeItem(PERSISTENT_SESSION_KEY); } catch (_) {} }
  return { SPOTIFY_CONFIG, KEYS, base64Url, randomString, createChallenge, statesMatch, parseCallback, isExpired, begin, handleCallback, getSession, disconnect };
});
