"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const discography = require("../frontend/js/discography.js");

test("up to 20 items fit in the initial presentation page", () => {
  assert.equal(discography.page(Array.from({ length: 20 }), 0).length, 20);
});
test("more than 20 items remain available to Carregar mais in blocks", () => {
  const items = Array.from({ length: 45 }, (_, id) => id);
  assert.deepEqual(discography.page(items, 0), items.slice(0, 20));
  assert.deepEqual(discography.page(items, 20), items.slice(20, 40));
  assert.deepEqual(discography.page(items, 40), items.slice(40));
});
test("categories rely only on real primary and secondary metadata", () => {
  assert.equal(discography.category({ primary_type: "Album" }), "Álbuns");
  assert.equal(discography.category({ primary_type: "EP" }), "Singles & EPs");
  assert.equal(discography.category({ primary_type: "Single" }), "Singles & EPs");
  assert.equal(discography.category({ secondary_types: ["Live"] }), "Ao Vivo");
  assert.equal(discography.category({ secondary_types: ["Compilation"] }), "Coletâneas");
  assert.equal(discography.category({ secondary_types: ["Demo"] }), "Demos");
  assert.equal(discography.category({ title: "Greatest Hits Live", cover_url: null, year: null }), "Outros");
});
test("secondary metadata has deterministic precedence", () => {
  assert.equal(discography.category({ primary_type: "Album", secondary_types: ["Compilation", "Live", "Demo"] }), "Demos");
  assert.equal(discography.category({ primary_type: "EP", secondary_types: ["Live"] }), "Ao Vivo");
});
test("groups contain each release once, omit no data, and choose a useful default", () => {
  const releases = [{ primary_type: "Single" }, { primary_type: "Album" }, {}];
  const groups = discography.group(releases);
  assert.equal(Object.values(groups).flat().length, releases.length);
  assert.equal(new Set(Object.values(groups).flat()).size, releases.length);
  assert.equal(discography.defaultCategory(groups), "Álbuns");
  assert.equal(discography.defaultCategory(discography.group([{ primary_type: "EP" }])), "Singles & EPs");
  assert.equal(discography.defaultCategory(discography.group([])), null);
  assert.deepEqual(Object.entries(groups).filter(([, items]) => items.length).map(([name]) => name), ["Álbuns", "Singles & EPs", "Outros"]);
});
