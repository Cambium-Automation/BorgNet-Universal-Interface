/* Permissions are persisted on the server, not merely represented in prompts. */
(() => {
  const dialog = document.createElement('dialog');
  dialog.id = 'permissionsDialog';
  dialog.setAttribute('aria-labelledby', 'permissionsTitle');
  dialog.innerHTML = `<div class="dialog-heading"><h2 id="permissionsTitle">Model permissions</h2><button type="button" id="permissionsClose" aria-label="Close">×</button></div>
    <label>Apply to<select id="permissionsScope"></select></label>
    <div id="permissionControls"></div>
    <p class="caption">These settings apply to text conversations, including every conference phase. API requests to model providers still require a connection. Image, video and shared-context tools keep their separate settings.</p>
    <p id="permissionsError" role="status"></p>
    <div class="dialog-footer"><button type="button" id="testBrowserAdapter">Test browser</button><button type="button" id="permissionsSave" class="primary">Save permissions</button></div>`;
  document.body.append(dialog);
  let config, adapters, scope = '', draft;
  const controls = dialog.querySelector('#permissionControls');
  const picker = dialog.querySelector('#permissionsScope');
  const error = dialog.querySelector('#permissionsError');
  function toggle(label, value, disabled, change, note='') {
    const row = el('div', 'permission-row');
    const text = el('div'); text.append(el('strong', '', label));
    if (note) text.append(el('p', 'caption', note));
    const control = button(value ? 'On' : 'Off', () => change(!value), 'permission-switch');
    control.setAttribute('role', 'switch'); control.setAttribute('aria-checked', String(value));
    control.setAttribute('aria-label', label); control.disabled = disabled;
    row.append(text, control); controls.append(row);
  }
  function render() {
    controls.replaceChildren(); error.textContent = '';
    const connection = state.connections.find(c => c.id === scope);
    const supported = !connection || connection.kind === 'cli' && ['codex','grok','copilot'].includes(connection.cli_provider);
    const inherits = scope && !config.overrides[scope];
    if (scope) toggle('Use shared permissions', !!inherits, false, on => {
      if (on) delete config.overrides[scope]; else config.overrides[scope] = {...config.defaults}; render();
    });
    draft = scope ? config.overrides[scope] || config.defaults : config.defaults;
    const locked = !!inherits || !supported;
    if (!supported) controls.append(el('p', 'caption', 'This API or Gemini adapter currently supports supplied text only. Host tools are unavailable; inherited access grants have no effect.'));
    const label = el('label', '', 'Working folder'); const input = el('input');
    input.value = draft.workspace; input.disabled = locked;
    input.addEventListener('input', () => { draft.workspace = input.value; }); label.append(input); controls.append(label);
    toggle('Network / web access', draft.network || draft.full_access, locked || draft.full_access || connection?.cli_provider === 'copilot', on => {draft.network=on;render();}, 'Codex and Grok: built-in web search/fetch. Copilot network access requires full access.');
    const grokReady=connection?.cli_provider!=='grok'||adapters.grok_registered;
    toggle('Browser control', !!draft.browser, locked||!draft.full_access||!adapters.browser.ready||!grokReady, on=>{draft.browser=on;render();}, 'Isolated Chromium via MCP. Requires Full CLI access. Pages and screenshots are sent to the selected model. '+(!adapters.browser.ready?'Run borgnet adapters install.':''));
    toggle('Computer use', !!draft.computer, locked||!draft.full_access||!adapters.computer.supported||!grokReady, on=>{draft.computer=on;render();}, 'Controls your current desktop; screenshots can expose private information. Requires Full CLI access. '+adapters.computer.message+(adapters.computer.ready?' OS permissions ready.':' OS permission/setup still required.'));
    if(!grokReady)controls.append(el('p','caption','Grok: run borgnet adapters install to register the local connector.'));
    toggle('Full CLI access', draft.full_access, locked, on => {draft.full_access=on;if(!on){draft.browser=false;draft.computer=false;}render();}, 'Allows file changes and command execution as your user, including network access and paths outside the working folder. Commands run without individual approvals. Applies to supported CLIs only.');
  }
  picker.addEventListener('change', () => {scope=picker.value;render();});
  document.querySelector('#permissionsSettings').addEventListener('click', action(async () => {
    [config,adapters] = await Promise.all([api('/permissions'),api('/adapters')]); scope='';
    picker.replaceChildren(new Option('All models · shared defaults', ''));
    for (const c of state.connections) picker.add(new Option(`${c.address} · ${c.model || c.id}`, c.id));
    render(); window.borgnetTransitions.openDialog(dialog);
  }));
  dialog.querySelector('#permissionsClose').onclick = () => window.borgnetTransitions.closeDialog(dialog);
  dialog.querySelector('#testBrowserAdapter').onclick = async () => {
    const control=dialog.querySelector('#testBrowserAdapter');control.disabled=true;error.textContent='Checking isolated Chromium…';
    try{const result=await api('/adapters/browser-test',{});error.textContent=result.message;}catch(e){error.textContent=e.message;}finally{control.disabled=false;}
  };
  dialog.querySelector('#permissionsSave').onclick = async () => {
    const save = dialog.querySelector('#permissionsSave'); save.disabled=true;
    try {await api('/permissions', config); window.borgnetTransitions.closeDialog(dialog); toast('Permissions saved for future requests.');}
    catch (e) {error.textContent=e.message;} finally {save.disabled=false;}
  };
})();
