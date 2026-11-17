const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const nodeCrypto=require('node:crypto').webcrypto;
const store=new Map();
const indexedDB={open(){const request={};queueMicrotask(()=>{request.result={close(){},transaction(){const tx={};tx.objectStore=()=>({get(k){const r={};queueMicrotask(()=>{r.result=store.get(k);r.onsuccess?.();queueMicrotask(()=>tx.oncomplete?.())});return r},put(v,k){store.set(k,v);queueMicrotask(()=>tx.oncomplete?.())},delete(k){store.delete(k);queueMicrotask(()=>tx.oncomplete?.())}});return tx}};request.onsuccess?.()});return request}};
let lockTail=Promise.resolve();
const locks={request(name,options,callback){const next=lockTail.then(callback);lockTail=next.catch(()=>{});return next}};
let writes=0,nonces=0,lookup=false;
function tab(){
 const elements=new Map();const element=s=>{if(!elements.has(s))elements.set(s,{innerHTML:'',textContent:'',hidden:true,querySelector(){return null},addEventListener(){}});return elements.get(s)};
 const context=vm.createContext({document:{querySelector:element,addEventListener(){},hidden:false},navigator:{onLine:true,locks},window:{addEventListener(){}},indexedDB,queueMicrotask,crypto:nodeCrypto,TextEncoder,Uint8Array,AbortSignal,
 btoa:v=>Buffer.from(v,'binary').toString('base64'),clearTimeout(){},setTimeout(){},fetch:async(url,options)=>{
  if(url.endsWith('/nonces')){nonces++;return {ok:true,status:200,json:async()=>({nonce_id:'nonce-'+nonces,issued_at_ms:1,expires_at_ms:60001})}}
  if(url.includes('/requests/'))return {ok:true,status:200,json:async()=>lookup?{state:'completed',result:{enabled:false,version:2}}:{state:'pending'}};
  if(url.endsWith('/controls/global')){writes++;if(writes===1)throw new DOMException('timeout','TimeoutError');return {ok:true,status:200,json:async()=>({enabled:false,version:2})}}
  return {ok:false,status:401,json:async()=>({})};
 }});
 vm.runInContext(fs.readFileSync('frontend/owner-mobile/app.js','utf8'),context);return context;
}
(async()=>{
 const first=tab(),second=tab();await new Promise(resolve=>setImmediate(resolve));
 const pair=await nodeCrypto.subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},false,['sign','verify']);
 for(const c of [first,second]){c.testKey=pair.privateKey;vm.runInContext("session={device_id:'device',device_epoch:1};deviceKey=testKey",c)}
 const command="signed('/controls/global',{owner_policy_id:'policy-main',enabled:false,expected_version:1})";
 const results=await Promise.allSettled([vm.runInContext(command,first),vm.runInContext(command,second)]);
 assert.equal(writes,1,'a second tab must not send while A has an unknown result');
 assert.equal(nonces,1,'cross-page lock must precede nonce issuance');
 assert.ok(results.every(r=>r.status==='rejected'));
 const pending=store.get('pending-write');assert.ok(pending?.proof?.idempotency_key);
 await assert.rejects(vm.runInContext(command,second));assert.equal(writes,1);
 lookup=true;assert.equal(await vm.runInContext('resolvePendingWrite()',second),true);assert.equal(store.get('pending-write'),null);
 // A stale completion must not remove B's newly persisted request.
 const b={proof:{idempotency_key:'request-B'}};store.set('pending-write',b);first.staleProof=pending.proof;
 await vm.runInContext('clearPendingWrite(staleProof)',first);assert.equal(store.get('pending-write').proof.idempotency_key,'request-B');
 process.stdout.write('pending-write timeout and readonly recovery passed; cross-tab mutex and identity clear passed\n');
})().catch(e=>{process.stderr.write(String(e.stack)+'\n');process.exitCode=1});
