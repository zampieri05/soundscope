"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const story = require("../frontend/js/story-mode.js");
const source = fs.readFileSync(require.resolve("../frontend/js/story-mode.js"), "utf8");

const artist = { name: "Arquivo", formed_year: "1996", country: "Brasil", biography: "Texto da fonte.", members: [{ name: "Ana", role: "voz", active: false }], albums: [
  { title: "Ano", year: "2002", primary_type: "Album", album_id: "t1" },
  { title: "Dia", year: "2001", first_release_date: "2001-05-03", primary_type: "Album", musicbrainz_release_group_id: "mb1", cover_url: "https://img.test/a.jpg" },
  { title: "Mês", first_release_date: "2001-02", primary_type: "EP" },
  { title: "Sem tipo", year: "2000" }, { title: "Sem data", primary_type: "Album" }
] };

test("normaliza apenas campos sustentados", () => { const value = story.normalizeArtist(artist); assert.equal(value.name, "Arquivo"); assert.equal(value.members[0].role, "voz"); assert.equal(value.albums.length, 5); });
test("preserva formed_year válido", () => assert.equal(story.normalizeArtist(artist).formedYear, "1996"));
test("omite formed_year ausente ou inválido", () => { assert.equal(story.normalizeArtist({ name: "A" }).formedYear, ""); assert.equal(story.normalizeArtist({ formed_year: "ano" }).formedYear, ""); });
test("ordena pela first_release_date antes do fallback year", () => assert.deepEqual(story.buildTimeline(artist).map((item) => item.title), ["Arquivo", "Dia", "Ano"]));
test("usa year quando first_release_date não existe", () => assert.equal(story.buildTimeline(artist).at(-1).date, "2002"));
test("mantém precisão de datas parciais", () => { assert.equal(story.formatDate("2001"), "2001"); assert.equal(story.formatDate("2001-02"), "FEV 2001"); assert.equal(story.formatDate("2001-02-03"), "03 FEV 2001"); });
test("não cria evento para release sem data", () => assert.equal(story.buildTimeline(artist, "all").some((item) => item.title === "Sem data"), false));
test("filtro padrão aceita somente primary_type Album", () => assert.deepEqual(story.filterAlbums(story.normalizeArtist(artist).albums).map((item) => item.title), ["Ano", "Dia"]));
test("ausência de primary_type só aparece em todos os registros", () => { const albums = story.normalizeArtist(artist).albums; assert.equal(story.filterAlbums(albums).some((item) => item.title === "Sem tipo"), false); assert.equal(story.filterAlbums(albums, "all").some((item) => item.title === "Sem tipo"), true); });
test("preserva IDs reais sem deduplicar registros distintos", () => { const albums = story.normalizeArtist(artist).albums; assert.equal(albums[0].albumId, "t1"); assert.equal(albums[1].musicbrainzReleaseGroupId, "mb1"); assert.equal(albums.length, 5); });
test("ausência de capa permanece vazia", () => assert.equal(story.normalizeArtist(artist).albums[0].coverUrl, ""));
test("ausência de Spotify URL permanece vazia", () => assert.equal(story.normalizeArtist(artist).albums[0].spotifyUrl, ""));
test("members não recebem datas históricas", () => assert.deepEqual(Object.keys(story.normalizeArtist(artist).members[0]).sort(), ["active", "name", "role"]));
test("active não é transformado em ano ou evento", () => assert.equal(story.buildTimeline(artist).some((item) => item.kind === "member"), false));
test("biography ausente fica vazia", () => assert.equal(story.normalizeArtist({}).biography, ""));
test("biography presente é preservada literalmente", () => assert.equal(story.normalizeArtist(artist).biography, "Texto da fonte."));
test("estado vazio produz timeline vazia", () => assert.deepEqual(story.buildTimeline({}), []));
test("estado controla abertura e fechamento", () => { const state = story.createState(); assert.equal(state.open().open, true); assert.equal(state.close().open, false); });
test("estado preserva reduced-motion", () => assert.equal(story.createState({ reducedMotion: true }).get().reducedMotion, true));
test("módulo implementa ESC e restauração de foco", () => { assert.match(source, /event\.key === "Escape"/); assert.match(source, /opener\?\.focus\?\.\(\)/); });
test("não possui cliente HTTP ou geração histórica", () => { assert.equal(/\bfetch\s*\(/.test(source), false); assert.equal(/XMLHttpRequest|axios|Wikipedia|Last\.fm|LLM|generative/i.test(source), false); });
