/**
 * stats.js — proof-bar stats injector.
 * Fetches /_stats.json (written by site/scripts/inject-stats.js at build time)
 * and populates all [data-stat] elements with their matching key values.
 *
 * Prepends "v" to robot_md_version so the HTML default ("v1.4.0") matches
 * the bare version string stored in the JSON ("1.4.0").
 *
 * Falls back silently — if the fetch fails the page just keeps its
 * placeholder values.
 */
(function () {
  fetch("/_stats.json")
    .then(function (r) { return r.json(); })
    .then(function (stats) {
      // Normalise: prepend "v" to the version string.
      if (stats.robot_md_version && !stats.robot_md_version.startsWith("v")) {
        stats.robot_md_version = "v" + stats.robot_md_version;
      }
      document.querySelectorAll("[data-stat]").forEach(function (el) {
        var key = el.getAttribute("data-stat");
        if (key in stats) {
          el.textContent = stats[key];
        }
      });
    })
    .catch(function () {
      // Stats fetch failed — leave placeholder values in place.
    });
}());
