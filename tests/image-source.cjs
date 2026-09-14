const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('borgnet/web/images.js','utf8');
const context={};vm.createContext(context);
vm.runInContext(source.match(/^function imageSource\(.*$/m)[0],context);
for(const [id,expected] of [['local::bonsai','local'],['api::horde::auto','community'],['api::openrouter::vendor/model','community'],['api::pollinations::flux','community'],['api::xai::grok-imagine','frontier'],['signedin::grok','frontier'],['api::gemini::image','frontier']])assert.equal(context.imageSource({id}),expected);
assert(source.includes("localStorage.setItem('borgnet-image-source',sourceGroup)"));
assert(source.includes("'borgnet-image-model-'+sourceGroup"));
console.log('Image source groups preserve local/frontier/community separation and per-group selection keys.');
