const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const nodeCrypto=require('node:crypto').webcrypto;
const elements=new Map();
function element(s){if(!elements.has(s))elements.set(s,{innerHTML:'',textContent:'',hidden:true,querySelector(){return null},addEventListener(){}});return elements.get(s)}
const store=new Map();
const indexedDB={};
// A small faithful IDB transaction fixture; application storage functions run unchanged.
indexedDB.open=function(){const request={};queueMicrotask(()=>{request.result={close(){},transaction(){const tx={};tx.objectStore=()=>({get(k){const r={};queueMicrotask(()=>{r.result=store.get(k);r.onsuccess?.()});return r},put(v,k){store.set(k,v);queueMicrotask(()=>tx.oncomplete?.())}});return tx}};request.onsuccess?.()});return request};
let writes=0,lookup=false;
const context=vm.createContext({document:{querySelector:element,addEventListener(){},hidden:false},navigator:{onLine:true},
 window:{addEventListener(){}},indexedDB,queueMicrotask,crypto:nodeCrypto,TextEncoder,Uint8Array,AbortSignal,
 btoa:v=>Buffer.from(v,'binary').toString('base64'),clearTimeout(){},setTimeout(){},
 fetch:async(url,options)=>{
  if(url.endsWith('/nonces'))return {ok:true,status:200,json:async()=>({nonce_id:'nonce',issued_at_ms:1,expires_at_ms:60001})};
  if(url.includes('/requests/'))return {ok:true,status:200,json:async()=>lookup?{state:'completed',result:{enabled:false,version:2}}:{state:'pending'}};
  if(url.endsWith('/controls/global')){writes++;throw new DOMException('timeout','TimeoutError')}
  return {ok:false,status:401,json:async()=>({})};
 }});
(async()=>{
 vm.runInContext(fs.readFileSync('frontend/owner-mobile/app.js','utf8'),context);
 await new Promise(resolve=>setImmediate(resolve));
 const pair=await nodeCrypto.subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},false,['sign','verify']);
 context.testKey=pair.privateKey;
 vm.runInContext("session={device_id:'device',device_epoch:1};deviceKey=testKey",context);
 await assert.rejects(vm.runInContext("signed('/controls/global',{owner_policy_id:'policy-main',enabled:false,expected_version:1})",context));
 assert.equal(writes,1);
 const pending=store.get('pending-write');assert.ok(pending?.proof?.idempotency_key);
 await assert.rejects(vm.runInContext("signed('/controls/global',{owner_policy_id:'policy-main',enabled:false,expected_version:1})",context));
 assert.equal(writes,1,'unknown first outcome must block a new UUID send');
 lookup=true;
 assert.equal(await vm.runInContext('resolvePendingWrite()',context),true);
 assert.equal(store.get('pending-write'),null);
 process.stdout.write('pending-write timeout and readonly recovery passed\n');
})().catch(e=>{process.stderr.write(String(e.stack)+'\n');process.exitCode=1});
