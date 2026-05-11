(() => {
  const dropdowns = document.querySelectorAll('[data-nav-dropdown]');
  if (!dropdowns.length) return;

  function closeAll(except) {
    dropdowns.forEach((d) => {
      if (d === except) return;
      const trigger = d.querySelector('.nav-dropdown-trigger');
      const menu = d.querySelector('.nav-dropdown-menu');
      trigger.setAttribute('aria-expanded', 'false');
      menu.hidden = true;
    });
  }

  dropdowns.forEach((d) => {
    const trigger = d.querySelector('.nav-dropdown-trigger');
    const menu = d.querySelector('.nav-dropdown-menu');

    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = trigger.getAttribute('aria-expanded') === 'true';
      closeAll(d);
      trigger.setAttribute('aria-expanded', String(!open));
      menu.hidden = open;
    });

    menu.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        trigger.setAttribute('aria-expanded', 'false');
        menu.hidden = true;
        trigger.focus();
      }
    });
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('[data-nav-dropdown]')) closeAll(null);
  });
})();
