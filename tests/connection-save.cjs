const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('borgnet/web/app.js','utf8');
const start=source.indexOf("$('#connectionForm').addEventListener('submit'");
const end=source.indexOf("\n$('#connectionForm').elements.use_ssh",start);
const helpers=[source.match(/^function loopbackHost.*$/m)[0],source.match(/^function loopbackEndpoint.*$/m)[0]].join('\n');
async function check(old,values,expected,reasoning=false,proxy=false) {
  let handler,body;
  const form={elements:{use_ssh:{checked:false},use_proxy_ssh:{checked:proxy},show_local_reasoning:{checked:reasoning}},addEventListener:(_,fn)=>handler=fn};
  vm.runInNewContext(helpers+'\n'+source.slice(start,end),{
    $:s=>s==='#connectionForm'?form:{close(){}},action:fn=>fn,
    state:{connections:old?[old]:[]},FormData:class {constructor(){return Object.entries(values);}},
    URL,
    api:async(_,payload)=>{body=payload;return {id:'test'};},load:async()=>{},discover:async()=>{},
  });
  await handler({preventDefault(){},currentTarget:form});
  assert.equal(body.url,expected);
  return body;
}
(async()=>{
  const values={id:'astra',kind:'cli',cli_provider:'codex',model:'gpt-6-astra',options:'{}',timeout:'180'};
  await check({id:'astra',url:'http://127.0.0.1:7340/codex_cli/v1'},values,'http://127.0.0.1:7340/codex_cli/v1');
  await check(null,{...values,id:''},'http://127.0.0.1');
  await check({id:'astra',url:'https://old.example/v1'},{...values,kind:'openai',url:'https://new.example/v1'},'https://new.example/v1');
  const local=await check(null,{...values,kind:'openai',url:'http://127.0.0.1:1234/v1'},'http://127.0.0.1:1234/v1',true);
  assert.equal(local.options.show_local_reasoning,true);
  const cloud=await check(null,{...values,kind:'openai',url:'https://api.example/v1'},'https://api.example/v1');
  assert.equal(cloud.options.show_local_reasoning,undefined);
  const proxied=await check(null,{...values,kind:'openai',url:'https://api.example/v1',proxy_host:'egress.example.com',proxy_user:'',proxy_port:'22',proxy_identity_file:''},'https://api.example/v1',false,true);
  assert.equal(proxied.proxy_ssh.host,'egress.example.com');
  console.log('CLI saves preserve existing inert endpoint metadata; new CLI and API edits retain correct URLs.');
})().catch(error=>{console.error(error);process.exitCode=1;});
