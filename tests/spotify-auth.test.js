"use strict";
const test = require("node:test"); const assert = require("node:assert/strict"); const crypto = require("node:crypto").webcrypto;
const auth = require("../frontend/js/spotify-auth.js");
test("base64 URL-safe", () => assert.equal(auth.base64Url(Uint8Array.from([251, 255, 254])), "-__-"));
test("PKCE RFC vector", async () => assert.equal(await auth.createChallenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk", crypto), "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"));
test("state validation", () => { assert.equal(auth.statesMatch("abc", "abc"), true); assert.equal(auth.statesMatch("abc", "xyz"), false); assert.equal(auth.statesMatch(null, null), false); });
test("callback parsing", () => assert.deepEqual(auth.parseCallback("?code=c&state=s"), { code: "c", state: "s", error: null, errorDescription: null }));
test("expiration", () => { assert.equal(auth.isExpired({ accessToken: "x", expiresAt: 101 }, 100), false); assert.equal(auth.isExpired({ accessToken: "x", expiresAt: 100 }, 100), true); });
