const API='/api/owner/v1/mobile', screen=document.querySelector('#screen'), sheet=document.querySelector('#sheet'), overlay=document.querySelector('#overlay');
const $=s=>document.querySelector(s), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=(n,d=2)=>n==null?'—':Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
let session=null, deviceKey=null, positions=[], orders=[], ordersStatus='unavailable',controls=null,page='positions',connected=navigator.onLine,busy=false,confirmAction=null,refreshTimer=null;
function notice(text){$('#toast').textContent=text;$('#toast').hidden=false;setTimeout(()=>$('#toast').hidden=true,4500)}
function show(html){sheet.innerHTML='<div class="handle"></div>'+html;overlay.hidden=false;sheet.querySelector('button,input')?.focus()}
function close(){overlay.hidden=true;confirmAction=null}
const heading=t=>`<div class="row"><h2>${esc(t)}</h2><button class="close" data-action="dismiss" aria-label="关闭">×</button></div>`;
async function request(path,options={}){
 if(!navigator.onLine)throw Error('网络未连接');
 const response=await fetch(API+path,{signal:AbortSignal.timeout(15000),...options,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json',...options.headers}});
 let body={};try{body=await response.json()}catch{}
 if(response.status===401){session=null;renderBinding();throw Error('设备授权已失效，请重新绑定')}
 if(!response.ok){const error=Error(body.message||body.detail||body.code||`请求失败 ${response.status}`);error.status=response.status;throw error;}
 return body;
}
function db(){return new Promise((resolve,reject)=>{const r=indexedDB.open('brc-owner-device',1);r.onupgradeneeded=()=>r.result.createObjectStore('keys');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(Error('无法访问设备存储'))})}
async function getKey(slot='active'){const d=await db();return new Promise((resolve,reject)=>{const r=d.transaction('keys').objectStore('keys').get(slot);r.onsuccess=()=>{resolve(r.result||null);d.close()};r.onerror=()=>reject(r.error)})}
async function storeKey(key,slot='active'){const d=await db();await new Promise((resolve,reject)=>{const tx=d.transaction('keys','readwrite');tx.objectStore('keys').put(key,slot);tx.oncomplete=()=>{d.close();resolve()};tx.onerror=()=>reject(tx.error)})}
const b64=bytes=>btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
function canonical(value){if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';return JSON.stringify(value)}
async function digest(body){return 'sha256:'+Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(body))))).map(x=>x.toString(16).padStart(2,'0')).join('')}
async function signed(path,payload,key=crypto.randomUUID()){
 if(!navigator.locks?.request)throw Error('当前浏览器不支持操作互斥，请使用新版Safari');
 return navigator.locks.request('brc-owner-write',{mode:'exclusive'},()=>sendSigned(path,payload,key));
}
async function clearPendingWrite(proof){
 const d=await db();
 await new Promise((resolve,reject)=>{
  const tx=d.transaction('keys','readwrite'),storage=tx.objectStore('keys'),r=storage.get('pending-write');
  r.onsuccess=()=>{const p=r.result?.proof;if(p&&p.idempotency_key===proof.idempotency_key&&p.device_id===proof.device_id&&p.nonce_id===proof.nonce_id)storage.put(null,'pending-write')};
  tx.oncomplete=()=>{d.close();resolve()};tx.onerror=()=>{d.close();reject(tx.error)};
 });
}
async function sendSigned(path,payload,key){
 if(!session||!deviceKey)throw Error('设备未绑定');
 if(await getKey('pending-write'))throw Error('上次操作结果待核实，请刷新');
 const n=await request('/nonces',{method:'POST',body:'{}'});
 const proof={device_id:session.device_id,device_epoch:session.device_epoch,method:'POST',path:API+path,body_digest:await digest(payload),nonce_id:n.nonce_id,idempotency_key:key,issued_at_ms:n.issued_at_ms,expires_at_ms:n.expires_at_ms};
 const message=JSON.stringify(['brc-owner-device-v1',proof.device_id,proof.device_epoch,proof.method,proof.path,proof.body_digest,proof.nonce_id,proof.idempotency_key,proof.issued_at_ms,proof.expires_at_ms]);
 const sig=new Uint8Array(await crypto.subtle.sign({name:'ECDSA',hash:'SHA-256'},deviceKey,new TextEncoder().encode(message)));
 const packet={proof,signature:b64(sig),payload};
 await storeKey(packet,'pending-write');
 try{
  const result=await request(path,{method:'POST',body:JSON.stringify(packet)});
  await clearPendingWrite(proof);return result;
 }catch(error){
  // A known client rejection is terminal. Timeout, disconnect and 5xx remain
  // unknown and survive page closure. No new UUID or automatic write retry.
  if(error.status>=400&&error.status<500&&error.status!==408)await clearPendingWrite(proof);
  else throw Error('操作结果待核实，请刷新');
  throw error;
 }
}
async function resolvePendingWrite(){
 if(!navigator.locks?.request)return !await getKey('pending-write');
 return navigator.locks.request('brc-owner-write',{mode:'exclusive'},resolveStoredPendingWrite);
}
async function resolveStoredPendingWrite(){
 const pending=await getKey('pending-write');
 if(!pending)return true;
 try{
  const receipt=await request('/requests/'+encodeURIComponent(pending.proof.idempotency_key)+'?nonce_id='+encodeURIComponent(pending.proof.nonce_id));
  if(receipt.state==='completed'||receipt.state==='not_accepted'){
   await clearPendingWrite(pending.proof);notice(receipt.state==='completed'?'上次操作已核实':'上次操作未受理，可重新操作');return true;
  }
 }catch{}
 return false;
}

function renderBinding(){clearTimeout(refreshTimer);$('#nav').innerHTML='';screen.innerHTML=`<div class="binding"><div class="wordmark">OWNER ACCESS</div><h1>绑定这台设备</h1><form id="bindForm"><div class="field"><label for="binding">一次性绑定码</label><div class="inputwrap"><input id="binding" class="authcode" autocomplete="off" spellcheck="false" required></div></div><div class="error" id="bindError" role="alert"></div><button class="primary" type="submit">绑定并进入</button></form><div class="bottomnote">绑定码由独立管理渠道提供。建议先添加到主屏幕，再在主屏幕入口绑定。</div></div>`}
async function bind(token){
 const pair=await crypto.subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},false,['sign','verify']);
 const publicKey=await crypto.subtle.exportKey('jwk',pair.publicKey);
 const {kty,crv,x,y}=publicKey;const record={privateKey:pair.privateKey,publicKey:{kty,crv,x,y}};await storeKey(record,'pending');
 const result=await request('/devices/bind',{method:'POST',body:JSON.stringify({token,public_key:{kty,crv,x,y}})});
 await storeKey({...record,device_id:result.device_id});deviceKey=pair.privateKey;session=result;await refresh();
}
function nav(){const labels={positions:'持仓',orders:'委托',control:'主控'},symbols={positions:'▤',orders:'☷',control:'⚙'};$('#nav').innerHTML=Object.entries(labels).map(([k,v])=>`<button data-action="nav" data-page="${k}" class="${page===k?'active':''}"><span style="font-size:22px">${symbols[k]}</span>${v}</button>`).join('')}
function render(){if(!session)return;nav();const banner=!connected?'<div class="banner">连接中断 · 写操作暂停</div>':busy?'<div class="banner">上次操作待核实 · 刷新查看结果</div>':'';
 if(page==='positions')screen.innerHTML=banner+`<div class="titlebar"><h2>持仓 <span class="muted">${positions.length}</span></h2><button class="refresh" data-action="refresh">刷新</button></div>`+(positions.length?positions.map(p=>{const coin=p.exchange_instrument_id.split(':')[1].replace('USDT',''),mode=p.management_mode==='AUTO'?'自动管理':p.management_mode==='MANUAL'?'人工管理':'待核实',cap=p.capabilities||{};return `<article class="position"><div class="row"><div><span class="side ${p.position_side==='short'?'red':'green'}">${p.position_side==='short'?'卖出 / 空':'买入 / 多'}</span><span class="symbol">${esc(coin)}<span style="font-size:12px;margin-left:4px">USDT</span></span><div class="meta"><span class="tag">${esc(p.strategy_group_id)}</span><span class="tag">${p.selected_leverage}×</span></div></div><span class="tag ${p.management_mode==='AUTO'?'auto':''}">${mode}</span></div><div class="grid"><div><label>数量 (${esc(coin)})</label><b>${esc(p.position_qty)}</b></div><div><label>入场价格</label><b>${number(p.average_fill_price)}</b></div><div><label>当前状态</label><b>${Number(p.position_qty)===0?'收尾中':'持有中'}</b></div></div><div class="protect"><span>已确认止损</span><span>${number(p.active_stop_price)}</span></div><div class="actions"><button data-action="reduce" data-id="${esc(p.ticket_id)}" ${!connected||busy||!cap.reduce?'disabled':''}>减仓</button><button data-action="protection" data-id="${esc(p.ticket_id)}" ${!connected||busy||!cap.tighten?'disabled':''}>止盈 / 止损</button><button data-action="close" data-id="${esc(p.ticket_id)}" ${!connected||busy||!cap.close?'disabled':''}>全平</button></div></article>`}).join(''):'<div class="empty">暂无持仓</div>');
 else if(page==='control')screen.innerHTML=banner+`<div class="titlebar"><h2>主控</h2><button class="refresh" data-action="refresh">刷新</button></div><div class="control row"><div><h3>全局允许新开仓</h3><span class="tiny muted">${controls?.global.new_entry_submit_enabled?'已开启':'已暂停'}</span></div>${switchButton('global',controls?.global.new_entry_submit_enabled)}</div><div class="subhead">策略 · 允许新开仓</div>`+(controls?.strategies||[]).map(s=>`<div class="control row"><div><h3>${esc(s.strategy_group_id)}</h3><span class="tiny muted">${s.entry_state!=='enabled'?'已暂停':!controls.global.new_entry_submit_enabled?'已启用 · 全局暂停中':'已启用'}</span></div>${switchButton(s.strategy_group_id,s.entry_state==='enabled')}</div>`).join('');
 else screen.innerHTML=banner+`<div class="titlebar"><h2>当前委托</h2><button class="refresh" data-action="refresh">刷新</button></div>`+(ordersStatus!=='ready'?'<div class="banner">委托状态待核实</div>':'')+(orders.length?orders.map(o=>`<div class="order"><div class="row"><span class="symbol">${esc(o.symbol)}</span><span class="tag">${esc(o.kind)}</span></div><div class="kv"><span>价格</span><span>${number(o.price)}</span></div><div class="kv"><span>数量</span><span>${esc(o.quantity)}</span></div></div>`).join(''):ordersStatus==='ready'?'<div class="empty">暂无委托</div>':'<div class="empty">暂时无法核实委托</div>');
}
function switchButton(key,on){return `<button class="toggle ${on?'on':''}" role="switch" aria-label="${esc(key)}允许新开仓" aria-checked="${!!on}" data-action="toggle" data-key="${esc(key)}" ${!connected||busy?'disabled':''}><span></span></button>`}
async function refresh(){if(!session)return;try{const [p,c]=await Promise.all([request('/positions'),request('/controls')]);positions=p.items;controls=c;busy=!await resolvePendingWrite();try{const o=await request('/orders');orders=o.items;ordersStatus=o.status}catch{ordersStatus='unavailable'}connected=true;render()}catch(e){connected=false;render();if(session)notice(e.message)}clearTimeout(refreshTimer);if(session&&!document.hidden)refreshTimer=setTimeout(refresh,10000)}
function confirmControl(key){const isGlobal=key==='global',s=isGlobal?controls.global:controls.strategies.find(s=>s.strategy_group_id===key),enabled=isGlobal?s.new_entry_submit_enabled:s.entry_state==='enabled';confirmAction=async()=>{busy=true;close();render();try{await signed(isGlobal?'/controls/global':'/controls/strategy',isGlobal?{owner_policy_id:s.owner_policy_id,enabled:!enabled,expected_version:s.policy_version}:{strategy_group_id:key,enabled:!enabled,expected_version:s.control_version});notice('状态已更新')}catch(e){notice(e.message)}finally{busy=false;await refresh()}};show(heading(enabled?'暂停新开仓':'恢复新开仓')+`<div class="subtitle">${isGlobal?'全局':esc(key)}</div><div class="kv"><span>已有仓位</span><span>继续管理</span></div><button class="primary" data-action="confirm">确认${enabled?'暂停':'恢复'}</button>`)}
function settings(){show(heading('设备与通知')+`<div class="kv"><span>登录</span><span>可信设备 · 长期会话</span></div><div class="kv"><span>设备</span><span>${esc(session.device_id.slice(0,8))}</span></div><div class="bottomnote">手机丢失或换机，通过独立管理渠道撤销并重新绑定。</div><button class="outline" data-action="install">添加到主屏幕</button>`)}
document.addEventListener('click',event=>{const b=event.target.closest('[data-action]');if(!b||b.disabled)return;const a=b.dataset.action;if(a==='nav'){page=b.dataset.page;render();screen.scrollTop=0}if(a==='dismiss')close();if(a==='refresh')refresh();if(a==='toggle')confirmControl(b.dataset.key);if(a==='confirm')confirmAction?.();if(a==='settings'&&session)settings();if(a==='install')show(heading('添加到主屏幕')+'<p style="line-height:1.8">在Safari中点击分享，再选择「添加到主屏幕」。</p>')});
document.addEventListener('submit',async event=>{if(event.target.id!=='bindForm')return;event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;try{await bind($('#binding').value.trim())}catch(e){const error=$('#bindError');if(error)error.textContent=e.message}finally{button.disabled=false}});
overlay.addEventListener('click',e=>{if(e.target===overlay)close()});document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});window.addEventListener('online',()=>{connected=true;refresh()});window.addEventListener('offline',()=>{connected=false;render()});document.addEventListener('visibilitychange',()=>{if(document.hidden)clearTimeout(refreshTimer);else refresh()});
async function boot(){
 if('serviceWorker'in navigator)navigator.serviceWorker.register('./sw.js').catch(()=>{});
 try{
  const active=await getKey(),pending=await getKey('pending');
  if(!active&&!pending){renderBinding();return}
  session=await request('/session');
  let record=null;
  for(const candidate of [active,pending]){
   if(candidate?.publicKey&&await digest(candidate.publicKey)===session.key_digest){record=candidate;break}
  }
  if(!record){session=null;renderBinding();notice('设备密钥不可用，需要重新绑定');return}
  deviceKey=record.privateKey;await storeKey({...record,device_id:session.device_id});
  await request('/session/renew',{method:'POST',body:'{}'});await refresh();
 }catch{session=null;renderBinding()}
}
boot();
