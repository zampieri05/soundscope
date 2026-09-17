"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const history = require("../frontend/js/spotify-history.js");

function memoryStorage() {
  const values = new Map();
  return { values, getItem: (key) => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
}
function item(playedAt, overrides = {}) {
  return { played_at: playedAt, track: { name: "Jóga", artists: [{ name: "Björk" }], album: { name: "Homogenic", images: [{ url: "https://image.test/cover.jpg" }] }, external_urls: { spotify: "https://open.spotify.com/track/one" }, ...overrides } };
}
function response(items = [], status = 200, headers = {}) {
  return { ok: status >= 200 && status < 300, status, headers: { get: (name) => headers[name] || null }, json: async () => ({ items }) };
}

test("normaliza resposta válida e usa somente os campos editoriais", () => {
  assert.deepEqual(history.normalizeResponse({ items: [item("2026-09-17T14:32:00Z")] })[0], { playedAt: "2026-09-17T14:32:00Z", name: "Jóga", artists: ["Björk"], album: "Homogenic", image: "https://image.test/cover.jpg", spotifyUrl: "https://open.spotify.com/track/one" });
});
test("ordena do evento mais novo ao mais antigo sem remover duplicatas", () => {
  const items = history.normalizeResponse({ items: [item("2026-09-16T10:00:00Z"), item("2026-09-17T10:00:00Z"), item("2026-09-17T10:00:00Z")] });
  assert.equal(items.length, 3); assert.deepEqual(items.map((value) => value.playedAt), ["2026-09-17T10:00:00Z", "2026-09-17T10:00:00Z", "2026-09-16T10:00:00Z"]);
});
test("descarta played_at inválido", () => assert.deepEqual(history.normalizeResponse({ items: [item("invalid"), item("2026-09-17T10:00:00Z")] }).length, 1));
test("tolera ausência de imagem e URL externa sem inventar valores", () => {
  const normalized = history.normalizeItem(item("2026-09-17T10:00:00Z", { album: { name: "Homogenic", images: [] }, external_urls: {} }));
  assert.equal(normalized.image, ""); assert.equal(normalized.spotifyUrl, "");
});
test("aceita resposta vazia", () => assert.deepEqual(history.normalizeResponse({ items: [] }), []));
test("agrupa e formata datas no timezone local", () => {
  const groups = history.groupByLocalDate(history.normalizeResponse({ items: [item("2026-09-17T14:32:00Z"), item("2026-09-16T12:00:00Z")] }), { locale: "pt-BR", now: "2026-09-17T18:00:00Z" });
  assert.equal(groups[0].label, "HOJE"); assert.equal(groups[1].label, "ONTEM"); assert.match(groups[0].items[0].time, /^\d{2}:\d{2}$/);
});
test("cache hit dentro do TTL não consulta a rede nem persiste token", async () => {
  const storage = memoryStorage(); let calls = 0; const fetchApi = async (url) => { calls += 1; assert.equal(new URL(url).searchParams.get("limit"), "20"); return response([item("2026-09-17T10:00:00Z")]); }; const now = () => 1000;
  await history.getRecentlyPlayed("secret-token", { storage, fetchApi, now }); const second = await history.getRecentlyPlayed("secret-token", { storage, fetchApi, now: () => 1000 + history.CACHE_TTL_MS - 1 });
  assert.equal(second.cached, true); assert.equal(calls, 1); assert.doesNotMatch(storage.values.get(history.CACHE_KEY), /secret-token/);
});
test("cache expirado faz nova consulta", async () => {
  const storage = memoryStorage(); let calls = 0; const fetchApi = async () => { calls += 1; return response([]); };
  await history.getRecentlyPlayed("token", { storage, fetchApi, now: () => 1 }); await history.getRecentlyPlayed("token", { storage, fetchApi, now: () => 1 + history.CACHE_TTL_MS }); assert.equal(calls, 2);
});
test("reutiliza a Promise de requisições simultâneas", async () => {
  let release; let calls = 0; const fetchApi = () => { calls += 1; return new Promise((resolve) => { release = () => resolve(response([])); }); }; const storage = memoryStorage();
  const first = history.getRecentlyPlayed("token", { storage, fetchApi }); const second = history.getRecentlyPlayed("token", { storage, fetchApi }); release(); await Promise.all([first, second]); assert.equal(calls, 1);
});
test("atualização manual invalida e ignora o cache", async () => {
  const storage = memoryStorage(); let calls = 0; const fetchApi = async () => { calls += 1; return response([]); };
  await history.getRecentlyPlayed("token", { storage, fetchApi }); await history.getRecentlyPlayed("token", { storage, fetchApi, forceRefresh: true }); assert.equal(calls, 2);
});
for (const [status, message] of [[401, "SESSION_EXPIRED"], [403, "SPOTIFY_SCOPE_REQUIRED"]]) test(`trata HTTP ${status}`, async () => {
  await assert.rejects(history.getRecentlyPlayed("token", { storage: memoryStorage(), fetchApi: async () => response([], status) }), { message });
});
test("trata 429, preserva Retry-After e não repete", async () => {
  let calls = 0; await assert.rejects(history.getRecentlyPlayed("token", { storage: memoryStorage(), fetchApi: async () => { calls += 1; return response([], 429, { "Retry-After": "30" }); } }), (error) => error.message === "RATE_LIMITED" && error.retryAfter === "30"); assert.equal(calls, 1);
});
test("trata erro de rede", async () => { await assert.rejects(history.getRecentlyPlayed("token", { storage: memoryStorage(), fetchApi: async () => { throw new TypeError("offline"); } }), { message: "SPOTIFY_NETWORK_ERROR" }); });
test("trata timeout", async () => {
  const fetchApi = (_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" }))));
  await assert.rejects(history.getRecentlyPlayed("token", { storage: memoryStorage(), fetchApi, timeoutMs: 1 }), { message: "SPOTIFY_TIMEOUT" });
});
test("rejeita ausência de token antes da rede", async () => { await assert.rejects(history.getRecentlyPlayed("", { fetchApi: async () => assert.fail("não deve chamar") }), { message: "SPOTIFY_DISCONNECTED" }); });
