const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('borgnet/web/session.js','utf8');
async function fixture(native=true){
 let server='first', renewals=0, posts=0, dialogs=0, writes=[];
 const storage=new Map();
 const fetch=async(input,options={})=>{
  const path=typeof input==='string'?input:input.url,h=new Headers(options.headers);
  if(path.startsWith('https://external'))return {ok:true,status:200};
  if(h.get('X-BorgNet-Session')!==server)return {ok:false,status:401};
  if(path==='/api/session')return {ok:true,status:200,json:async()=>({media_token:'media-'+server})};
  if(path==='/api/state')return {ok:true,status:200,json:async()=>({token:'csrf-'+server})};
  if(options.method==='POST'){posts++;writes.push(h.get('X-BorgNet-Token'));}
  return {ok:true,status:200,json:async()=>({ok:true})};
 };
 const ctx={URL,URLSearchParams,Headers,Request,Promise,Error,location:{hash:'#session=first',href:'http://127.0.0.1:7337/',origin:'http://127.0.0.1:7337',pathname:'/',search:''},history:{replaceState(){}},sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},document:{getElementById:()=>null,createElement:()=>({append(){},addEventListener(){},setAttribute(){},showModal(){dialogs++;}}),body:{append(){}}},window:{fetch}};
 if(native)ctx.window.webkit={messageHandlers:{borgnetSession:{postMessage:async()=>{renewals++;return server;}}}};
 vm.runInNewContext(source,ctx);await ctx.window.fetch('/api/state');
 return {ctx,rotate:()=>{server='second';},stats:()=>({renewals,posts,dialogs,writes})};
}
(async()=>{
 const f=await fixture();f.rotate();
 const r=await Promise.all([f.ctx.window.fetch('/api/permissions'),f.ctx.window.fetch('/api/adapters')]);
 assert(r.every(r=>r.status===200));assert.equal(f.stats().renewals,1);assert.equal(f.stats().dialogs,0);
 await f.ctx.window.fetch('/api/permissions',{method:'POST',headers:{'X-BorgNet-Token':'csrf-first'},body:'{}'});
 assert.deepEqual(f.stats().writes,['csrf-second']);assert.equal(f.stats().posts,1);
 assert.equal((await f.ctx.window.fetch('https://external.example/api/test')).status,200);
 const browser=await fixture(false);browser.rotate();assert.equal((await browser.ctx.window.fetch('/api/state')).status,401);assert.equal(browser.stats().dialogs,1);
 console.log('Native rotation reconnects once and refreshes CSRF; browser stays locked.');
})().catch(e=>{console.error(e);process.exitCode=1;});
