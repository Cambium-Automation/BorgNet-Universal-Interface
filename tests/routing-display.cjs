const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('borgnet/web/app.js', 'utf8');
const start = source.indexOf('function dispatchGroupItems(');
const end = source.indexOf('function addGroupModel(', start);
assert.ok(start >= 0 && end > start);
const context = vm.createContext({});
vm.runInContext(source.slice(start, end), context);
const connections = [{id: 'a'}, {id: 'b'}, {id: 'c'}];
assert.equal(context.dispatchGroupItems('__route__', connections.map(c => c.id), connections).length, 0);
assert.deepEqual(Array.from(context.dispatchGroupItems('__single__', ['b'], connections), c => c.id), ['b']);
assert.deepEqual(Array.from(context.dispatchGroupItems('__independent__', [], connections), c => c.id), ['a', 'b', 'c']);
console.log('Routing displays no candidate as working before selection.');
