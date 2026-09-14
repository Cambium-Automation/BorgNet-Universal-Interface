// Exercise the actual browser keyboard handler without contacting a model.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('borgnet/web/app.js','utf8');
const start = source.indexOf("$('#prompt').addEventListener('keydown'");
const end = source.indexOf('\n',start);
let handler, sends=0, prevented=0;
vm.runInNewContext(source.slice(start,end), {$:()=>({addEventListener:(_,fn)=>{handler=fn;}}), action:fn=>fn, sendPrompt:()=>{sends++;}});
for (const flags of [{}, {ctrlKey:true}, {metaKey:true}]) handler({key:'Enter',preventDefault:()=>{prevented++;},...flags});
assert.equal(sends,3);assert.equal(prevented,3);
for (const flags of [{shiftKey:true},{isComposing:true},{key:'a'}]) handler({key:'Enter',preventDefault:()=>{throw Error('Must not swallow newline/composition');},...flags});
assert.equal(sends,3);
console.log('Enter submits; Shift+Enter and IME composition preserved.');
