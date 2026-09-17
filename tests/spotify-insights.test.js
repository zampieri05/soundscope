"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const insights = require("../frontend/js/spotify-insights.js");

function memoryStorage() {
  const values = new Map();
  return { values, getItem: (key) => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
}
function response(items = [], status = 200, headers = {}) { return { ok: status >= 200 && status < 300, status, headers: { get: (key) => headers[key] || null }, json: async () => ({ items }) }; }
const artist = { id: "a1", name: "Björk", images: [{ url: "https://image.test/artist.jpg" }], external_urls: { spotify: "https://open.spotify.com/artist/a1" }, genres: ["irrelevant"] };
const track = { id: "t1", name: "Jóga", artists: [{ name: "Björk" }], album: { name: "Homogenic", images: [{ url: "https://image.test/album.jpg" }] }, external_urls: { spotify: "https://open.spotify.com/track/t1" }, preview_url: "https://unused.test" };

for (const range of ["short_term", "medium_term", "long_term"]) test(`envia o período ${range}`, async () => {
  let requested; await insights.getTopArtists(range, "token", { storage: memoryStorage(), fetchApi: async (url) => { requested = new URL(url); return response([artist]); } });
  assert.equal(requested.searchParams.get("time_range"), range); assert.equal(requested.searchParams.get("limit"), "10");
});
test("busca e normaliza top artists", async () => {
  const result = await insights.getTopArtists("short_term", "token", { storage: memoryStorage(), fetchApi: async (url) => { assert.match(url, /\/top\/artists/); return response([artist]); } });
  assert.deepEqual(result.items[0], { id: "a1", name: "Björk", image: "https://image.test/artist.jpg", spotifyUrl: "https://open.spotify.com/artist/a1" });
});
test("busca e normaliza top tracks sem preview", async () => {
  const result = await insights.getTopTracks("short_term", "token", { storage: memoryStorage(), fetchApi: async (url) => { assert.match(url, /\/top\/tracks/); return response([track]); } });
  assert.deepEqual(result.items[0], { id: "t1", name: "Jóga", artists: ["Björk"], album: "Homogenic", image: "https://image.test/album.jpg", spotifyUrl: "https://open.spotify.com/track/t1" });
});
test("cache é separado por período e tipo e não persiste token", async () => {
  const storage = memoryStorage(); let calls = 0; const fetchApi = async () => { calls += 1; return response([artist]); };
  await insights.getTopArtists("short_term", "secret-token", { storage, fetchApi }); await insights.getTopArtists("short_term", "secret-token", { storage, fetchApi });
  await insights.getTopArtists("long_term", "secret-token", { storage, fetchApi }); await insights.getTopTracks("short_term", "secret-token", { storage, fetchApi: async () => { calls += 1; return response([track]); } });
  assert.equal(calls, 3); assert.equal(storage.values.size, 3); assert.doesNotMatch([...storage.values.values()].join(""), /secret-token/);
  insights.clearCache(storage); assert.equal(storage.values.size, 0);
});
test("aceita resposta vazia e a mantém em cache", async () => {
  const storage = memoryStorage(); let calls = 0; const fetchApi = async () => { calls += 1; return response([]); };
  assert.deepEqual((await insights.getTopTracks("medium_term", "token", { storage, fetchApi })).items, []); assert.equal((await insights.getTopTracks("medium_term", "token", { storage, fetchApi })).cached, true); assert.equal(calls, 1);
});
for (const [status, message] of [[401, "SESSION_EXPIRED"], [403, "SPOTIFY_SCOPE_REQUIRED"]]) test(`trata HTTP ${status}`, async () => {
  await assert.rejects(insights.getTopArtists("short_term", "token", { storage: memoryStorage(), fetchApi: async () => response([], status) }), { message });
});
test("trata 429 e preserva Retry-After sem repetir chamada", async () => {
  let calls = 0; await assert.rejects(insights.getTopTracks("short_term", "token", { storage: memoryStorage(), fetchApi: async () => { calls += 1; return response([], 429, { "Retry-After": "30" }); } }), (error) => error.message === "RATE_LIMITED" && error.retryAfter === "30"); assert.equal(calls, 1);
});
test("trata falha de rede", async () => { await assert.rejects(insights.getTopArtists("short_term", "token", { storage: memoryStorage(), fetchApi: async () => { throw new TypeError("offline"); } }), { message: "SPOTIFY_NETWORK_ERROR" }); });
test("rejeita ausência de token antes da rede", async () => { await assert.rejects(insights.getTopArtists("short_term", "", { fetchApi: async () => assert.fail("não deve chamar") }), { message: "SPOTIFY_DISCONNECTED" }); });
test("normalização é segura com campos ausentes e URLs não HTTPS", () => {
  assert.deepEqual(insights.normalizeArtist({ external_urls: { spotify: "javascript:alert(1)" } }), { id: "", name: "Artista não informado", image: "", spotifyUrl: "" });
  assert.deepEqual(insights.normalizeTrack({ artists: [null, { name: "A" }], album: {} }), { id: "", name: "Música não informada", artists: ["A"], album: "Álbum não informado", image: "", spotifyUrl: "" });
});
