const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const source=fs.readFileSync('borgnet/web/app.js','utf8');
const start=source.indexOf('function loopbackHost(');
const end=source.indexOf('function modelOptions(',start);
const eligibleStart=source.indexOf('function localReasoningEligible(');
const eligibleEnd=source.indexOf('function resultCard(',eligibleStart);
const context=vm.createContext({URL});
vm.runInContext(source.slice(start,end)+source.slice(eligibleStart,eligibleEnd),context);

const eligible=context.localReasoningEligible;
assert.equal(eligible({kind:'ollama',url:'http://localhost:11434'}),true);
assert.equal(eligible({kind:'openai',url:'http://127.0.0.1:1234/v1',options:{}}),false);
assert.equal(eligible({kind:'openai',url:'http://127.0.0.1:1234/v1',options:{show_local_reasoning:true}}),true);
assert.equal(eligible({kind:'openai',url:'https://example.com/v1',options:{show_local_reasoning:true}}),false);
assert.equal(eligible({kind:'openai',ssh:{remote_host:'127.0.0.1'},url:'http://127.0.0.1:1/v1'}),true);
assert.equal(eligible({kind:'openai',ssh:{remote_host:'api.example.com'},url:'http://127.0.0.1:1/v1'}),false);
assert.equal(eligible({kind:'responses',url:'http://localhost:1234/v1',options:{show_local_reasoning:true}}),false);
assert.match(source,/message\.type==='reasoning'.*appendReasoning\(card,message\.text\)/);
console.log('Reasoning panel accepts only trusted local connection events.');
