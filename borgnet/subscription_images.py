"""Opt-in native image tools through installed, already authenticated CLIs."""
import asyncio,json,os,signal,time,uuid,shutil
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace

def create_subscription_images(root,state_store):
 ROOT=Path(root)
 store=state_store
 lock=asyncio.Lock()
 def catalog():
  models=[]
  for provider,label,program in [('codex','Codex','codex'),('grok','Grok','grok')]:
   if os.environ.get('BORGNET_'+provider.upper()+'_IMAGES')!='1' or not shutil.which(program):continue
   models.append({'id':'signedin::'+provider,'label':label+' · existing sign-in','backend':'signedin','installed':True,'ready':True,'status':'Uses existing CLI sign-in; account access is checked during generation','sizes':['auto'],'default_size':'auto','modes':[['auto','Native image generation']],'min_steps':1,'max_steps':1,'default_steps':1})
  return models

 def no_image_message(events):
  """Only show public assistant output, never tool arguments or reasoning."""
  messages=[]
  for line in events.splitlines():
   try:record=json.loads(line)
   except (ValueError,TypeError):continue
   item=record.get('item',{})
   if record.get('type')=='item.completed' and item.get('type')=='agent_message':
    messages.append(str(item.get('text','')))
   elif 'sessionId' in record and isinstance(record.get('text'),str):
    messages.append(record['text'])
  if messages:
   message=messages[-1].strip()[:1600]
   if message:return 'No image generated.\n'+message
  return 'No image generated. The provider returned no image or explanation. Check sign-in and usage limits.'

 async def generate(body):
  prompt=str(body.get('prompt','')).strip();identity=body.get('model_id')
  if identity not in {m['id'] for m in catalog()} or not prompt or len(prompt)>4000:raise ValueError('Choose a connected image workflow and enter a prompt')
  original=prompt
  if body.get('negative_prompt'):prompt+='\nAvoid: '+str(body['negative_prompt'])[:2000]
  async with lock:
   job=ROOT/'image-jobs'/uuid.uuid4().hex;job.mkdir(parents=True,mode=0o700)
   instruction='Use your native image generation tool to create exactly one raster image from the following request. Save or copy the generated image into this working directory. Use the existing ChatGPT sign-in. Do not use API keys, browsers, web search, or substitute procedural drawings. If the native tool is unavailable, stop and report that. Return the absolute saved image path.\n\nIMAGE REQUEST:\n'+prompt
   argv=[shutil.which('codex'),'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--sandbox','workspace-write','-C',str(job),'--json',instruction]
   if identity=='signedin::grok':
    instruction='Use your native image_gen tool to generate exactly one image from this request. Do not use MCP servers, new API keys, or unrelated files. Return the generated image path. IMAGE REQUEST: '+prompt
    argv=[shutil.which('grok'),'--cwd',str(job),'--output-format','json','--max-turns','4','--no-plan','--no-subagents','--disable-web-search','--sandbox','workspace','--tools','image_gen,read_file','--allow','image_gen','--permission-mode','dontAsk','-p',instruction]
   start=time.monotonic()
   with (job/'events.jsonl').open('wb') as out,(job/'stderr.log').open('wb') as err:
    process=await asyncio.create_subprocess_exec(*argv,stdout=out,stderr=err,start_new_session=True)
    try:await asyncio.wait_for(process.wait(),420)
    except BaseException:
     try:os.killpg(process.pid,signal.SIGTERM)
     except ProcessLookupError:pass
     try:await asyncio.wait_for(process.wait(),5)
     except TimeoutError:
      try:os.killpg(process.pid,signal.SIGKILL)
      except ProcessLookupError:pass
      await process.wait()
     raise
   paths=[p for p in job.rglob('*') if p.suffix.lower() in {'.png','.jpg','.jpeg','.webp'} and not p.is_symlink() and p.is_file() and p.resolve().is_relative_to(job.resolve())]
   if identity=='signedin::grok':
    try:
     output=json.loads((job/'events.jsonl').read_text());session_id=output.get('sessionId','')
     uuid.UUID(session_id)
     # Only inspect the session created by this request, and accept its image tool output.
     for updates in (Path.home()/'.grok/sessions').glob('*/'+session_id+'/updates.jsonl'):
      def inspect(value):
       if isinstance(value,dict):
        raw=value.get('rawOutput',{})
        if isinstance(raw,dict) and raw.get('type')=='ImageGen' and raw.get('path'):
         candidate=Path(raw['path'])
         if candidate.is_file() and not candidate.is_symlink() and candidate.resolve().is_relative_to(updates.parent.resolve()):paths.append(candidate)
        for child in value.values():inspect(child)
       elif isinstance(value,list):
        for child in value:inspect(child)
      for line in updates.read_text().splitlines():inspect(json.loads(line))
    except (ValueError,OSError):pass
   if not paths:raise ValueError(no_image_message((job/'events.jsonl').read_text()))
   image=paths[0].read_bytes()
   mime='image/png' if image.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if image.startswith(b'\xff\xd8\xff') else 'image/webp' if image[:4]==b'RIFF' and image[8:12]==b'WEBP' else None
   if not mime or len(image)>64_000_000:raise ValueError('Native generator returned an invalid or oversized image')
   name=datetime.now().strftime('%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:8];directory=ROOT/'api-images';directory.mkdir(mode=0o700,exist_ok=True)
   file=directory/name
   with file.open('xb') as f:os.chmod(file,0o600);f.write(image)
   result={'id':name,'model_id':identity,'model_label':'Codex' if identity.endswith('codex') else 'Grok native image generation','prompt':original,'render_prompt':prompt,'created_at':datetime.now(timezone.utc).isoformat(),'seconds':round(time.monotonic()-start,2),'url':'/api/imagegen/images/'+name,'mime':mime}
   with store.lock:
    history=store.read('api-image-history',[]);history.append(result);store.write('api-image-history',history)
   return result
 return SimpleNamespace(catalog=catalog,generate=generate,no_image_message=no_image_message)
