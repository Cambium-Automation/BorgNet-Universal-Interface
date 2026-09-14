/* Parse pasted examples as text only. Never execute code or follow their URLs. */
function parseOpenRouterExample(source) {
  if (typeof source !== 'string' || source.length > 32000) throw Error('Paste an example under 32,000 characters.');
  const keys = [...new Set(source.match(/\bsk-or-v1-[A-Za-z0-9_-]+\b/g) || [])];
  if (keys.length !== 1 || keys[0].length < 24 || /your|example|placeholder/i.test(keys[0])) {
    throw Error(keys.length > 1 ? 'Multiple keys found. Paste an example with one key.' : 'No complete OpenRouter API key found. Replace the placeholder in the example or use the API key field.');
  }
  const models = [...source.matchAll(/["']model["']\s*:\s*["']([^"'\r\n]{1,300})["']/g)].map(match => match[1]);
  return {key: keys[0], model: models[0] || ''};
}
(() => {
  const form = document.getElementById('connectionForm');
  const box = document.getElementById('openrouterExample');
  const status = document.getElementById('openrouterImportStatus');
  document.getElementById('openrouterImport').addEventListener('click', () => {
    try {
      if (form.elements.kind.value !== 'openai' || form.elements.url.value.replace(/\/$/, '') !== 'https://openrouter.ai/api/v1') {
        throw Error('Select the OpenRouter connection preset first.');
      }
      const parsed = parseOpenRouterExample(box.value);
      const options = JSON.parse(form.elements.options.value || '{}');
      if (!options || typeof options !== 'object' || Array.isArray(options)) throw Error('Provider options must be a JSON object.');
      form.elements.api_key.value = parsed.key;
      form.elements.key_env.value = '';
      const paid = parsed.model && parsed.model !== 'openrouter/free' && !parsed.model.endsWith(':free');
      if (parsed.model && !(paid && options.free_only)) form.elements.model.value = parsed.model;
      box.value = '';
      status.textContent = paid && options.free_only
        ? 'Key imported. The example uses a paid model; your free-model selection was kept. Review the settings, then save.'
        : 'Key and available model imported. Review the settings, then save the connection.';
    } catch (error) { status.textContent = error.message; }
  });
  function clear() { box.value = ''; status.textContent = ''; }
  form.addEventListener('reset', clear);
  form.elements.preset.addEventListener('change', clear);
  document.getElementById('connectionDialog').addEventListener('close', () => {
    clear(); form.elements.api_key.value = '';
  });
})();
