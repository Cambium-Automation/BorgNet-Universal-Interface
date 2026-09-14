const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
class Element {constructor(tag){this.tag=tag;this.children=[];} append(x){this.children.push(x);}}
const context={window:{},document:{createElement:tag=>new Element(tag)}};
vm.runInNewContext(fs.readFileSync('borgnet/web/media-responses.js','utf8'),context);
const output=context.window.borgnetProviderResponses({provider_responses:[{messages:['<script>synthetic refusal</script>'],codes:['SAFETY'],truncated:true}],error:'No image'});
assert.equal(output.tag,'details');
assert(output.children.some(x=>x.textContent==='<script>synthetic refusal</script>'));
assert(output.children.some(x=>x.textContent.includes('truncated')));
assert(output.children.every(x=>!('innerHTML' in x)));
console.log('Provider responses render as expandable literal text with truncation notice.');
