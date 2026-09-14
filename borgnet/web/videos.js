(() => {
  const q = s => document.querySelector(s);
  const make = (tag, text, cls) => { const node = document.createElement(tag); if (text) node.textContent = text; if (cls) node.className = cls; return node; };
  const panel = make('section', null, 'panel local-mode-panel');
  panel.id = 'videogenPanel';
  panel.innerHTML = `<div class="panel-heading"><div><p class="eyebrow">VIDEO WORKSPACE</p><h1>Video generation</h1><p>Generate clips with your connected provider APIs.</p></div></div>
    <form id="videoForm" class="local-form"><div class="local-controls">
    <label>Video model<select id="videoModel"></select></label>
    <label>Duration<select id="videoDuration"></select></label>
    <label>Format<select id="videoSize"></select></label></div>
    <p id="videoAccess" class="caption"></p>
    <label>Video prompt<textarea id="videoPrompt" rows="4" maxlength="4000" required placeholder="Describe the scene, motion, lighting and camera movement"></textarea></label>
    <button id="videoGenerate" class="primary" disabled>Generate video ↑</button>
    <button id="videoConnect" type="button" class="subtle">Connect provider API</button>
    <p class="caption">Uses your existing image/chat API key. Video usage is billed by the provider; CLI subscriptions do not supply API access. Clips use 720p. Closing this page does not cancel provider generation.</p>
    <p id="videoStatus" class="caption" role="status"></p></form>
    <h2>Video jobs and library</h2><div id="videoLibrary" class="local-gallery"></div>`;
  q('#historyPanel').parentElement.append(panel);
  const button = make('button', 'Video generation'); button.dataset.tab = 'videogen'; button.addEventListener('click', () => tab('videogen')); q('.tabs').append(button);
  let models = [], jobs = [], submitting = false, refreshing = false, timer;
  const cards = new Map();
  function saved() { try { return localStorage.getItem('borgnet-video-model') || ''; } catch { return ''; } }
  async function request(path, body) {
    const options = body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json', 'X-BorgNet-Token': (await (await fetch('/api/state')).json()).token}, body: JSON.stringify(body)};
    const response = await fetch('/api/videos' + path, options);
    const data = await response.json(); if (!response.ok) throw Error(data.error || data.detail || 'Video request failed'); return data;
  }
  function settings(reset = true) {
    const model = models.find(m => m.id === q('#videoModel').value);
    if (!model) { q('#videoGenerate').disabled = true; return; }
    if (reset) {
      q('#videoDuration').replaceChildren(...model.durations.map(n => new Option(n + ' seconds', n)));
      q('#videoSize').replaceChildren(...model.sizes.map(s => new Option(s, s)));
    }
    q('#videoAccess').textContent = model.ready ? 'API key found · model access and quota checked when generating.' : 'API key required · connect this provider to enable video generation.';
    q('#videoGenerate').disabled = submitting || !model.ready || jobs.some(j => ['pending','submitting'].includes(j.status));
  }
  function render() {
    const library = q('#videoLibrary');
    for (const job of jobs) {
      const signature = JSON.stringify(job);
      if (cards.get(job.id)?.signature === signature) continue;
      const card = make('article', null, 'local-image-card');
      card.append(make('p', job.prompt), make('p', `${job.model_id} · ${job.duration}s · ${job.status}${job.progress !== undefined ? ' · ' + job.progress + '%' : ''}`, 'caption'));
      if (job.error || job.warning) card.append(make('p', job.error || job.warning, 'caption'));
      if (job.status === 'completed' && /^\/api\/videos\/[a-f0-9]{32}\/content$/.test(job.url)) {
        const video = make('video'); video.controls = true; video.preload = 'metadata'; video.src = window.borgnetMediaURL(job.url); video.className = 'local-image'; card.append(video);
        const link = make('a', 'Download MP4'); link.href = window.borgnetMediaURL(job.url + '?download=true'); link.download = 'BorgNet-' + job.id + '.mp4'; card.append(link);
      }
      const previous = cards.get(job.id); if (previous) previous.node.replaceWith(card); else library.prepend(card);
      cards.set(job.id, {signature, node: card});
    }
    settings(false);
  }
  async function refresh() {
    if (refreshing) return; refreshing = true; clearTimeout(timer);
    try {
      const data = await request(''); jobs = data.jobs || [];
      for (const job of jobs) if (job.status === 'pending') Object.assign(job, await request('/' + job.id + '/refresh', {}));
      render();
    } catch (error) { q('#videoStatus').textContent = error.message; }
    finally { refreshing = false; if (jobs.some(j => j.status === 'pending')) timer = setTimeout(refresh, 10000); }
  }
  async function loadModels() {
    try {
      const previous = q('#videoModel').value || saved(); const data = await request('/models'); models = data.models || [];
      q('#videoModel').replaceChildren(...models.map(m => new Option(m.label + (m.ready ? '' : ' · API key required'), m.id)));
      q('#videoModel').value = models.some(m => m.id === previous) ? previous : (models.find(m => m.ready) || models[0])?.id || '';
      settings();
    } catch (error) { q('#videoStatus').textContent = error.message; }
  }
  q('#videoModel').addEventListener('change', () => { try { localStorage.setItem('borgnet-video-model', q('#videoModel').value); } catch {} settings(); });
  q('#videoConnect').addEventListener('click', () => q('#localImageConnect').click());
  q('#videoForm').addEventListener('submit', async event => {
    event.preventDefault(); if (q('#videoGenerate').disabled) return;
    submitting = true; settings(false); q('#videoStatus').textContent = 'Submitting video request…';
    try {
      await request('', {model_id: q('#videoModel').value, prompt: q('#videoPrompt').value, duration: Number(q('#videoDuration').value), size: q('#videoSize').value});
      q('#videoStatus').textContent = 'Video queued. Progress updates automatically; reloading resumes status checks.';
    } catch (error) { q('#videoStatus').textContent = error.message; }
    finally { submitting = false; await refresh(); settings(false); }
  });
  window.addEventListener('borgnet-tab-change', event => { if (event.detail === 'videogen') { loadModels(); refresh(); } });
  window.addEventListener('borgnet-connections-changed', loadModels);
  window.addEventListener('borgnet-image-credentials-changed', loadModels);
})();
