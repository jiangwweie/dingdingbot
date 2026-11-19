const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),element=s=>{if(!elements.has(s))elements.set(s,{innerHTML:'',hidden:false,addEventListener(){},querySelector(){return null}});return elements.get(s)};
let calls=0;
const context=vm.createContext({document:{querySelector:element,addEventListener(){},hidden:false},navigator:{onLine:true},window:{addEventListener(){}},clearTimeout(){},setTimeout(){},fetch(){calls++;throw Error('Guide must not call API')},indexedDB:{open(){const r={};queueMicrotask(()=>{r.result={close(){},transaction(){return{objectStore(){return{get(){const q={};queueMicrotask(()=>{q.result=null;q.onsuccess()});return q}}}}}};r.onsuccess()});return r}},queueMicrotask});
vm.runInContext(fs.readFileSync('frontend/owner-mobile/app.js','utf8'),context);
vm.runInContext(`session={device_id:'fixture'};positions=[{ticket_id:'t',exchange_instrument_id:'binance-usdm:XRPUSDT:perpetual',position_side:'short',strategy_group_id:'BRF2-001',selected_leverage:5,position_qty:'2474.5',average_fill_price:'0.9996',active_stop_price:'0.9984',management_mode:'AUTO',status:'runner_protected',capabilities:{reduce:true,tighten:true,tp:true,close:true}}];render()`,context);
assert.match(element('#screen').innerHTML,/操作帮助/);
vm.runInContext('operationGuide()',context);
assert.match(element('#sheet').innerHTML,/想降低仓位/);
for(const topic of ['reduce','protection','tp','cancel','close','pause']){
 vm.runInContext(`operationGuide('${topic}','t')`,context);
 assert.match(element('#sheet').innerHTML,/用一个例子理解/);
 assert.doesNotMatch(element('#sheet').innerHTML,/data-action="confirm"/);
}
vm.runInContext(`operationGuide('reduce','t')`,context);
assert.match(element('#sheet').innerHTML,/继续原Runner/);
vm.runInContext(`guideEnter('reduce','t')`,context);
assert.match(element('#sheet').innerHTML,/核实并预览/);
assert.equal(calls,0);
vm.runInContext(`positions[0].capabilities.reduce=false;operationGuide('reduce','t')`,context);
assert.match(element('#sheet').innerHTML,/disabled/);
vm.runInContext(`positions=[];guideEnter('reduce','t')`,context);
assert.equal(calls,0);
console.log('Read-only guide, current capabilities and preview-only entry passed');
