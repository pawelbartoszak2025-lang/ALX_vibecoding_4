// tests/criteria.test.mjs
import assert from "node:assert";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { matchesCriteria } = require("../criteria.js");

const base = { price: 500000, ppm: 10000, area: 50, rooms: "2",
               miasto: "Poznań", private: false };

// brak kryteriów -> pasuje wszystko
assert.strictEqual(matchesCriteria(base, {}), true);
// cena maks.
assert.strictEqual(matchesCriteria(base, { price_max: 400000 }), false);
assert.strictEqual(matchesCriteria(base, { price_max: 600000 }), true);
// cena/m2 maks.
assert.strictEqual(matchesCriteria(base, { ppm_max: 9000 }), false);
// min pokoi (z obsługą "10+")
assert.strictEqual(matchesCriteria(base, { rooms_min: 3 }), false);
assert.strictEqual(matchesCriteria(base, { rooms_min: 2 }), true);
// powierzchnia
assert.strictEqual(matchesCriteria(base, { area_min: 60 }), false);
assert.strictEqual(matchesCriteria(base, { area_max: 40 }), false);
// miasto
assert.strictEqual(matchesCriteria(base, { cities: ["Kraków"] }), false);
assert.strictEqual(matchesCriteria(base, { cities: ["Poznań"] }), true);
// typ
assert.strictEqual(matchesCriteria(base, { owner_type: "private" }), false);
assert.strictEqual(matchesCriteria(base, { owner_type: "agency" }), true);
// inwestycja (brak ceny) odpada gdy ustawiono limit ceny
assert.strictEqual(matchesCriteria({ ...base, price: null }, { price_max: 600000 }), false);
console.log("criteria.test.mjs: OK");
