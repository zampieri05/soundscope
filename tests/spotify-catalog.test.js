"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const catalog = require("../frontend/js/spotify-catalog.js");

const input = { artistName: "Beyoncé", albumTitle: "Renaissance", releaseYear: "2022" };
function album(overrides = {}) {
  return { artist: ["Beyoncé"], title: "Renaissance", releaseDate: "2022-07-29", type: "album", spotifyId: "id-1", spotifyUrl: "https://open.spotify.com/album/id-1", ...overrides };
}

test("normaliza acentos, pontuação e espaços do título", () => {
  assert.equal(catalog.normalize("  ÁLBUM:  Único! "), "album unico");
});

test("aceita artista e título corretos", () => {
  const result = catalog.matchAlbum(input, [album()]);
  assert.equal(result.matched, true); assert.equal(result.album.spotifyId, "id-1");
});

test("rejeita artista incorreto mesmo com título correto", () => {
  assert.equal(catalog.matchAlbum(input, [album({ artist: ["Outra artista"] })]).matched, false);
});

test("rejeita título incorreto mesmo com artista correto", () => {
  assert.equal(catalog.matchAlbum(input, [album({ title: "Lemonade" })]).matched, false);
});

test("rejeita diferença de ano superior a um", () => {
  assert.equal(catalog.matchAlbum(input, [album({ releaseDate: "2019" })]).matched, false);
});

test("reconhece qualificadores Deluxe e Remastered sem apagar o título original", () => {
  assert.equal(catalog.titleParts("Rumours (Deluxe Edition)").base, "rumours");
  assert.equal(catalog.titleParts("Rumours - 2013 Remastered").base, "rumours");
});

test("prefere a edição integralmente igual a uma variante Deluxe", () => {
  const deluxe = album({ title: "Renaissance Deluxe Edition", spotifyId: "deluxe", spotifyUrl: "https://open.spotify.com/album/deluxe" });
  const original = album({ spotifyId: "original", spotifyUrl: "https://open.spotify.com/album/original" });
  assert.equal(catalog.matchAlbum(input, [deluxe, original]).album.spotifyId, "original");
});

test("não associa resultados ambíguos", () => {
  const other = album({ spotifyId: "id-2", spotifyUrl: "https://open.spotify.com/album/id-2" });
  const result = catalog.matchAlbum(input, [album(), other]);
  assert.equal(result.matched, false); assert.equal(result.confidence, "ambiguous");
});

test("trata lista sem resultados", () => {
  assert.deepEqual(catalog.matchAlbum(input, []), { matched: false, confidence: "none", reason: "no_confident_match", album: null });
});

test("cache de sessão evita buscas duplicadas e não armazena token", async () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key) || null, setItem: (key, value) => values.set(key, value) };
  let calls = 0;
  const fetchApi = async (url, options) => {
    calls += 1; assert.match(url, /^https:\/\/api\.spotify\.com\/v1\/search\?/);
    assert.equal(options.headers.Authorization, "Bearer secret-token");
    return { ok: true, status: 200, json: async () => ({ albums: { items: [{ id: "id-1", name: "Renaissance", release_date: "2022", album_type: "album", artists: [{ name: "Beyoncé" }], external_urls: { spotify: "https://open.spotify.com/album/id-1" } }] } }) };
  };
  const first = await catalog.lookupAlbum(input, "secret-token", { storage, fetchApi });
  const second = await catalog.lookupAlbum(input, "secret-token", { storage, fetchApi });
  assert.equal(first.matched, true); assert.equal(second.cached, true); assert.equal(calls, 1);
  assert.doesNotMatch(values.get(catalog.CACHE_KEY), /secret-token/);
});

test("seleciona o melhor candidato entre resultados válidos", () => {
  const nearYear = album({ releaseDate: "2021", spotifyId: "near", spotifyUrl: "https://open.spotify.com/album/near" });
  const exactYear = album({ spotifyId: "exact", spotifyUrl: "https://open.spotify.com/album/exact" });
  assert.equal(catalog.matchAlbum(input, [nearYear, exactYear]).album.spotifyId, "exact");
});


test("resolver de artista exige correspondência exata e única", () => {
  const result = catalog.matchArtist("Fhop Music", [
    { name: "FHOP", spotifyId: "sparse" },
    { name: "Fhop Music", spotifyId: "canonical" }
  ]);
  assert.equal(result.matched, true);
  assert.equal(result.artist.spotifyId, "canonical");
});

test("normaliza releases do Spotify para a discografia SoundScope", () => {
  const item = catalog.catalogAlbumFromApi({
    id: "release-1",
    name: "A Boa Parte (Ao Vivo)",
    release_date: "2024-05-10",
    album_type: "album",
    images: [{ url: "https://example.test/cover.jpg" }],
    external_urls: { spotify: "https://open.spotify.com/album/release-1" }
  });
  assert.equal(item.title, "A Boa Parte (Ao Vivo)");
  assert.equal(item.year, "2024");
  assert.equal(item.primary_type, "Album");
  assert.equal(item.album_id, "spotify:release-1");
  assert.equal(item.cover_url, "https://example.test/cover.jpg");
});

test("resolve catálogo completo do artista via Spotify sem armazenar token", async () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key) || null, setItem: (key, value) => values.set(key, value) };
  const fetchApi = async (url, options) => {
    assert.equal(options.headers.Authorization, "Bearer catalog-token");
    if (url.includes("/v1/search?")) {
      return { ok: true, status: 200, json: async () => ({ artists: { items: [
        { id: "0V208yTQ5OGOUBZuszu6Fn", name: "Fhop Music", external_urls: { spotify: "https://open.spotify.com/artist/0V208yTQ5OGOUBZuszu6Fn" } }
      ] } }) };
    }
    assert.match(url, /\/v1\/artists\/0V208yTQ5OGOUBZuszu6Fn\/albums\?/);
    return { ok: true, status: 200, json: async () => ({
      items: [{ id: "r1", name: "De Volta", release_date: "2025-01-01", album_type: "album", images: [], external_urls: { spotify: "https://open.spotify.com/album/r1" } }],
      next: null
    }) };
  };
  const result = await catalog.resolveArtistCatalog("Fhop Music", "catalog-token", { storage, fetchApi });
  assert.equal(result.matched, true);
  assert.equal(result.albums.length, 1);
  assert.equal(result.albums[0].title, "De Volta");
  assert.doesNotMatch(values.get(catalog.ARTIST_CATALOG_CACHE_KEY), /catalog-token/);
});


test("resolve homônimo quando um candidato exato tem liderança material de audiência", () => {
  const result = catalog.matchArtist("Morada", [
    { name: "Morada", spotifyId: "br", followers: 300000, popularity: 60 },
    { name: "Morada", spotifyId: "other", followers: 5000, popularity: 25 }
  ]);
  assert.equal(result.matched, true);
  assert.equal(result.artist.spotifyId, "br");
  assert.equal(result.reason, "exact_name_audience_lead");
});

test("rejeita homônimos sem evidência suficiente", () => {
  const result = catalog.matchArtist("Morada", [
    { name: "Morada", spotifyId: "a", followers: 10000, popularity: 40 },
    { name: "Morada", spotifyId: "b", followers: 9000, popularity: 39 }
  ]);
  assert.equal(result.matched, false);
  assert.equal(result.confidence, "ambiguous");
});
