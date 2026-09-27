const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('borgnet/web/app.js','utf8');
const fn=source.slice(source.indexOf('async function api('),source.indexOf('\nfunction action('));
async function run(response){const context={fetch:async()=>response};vm.createContext(context);vm.runInContext(fn,context);return context.api('/adapters');}
(async()=>{
 await assert.rejects(run({status:500,json:async()=>{throw new SyntaxError('The string did not match the expected pattern.');}}),/\/adapters returned HTTP 500/);
 assert.equal((await run({ok:true,json:async()=>({ready:true})})).ready,true);
 await assert.rejects(run({ok:false,json:async()=>({error:'Workspace locked'})}),/Workspace locked/);
 console.log('Non-JSON server errors are actionable; JSON errors and success preserved.');
})().catch(e=>{console.error(e);process.exitCode=1;});
