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
  assert.equal(discography.category({ primary_type: "Album" }), "Álbum");
  assert.equal(discography.category({ primary_type: "EP" }), "EP");
  assert.equal(discography.category({ primary_type: "Single" }), "Single");
  assert.equal(discography.category({ secondary_types: ["Live"] }), "Ao vivo");
  assert.equal(discography.category({ secondary_types: ["Compilation"] }), "Compilação");
  assert.equal(discography.category({ title: "Greatest Hits Live", cover_url: null, year: null }), "Outro");
});
