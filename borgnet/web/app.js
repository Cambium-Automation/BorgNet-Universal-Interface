'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
let state = {connections: [], mcp_sources: [], context: [], history: []};
const discovered = new Map(), health = new Map(), attached = new Set();
let layoutPreferences={};
try{layoutPreferences=JSON.parse(localStorage.getItem('borgnet-layout')||'{}')||{};}catch{}
function saveLayout(){try{localStorage.setItem('borgnet-layout',JSON.stringify(layoutPreferences));}catch{}}
const collapsedModels=new Set(Array.isArray(layoutPreferences.collapsed)?layoutPreferences.collapsed:[]);
let conversation = '', busy = false, controller = null, fetchSource = '', mcpItems = [], pullConnection = '', toastTimer;
if (window.borgnetNativeAppearance || new URLSearchParams(location.search).get('native') === '1') document.body.classList.add('native');
window.addEventListener('borgnet-native-appearance', () => document.body.classList.add('native'));
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 6500); }
async function api(path, body) {
  const response = await fetch('/api' + path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json', 'X-BorgNet-Token': state.token}, body: JSON.stringify(body)});
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`BorgNet ${path} returned HTTP ${response.status} without a valid JSON response. Check the server log and installed dependencies.`); }
  if (!response.ok) throw new Error(data.error || (typeof data.detail === 'string' ? data.detail : 'Check the supplied fields and try again'));
  return data;
}
function action(fn) { return async event => { try { await fn(event); } catch (error) { toast(error.message); } }; }
function button(text, handler, className='subtle') { const b=el('button', className, text); b.type='button'; b.addEventListener('click', action(handler)); return b; }
function cleanConnection(c) { return Object.fromEntries(Object.entries(c).filter(([key]) => !['address','has_key'].includes(key))); }
function loopbackHost(host){return ['localhost','127.0.0.1','::1','[::1]'].includes(host);}
function loopbackEndpoint(url){try{return loopbackHost(new URL(url).hostname);}catch{return false;}}
function modelOptions(connection,model){const saved=model!==connection.model&&connection.model_options?.[model],options=saved?{...saved}:{...connection.options};if(connection.kind==='ollama'&&model!==connection.model&&!saved){delete options.think;delete options.num_gpu;}if(connection.kind==='openai'){if(connection.options?.show_local_reasoning===true)options.show_local_reasoning=true;else delete options.show_local_reasoning;}return options;}
function modelProfiles(connection){return connection.model?{...connection.model_options,[connection.model]:{...connection.options}}:{...connection.model_options};}
function selected() { return state.connections.filter(c => c.enabled && c.model); }
function tab(name) { if (!document.getElementById(name + 'Panel')) return; try { localStorage.setItem('borgnet-active-tab', name); } catch {} $$('.tabs button').forEach(b => { b.classList.toggle('active', b.dataset.tab === name); b.setAttribute('aria-pressed', String(b.dataset.tab === name)); }); window.borgnetTransitions.select(name); window.dispatchEvent(new CustomEvent('borgnet-tab-change', {detail:name})); }
let imageConnectionSignature='';
async function load() { state = await api('/state'); const signature=JSON.stringify(state.connections); if(signature!==imageConnectionSignature){imageConnectionSignature=signature;window.dispatchEvent(new Event('borgnet-connections-changed'));} discovered.clear();for(const [id,models] of Object.entries(state.model_catalog||{}))discovered.set(id,models); document.body.dataset.theme = state.theme; $('#theme').value = state.theme; renderConnections(); renderContext(); renderHistory(); }
function updateComposer() {
  const welcomeButton = $('#welcomeConnect'); if (welcomeButton) welcomeButton.textContent = state.connections.length ? 'Add another connection ↗' : 'Connect your first model ↗';
  const items = selected(); $('#selectionCount').textContent = `${items.length} model${items.length===1?'':'s'} selected`;
  $('#send').disabled = busy || !items.length; $('#stop').hidden = !busy;
  $('#status').textContent = busy ? 'Models are working…' : state.connections.length ? `${state.connections.length} connection${state.connections.length===1?'':'s'} in your workspace` : 'Your workspace, connected.';
  const previous = state.synthesis || $('#synthesis').value; $('#synthesis').replaceChildren(new Option('Auto · collaborate', ''));
  $('#synthesis').add(new Option('Chat with one model', '__single__'));
  const quickItems=items.filter(c=>c.kind==='openai'&&c.options?.quick_response);
  if(quickItems.length)$('#synthesis').add(new Option('Quick chat with one model', '__single_quick__'));
  $('#synthesis').add(new Option(state.routing?.backend==='jev'?'Jev routes · one model':'Auto route · one model', '__route__'));
  $('#synthesis').add(new Option('Independent answers only', '__independent__'));
  items.forEach(c => $('#synthesis').add(new Option(`${c.model} · ${c.address}`, c.id)));
  if (['__independent__','__route__','__single__'].includes(previous) || (previous==='__single_quick__'&&quickItems.length) || items.some(c => c.id === previous)) $('#synthesis').value = previous;
  $('#synthesis').disabled = busy || !items.length;
  const direct=$('#directModel'), previousDirect=direct.value||localStorage.getItem('borgnet-direct-model')||'';
  const directItems=$('#synthesis').value==='__single_quick__'?quickItems:items;
  direct.replaceChildren(...directItems.map(c=>new Option(`${c.model} · ${c.address}`,c.id)));
  if(directItems.some(c=>c.id===previousDirect))direct.value=previousDirect;
  direct.disabled=busy||!items.length;
  $('#directModelLabel').hidden=!['__single__','__single_quick__'].includes($('#synthesis').value);
  updateDebateControls();
}
function renderConnections() {
  $('#connections').replaceChildren();
  if (!state.connections.length) { const empty = el('p','caption','Nothing connected yet. Add a local endpoint, a remote computer, or a cloud API to get started.'); $('#connections').append(empty); }
  state.connections.forEach(c => {
    const card=el('article','connection'), top=el('div','section-head'), check=document.createElement('button');
    check.type='button';check.className='connection-toggle';check.setAttribute('role','switch');check.setAttribute('aria-checked',String(c.enabled));check.setAttribute('aria-label',`Enable ${c.address}`);check.disabled=busy;
    check.append(el('span','toggle-label',c.enabled?'On':'Off'),el('span','toggle-track'));
    check.addEventListener('click', action(async()=>{check.disabled=true;try{await api('/connections', {...cleanConnection(c),enabled:!c.enabled});await load();}finally{check.disabled=busy;}}));
    const modelName=c.model&&c.model!=='default'?c.model:c.kind==='cli'?`${c.cli_provider[0].toUpperCase()+c.cli_provider.slice(1)} · default`:c.kind;
    const details=el('div','connection-details');details.id=`connection-details-${c.id}`;details.hidden=collapsedModels.has(c.id);
    const expand=button('',()=>{details.hidden=!details.hidden;expand.setAttribute('aria-expanded',String(!details.hidden));if(details.hidden)collapsedModels.add(c.id);else collapsedModels.delete(c.id);layoutPreferences.collapsed=[...collapsedModels];saveLayout();},'connection-expand');
    expand.setAttribute('aria-expanded',String(!details.hidden));expand.setAttribute('aria-controls',details.id);expand.setAttribute('aria-label',`Details for ${modelName}`);expand.title=modelName;
    expand.append(el('span','connection-chevron','›'),el('span','connection-name',modelName));
    top.append(expand,check);card.append(top,details);
    details.append(el('span','kind',c.kind === 'openai' ? 'OpenAI compatible' : c.kind),el('div','address',c.address));
    const picker=el('select'); picker.setAttribute('aria-label',`Model for ${c.address}`); picker.disabled=busy;
    const models=[...new Set([...(discovered.get(c.id)||[]),...(c.model?[c.model]:[])])];
    picker.add(new Option(models.length ? 'Choose a model' : 'Discover or enter a model', ''));
    models.forEach(model=>picker.add(new Option(model,model))); picker.value=c.model;
    picker.addEventListener('change',action(async()=>{await api('/connections',{...cleanConnection(c),model:picker.value,options:modelOptions(c,picker.value),model_options:modelProfiles(c),capabilities:picker.value===c.model?c.capabilities:'',context_window:picker.value===c.model?c.context_window:null}); await load();})); details.append(picker);
    if(c.purpose) details.append(el('p','purpose',c.purpose));
    if(c.capabilities) details.append(el('p','purpose',`Declared capabilities: ${c.capabilities}`));
    if(c.context_window) details.append(el('p','purpose',`Configured context window: ${Number(c.context_window).toLocaleString()} tokens`));
    const h=health.get(c.id), footer=el('footer'),needsKey=c.kind==='gemini'&&!c.has_key; footer.append(el('span',`health${h?.error||needsKey?' error':''}`,needsKey?'API key needed · add in Edit connection':h?.text || 'Not checked'));
    const controls=el('div'); const refresh=button('↻',()=>discover(c.id),'icon'); refresh.title='Discover models'; refresh.setAttribute('aria-label',`Discover models for ${c.address}`); controls.append(refresh);
    if(c.kind==='ollama'){const pull=button('↓',()=>{pullConnection=c.id; $('#pullForm').reset(); $('#pullTarget').textContent=c.address; $('#pullDialog').showModal();},'icon');pull.title='Download model';pull.setAttribute('aria-label',`Download model on ${c.address}`);controls.append(pull);}
    const edit=button('⋯',()=>editConnection(c),'icon'); edit.title='Edit connection';edit.setAttribute('aria-label',`Edit ${c.address}`); controls.append(edit); footer.append(controls);details.append(footer);$('#connections').append(card);
  }); updateComposer();
}
async function discover(identity) {
  health.set(identity,{text:'Discovering…'});renderConnections();
  try { const result=await api(`/connections/${identity}/discover`,{});discovered.set(identity,result.models); health.set(identity,{text: result.models.length ? `${result.models.length} models · ${result.latency_ms} ms` : 'No models returned'});
    const c=state.connections.find(c=>c.id===identity); if(c?.kind==='cli')health.set(identity,{text:'CLI installed · sign-in checked when sending'}); if(c && !c.model && result.models.length){await api('/connections',{...cleanConnection(c),model:result.models[0]});await load();}
  } catch(error){health.set(identity,{text:error.message,error:true});toast(error.message);} renderConnections();
}
const providerPresets = [
  ['Ollama','ollama','http://localhost:11434',''],
  ['LM Studio','openai','http://localhost:1234/v1',''],
  ['llama.cpp / vLLM','openai','http://localhost:8080/v1',''],
  ['OpenAI · Responses','responses','https://api.openai.com/v1','OPENAI_API_KEY'],
  ['OpenAI · Chat Completions','openai','https://api.openai.com/v1','OPENAI_API_KEY'],
  ['Anthropic','anthropic','https://api.anthropic.com/v1','ANTHROPIC_API_KEY'],
  ['Google Gemini','gemini','https://generativelanguage.googleapis.com/v1beta','GEMINI_API_KEY'],
  ['Cohere','cohere','https://api.cohere.com','COHERE_API_KEY'],
  ['Groq','openai','https://api.groq.com/openai/v1','GROQ_API_KEY'],
  ['Pollinations · Pollen credits','openai','https://gen.pollinations.ai/v1','POLLINATIONS_API_KEY'],
  ['OpenRouter · free models','openai','https://openrouter.ai/api/v1','OPENROUTER_API_KEY'],
  ['DeepSeek','openai','https://api.deepseek.com','DEEPSEEK_API_KEY'],
  ['Together AI','openai','https://api.together.xyz/v1','TOGETHER_API_KEY'],
  ['Microsoft BitNet · local','openai','http://127.0.0.1:18081/v1',''],
  ...['codex','grok','gemini','copilot'].map(name=>[`${name} · installed CLI`,'cli','http://127.0.0.1','',name])
];
providerPresets.forEach((p,i)=>$('#connectionForm').elements.preset.add(new Option(p[0],String(i))));
$('#connectionForm').elements.preset.addEventListener('change',event=>{
  if(event.target.value==='')return;
  const form=$('#connectionForm'),p=providerPresets[Number(event.target.value)];
  if(form.elements.id.value)return;
  form.elements.kind.value=p[1];form.elements.url.value=p[2];form.elements.key_env.value=p[3];
  form.elements.model.value='';form.elements.api_key.value='';form.elements.options.value='{}';
  form.elements.use_ssh.checked=false;$('#sshFields').hidden=true;
  form.elements.use_proxy_ssh.checked=false;$('#proxyFields').hidden=true;
  form.elements.cli_provider.value=p[4]||'codex';form.elements.cli_agent.value='';
  if(p[1]==='cli')form.elements.model.value='default';
  if(p[2]==='https://openrouter.ai/api/v1'){form.elements.model.value='openrouter/free';form.elements.options.value=JSON.stringify({free_only:true});}
  updateConnectionFields();
});
function updateConnectionFields() {
  const form=$('#connectionForm'),cli=form.elements.kind.value==='cli';
  $('#openrouterImportBox').hidden=cli||form.elements.kind.value!=='openai'||form.elements.url.value.replace(/\/$/,'')!=='https://openrouter.ai/api/v1';
  $('#cliFields').hidden=!cli;$('#apiFields').hidden=cli;$('#sshToggle').hidden=cli;
  const proxyAllowed=!cli&&form.elements.url.value.startsWith('https://');
  $('#proxyToggle').hidden=!proxyAllowed;
  if(!proxyAllowed){form.elements.use_proxy_ssh.checked=false;$('#proxyFields').hidden=true;}
  $('#cliAgentField').hidden=!cli||form.elements.cli_provider.value!=='grok';
  form.elements.url.required=!cli;
  if(cli){form.elements.use_ssh.checked=false;$('#sshFields').hidden=true;form.elements.use_proxy_ssh.checked=false;$('#proxyFields').hidden=true;}
  $('#localReasoningOption').hidden=cli||form.elements.kind.value!=='openai'||form.elements.use_ssh.checked||!loopbackEndpoint(form.elements.url.value);
}
$('#connectionForm').elements.url.addEventListener('input',updateConnectionFields);
$('#connectionForm').elements.cli_provider.addEventListener('change',updateConnectionFields);
function editConnection(c) {
  const form=$('#connectionForm');form.reset();$('#presetLabel').hidden=Boolean(c);$('#connectionTitle').textContent=c?'Edit connection':'Connect a provider';
  for(const name of ['id','kind','url','purpose','capabilities','model','key_env']) form.elements[name].value=c?.[name] || (name==='kind'?'ollama':'');
  form.elements.context_window.value=c?.context_window||'';
  form.elements.use_ssh.checked=Boolean(c?.ssh);form.elements.options.value=JSON.stringify(c?.options||{},null,2);form.elements.timeout.value=c?.timeout||180;
  for(const [name,field] of [['ssh_host','host'],['ssh_user','user'],['ssh_port','port'],['remote_port','remote_port'],['identity_file','identity_file'],['remote_host','remote_host']]) if(c?.ssh) form.elements[name].value=c.ssh[field];
  form.elements.use_proxy_ssh.checked=Boolean(c?.proxy_ssh);
  for(const [name,field] of [['proxy_host','host'],['proxy_user','user'],['proxy_port','port'],['proxy_identity_file','identity_file']]) if(c?.proxy_ssh) form.elements[name].value=c.proxy_ssh[field];
  $('#proxyFields').hidden=!c?.proxy_ssh;
  $('#sshFields').hidden=!c?.ssh;$('#deleteConnection').hidden=!c;
  $('#keyHint').textContent=c?.has_key?'A key is configured. Leave blank to keep it. Entering a key switches from the environment variable to local key storage.':'Keys are stored separately with owner-only file permissions. Entering a key overrides the preset’s environment variable.';
  form.elements.cli_provider.value=c?.cli_provider||'codex';form.elements.cli_agent.value=c?.cli_agent||'';
  form.elements.show_local_reasoning.checked=c?.options?.show_local_reasoning===true;
  updateConnectionFields();$('#connectionDialog').showModal();
}
$('#connectionForm').addEventListener('submit',action(async event=>{
  event.preventDefault();const form=event.currentTarget, values=Object.fromEntries(new FormData(form));
  const old=state.connections.find(c=>c.id===values.id);
  const cli=values.kind==='cli';
  const options=JSON.parse(values.options||'{}');
  if(values.kind==='openai'&&!form.elements.use_ssh.checked&&loopbackEndpoint(values.url)&&form.elements.show_local_reasoning?.checked)options.show_local_reasoning=true;
  else delete options.show_local_reasoning;
  const body={cli_provider:values.cli_provider,cli_agent:cli&&values.cli_provider==='grok'?values.cli_agent:'',id:values.id,kind:values.kind,url:cli?(old?.url||'http://127.0.0.1'):values.url,purpose:values.purpose,capabilities:values.capabilities,context_window:values.context_window?Number(values.context_window):null,model:values.model,key_env:cli?'':values.key_env,enabled:old?.enabled??true,model_options:old?.model_options||{},api_key:values.api_key||null,
    ssh:form.elements.use_ssh.checked?{host:values.ssh_host,user:values.ssh_user,port:Number(values.ssh_port),remote_port:Number(values.remote_port),identity_file:values.identity_file,remote_host:values.remote_host||'127.0.0.1'}:null,
    proxy_ssh:form.elements.use_proxy_ssh.checked?{host:values.proxy_host,user:values.proxy_user,port:Number(values.proxy_port),identity_file:values.proxy_identity_file}:null,options,timeout:Number(values.timeout)};
  const result=await api('/connections',body);$('#connectionDialog').close();await load();await discover(result.id);
}));
$('#connectionForm').elements.use_ssh.addEventListener('change',event=>{if(event.target.checked){$('#connectionForm').elements.use_proxy_ssh.checked=false;$('#proxyFields').hidden=true;}$('#sshFields').hidden=!event.target.checked;updateConnectionFields();});
$('#connectionForm').elements.use_proxy_ssh.addEventListener('change',event=>{if(event.target.checked){$('#connectionForm').elements.use_ssh.checked=false;$('#sshFields').hidden=true;}$('#proxyFields').hidden=!event.target.checked;updateConnectionFields();});
$('#connectionForm').elements.kind.addEventListener('change',event=>{const form=$('#connectionForm'); if(!form.elements.id.value){const defaults={ollama:'http://localhost:11434',openai:'https://api.openai.com/v1',anthropic:'https://api.anthropic.com/v1',gemini:'https://generativelanguage.googleapis.com/v1beta',responses:'https://api.openai.com/v1',cohere:'https://api.cohere.com',cli:'http://127.0.0.1'};form.elements.preset.value='';form.elements.key_env.value='';form.elements.api_key.value='';form.elements.options.value='{}';form.elements.url.value=defaults[event.target.value];if(event.target.value==='cli')form.elements.model.value='default';}updateConnectionFields();});
$('#deleteConnection').addEventListener('click',action(async()=>{await api(`/connections/${$('#connectionForm').elements.id.value}/delete`,{});$('#connectionDialog').close();await load();}));
$('#pullForm').addEventListener('submit',action(async event=>{event.preventDefault();const model=new FormData(event.currentTarget).get('model');$('#pullDialog').close();health.set(pullConnection,{text:'Downloading…'});renderConnections();toast('Download started. Large models may take several minutes.');const id=pullConnection;try{await api(`/connections/${id}/pull`,{model});toast('Model downloaded.');await discover(id);}catch(error){health.set(id,{text:error.message,error:true});renderConnections();throw error;}}));
function renderContext() {
  $('#contextCount').textContent=state.context.length;$('#mcpSources').replaceChildren();$('#contextLibrary').replaceChildren();$('#attachments').replaceChildren();
  const available=new Set(state.context.map(c=>c.id));for(const id of attached)if(!available.has(id))attached.delete(id);
  if(!state.mcp_sources.length)$('#mcpSources').append(el('p','caption','Connect a Streamable HTTP server or an installed stdio server.'));
  state.mcp_sources.forEach(source=>{const card=el('article','mcp-card');card.append(el('h3','',source.name),el('p','caption',source.transport==='http'?source.url:source.command));const footer=el('footer');footer.append(button('Inspect & fetch',()=>inspectMcp(source)),button('Edit',()=>editMcp(source)),button('Remove',async()=>{await api(`/mcp/${source.id}/delete`,{});await load();}));card.append(footer);$('#mcpSources').append(card);});
  if(!state.context.length)$('#contextLibrary').append(el('p','caption','No context yet. Add text or fetch a resource from MCP.'));
  state.context.forEach(c=>{const card=el('article','context-card'),label=el('label','check'),check=document.createElement('input');check.type='checkbox';check.checked=attached.has(c.id);check.addEventListener('change',()=>{check.checked?attached.add(c.id):attached.delete(c.id);renderContext();});label.append(check,document.createTextNode(c.title));card.append(label,el('p','',c.text.slice(0,150)+(c.text.length>150?'…':'')));const footer=el('footer');footer.append(el('span','health',c.shared?'Shared via MCP':'Private'),button('Edit',()=>editContext(c)),button('Remove',async()=>{await api(`/context/${c.id}/delete`,{});attached.delete(c.id);await load();}));card.append(footer);$('#contextLibrary').append(card);if(attached.has(c.id))$('#attachments').append(el('span','attachment',c.title));});
}
function editContext(item){const form=$('#contextForm');form.reset();for(const key of ['id','title','text'])form.elements[key].value=item?.[key]||'';form.elements.shared.checked=Boolean(item?.shared);$('#contextDialog').showModal();}
$('#contextForm').addEventListener('submit',action(async event=>{event.preventDefault();const form=event.currentTarget;await api('/context',{...Object.fromEntries(new FormData(form)),shared:form.elements.shared.checked});$('#contextDialog').close();await load();}));
function editMcp(source){const form=$('#mcpForm');form.reset();for(const key of ['id','name','transport','url','command','key_env'])form.elements[key].value=source?.[key]||(key==='transport'?'http':'');form.elements.args.value=JSON.stringify(source?.args||[]);mcpTransport();$('#mcpDialog').showModal();}
function mcpTransport(){const stdio=$('#mcpForm').elements.transport.value==='stdio';$('#mcpStdio').hidden=!stdio;$('#mcpHttp').hidden=stdio;}
$('#mcpForm').elements.transport.addEventListener('change',mcpTransport);
$('#mcpForm').addEventListener('submit',action(async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));values.args=JSON.parse(values.args||'[]');values.api_key=values.api_key||null;await api('/mcp',values);$('#mcpDialog').close();await load();}));
async function inspectMcp(source){toast('Discovering MCP tools and resources…');const result=await api(`/mcp/${source.id}/inspect`,{});fetchSource=source.id;mcpItems=[...result.resources.map(r=>({...r,kind:'resource',target:r.uri})),...result.tools.map(t=>({...t,kind:'tool',target:t.name}))];if(!mcpItems.length)throw new Error('This server returned no tools or resources');$('#mcpItems').replaceChildren();mcpItems.forEach((item,index)=>$('#mcpItems').add(new Option(`${item.kind} · ${item.name||item.uri}`,String(index))));$('#fetchSource').textContent=source.name;showMcpItem();$('#fetchDialog').showModal();}
function showMcpItem(){const item=mcpItems[Number($('#mcpItems').value)];$('#toolDescription').textContent=item.description||'';$('#toolSchema').textContent=JSON.stringify(item.inputSchema||{},null,2);$('#argumentsLabel').hidden=item.kind!=='tool';$('#toolArguments').value='{}';}
$('#mcpItems').addEventListener('change',showMcpItem);
$('#fetchForm').addEventListener('submit',action(async event=>{event.preventDefault();const item=mcpItems[Number($('#mcpItems').value)], args=JSON.parse($('#toolArguments').value||'{}');if(Array.isArray(args)||args===null||typeof args!=='object')throw new Error('Tool arguments must be a JSON object');const submit=event.currentTarget.querySelector('[type=submit]')||event.currentTarget.querySelector('.primary');submit.disabled=true;try{await api(`/mcp/${fetchSource}/fetch`,{kind:item.kind,name:item.target,arguments:args});$('#fetchDialog').close();await load();toast('Context added. Select it to attach to your next message.');}finally{submit.disabled=false;}}));
function renderHistory(){$('#history').replaceChildren();if(!state.history.length)$('#history').append(el('p','caption','Your conversations will appear here.'));[...state.history].reverse().forEach(run=>{const b=button(run.prompt,()=>{if(busy)return toast('Wait for the current response before switching conversations.');conversation=run.conversation;$('#feed').replaceChildren();state.history.filter(r=>r.conversation===conversation).forEach(r=>{addPrompt(r.prompt);const group=conferenceBar(r.results);if(r.routing){group.label.textContent='Routed answer';group.root.prepend(el('p','caption',`Selected ${r.routing.model} via ${r.routing.selector}: ${r.routing.reason}`));}r.results.forEach(result=>{const card=resultCard(result,group);finishCard(card,result);modelStatus(group,result,result.status==='error'?'error':'complete');});});tab('conversation');},'history-item');b.append(el('small','',`${new Date(run.created_at*1000).toLocaleString()} · ${run.results.length} responses`));$('#history').append(b);});}
function addPrompt(text){$('#feed').append(el('div','user-message',text));}
function dispatchGroupItems(mode,ids,connections){
  if(mode==='__route__')return [];
  if(['__single__','__single_quick__'].includes(mode))return connections.filter(c=>c.id===ids[0]);
  return connections;
}
function addGroupModel(group,item,status='Thinking'){
  const id=item.connection||item.id;
  if(group.statuses.has(id))return;
  group.connections.set(id,item);
  const chip=el('span','model-status'),name=el('span','model-name',item.model),working=el('span','model-working',status);
  chip.title=item.address||item.url||'';
  chip.append(name,working);group.models.append(chip);
  group.statuses.set(id,{chip,status:working});
}
function conferenceBar(items){
  const root=el('details','conference'),summary=el('summary','conference-bar'),label=el('span','conference-label','Conference'),models=el('div','conference-models'),body=el('div','conference-body');
  const heading=el('div','conference-heading'),preview=el('div','conference-preview','Waiting for model output…');heading.append(label,models);summary.append(heading,preview);summary.title='Click to expand or collapse live model output';root.append(summary,body);$('#feed').append(root);
  const group={root,label,body,models,preview,statuses:new Map(),streams:new Map(),connections:new Map(),follow:true};
  body.addEventListener('scroll',()=>{group.follow=body.scrollHeight-body.scrollTop-body.clientHeight<40;});
  root.addEventListener('toggle',()=>{if(root.open&&group.follow)body.scrollTop=body.scrollHeight;});
  items.forEach(item=>addGroupModel(group,item));
  return group;
}
function showRoutingChoice(group,message,connections){
  const chosen=connections.find(c=>c.id===message.connection);
  if(chosen)addGroupModel(group,chosen,'Selected');
  group.label.textContent='Routed answer';
  group.preview.textContent=`${message.model} selected · awaiting answer…`;
  group.root.prepend(el('p','caption',`Selected ${message.model} via ${message.selector}: ${message.reason}`));
}
function streamPreview(group,message,reset=false){
  const key=message.connection+'-'+(message.phase||'response');
  const text=reset?'':((group.streams.get(key)||'')+(message.text||'')).slice(-2400);
  group.streams.set(key,text);
  group.preview.textContent=`${message.model} · ${message.phase||'response'}: ${text||(message.mode==='buffered'?'Waiting for completed message…':'Generating…')}`;
  if(!group.frame)group.frame=requestAnimationFrame(()=>{group.frame=null;group.preview.scrollTop=group.preview.scrollHeight;if(group.root.open&&group.follow)group.body.scrollTop=group.body.scrollHeight;});
}
function modelStatus(group,result,status){const item=group.statuses.get(result.connection);if(!item)return;item.chip.dataset.status=status;item.status.textContent=status==='thinking'?'Thinking':status==='error'?'Error':status==='stopped'?'Stopped':status==='not selected'?'Not selected':'';}
function localReasoningEligible(connection){
  if(!connection)return false;
  if(connection.kind==='ollama')return true;
  if(connection.kind!=='openai')return false;
  if(connection.ssh)return loopbackHost(connection.ssh.remote_host);
  if(connection.options?.show_local_reasoning!==true)return false;
  return loopbackEndpoint(connection.url);
}
function resultCard(result,group){
  const final=result.phase==='final'||result.synthesis;
  const card=el('article',`result${final?' synthesis':''}`),head=el('header'),name=el('div');
  name.append(el('strong','',`${final?'Unified answer · ':result.phase==='review'?'Peer review · ':result.phase==='proposal'?'Proposal '+result.proposal_id+' · ':result.phase?.startsWith('argument-')?'Argument R'+result.revision+' · ':result.phase?.startsWith('challenge-')?'Challenge R'+result.revision+' · ':result.phase==='implementation'?'Implementation · ':''}${result.model}`),el('small','',result.address));
  head.append(name,el('span','health','Thinking…'));
  card.append(head);
  const reasoning=el('section','model-reasoning');
  reasoning.append(el('h4','','Model-emitted reasoning'));
  const reasoningText=el('div','reasoning-text','Waiting for reasoning from this local model…');
  reasoning.append(reasoningText);
  reasoning.hidden=!localReasoningEligible(group.connections.get(result.connection));
  card.reasoningSection=reasoning;
  card.reasoningText=reasoningText;
  card.reasoningChars=0;
  card.append(reasoning,el('div','answer','Waiting for a response…'));
  card.conferenceGroup=group;
  group.body.append(card);
  return card;
}
function appendReasoning(card,text){
  if(typeof text!=='string'||!text)return;
  const limit=80000;
  if(card.reasoningChars===0)card.reasoningText.textContent='';
  card.reasoningSection.hidden=false;
  const remaining=limit-card.reasoningChars;
  if(remaining<=0)return;
  card.reasoningText.append(document.createTextNode(text.slice(0,remaining)));
  card.reasoningChars+=Math.min(text.length,remaining);
  if(text.length>remaining)card.reasoningText.append(document.createTextNode('\n[Further reasoning hidden at the display limit.]'));
  if(card.conferenceGroup?.root.open&&card.conferenceGroup.follow)card.conferenceGroup.body.scrollTop=card.conferenceGroup.body.scrollHeight;
}
function finishCard(card,result){
  if(card.conferenceGroup&&(result.phase==='final'||!card.conferenceGroup.streams.size))streamPreview(card.conferenceGroup,{...result,text:result.text||result.error||'Complete'});
  if((result.phase==='final'||result.synthesis)&&card.conferenceGroup)card.conferenceGroup.root.insertAdjacentElement('afterend',card);
  if(!card.reasoningSection.hidden&&!card.reasoningChars)card.reasoningText.textContent='This endpoint did not expose a reasoning stream for this response.';
  card.querySelector('.answer').textContent=result.text||result.error||'No response';
  card.querySelector('.answer').classList.toggle('error',result.status==='error');
  card.querySelector('.health').textContent=result.status==='error'?'Error':result.status==='partial'?'Partial participation':result.seconds!==undefined?`${result.seconds}s`:'Complete';
  if(result.tools?.length)card.querySelector('header').append(el('small','',`Tools: ${result.tools.map(t=>t.name+(t.ok?'':' (failed)')).join(', ')}`));
  if(result.text)card.querySelector('header').append(button('Copy',async()=>{await navigator.clipboard.writeText(result.text);toast('Copied response.');}));
}
function showDispatchFailure(group,cards,error,stopped){
  const message=stopped?'Stopped waiting. A remote provider may continue an already accepted request.':error.message||'Request failed';
  group.preview.textContent=message;
  for(const [id,item] of group.statuses)if(item.status.textContent==='Thinking')modelStatus(group,{connection:id},stopped?'stopped':'error');
  for(const card of cards.values()){
    const health=card.querySelector('.health'),answer=card.querySelector('.answer');
    if(health.textContent==='Complete'||health.textContent==='Error')continue;
    health.textContent=stopped?'Stopped':'Interrupted';
    if(!answer.textContent.trim())answer.textContent=stopped?'Request cancelled in this workspace.':message;
  }
  return message;
}
async function sendPrompt(event){event?.preventDefault();const prompt=$('#prompt').value.trim();if(!prompt||busy)return;if(!selected().length)return toast('Connect a provider and choose a model first.');if($('#feed .welcome'))$('#feed').replaceChildren();addPrompt(prompt);$('#prompt').value='';const synthesis=$('#synthesis').disabled?'':$('#synthesis').value, ids=['__single__','__single_quick__'].includes(synthesis)?[$('#directModel').value]:selected().map(c=>c.id);if(ids.some(id=>!selected().some(c=>c.id===id)))return toast('Choose an enabled model for direct chat.');busy=true;controller=new AbortController();renderConnections();tab('conversation');const cards=new Map(),group=conferenceBar(dispatchGroupItems(synthesis,ids,selected()));if(synthesis==='__route__'){group.label.textContent='Routing';group.preview.textContent=state.routing?.backend==='jev'?'Asking Jev to select one model…':'Asking the configured selector to choose one model…';}try{const response=await fetch('/api/dispatch',{method:'POST',headers:{'Content-Type':'application/json','X-BorgNet-Token':state.token},body:JSON.stringify({prompt,connections:ids,contexts:[...attached],conversation,quick_response:synthesis==='__single_quick__',auto_select:synthesis==='__route__',synthesize:['__independent__','__route__','__single__','__single_quick__'].includes(synthesis)?'':synthesis,collaborate:!['__independent__','__route__','__single__','__single_quick__'].includes(synthesis),collaboration_mode:$('#collaborationMode').value,debate_rounds:Number($('#debateRounds').value),implement:$('#collaborationMode').value==='debate'&&$('#debateImplement').getAttribute('aria-checked')==='true',executor:$('#debateExecutor').value}),signal:controller.signal});if(!response.ok){const error=await response.json();throw new Error(error.error||error.detail||'Request failed');}const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});let newline;while((newline=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,newline);buffer=buffer.slice(newline+1);if(!line)continue;const message=JSON.parse(line),key=message.connection+'-'+(message.phase||'response')+(message.synthesis?'-synthesis':'');if(message.type==='routing')showRoutingChoice(group,message,selected());if(message.type==='run')conversation=message.conversation;if(message.type==='phase')$('#status').textContent=message.text;if(message.type==='started'){modelStatus(group,message,'thinking');cards.set(key,resultCard(message,group));}if(message.type==='stream-reset'){streamPreview(group,message,true);const card=cards.get(key)||resultCard(message,group);cards.set(key,card);card.querySelector('.answer').textContent='';card.querySelector('.health').textContent=message.mode==='buffered-tools'?'Waiting · model may use tools':message.mode==='buffered'?'Waiting · CLI returns completed messages':'Streaming…';}if(message.type==='tool'){const card=cards.get(key)||resultCard(message,group);cards.set(key,card);card.querySelector('.health').textContent=`Tool ${message.ok?'used':'failed'} · ${message.name}`;}if(message.type==='reasoning'){const card=cards.get(key)||resultCard(message,group);cards.set(key,card);appendReasoning(card,message.text);}if(message.type==='delta'){streamPreview(group,message);const card=cards.get(key)||resultCard(message,group);cards.set(key,card);card.querySelector('.answer').append(document.createTextNode(message.text));card.querySelector('.health').textContent='Receiving…';}if(message.type==='result'){const card=cards.get(key)||resultCard(message,group);cards.set(key,card);finishCard(card,message);modelStatus(group,message,message.status==='error'?'error':'complete');}if(!group.root.open)$('#feed').scrollTop=$('#feed').scrollHeight;}if(done)break;}}catch(error){const stopped=error.name==='AbortError';toast(showDispatchFailure(group,cards,error,stopped));if(!stopped)$('#prompt').value=prompt;}finally{busy=false;controller=null;await load();}}
$('#composer').addEventListener('submit',action(sendPrompt));
$('#prompt').addEventListener('keydown',event=>{if(event.key!=='Enter'||event.shiftKey||event.isComposing)return;event.preventDefault();action(sendPrompt)(event);});
$('#stop').addEventListener('click',()=>controller?.abort());
$('#newChat').addEventListener('click',()=>{if(busy)return toast('Stop or finish the current request first.');conversation='';$('#feed').replaceChildren(el('p','caption','New conversation. Choose your models and send a message.'));tab('conversation');});
$$('[data-tab]').forEach(b=>b.addEventListener('click',()=>tab(b.dataset.tab)));
$$('[data-close]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
for(const id of ['addConnection','addAnother','welcomeConnect'])$('#'+id).addEventListener('click',()=>editConnection());
$('#addMcp').addEventListener('click',()=>editMcp());$('#addContext').addEventListener('click',()=>editContext());
$('#refresh').addEventListener('click',action(async()=>{await Promise.all(state.connections.map(c=>discover(c.id)));}));
$('#theme').addEventListener('change',action(async event=>{await api('/settings',{theme:event.target.value});await load();}));
load().catch(error=>toast(error.message));

$('#synthesis').addEventListener('change',action(async event=>{state.synthesis=event.target.value;await api('/settings',{synthesis:state.synthesis});}));

// Resize the connection column and message section without changing model settings.
function installSectionResize(handle,axis,key,measure,limits,apply,defaultSize){
  const sync=value=>{const [min,max]=limits();const size=Math.round(Math.max(min,Math.min(max,value)));apply(size);handle.setAttribute('aria-valuemin',String(min));handle.setAttribute('aria-valuemax',String(Math.round(max)));handle.setAttribute('aria-valuenow',String(size));return size;};
  const initial=Number(layoutPreferences[key]);if(Number.isFinite(initial)&&initial>0)sync(initial);else sync(measure());
  let drag=null;
  handle.addEventListener('pointerdown',event=>{if(event.button!==0)return;event.preventDefault();handle.focus();drag={position:axis==='x'?event.clientX:event.clientY,size:measure()};handle.setPointerCapture(event.pointerId);});
  handle.addEventListener('pointermove',event=>{if(!drag)return;const delta=(axis==='x'?event.clientX:event.clientY)-drag.position;sync(drag.size+(axis==='x'?delta:-delta));});
  const finish=()=>{if(!drag)return;drag=null;layoutPreferences[key]=measure();saveLayout();};
  handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',finish);handle.addEventListener('lostpointercapture',finish);
  handle.addEventListener('keydown',event=>{const keys=axis==='x'?['ArrowLeft','ArrowRight']:['ArrowDown','ArrowUp'];if(!keys.includes(event.key)&&!['Home','End'].includes(event.key))return;event.preventDefault();const [min,max]=limits();layoutPreferences[key]=sync(event.key==='Home'?min:event.key==='End'?max:measure()+(event.key===keys[0]?-20:20));saveLayout();});
  handle.addEventListener('dblclick',()=>{layoutPreferences[key]=sync(defaultSize);saveLayout();});
  window.addEventListener('resize',()=>sync(measure()));
}
const layoutNode=$('.layout'),sidebarNode=$('.sidebar'),composerNode=$('#composer');
installSectionResize($('#sidebarResize'),'x','sidebarWidth',()=>sidebarNode.getBoundingClientRect().width,()=>[220,Math.max(220,Math.min(580,layoutNode.clientWidth-360))],size=>layoutNode.style.setProperty('--sidebar-width',`${size}px`),280);
installSectionResize($('#composerResize'),'y','composerHeight',()=>composerNode.getBoundingClientRect().height,()=>[150,Math.max(150,Math.min(480,$('.workspace').clientHeight-220))],size=>composerNode.style.height=`${size}px`,180);

document.addEventListener('DOMContentLoaded',()=>{let name='conversation';try{name=localStorage.getItem('borgnet-active-tab')||name;}catch{}tab(name);});

function updateDebateControls(){
  const debate=$('#collaborationMode').value==='debate';
  $('#debateSettings').hidden=!debate;
  const independent=['__independent__','__route__','__single__','__single_quick__'].includes($('#synthesis').value);
  $('#collaborationMode').disabled=busy||independent;
  if(independent) {$('#collaborationMode').value='review';$('#debateSettings').hidden=true;}
  const previous=$('#debateExecutor').value;$('#debateExecutor').replaceChildren(new Option('Choose a CLI with Full access',''));
  for(const c of selected().filter(c=>c.kind==='cli'&&['codex','grok','copilot'].includes(c.cli_provider))) $('#debateExecutor').add(new Option(c.address,c.id));
  if([...$('#debateExecutor').options].some(o=>o.value===previous))$('#debateExecutor').value=previous;
  for(const id of ['debateRounds','debateImplement','debateExecutor'])$('#'+id).disabled=busy;
}
try{$('#collaborationMode').value=localStorage.getItem('borgnet-collaboration-mode')||'review';}catch{}
$('#collaborationMode').addEventListener('change',()=>{try{localStorage.setItem('borgnet-collaboration-mode',$('#collaborationMode').value);}catch{}updateDebateControls();});
$('#debateImplement').addEventListener('click',()=>{const on=$('#debateImplement').getAttribute('aria-checked')!=='true';$('#debateImplement').setAttribute('aria-checked',String(on));$('#debateImplement').textContent='Implement after agreement · '+(on?'On':'Off');});
$('#synthesis').addEventListener('change',updateComposer);
$('#directModel').addEventListener('change',event=>localStorage.setItem('borgnet-direct-model',event.target.value));

$('#routingSettings').addEventListener('click',()=>{
  const f=$('#routingForm'),cfg=state.routing||{};
  f.elements.backend.value=cfg.backend||'connection';f.elements.model.value=cfg.model||'jev-latest';f.elements.api_key.value='';
  f.elements.selector.replaceChildren(new Option('Choose a selector',''));
  for(const c of selected().filter(c=>['ollama','openai'].includes(c.kind)))f.elements.selector.add(new Option(`${c.model} · ${c.address}`,c.id));
  f.elements.selector.value=cfg.selector||'';$('#routingDialog').showModal();
});
$('#routingForm').addEventListener('submit',action(async event=>{
  event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));if(!data.api_key)delete data.api_key;
  await api('/routing',data);$('#routingForm').elements.api_key.value='';$('#routingDialog').close();await load();toast('Model selector saved. Choose the one-model routing mode to use it.');
}));
