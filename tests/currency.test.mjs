// tests/currency.test.mjs
import assert from "node:assert";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { convertAmount, formatMoney } = require("../currency.js");

// convertAmount: dzielenie i zaokrąglenie
assert.strictEqual(convertAmount(377560, 3.7756), 100000);
assert.strictEqual(convertAmount(520000, 4.25), 122353);   // 122352.9 -> 122353
assert.strictEqual(convertAmount(null, 4.25), null);        // inwestycja bez ceny
assert.strictEqual(convertAmount(100000, 0), null);         // brak kursu
assert.strictEqual(convertAmount(100000, undefined), null);

// formatMoney: odstępy co tysiąc, zwykła spacja
assert.strictEqual(formatMoney(999), "999");
assert.strictEqual(formatMoney(1000), "1 000");
assert.strictEqual(formatMoney(137600), "137 600");
assert.strictEqual(formatMoney(null), null);

console.log("currency.test.mjs: OK");
