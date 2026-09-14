const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map(), events={};
function node(id=''){return {value:'',disabled:false,textContent:'',dataset:{},scrollTop:0,children:[],classList:{contains:()=>true},addEventListener(type,fn){this[type]=fn;},append(...items){this.children.push(...items);},before(){},replaceChildren(){this.children=[];},setAttribute(){},reportValidity:()=>true,getBoundingClientRect:()=>({top:0,bottom:600}),querySelectorAll:()=>[],scrollIntoView(){}};}
const q=id=>{if(!nodes.has(id))nodes.set(id,node(id));return nodes.get(id);};
q('#localImagePrompt').value='A mountain lake';q('#localImageSize').value='auto';q('#localImageMode').value='auto';q('#localImageSteps').value='1';q('#localImageSeed').value='-1';q('#imageFeedLimit').value='4';
let calls=0,resolveRequest,model='signedin::grok';
const context={q,make:()=>node(),selectedImage:()=>({id:model,installed:true}),running:false,refreshPending:false,request:()=>{calls++;return new Promise(resolve=>{resolveRequest=()=>resolve({json:async()=>({id:'fixture',url:'/image',prompt:'fixture'})});});},imageURL:x=>x,imageActions:()=>node(),showImage(){},gallery:async()=>{},imageSettings(){},refreshImages(){},document:{hidden:false,addEventListener:(name,fn)=>events[name]=fn},window:{addEventListener:(name,fn)=>events[name]=fn},Number};
vm.createContext(context);
const source=fs.readFileSync('borgnet/web/images.js','utf8');
vm.runInContext(source.slice(source.indexOf('// Feed requests'),source.indexOf("q('#localImageModel').addEventListener('change'")),context);
const finish=async()=>{resolveRequest();await new Promise(resolve=>setImmediate(resolve));};
(async()=>{
 q('#imageFeedStart').onclick(); assert.equal(calls,1);
 q('#imageFeedMore').onclick();assert.equal(calls,1,'in-flight requests cannot overlap');
 await finish();assert.equal(calls,1,'completion alone does not generate');
 q('#imageFeedViewport').scrollTop=100;q('#imageFeedViewport').scroll();assert.equal(calls,2);
 q('#imageFeedPause').onclick();await finish();q('#imageFeedMore').onclick();assert.equal(calls,2,'pause prevents generation');
 q('#imageFeedResume').onclick();await finish();assert.equal(calls,3);
 q('#imageFeedMore').onclick();await finish();assert.equal(calls,4);
 q('#imageFeedMore').onclick();q('#imageFeedResume').onclick();assert.equal(calls,4,'request cap enforced');
 q('#imageFeedStart').onclick();await finish();events['borgnet-tab-change']({detail:'conversation'});q('#imageFeedMore').onclick();assert.equal(calls,5,'leaving tab pauses');
 q('#imageFeedResume').onclick();await finish();q('#localImagePrompt').input();q('#imageFeedMore').onclick();assert.equal(calls,6,'editing invalidates old feed');
 assert.equal(q('#imageFeedResume').disabled,true);
 model='api::horde::auto';vm.runInContext('feedButtons()',context);assert.equal(vm.runInContext('feedControls.hidden',context),true);q('#imageFeedStart').onclick();assert.equal(calls,6,'non-Grok cannot start feed');
 model='api::xai::grok-imagine-image';vm.runInContext('feedButtons()',context);assert.equal(vm.runInContext('feedControls.hidden',context),false);
 console.log('Image feed: sequential requests, scroll trigger, cap, pause/resume, tab pause, and settings invalidation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
