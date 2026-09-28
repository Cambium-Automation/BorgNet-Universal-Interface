const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const source=fs.readFileSync('borgnet/web/app.js','utf8');
const start=source.indexOf('function showDispatchFailure(');
const end=source.indexOf('async function sendPrompt(',start);
assert.ok(start>=0&&end>start);
const statuses=[];
const context=vm.createContext({modelStatus:(_group,result,status)=>statuses.push([result.connection,status])});
vm.runInContext(source.slice(start,end),context);

const group={preview:{textContent:'Waiting for model output…'},statuses:new Map([['local-model',{status:{textContent:'Thinking'}}]])};
const busy=context.showDispatchFailure(group,new Map(),new Error('A selected connection is already busy'),false);
assert.equal(busy,'A selected connection is already busy');
assert.equal(group.preview.textContent,busy);
assert.deepEqual(statuses,[['local-model','error']]);

const health={textContent:'Streaming…'},answer={textContent:''};
const card={querySelector:selector=>selector==='.health'?health:answer};
const interrupted=context.showDispatchFailure(group,new Map([['local-model',card]]),new Error('Connection interrupted'),false);
assert.equal(interrupted,'Connection interrupted');
assert.equal(health.textContent,'Interrupted');
assert.equal(answer.textContent,'Connection interrupted');

console.log('Dispatch failures replace the waiting placeholder and mark an interrupted stream.');
