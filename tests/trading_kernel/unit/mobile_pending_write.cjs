const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const nodeCrypto=require('node:crypto').webcrypto;
const store=new Map();
const indexedDB={open(){const request={};queueMicrotask(()=>{request.result={close(){},transaction(){const tx={};tx.objectStore=()=>({get(k){const r={};queueMicrotask(()=>{r.result=store.get(k);r.onsuccess?.();queueMicrotask(()=>tx.oncomplete?.())});return r},put(v,k){store.set(k,v);queueMicrotask(()=>tx.oncomplete?.())},delete(k){store.delete(k);queueMicrotask(()=>tx.oncomplete?.())}});return tx}};request.onsuccess?.()});return request}};
let lockTail=Promise.resolve();
const locks={request(name,options,callback){const next=lockTail.then(callback);lockTail=next.catch(()=>{});return next}};
let writes=0,nonces=0,lookup=false,responseFault=null,receiptResult={enabled:false,version:2};
function tab(){
 const elements=new Map();const element=s=>{if(!elements.has(s))elements.set(s,{innerHTML:'',textContent:'',hidden:true,querySelector(){return null},addEventListener(){}});return elements.get(s)};
 const context=vm.createContext({document:{querySelector:element,addEventListener(){},hidden:false},navigator:{onLine:true,locks},window:{addEventListener(){}},indexedDB,queueMicrotask,crypto:nodeCrypto,TextEncoder,Uint8Array,AbortSignal,
 btoa:v=>Buffer.from(v,'binary').toString('base64'),clearTimeout(){},setTimeout(){},fetch:async(url,options)=>{
  if(url.endsWith('/nonces')){nonces++;return {ok:true,status:200,json:async()=>({nonce_id:'nonce-'+nonces,issued_at_ms:1,expires_at_ms:60001})}}
  if(url.includes('/requests/'))return {ok:true,status:200,json:async()=>lookup?{state:'completed',result:receiptResult}:{state:'pending'}};
  if(url.endsWith('/controls/global')){
   if(responseFault!==null){writes++;return {ok:true,status:200,json:async()=>{
    if(responseFault==='body-error')throw new TypeError('body stream interrupted');
    if(responseFault==='bad-json')throw new SyntaxError('truncated JSON');
    return {empty:{},null:null,array:[],wrongType:{enabled:'false',version:2},wrongTarget:{enabled:true,version:2},wrongVersion:{enabled:false,version:99}}[responseFault];
   }}}
   writes++;if(writes===1)throw new DOMException('timeout','TimeoutError');return {ok:true,status:200,json:async()=>({enabled:false,version:2})}}
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
 for(const fault of ['body-error','bad-json','empty','null','array','wrongType','wrongTarget','wrongVersion']){
  store.set('pending-write',null);responseFault=fault;
  await assert.rejects(vm.runInContext(command,first),`HTTP 200 ${fault} must not be success`);
  const uncertain=store.get('pending-write');assert.ok(uncertain?.proof?.idempotency_key,`${fault} must retain original identity`);
  receiptResult={};assert.equal(await vm.runInContext('resolvePendingWrite()',first),false,'malformed completed receipt cannot clear unknown');
  assert.equal(store.get('pending-write').proof.idempotency_key,uncertain.proof.idempotency_key);
  receiptResult={enabled:false,version:2};assert.equal(await vm.runInContext('resolvePendingWrite()',first),true);
 }
 responseFault=null;store.set('pending-write',null);
 const confirmed=await vm.runInContext(command,first);assert.equal(confirmed.enabled,false);assert.equal(store.get('pending-write'),null);
 assert.equal(vm.runInContext("validWriteResult('/controls/strategy',{strategy_group_id:'BRF2-001',enabled:true,expected_version:2},{strategy_group_id:'BRF2-001',entry_state:'enabled',control_version:3,last_event_id:'event',updated_at_ms:3000})",first),true);
 assert.equal(vm.runInContext("validWriteResult('/controls/strategy',{strategy_group_id:'BRF2-001',enabled:true,expected_version:2},{strategy_group_id:'MI-001',entry_state:'enabled',control_version:3,last_event_id:'event',updated_at_ms:3000})",first),false);
 assert.equal(vm.runInContext("validWriteResult('/operations/submit',{operation_id:'op',ticket_id:'t',expected_version:2},{operation_id:'op',ticket_id:'t',state:'accepted',version:3})",first),true);
 assert.equal(vm.runInContext("validWriteResult('/operations/submit',{operation_id:'op',ticket_id:'t',expected_version:2},{operation_id:'other',ticket_id:'t',state:'accepted',version:3})",first),false);
 assert.equal(vm.runInContext("exactFraction('0.007',50)",first),'0.0035');
 process.stdout.write('pending-write timeout and readonly recovery passed; cross-tab mutex, identity clear and invalid 200 body passed\n');
})().catch(e=>{process.stderr.write(String(e.stack)+'\n');process.exitCode=1});
