const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('borgnet/web/openrouter-import.js','utf8');
const context={};vm.createContext(context);vm.runInContext(source.slice(0,source.indexOf('(() =>')),context);
const parse=context.parseOpenRouterExample,key='sk-or-v1-0123456789abcdef0123456789abcdef';
for(const script of [
 `curl https://openrouter.ai/api/v1/chat/completions -H "Authorization: Bearer ${key}" -d '{"model":"openrouter/free"}'`,
 `fetch('https://openrouter.ai/api/v1/chat/completions', {headers:{Authorization:'Bearer ${key}'}, body:JSON.stringify({"model":"vendor/model:free"})})`,
 `requests.post('https://openrouter.ai/api/v1/chat/completions',headers={'Authorization':'Bearer ${key}'},json={'model':'vendor/model:free'})`
]){assert.equal(parse(script).key,key);assert.ok(parse(script).model);}
assert.throws(()=>parse('Bearer <OPENROUTER_API_KEY>'));
assert.throws(()=>parse(key+' sk-or-v1-abcdef0123456789abcdef0123456789'));
assert.throws(()=>parse('x'.repeat(32001)));
assert.equal(parse(key+'; process.exit(1)').key,key);
console.log('OpenRouter import: curl/fetch/Python parsing, placeholders, duplicate keys, size limit, and inert script text passed.');
