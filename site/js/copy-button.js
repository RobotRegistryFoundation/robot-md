/* Copy install command to clipboard. Bound to every element with [data-copy].
 * Each button independently handles its own click; supports multiple buttons
 * per page (e.g., /agents/claude-code/ has several install snippets).
 * Kept in an external file so site CSP stays strict (script-src 'self',
 * no 'unsafe-inline').
 */
(function () {
  function bindCopy(btn) {
    btn.addEventListener('click', function () {
      var text = btn.getAttribute('data-copy');
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          var original = btn.textContent;
          btn.textContent = 'Copied!';
          btn.setAttribute('aria-label', 'Copied to clipboard');
          setTimeout(function () {
            btn.textContent = original;
            btn.setAttribute('aria-label', 'Copy install command');
          }, 1800);
        }).catch(function () {
          btn.textContent = 'Failed';
          setTimeout(function () { btn.textContent = 'Copy'; }, 1800);
        });
      } else {
        /* fallback for browsers without clipboard API */
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try {
          document.execCommand('copy');
          btn.textContent = 'Copied!';
          setTimeout(function () { btn.textContent = 'Copy'; }, 1800);
        } catch (e) {
          btn.textContent = 'Copy';
        }
        document.body.removeChild(ta);
      }
    });
  }
  var btns = document.querySelectorAll('[data-copy]');
  for (var i = 0; i < btns.length; i++) bindCopy(btns[i]);
}());
