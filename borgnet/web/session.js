/* Private per-origin browser credential. Never placed in cookies or sent to providers. */
(() => {
  const originalFetch = window.fetch.bind(window);
  let session = '';
  const fragment = new URLSearchParams(location.hash.slice(1));
  try {
    session = fragment.get('session') || sessionStorage.getItem('borgnet-session') || '';
    if (session) sessionStorage.setItem('borgnet-session', session);
  } catch { session = fragment.get('session') || ''; }
  if (fragment.has('session')) history.replaceState(null, '', location.pathname + location.search);
  let media = '';
  function locked() {
    if (document.getElementById('sessionDialog')) return;
    const dialog = document.createElement('dialog'); dialog.id = 'sessionDialog';
    const title = document.createElement('h2'); title.textContent = 'Unlock your local workspace';
    const note = document.createElement('p'); note.textContent = 'Open the private link printed by borgnet serve, or paste that link below. It stays on this computer.';
    const form = document.createElement('form'), input = document.createElement('input'), button = document.createElement('button');
    input.type = 'password'; input.placeholder = 'Private launch link'; input.autocomplete = 'off'; input.required = true; input.setAttribute('aria-label', 'Private launch link');
    button.textContent = 'Unlock'; form.append(input, button); dialog.append(title, note, form); document.body.append(dialog);
    form.addEventListener('submit', event => { event.preventDefault(); try { const url = new URL(input.value); const value = new URLSearchParams(url.hash.slice(1)).get('session'); if (url.origin !== location.origin || !value) throw Error(); sessionStorage.setItem('borgnet-session', value); location.reload(); } catch { note.textContent = 'Paste the private launch link for this workspace.'; } });
    dialog.addEventListener('cancel', event => event.preventDefault()); dialog.showModal();
  }
  const ready = originalFetch('/api/session', {headers: {'X-BorgNet-Session': session}}).then(async response => {
    if (!response.ok) { locked(); return false; }
    media = (await response.json()).media_token; return true;
  }).catch(() => { locked(); return false; });
  window.fetch = async (input, options = {}) => {
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    if (url.origin === location.origin && url.pathname.startsWith('/api/')) {
      if (!await ready) throw Error('Workspace locked. Use your private launch link.');
      const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
      headers.set('X-BorgNet-Session', session);
      const response = await originalFetch(input, {...options, headers});
      if (response.status === 401) locked();
      return response;
    }
    return originalFetch(input, options);
  };
  window.borgnetMediaURL = path => path + (path.includes('?') ? '&' : '?') + 'media_token=' + encodeURIComponent(media);
})();
