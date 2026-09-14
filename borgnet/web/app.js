'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
let state = {connections: [], mcp_sources: [], context: [], history: []};
const discovered = new Map(), health = new Map(), attached = new Set();
let conversation = '', busy = false, controller = null, fetchSource = '', mcpItems = [], pullConnection = '', toastTimer;
if (window.borgnetNativeAppearance || new URLSearchParams(location.search).get('native') === '1') document.body.classList.add('native');
window.addEventListener('borgnet-native-appearance', () => document.body.classList.add('native'));
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 6500); }
async function api(path, body) {
  const response = await fetch('/api' + path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json', 'X-BorgNet-Token': state.token}, body: JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || (typeof data.detail === 'string' ? data.detail : 'Check the supplied fields and try again'));
  return data;
}
function action(fn) { return async event => { try { await fn(event); } catch (error) { toast(error.message); } }; }
function button(text, handler, className='subtle') { const b=el('button', className, text); b.type='button'; b.addEventListener('click', action(handler)); return b; }
function cleanConnection(c) { return Object.fromEntries(Object.entries(c).filter(([key]) => !['address','has_key'].includes(key))); }
function selected() { return state.connections.filter(c => c.enabled && c.model); }
function tab(name) { $$('.tabs button').forEach(b => { b.classList.toggle('active', b.dataset.tab === name); b.setAttribute('aria-pressed', String(b.dataset.tab === name)); }); $$('.panel').forEach(p => p.classList.toggle('active', p.id === name + 'Panel')); }
async function load() { state = await api('/state'); document.body.dataset.theme = state.theme; $('#theme').value = state.theme; renderConnections(); renderContext(); renderHistory(); }
function updateComposer() {
  const welcomeButton = $('#welcomeConnect'); if (welcomeButton) welcomeButton.textContent = state.connections.length ? 'Add another connection ↗' : 'Connect your first model ↗';
  const items = selected(); $('#selectionCount').textContent = `${items.length} model${items.length===1?'':'s'} selected`;
  $('#send').disabled = busy || !items.length; $('#stop').hidden = !busy;
  $('#status').textContent = busy ? 'Models are working…' : state.connections.length ? `${state.connections.length} connection${state.connections.length===1?'':'s'} in your workspace` : 'Your workspace, connected.';
  const previous = state.synthesis || $('#synthesis').value; $('#synthesis').replaceChildren(new Option('Auto · collaborate', ''));
  $('#synthesis').add(new Option('Independent answers only', '__independent__'));
  items.forEach(c => $('#synthesis').add(new Option(`${c.model} · ${c.address}`, c.id)));
  if (previous === '__independent__' || items.some(c => c.id === previous)) $('#synthesis').value = previous;
  $('#synthesis').disabled = busy || items.length < 2;
}
function renderConnections() {
  $('#connections').replaceChildren();
  if (!state.connections.length) { const empty = el('p','caption','Nothing connected yet. Add a local endpoint, a remote computer, or a cloud API to get started.'); $('#connections').append(empty); }
  state.connections.forEach(c => {
    const card=el('article','connection'), top=el('div','section-head'), check=document.createElement('input'); check.type='checkbox'; check.checked=c.enabled; check.setAttribute('aria-label',`Include ${c.address}`); check.disabled=busy;
    check.addEventListener('change', action(async()=>{ await api('/connections', {...cleanConnection(c),enabled:check.checked}); await load(); }));
    top.append(el('span','kind',c.kind === 'openai' ? 'OpenAI compatible' : c.kind),check);
    card.append(top,el('div','address',c.address));
    const picker=el('select'); picker.setAttribute('aria-label',`Model for ${c.address}`); picker.disabled=busy;
    const models=[...new Set([...(discovered.get(c.id)||[]),...(c.model?[c.model]:[])])];
    picker.add(new Option(models.length ? 'Choose a model' : 'Discover or enter a model', ''));
    models.forEach(model=>picker.add(new Option(model,model))); picker.value=c.model;
    picker.addEventListener('change',action(async()=>{await api('/connections',{...cleanConnection(c),model:picker.value}); await load();})); card.append(picker);
    if(c.purpose) card.append(el('p','purpose',c.purpose));
    const h=health.get(c.id), footer=el('footer'); footer.append(el('span',`health${h?.error?' error':''}`,h?.text || 'Not checked'));
    const controls=el('div'); const refresh=button('↻',()=>discover(c.id),'icon'); refresh.title='Discover models'; refresh.setAttribute('aria-label',`Discover models for ${c.address}`); controls.append(refresh);
    if(c.kind==='ollama'){const pull=button('↓',()=>{pullConnection=c.id; $('#pullForm').reset(); $('#pullTarget').textContent=c.address; $('#pullDialog').showModal();},'icon');pull.title='Download model';pull.setAttribute('aria-label',`Download model on ${c.address}`);controls.append(pull);}
    const edit=button('⋯',()=>editConnection(c),'icon'); edit.title='Edit connection';edit.setAttribute('aria-label',`Edit ${c.address}`); controls.append(edit); footer.append(controls);card.append(footer);$('#connections').append(card);
  }); updateComposer();
}
async function discover(identity) {
  health.set(identity,{text:'Discovering…'});renderConnections();
  try { const result=await api(`/connections/${identity}/discover`,{});discovered.set(identity,result.models); health.set(identity,{text: result.models.length ? `${result.models.length} models · ${result.latency_ms} ms` : 'No models returned'});
    const c=state.connections.find(c=>c.id===identity); if(c && !c.model && result.models.length){await api('/connections',{...cleanConnection(c),model:result.models[0]});await load();}
  } catch(error){health.set(identity,{text:error.message,error:true});toast(error.message);} renderConnections();
}
function editConnection(c) {
  const form=$('#connectionForm');form.reset();$('#connectionTitle').textContent=c?'Edit connection':'Connect a provider';
  for(const name of ['id','kind','url','purpose','model','key_env']) form.elements[name].value=c?.[name] || (name==='kind'?'ollama':'');
  form.elements.use_ssh.checked=Boolean(c?.ssh);form.elements.options.value=JSON.stringify(c?.options||{},null,2);form.elements.timeout.value=c?.timeout||180;
  for(const [name,field] of [['ssh_host','host'],['ssh_user','user'],['ssh_port','port'],['remote_port','remote_port'],['identity_file','identity_file'],['remote_host','remote_host']]) if(c?.ssh) form.elements[name].value=c.ssh[field];
  $('#sshFields').hidden=!c?.ssh;$('#deleteConnection').hidden=!c;
  $('#keyHint').textContent=c?.has_key?'A key is configured. Leave blank to keep it, or enter a replacement. An environment variable takes precedence.':'Keys are stored separately with owner-only file permissions.';
  $('#connectionDialog').showModal();
}
$('#connectionForm').addEventListener('submit',action(async event=>{
  event.preventDefault();const form=event.currentTarget, values=Object.fromEntries(new FormData(form));
  const old=state.connections.find(c=>c.id===values.id);
  const body={id:values.id,kind:values.kind,url:values.url,purpose:values.purpose,model:values.model,key_env:values.key_env,enabled:old?.enabled??true,api_key:values.api_key||null,
    ssh:form.elements.use_ssh.checked?{host:values.ssh_host,user:values.ssh_user,port:Number(values.ssh_port),remote_port:Number(values.remote_port),identity_file:values.identity_file,remote_host:values.remote_host||'127.0.0.1'}:null,options:JSON.parse(values.options||'{}'),timeout:Number(values.timeout)};
  const result=await api('/connections',body);$('#connectionDialog').close();await load();await discover(result.id);
}));
$('#connectionForm').elements.use_ssh.addEventListener('change',event=>{$('#sshFields').hidden=!event.target.checked;});
$('#connectionForm').elements.kind.addEventListener('change',event=>{const form=$('#connectionForm'); if(!form.elements.id.value){const defaults={ollama:'http://localhost:11434',openai:'https://api.openai.com/v1',anthropic:'https://api.anthropic.com/v1',gemini:'https://generativelanguage.googleapis.com/v1beta'};form.elements.url.value=defaults[event.target.value];}});
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
function renderHistory(){$('#history').replaceChildren();if(!state.history.length)$('#history').append(el('p','caption','Your conversations will appear here.'));[...state.history].reverse().forEach(run=>{const b=button(run.prompt,()=>{if(busy)return toast('Wait for the current response before switching conversations.');conversation=run.conversation;$('#feed').replaceChildren();state.history.filter(r=>r.conversation===conversation).forEach(r=>{addPrompt(r.prompt);r.results.forEach(result=>{const card=resultCard(result);finishCard(card,result);});});tab('conversation');},'history-item');b.append(el('small','',`${new Date(run.created_at*1000).toLocaleString()} · ${run.results.length} responses`));$('#history').append(b);});}
function addPrompt(text){$('#feed').append(el('div','user-message',text));}
function resultCard(result){const intermediate=result.phase==='proposal'||result.phase==='review';const card=el(intermediate?'details':'article',`result${result.synthesis?' synthesis':''}`),head=el(intermediate?'summary':'header'),name=el('div');name.append(el('strong','',`${result.phase==='final'?'Final decision · ':result.phase==='review'?'Peer review · ':result.phase==='proposal'?result.proposal_id+' · ':result.synthesis?'Synthesis · ':''}${result.model}`),el('small','',result.address));head.append(name,el('span','health','Thinking…'));card.append(head,el('div','answer','Waiting for a response…'));$('#feed').append(card);return card;}
function finishCard(card,result){card.querySelector('.answer').textContent=result.text||result.error||'No response';card.querySelector('.answer').classList.toggle('error',result.status==='error');card.querySelector('.health').textContent=result.status==='error'?'Error':result.status==='partial'?'Partial participation':result.seconds!==undefined?`${result.seconds}s`:'Complete';if(result.text)card.querySelector('header,summary').append(button('Copy',async()=>{await navigator.clipboard.writeText(result.text);toast('Copied response.');}));}
async function sendPrompt(event){event?.preventDefault();const prompt=$('#prompt').value.trim();if(!prompt||busy)return;if(!selected().length)return toast('Connect a provider and choose a model first.');if($('#feed .welcome'))$('#feed').replaceChildren();addPrompt(prompt);$('#prompt').value='';const ids=selected().map(c=>c.id), synthesis=$('#synthesis').disabled?'':$('#synthesis').value;busy=true;controller=new AbortController();renderConnections();tab('conversation');const cards=new Map();try{const response=await fetch('/api/dispatch',{method:'POST',headers:{'Content-Type':'application/json','X-BorgNet-Token':state.token},body:JSON.stringify({prompt,connections:ids,contexts:[...attached],conversation,synthesize:synthesis==='__independent__'?'':synthesis,collaborate:synthesis!=='__independent__'}),signal:controller.signal});if(!response.ok){const error=await response.json();throw new Error(error.error||error.detail||'Request failed');}const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});let newline;while((newline=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,newline);buffer=buffer.slice(newline+1);if(!line)continue;const message=JSON.parse(line),key=message.connection+'-'+(message.phase||'response')+(message.synthesis?'-synthesis':'');if(message.type==='run')conversation=message.conversation;if(message.type==='phase')$('#status').textContent=message.text;if(message.type==='started')cards.set(key,resultCard(message));if(message.type==='result'){const card=cards.get(key)||resultCard(message);finishCard(card,message);}$('#feed').scrollTop=$('#feed').scrollHeight;}if(done)break;}}catch(error){const stopped=error.name==='AbortError';toast(stopped?'Stopped waiting. A remote provider may continue an already accepted request.':error.message);for(const card of cards.values())if(card.querySelector('.health').textContent==='Thinking…'){card.querySelector('.health').textContent=stopped?'Stopped':'Interrupted';card.querySelector('.answer').textContent=stopped?'Request cancelled in this workspace.':'Connection interrupted before a response arrived.';}if(!stopped)$('#prompt').value=prompt;}finally{busy=false;controller=null;await load();}}
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
