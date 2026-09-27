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
  let writeToken = '', renewing;
  async function authenticate(renew = false) {
    const bridge = window.webkit?.messageHandlers?.borgnetSession;
    if (renew && bridge) {
      session = await bridge.postMessage({});
      try { sessionStorage.setItem('borgnet-session', session); } catch {}
    }
    const response = await originalFetch('/api/session', {headers: {'X-BorgNet-Session': session}});
    if (response.status === 401 && !renew && bridge) return authenticate(true);
    if (!response.ok) {
      if (response.status === 401) locked();
      throw Error(response.status === 401 ? 'Workspace locked. Use your private launch link.' : 'BorgNet is temporarily unavailable. Try again.');
    }
    media = (await response.json()).media_token;
    if (renew) {
      const stateResponse = await originalFetch('/api/state', {headers: {'X-BorgNet-Session': session}});
      if (!stateResponse.ok) throw Error('Could not reconnect to BorgNet. Try again.');
      writeToken = (await stateResponse.json()).token;
      document.getElementById('sessionDialog')?.remove();
    }
  }
  // Handle initial rejection without an unhandled promise; a later request may retry.
  let ready = authenticate().then(() => true, () => false);
  function reconnect() {
    if (!renewing) renewing = authenticate(true).finally(() => { renewing = null; });
    return renewing;
  }
  window.fetch = async (input, options = {}) => {
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    if (url.origin === location.origin && url.pathname.startsWith('/api/')) {
      if (!await ready) {
        await reconnect(); ready = Promise.resolve(true);
      }
      const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
      headers.set('X-BorgNet-Session', session);
      if (writeToken && headers.has('X-BorgNet-Token')) headers.set('X-BorgNet-Token', writeToken);
      // Preserve a replayable Request; only retry a 401 rejected by the boundary.
      const retryInput = input instanceof Request ? input.clone() : input;
      let response = await originalFetch(input, {...options, headers});
      if (response.status === 401 && window.webkit?.messageHandlers?.borgnetSession) {
        await reconnect();
        headers.set('X-BorgNet-Session', session);
        if (writeToken && headers.has('X-BorgNet-Token')) headers.set('X-BorgNet-Token', writeToken);
        response = await originalFetch(retryInput, {...options, headers});
      }
      if (response.status === 401) locked();
      return response;
    }
    return originalFetch(input, options);
  };
  window.borgnetMediaURL = path => path + (path.includes('?') ? '&' : '?') + 'media_token=' + encodeURIComponent(media);
})();
