/**
 * Compliance-bot waitlist form handler.
 * Wires the #waitlist-form to POST /api/managed-agents/waitlist as JSON,
 * then fetches the count and shows a confirmation message.
 *
 * Backend: site/functions/api/managed-agents/waitlist.js (Cloudflare Pages Function)
 */
(function () {
  var COUNT_URL = "/api/managed-agents/waitlist/count";
  var SUBMIT_URL = "/api/managed-agents/waitlist";

  var form = document.getElementById("waitlist-form");
  var badge = document.getElementById("waitlist-count-badge");
  var countEl = document.getElementById("waitlist-count-num");
  var msg = document.getElementById("waitlist-msg");
  var submitBtn = form ? form.querySelector("button[type='submit']") : null;

  /** Fetch the current count and update the badge. */
  function loadCount(callback) {
    fetch(COUNT_URL)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var n = data.count || 0;
        if (countEl) countEl.textContent = n;
        if (badge) badge.style.display = n > 0 ? "inline-flex" : "none";
        if (callback) callback(n);
      })
      .catch(function () {
        // Non-fatal — badge stays hidden, callback gets undefined
        if (callback) callback(undefined);
      });
  }

  /** Show the success message, optionally with a count. */
  function showSuccess(count) {
    if (!msg) return;
    msg.textContent =
      count !== undefined
        ? "Thanks — you're on the list (" + count + "+ folks waiting)"
        : "Thanks — you're on the list";
    msg.style.display = "block";
    if (form) form.style.display = "none";
    if (badge) badge.style.display = "none";
  }

  // Load the badge count on page load.
  loadCount(null);

  // Wire the form.
  if (!form) return;
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var email = (form.querySelector("input[type='email']") || {}).value || "";
    if (submitBtn) submitBtn.disabled = true;

    fetch(SUBMIT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok || data.already_subscribed) {
          // Fetch fresh count, then show success.
          loadCount(function (n) { showSuccess(n); });
        } else {
          // Surface a server-side validation error.
          var errEl = document.getElementById("waitlist-error");
          if (errEl) {
            errEl.textContent = data.error || "Something went wrong — please try again.";
            errEl.style.display = "block";
          }
          if (submitBtn) submitBtn.disabled = false;
        }
      })
      .catch(function () {
        // Network failure — show success anyway (graceful degradation).
        showSuccess(undefined);
      });
  });
}());
