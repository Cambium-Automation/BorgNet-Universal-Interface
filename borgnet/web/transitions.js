/* Keep real panels mounted so forms, media and scroll positions survive navigation. */
(() => {
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  let track, panels, current, motion;
  function select(name) {
    if (!track) {
      panels = [...document.querySelectorAll('.tabs [data-tab]')]
        .map(button => document.getElementById(button.dataset.tab + 'Panel')).filter(Boolean);
      const viewport = document.createElement('div');
      viewport.className = 'panel-viewport';
      track = document.createElement('div');
      track.className = 'panel-track';
      panels[0].before(viewport);
      viewport.append(track);
      panels.forEach((panel, index) => {
        panel.style.left = `${index * 100}%`;
        track.append(panel);
      });
    }
    const target = panels.findIndex(panel => panel.id === name + 'Panel');
    if (target < 0) return;
    const first = current === undefined;
    const previous = current;
    const from = getComputedStyle(track).transform;
    if (motion) { motion.cancel(); motion = null; }
    current = target;
    panels.forEach((panel, index) => {
      panel.classList.toggle('active', index === target);
      panel.inert = index !== target;
      panel.setAttribute('aria-hidden', String(index !== target));
    });
    track.style.transform = `translateX(-${target * 100}%)`;
    track.classList.remove('sliding');
    if (first || reduced() || previous === target) return;
    track.classList.add('sliding');
    const animation = track.animate([
      {transform: from === 'none' ? 'translateX(0%)' : from},
      {transform: `translateX(-${target * 100}%)`},
    ], {duration: 330, easing: 'cubic-bezier(.22,.61,.36,1)'});
    motion = animation;
    animation.finished.then(() => {
      if (motion !== animation) return;
      track.classList.remove('sliding');
      motion = null;
    }).catch(() => {});
  }
  const dialogs = new WeakMap();
  const bound = new WeakSet();
  function fade(dialog, closing) {
    const prior = dialogs.get(dialog);
    const opacity = dialog.open ? getComputedStyle(dialog).opacity : '0';
    if (prior) prior.cancel();
    dialog.classList.add('configuration-dialog');
    dialog.classList.toggle('configuration-closing', closing);
    if (!closing && !dialog.open) dialog.showModal();
    if (!bound.has(dialog)) {
      bound.add(dialog);
      dialog.addEventListener('cancel', event => {
        event.preventDefault();
        fade(dialog, true);
      });
    }
    if (reduced()) {
      if (closing) dialog.close();
      return;
    }
    const animation = dialog.animate([{opacity}, {opacity: closing ? 0 : 1}],
      {duration: 500, easing: 'ease-in-out'});
    dialogs.set(dialog, animation);
    animation.finished.then(() => {
      if (dialogs.get(dialog) !== animation) return;
      dialogs.delete(dialog);
      if (closing) dialog.close();
    }).catch(() => {});
  }
  window.borgnetTransitions = {select, openDialog: dialog => fade(dialog, false),
    closeDialog: dialog => fade(dialog, true)};
})();
