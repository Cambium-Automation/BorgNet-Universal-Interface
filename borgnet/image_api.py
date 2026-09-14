"""Image APIs using explicit credentials or existing official-provider connections."""
import asyncio,base64,json,os,re,uuid,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
from types import SimpleNamespace
import httpx
from fastapi import Request
from borgnet.config import Connection

def create_image_api(root, state_store):
 ROOT=Path(root)
 store=state_store
 PRESETS={
  'openai':{'url':'https://api.openai.com/v1','env':'OPENAI_API_KEY','models':['gpt-image-2.5-sunburst','gpt-image-2.5-flare']},
  'gemini':{'url':'https://generativelanguage.googleapis.com/v1beta','env':'GEMINI_API_KEY','models':['gemini-3.1-flash-image','gemini-3-pro-image','gemini-2.5-flash-image']},
  'xai':{'url':'https://api.x.ai/v1','env':'XAI_API_KEY','models':['grok-imagine-image-2.0']},
 }
 def credential(provider):
  p=PRESETS[provider];key=os.environ.get(p['env']) or store.read('secrets',{}).get('image-'+provider,'')
  if not key:
   # Reuse only credentials for the same official provider origin.
   for entry in store.config()['connections']:
    if entry.get('url','').rstrip('/')==p['url']:
     key=store.secret(Connection(**entry))
     if key:break
  return key

 def profile(provider,model,has_key,status):
  sizes=['auto','1024x1024','1536x1024','1024x1536'] if provider=='openai' else ['auto','1:1','16:9','9:16','4:3','3:4']
  modes=[['auto','Automatic'],['low','Low quality'],['medium','Medium quality'],['high','High quality']] if provider=='openai' else [['auto','Automatic']]
  if provider=='xai':modes += [['low','Low quality'],['medium','Medium quality']]
  return {'id':f'api::{provider}::{model}','model':model,'provider':provider,'label':f'{provider.title()} · {model}','backend':'api','installed':has_key,'ready':has_key,'status':status,'sizes':sizes,'default_size':'auto','modes':modes,'min_steps':1,'max_steps':1,'default_steps':1}

 async def catalog():
  async def one(provider,p):
   key=await asyncio.to_thread(credential,provider);models=p['models'];status='API key required'
   if key:
    headers={'x-goog-api-key':key} if provider=='gemini' else {'Authorization':'Bearer '+key}
    try:
     async with httpx.AsyncClient(timeout=20,trust_env=False,follow_redirects=False) as c:
      async with c.stream('GET',p['url']+'/models',headers=headers) as r:
       raw=bytearray()
       async for chunk in r.aiter_bytes():
        raw.extend(chunk)
        if len(raw)>2_000_000:raise ValueError('Model catalog too large')
      if r.status_code!=200:raise ValueError(f'Model discovery HTTP {r.status_code}')
      data=json.loads(raw)
      if provider=='gemini':models=[m['name'].removeprefix('models/') for m in data.get('models',[]) if 'image' in m['name'] and 'generateContent' in m.get('supportedGenerationMethods',[])]
      else:models=[m['id'] for m in data.get('data',[]) if ('gpt-image' if provider=='openai' else 'grok-imagine-image') in m['id']]
      status='Available from API · billed by provider'
      store.write('image-models-'+provider,models)
    except Exception:
     models=store.read('image-models-'+provider,models);status='Discovery unavailable · saved/catalog model · access unverified'
   return [profile(provider,m,bool(key),status) for m in models]
  return [m for group in await asyncio.gather(*(one(k,v) for k,v in PRESETS.items())) for m in group]

 def image_path(identity):
  if not re.fullmatch(r'\d{8}-\d{6}-[a-f0-9]{8}',identity):return None
  p=ROOT/'api-images'/identity
  return p if p.is_file() and not p.is_symlink() else None

 def image_failure(data, provider, status=200):
  """Distinguish explicit policy blocks from quota and unexplained empty output."""
  error=data.get('error') or {}
  if not isinstance(error,dict):error={}
  code=str(error.get('code','')).lower()
  blocked=data.get('promptFeedback',{}).get('blockReason')
  reasons={str(c.get('finishReason','')) for c in data.get('candidates',[])}
  if blocked or reasons & {'SAFETY','IMAGE_SAFETY','PROHIBITED_CONTENT','BLOCKLIST','RECITATION'} or code in {'content_policy_violation','safety_violation','moderation_blocked'}:
   return f'{provider.title()} rejected this prompt under its content policy. No image was generated.'
  if status==429:return f'{provider.title()} image quota or rate limit reached. No image was generated.'
  texts=[str(b.get('text','')) for c in data.get('candidates',[]) for b in c.get('content',{}).get('parts',[]) if not b.get('thought') and b.get('text')]
  if texts:return f'{provider.title()} returned no image.\n'+('\n'.join(texts))[:1600]
  return f'{provider.title()} returned no image'+(f' (HTTP {status})' if status!=200 else '')+'. The provider did not supply a rejection reason.'

 async def generate(body):
  parts=str(body.get('model_id','')).split('::',2)
  if len(parts)!=3 or parts[1] not in PRESETS:raise ValueError('Unknown image provider')
  _,provider,model=parts;key=await asyncio.to_thread(credential,provider)
  if not key:raise ValueError('Configure this image provider API key first')
  known=store.read('image-models-'+provider,PRESETS[provider]['models'])
  if model not in known:raise ValueError('Refresh image models before using this model')
  prompt=str(body.get('prompt','')).strip();size=body.get('size','auto');mode=body.get('quality','auto')
  if not prompt or len(prompt)>4000:raise ValueError('Image prompt must contain 1–4000 characters')
  p=profile(provider,model,True,'');
  if size not in p['sizes'] or mode not in dict(p['modes']):raise ValueError('Unsupported size or quality for this provider')
  if body.get('negative_prompt'):prompt+='\nAvoid: '+str(body['negative_prompt'])[:2000]
  if provider=='gemini':
   path='/models/'+quote(model,safe='')+':generateContent';headers={'x-goog-api-key':key}
   payload={'contents':[{'role':'user','parts':[{'text':prompt}]}],'generationConfig':{'responseModalities':['TEXT','IMAGE']}}
   if size!='auto':payload['generationConfig']['imageConfig']={'aspectRatio':size}
  else:
   path='/images/generations';headers={'Authorization':'Bearer '+key};payload={'model':model,'prompt':prompt,'n':1}
   if provider=='openai':payload.update(size=size,quality=mode,output_format='png')
   else:
    payload['response_format']='b64_json'
    if size!='auto':payload['aspect_ratio']=size
    if mode!='auto':payload['quality']=mode
  start=time.monotonic()
  async with httpx.AsyncClient(timeout=240,trust_env=False,follow_redirects=False) as c:
   async with c.stream('POST',PRESETS[provider]['url']+path,headers=headers,json=payload) as r:
    raw=bytearray()
    async for chunk in r.aiter_bytes():
     raw.extend(chunk)
     if len(raw)>90_000_000:raise ValueError('Image API response too large')
   data=json.loads(raw)
   if r.status_code!=200:raise ValueError(image_failure(data,provider,r.status_code))
  if provider=='gemini':
   candidates=data.get('candidates',[])
   blocks=candidates[0].get('content',{}).get('parts',[]) if candidates else []
   encoded=next((b['inlineData']['data'] for b in blocks if not b.get('thought') and b.get('inlineData',{}).get('mimeType','').startswith('image/')),None)
  else:encoded=(data.get('data') or [{}])[0].get('b64_json')
  if not encoded:raise ValueError(image_failure(data,provider))
  image=base64.b64decode(encoded,validate=True)
  if not image or len(image)>64_000_000:raise ValueError('Invalid image size')
  mime='image/png' if image.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if image.startswith(b'\xff\xd8\xff') else 'image/webp' if image[:4]==b'RIFF' and image[8:12]==b'WEBP' else None
  if not mime:raise ValueError('Provider did not return PNG, JPEG, or WebP')
  identity=datetime.now().strftime('%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:8];directory=ROOT/'api-images';directory.mkdir(mode=0o700,exist_ok=True)
  file=directory/identity
  with file.open('xb') as f:os.chmod(file,0o600);f.write(image)
  result={'id':identity,'model_id':body['model_id'],'model_label':model,'prompt':body['prompt'],'created_at':datetime.now(timezone.utc).isoformat(),'seconds':round(time.monotonic()-start,2),'url':'/api/imagegen/images/'+identity,'mime':mime}
  with store.lock:
   history=store.read('api-image-history',[]);history.append(result);store.write('api-image-history',history)
  return result

 def register(app):
  @app.post('/api/image-providers')
  async def configure(request:Request):
   d=await request.json();provider=d.get('provider');key=d.get('api_key','')
   if provider not in PRESETS or not isinstance(key,str) or not key.strip():raise ValueError('Select a provider and enter its API key')
   store.save_secret('image-'+provider,key.strip());return {'saved':True}
 return SimpleNamespace(credential=credential,catalog=catalog,generate=generate,image_path=image_path,register=register,image_failure=image_failure)
