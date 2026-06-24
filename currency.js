// Czyste funkcje przeliczania i formatowania kwot. Używane w przeglądarce
// (przez <script src>) oraz w teście Node (przez require). Wzór: criteria.js.
(function (root) {
  function convertAmount(pricePln, rate) {
    if (pricePln == null || !rate) return null;
    return Math.round(pricePln / rate);
  }

  function formatMoney(n) {
    if (n == null) return null;
    // zwykła spacja co tysiąc — deterministycznie (niezależnie od locale Node)
    return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }

  if (typeof module !== "undefined" && module.exports)
    module.exports = { convertAmount, formatMoney };
  else { root.convertAmount = convertAmount; root.formatMoney = formatMoney; }
})(typeof window !== "undefined" ? window : globalThis);
