"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const orbit = require("../frontend/js/spotify-orbit.js");

const artists = Array.from({ length: 14 }, (_, index) => ({ id: `a${index}`, name: `Artista ${index}`, image: `https://images.test/${index}.jpg`, spotifyUrl: `https://open.spotify.com/artist/a${index}`, streams: 999 }));

test("normaliza Top Artists, limita a dez e preserva ranking e ordem", () => {
  const result = orbit.normalizeArtists(artists);
  assert.equal(result.length, 10); assert.deepEqual(result.map((item) => item.rank), [1,2,3,4,5,6,7,8,9,10]);
  assert.deepEqual(result.map((item) => item.name), artists.slice(0, 10).map((item) => item.name));
});
test("usa fallback neutro para imagem ausente e remove URL ausente ou inválida", () => {
  const [missing, invalid] = orbit.normalizeArtists([{ name: "Sem mídia" }, { name: "Inválido", image: "data:x", spotifyUrl: "https://evil.test/a" }]);
  assert.equal(missing.image, ""); assert.equal(missing.spotifyUrl, ""); assert.equal(invalid.image, ""); assert.equal(invalid.spotifyUrl, "");
});
test("aceita somente URL oficial HTTPS de artista retornada", () => {
  assert.equal(orbit.safeUrl("https://open.spotify.com/artist/abc123"), "https://open.spotify.com/artist/abc123");
  for (const value of ["http://open.spotify.com/artist/a", "https://open.spotify.com/track/a", "javascript:alert(1)", undefined]) assert.equal(orbit.safeUrl(value), "");
});
test("layout é determinístico, finito e sem NaN", () => {
  assert.deepEqual(orbit.calculateLayout(10), orbit.calculateLayout(10));
  orbit.calculateLayout(10).forEach((position) => Object.values(position).forEach((value) => assert.equal(Number.isFinite(value), true)));
  assert.deepEqual(orbit.calculateLayout(undefined), []);
});
test("estado aceita ausência de dados e estado vazio", () => {
  const state = orbit.createState(); assert.deepEqual(state.setArtists(undefined).artists, []); assert.deepEqual(state.setArtists([]).artists, []);
});
for (const range of ["short_term", "medium_term", "long_term"]) test(`troca período ${range} sem buscar dados`, () => {
  let changes = 0; const state = orbit.createState({ onChange: () => { changes += 1; } }); state.setRange(range);
  assert.equal(state.get().range, range); assert.equal(changes, 1); assert.equal("fetch" in state, false);
});
test("seleciona artista e chama integração Explorar no SoundScope", () => {
  let explored; const state = orbit.createState({ onExplore: (artist) => { explored = artist; } }); state.setArtists(artists); const selected = state.select("a1"); state.explore();
  assert.equal(selected.name, "Artista 1"); assert.equal(state.get().selected.id, "a1"); assert.equal(explored.id, "a1");
});
test("não explora sem seleção e ignora seleção desconhecida", () => {
  let calls = 0; const state = orbit.createState({ onExplore: () => { calls += 1; } }); state.setArtists(artists); assert.equal(state.select("ausente"), null); state.explore(); assert.equal(calls, 0);
});
test("não cria métricas inferidas", () => {
  const [artist] = orbit.normalizeArtists(artists); assert.deepEqual(Object.keys(artist).sort(), ["id", "image", "name", "rank", "spotifyUrl"]); assert.equal("streams" in artist, false);
});
test("preserva preferência reduced-motion no estado", () => { assert.equal(orbit.createState({ reducedMotion: true }).get().reducedMotion, true); });
test("módulo não possui cliente Spotify nem dispara requisição duplicada", () => {
  assert.equal("getTopArtists" in orbit, false); assert.equal("fetch" in orbit, false);
});
test("rejeita período desconhecido", () => { assert.throws(() => orbit.createState().setRange("weekly"), /INVALID_TIME_RANGE/); });
