// Czysta funkcja dopasowania oferty do kryteriów. Używana w przeglądarce
// (przez <script src>) oraz w teście Node (przez require).
(function (root) {
  function roomsToInt(r) {
    if (r == null) return null;
    const n = parseInt(String(r), 10);
    return Number.isNaN(n) ? null : n;  // "10+" -> 10
  }

  function matchesCriteria(o, c) {
    c = c || {};
    const hasPriceLimit = c.price_max != null || c.ppm_max != null;
    if (hasPriceLimit && o.price == null) return false;        // inwestycja bez ceny
    if (c.price_max != null && !(o.price != null && o.price <= c.price_max)) return false;
    if (c.ppm_max != null && !(o.ppm != null && o.ppm <= c.ppm_max)) return false;
    if (c.rooms_min != null) {
      const r = roomsToInt(o.rooms);
      if (r == null || r < c.rooms_min) return false;
    }
    if (c.area_min != null && !(o.area != null && o.area >= c.area_min)) return false;
    if (c.area_max != null && !(o.area != null && o.area <= c.area_max)) return false;
    if (Array.isArray(c.cities) && c.cities.length && !c.cities.includes(o.miasto)) return false;
    if (c.owner_type === "private" && !o.private) return false;
    if (c.owner_type === "agency" && o.private) return false;
    return true;
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { matchesCriteria };
  else root.matchesCriteria = matchesCriteria;
})(typeof window !== "undefined" ? window : globalThis);
