"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const share = require("../frontend/js/orbit-share.js");
const source = fs.readFileSync(require.resolve("../frontend/js/orbit-share.js"), "utf8");

const artists = Array.from({ length: 8 }, (_, index) => ({ name: `Artista ${index + 1}`, image: `https://images.test/${index}.jpg`, affinity: 99, minutes: 500 }));
function context() {
  return { fillStyle: "", strokeStyle: "", lineWidth: 0, font: "", textAlign: "", textBaseline: "", save() {}, restore() {}, beginPath() {}, arc() {}, fill() {}, stroke() {}, moveTo() {}, lineTo() {}, clip() {}, drawImage() {}, fillRect() {}, fillText() {}, measureText(value) { return { width: String(value).length * 10 }; }, createRadialGradient() { return { addColorStop() {} }; } };
}
function canvas() { const ctx = context(); return { width: 0, height: 0, getContext: () => ctx, toBlob: (callback, type) => callback(new Blob(["png"], { type })) }; }
class FailingImage { set src(_) { this.onerror(); } }

test("seleciona no máximo cinco artistas e preserva a ordem", () => {
  const result = share.selectArtists(artists);
  assert.equal(result.length, 5); assert.deepEqual(result.map((item) => item.name), artists.slice(0, 5).map((item) => item.name));
});
test("mantém somente nome, imagem e posição, sem métricas inventadas", () => {
  const [artist] = share.selectArtists(artists); assert.deepEqual(Object.keys(artist).sort(), ["image", "name", "rank"]); assert.equal("affinity" in artist, false); assert.equal("minutes" in artist, false);
});
test("imagem inválida ou com falha usa fallback sem impedir renderização", async () => {
  const target = canvas(); const result = await share.render(target, [{ name: "Ana Silva", image: "https://images.test/a.jpg" }], { ImageClass: FailingImage });
  assert.equal(result.imageFallbacks, 1); assert.equal(share.initials("Ana Silva"), "AS");
});
test("gera composição Canvas exatamente em 1080 × 1920", async () => {
  const target = canvas(); await share.render(target, artists, { ImageClass: FailingImage }); assert.equal(target.width, 1080); assert.equal(target.height, 1920);
});
test("converte Canvas em Blob PNG", async () => { const blob = await share.canvasToBlob(canvas()); assert.equal(blob.type, "image/png"); });
test("cria arquivo com o nome oficial", () => {
  class FakeFile { constructor(parts, name, options) { this.parts = parts; this.name = name; this.type = options.type; } }
  const file = share.createFile(new Blob(["x"]), FakeFile); assert.equal(file.name, "soundscope-minha-orbita.png"); assert.equal(file.type, "image/png");
});
test("usa Web Share quando share e canShare aceitam arquivos", async () => {
  let shared = 0; let downloads = 0; const navigator = { canShare: ({ files }) => files[0].name === share.FILE_NAME, share: async () => { shared += 1; } };
  const result = await share.shareOrDownload(new Blob(["x"]), navigator, { FileClass: class { constructor(_, name) { this.name = name; } }, download: () => { downloads += 1; } });
  assert.equal(result, "shared"); assert.equal(shared, 1); assert.equal(downloads, 0);
});
test("faz download quando Web Share não está disponível", async () => {
  let downloads = 0; const result = await share.shareOrDownload(new Blob(["x"]), {}, { download: () => { downloads += 1; } }); assert.equal(result, "downloaded"); assert.equal(downloads, 1);
});
test("faz download quando canShare retorna false", async () => {
  let shared = 0; let downloads = 0; const navigator = { canShare: () => false, share: async () => { shared += 1; } }; const result = await share.shareOrDownload(new Blob(["x"]), navigator, { download: () => { downloads += 1; } }); assert.equal(result, "downloaded"); assert.equal(shared, 0); assert.equal(downloads, 1);
});
test("módulo implementa abertura, fechamento, Escape e restauração de foco", () => {
  assert.match(source, /function open\(/); assert.match(source, /function close\(/); assert.match(source, /event\.key === "Escape"/); assert.match(source, /opener\?\.focus\?\.\(\)/);
});
test("módulo Share não possui cliente Spotify nem nova chamada HTTP", () => {
  assert.equal(/\bfetch\s*\(/.test(source), false); assert.equal(/getTopArtists|api\.spotify\.com|accessToken/.test(source), false);
});
