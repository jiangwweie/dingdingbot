const API='/api/owner/v1/mobile', screen=document.querySelector('#screen'), sheet=document.querySelector('#sheet'), overlay=document.querySelector('#overlay');
const $=s=>document.querySelector(s), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=(n,d=2)=>n==null?'—':Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
let operationItems=[],formIntent=null;
let session=null, deviceKey=null, positions=[], orders=[], ordersStatus='unavailable',controls=null,page='positions',connected=navigator.onLine,busy=false,confirmAction=null,refreshTimer=null;
function notice(text){$('#toast').textContent=text;$('#toast').hidden=false;setTimeout(()=>$('#toast').hidden=true,4500)}
function show(html){sheet.innerHTML='<div class="handle"></div>'+html;overlay.hidden=false;sheet.querySelector('button,input')?.focus()}
function close(){overlay.hidden=true;confirmAction=null}
const heading=t=>`<div class="row"><h2>${esc(t)}</h2><button class="close" data-action="dismiss" aria-label="关闭">×</button></div>`;
async function request(path,options={}){
 if(!navigator.onLine)throw Error('网络未连接');
 const response=await fetch(API+path,{signal:AbortSignal.timeout(15000),...options,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json',...options.headers}});
 let body;
 try{body=await response.json()}catch{throw Error('响应正文不可用，操作结果待核实，请刷新')}
 if(!body||typeof body!=='object'||Array.isArray(body))throw Error('响应格式无效，操作结果待核实，请刷新');
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
function validWriteResult(path,payload,result){
 if(path==='/operations/submit')return !!result&&result.operation_id===payload.operation_id&&result.ticket_id===payload.ticket_id&&result.state==='accepted'&&Number.isSafeInteger(result.version)&&result.version===payload.expected_version+1;
 if(!result||typeof result!=='object'||Array.isArray(result)||!payload||typeof payload.enabled!=='boolean'||!Number.isSafeInteger(payload.expected_version)||payload.expected_version<=0)return false;
 const versionOK=v=>Number.isSafeInteger(v)&&v>0&&(v===payload.expected_version||v===payload.expected_version+1);
 if(path==='/controls/global')return typeof result.enabled==='boolean'&&result.enabled===payload.enabled&&versionOK(result.version);
 if(path==='/controls/strategy')return result.strategy_group_id===payload.strategy_group_id&&
  result.entry_state===(payload.enabled?'enabled':'paused')&&versionOK(result.control_version)&&
  typeof result.last_event_id==='string'&&result.last_event_id.length>0&&Number.isSafeInteger(result.updated_at_ms)&&result.updated_at_ms>0;
 return false;
}
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
  if(!validWriteResult(path,payload,result))throw Error('操作结果待核实，请刷新');
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
  if(receipt&&typeof receipt==='object'&&!Array.isArray(receipt)&&
      (receipt.state==='not_accepted'||receipt.state==='completed'&&
       validWriteResult(pending.proof.path.slice(API.length),pending.payload,receipt.result))){
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
function render(){if(!session)return;nav();const banner=operationBanner()+(!connected?'<div class="banner">连接中断 · 写操作暂停</div>':busy?'<div class="banner">上次操作待核实 · 刷新查看结果</div>':'');
 if(page==='positions')screen.innerHTML=banner+`<div class="titlebar"><h2>持仓 <span class="muted">${positions.length}</span></h2><button class="refresh" data-action="refresh">刷新</button></div>`+(positions.length?positions.map(p=>{const coin=p.exchange_instrument_id.split(':')[1].replace('USDT',''),mode=p.management_mode==='AUTO'?'自动管理':p.management_mode==='MANUAL'?'人工管理':'待核实',cap=p.capabilities||{};return `<article class="position"><div class="row"><div><span class="side ${p.position_side==='short'?'red':'green'}">${p.position_side==='short'?'卖出 / 空':'买入 / 多'}</span><span class="symbol">${esc(coin)}<span style="font-size:12px;margin-left:4px">USDT</span></span><div class="meta"><span class="tag">${esc(p.strategy_group_id)}</span><span class="tag">${p.selected_leverage}×</span></div></div><span class="tag ${p.management_mode==='AUTO'?'auto':''}">${mode}</span></div><div class="grid"><div><label>数量 (${esc(coin)})</label><b>${esc(p.position_qty)}</b></div><div><label>入场价格</label><b>${number(p.average_fill_price)}</b></div><div><label>当前状态</label><b>${Number(p.position_qty)===0?'收尾中':'持有中'}</b></div></div><div class="protect"><span>已确认止损</span><span>${number(p.active_stop_price)}</span></div><div class="actions"><button data-action="reduce" data-id="${esc(p.ticket_id)}" ${!connected||busy||!cap.reduce?'disabled':''}>减仓</button><button data-action="protection" data-id="${esc(p.ticket_id)}" ${!connected||busy||!cap.tighten?'disabled':''}>止盈 / 止损</button><button data-action="close" data-id="${esc(p.ticket_id)}" ${!connected||busy||!cap.close?'disabled':''}>全平</button></div></article>`}).join(''):'<div class="empty">暂无持仓</div>');
 else if(page==='control')screen.innerHTML=banner+`<div class="titlebar"><h2>主控</h2><button class="refresh" data-action="refresh">刷新</button></div><div class="control row"><div><h3>全局允许新开仓</h3><span class="tiny muted">${controls?.global.new_entry_submit_enabled?'已开启':'已暂停'}</span></div>${switchButton('global',controls?.global.new_entry_submit_enabled)}</div><div class="subhead">策略 · 允许新开仓</div>`+(controls?.strategies||[]).map(s=>`<div class="control row"><div><h3>${esc(s.strategy_group_id)}</h3><span class="tiny muted">${s.entry_state!=='enabled'?'已暂停':!controls.global.new_entry_submit_enabled?'已启用 · 全局暂停中':'已启用'}</span></div>${switchButton(s.strategy_group_id,s.entry_state==='enabled')}</div>`).join('');
 else screen.innerHTML=banner+`<div class="titlebar"><h2>当前委托</h2><button class="refresh" data-action="refresh">刷新</button></div>`+(ordersStatus!=='ready'?'<div class="banner">委托状态待核实</div>':'')+(orders.length?orders.map(o=>`<div class="order"><div class="row"><span class="symbol">${esc(o.symbol)}</span><span class="tag">${esc(o.kind)}</span></div><div class="kv"><span>价格</span><span>${number(o.price)}</span></div><div class="kv"><span>数量</span><span>${esc(o.quantity)}</span></div></div>`).join(''):ordersStatus==='ready'?'<div class="empty">暂无委托</div>':'<div class="empty">暂时无法核实委托</div>');
}
function switchButton(key,on){return `<button class="toggle ${on?'on':''}" role="switch" aria-label="${esc(key)}允许新开仓" aria-checked="${!!on}" data-action="toggle" data-key="${esc(key)}" ${!connected||busy?'disabled':''}><span></span></button>`}
async function refresh(){if(!session)return;try{const [p,c]=await Promise.all([request('/positions'),request('/controls')]);positions=p.items;controls=c;try{operationItems=(await request('/operations')).items}catch{operationItems=[]}busy=!await resolvePendingWrite();try{const o=await request('/orders');orders=o.items;ordersStatus=o.status}catch{ordersStatus='unavailable'}connected=true;render()}catch(e){connected=false;render();if(session)notice(e.message)}clearTimeout(refreshTimer);if(session&&!document.hidden)refreshTimer=setTimeout(refresh,10000)}
function confirmControl(key){const isGlobal=key==='global',s=isGlobal?controls.global:controls.strategies.find(s=>s.strategy_group_id===key),enabled=isGlobal?s.new_entry_submit_enabled:s.entry_state==='enabled';confirmAction=async()=>{busy=true;close();render();try{await signed(isGlobal?'/controls/global':'/controls/strategy',isGlobal?{owner_policy_id:s.owner_policy_id,enabled:!enabled,expected_version:s.policy_version}:{strategy_group_id:key,enabled:!enabled,expected_version:s.control_version});notice('状态已更新')}catch(e){notice(e.message)}finally{busy=false;await refresh()}};show(heading(enabled?'暂停新开仓':'恢复新开仓')+`<div class="subtitle">${isGlobal?'全局':esc(key)}</div><div class="kv"><span>已有仓位</span><span>继续管理</span></div><button class="primary" data-action="confirm">确认${enabled?'暂停':'恢复'}</button>`)}
function settings(){show(heading('设备与通知')+`<div class="kv"><span>登录</span><span>可信设备 · 长期会话</span></div><div class="kv"><span>设备</span><span>${esc(session.device_id.slice(0,8))}</span></div><div class="bottomnote">手机丢失或换机，通过独立管理渠道撤销并重新绑定。</div><button class="outline" data-action="install">添加到主屏幕</button>`)}
document.addEventListener('click',event=>{const b=event.target.closest('[data-action]');if(!b||b.disabled)return;const a=b.dataset.action;if(a==='nav'){page=b.dataset.page;render();screen.scrollTop=0}if(a==='dismiss')close();if(a==='refresh')refresh();if(a==='toggle')confirmControl(b.dataset.key);if(a==='confirm')confirmAction?.();if(a==='settings'&&session)settings();if(['reduce','close','protection'].includes(a))positionForm(a,b.dataset.id);if(a==='tp-form')positionForm('tp',b.dataset.id);if(a==='cancel-tp')preparePosition('manual_tp_cancel',b.dataset.id,{});if(a==='percent')setPercent(b.dataset.percent);if(a==='operation')showOperation(b.dataset.id);if(a==='install')show(heading('添加到主屏幕')+'<p style="line-height:1.8">在Safari中点击分享，再选择「添加到主屏幕」。</p>')});
document.addEventListener('submit',async event=>{if(event.target.id==='positionForm'){event.preventDefault();submitPositionForm();return}if(event.target.id!=='bindForm')return;event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;try{await bind($('#binding').value.trim())}catch(e){const error=$('#bindError');if(error)error.textContent=e.message}finally{button.disabled=false}});
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

const operationReason=reason=>({natural_tp_won_owner_operation:'原止盈已成交，人工操作已结束，继续自动管理',natural_tp_recorded_owner_results_pending:'原止盈成交已记账，正在核实在途指令',owner_tp_target_crossed_repreview_required:'原止盈已停止替换，请重新预览并确认止盈',stop_not_sent_or_rejected_original_protection_kept:'收紧未执行，原止损仍有效',manual_tp_not_sent_or_rejected_protection_retained:'新止盈未执行，保护仍保留',protection_conversion_not_executed:'保护转换未执行，原计划保留',original_tp_restore_in_progress:'正在恢复原止盈',preview_expired:'预览已过期',preview_changed:'交易状态已变化，请重新预览',device_revoked:'设备授权已撤销',position_or_tp_changed:'数量或止盈成交已变化',stop_or_flat_requires_reconciliation:'止损或平仓结果正在核实',stop_or_flat_requires_readonly_closure:'退出结果正在核实',original_strategy_exit_priority:'原策略退出条件已满足',original_lifecycle_pending:'交易正在收尾',stop_price_crossed:'当前价格已越过申请止损',manual_tp_rejected_protection_retained:'止盈未能设置，原保护仍保留',exit_rejected_protection_retained:'平仓未执行，原保护仍保留',protection_truth_pending:'正在核实新保护',actual_reduction_verified:'减仓已核实',waiting_original_tp_price:'等待原目标价后续管'}[reason]||'当前操作需要核实，请刷新查看进度');
const operationLabels={repreview_required:'需重新预览 · 旧操作已结束',handed_to_lifecycle:'人工操作已结束 · 自动续管',natural_tp_reconciling:'原止盈已记账 · 核实在途指令',restoring_original_tp:'恢复原止盈',accepted:'已受理',preview_requested:'核实中',previewed:'待确认',protection_converting:'确认余仓保护',protection_pending:'止损处理中',tp_cancelling:'撤销原止盈',tp_pending:'止盈处理中',reduction_pending:'减仓处理中',closure_pending:'平仓收尾中',wait_price:'减仓已完成 · 自动续管',runner_continuing:'减仓已完成 · Runner续管',completed:'已完成',closed:'已平仓',facts_unavailable:'等待核实',review_required:'需要核实',restore_required:'计划恢复中',failed:'执行失败',rejected:'未执行',revoked:'授权已撤销',expired:'已过期'};
function operationBanner(){return operationItems.filter(o=>!['preview_requested','previewed','expired'].includes(o.state)).slice(0,3).map(o=>`<button class="banner" data-action="operation" data-id="${esc(o.operation_id)}">${esc(operationLabels[o.state]||'处理中')} ›</button>`).join('')}
function exactFraction(value,percent){const [a,b='']=String(value).split('.'),digits=b.length+2,scale=10n**BigInt(digits),n=BigInt(a+b)*BigInt(percent),fraction=(n%scale).toString().padStart(digits,'0').replace(/0+$/,'');return (n/scale).toString()+(fraction?'.'+fraction:'')}

function setPercent(percent){if(!formIntent)return;const p=positions.find(x=>x.ticket_id===formIntent.ticket_id),input=$('#operationQty');if(input&&p)input.value=exactFraction(p.position_qty,percent)}
function positionForm(action,id){const p=positions.find(x=>x.ticket_id===id);if(!p||busy||!connected)return;formIntent={ticket_id:id,kind:action==='reduce'?'position_reduce':action==='close'?'position_close':action==='tp'?'manual_tp_set':'protection_tighten'};
 const qty=['reduce','tp'].includes(action),price=['protection','tp'].includes(action),title={reduce:'市价减仓',close:'市价全平',protection:'收紧止损',tp:'限价止盈'}[action];
 show(heading(title)+`<div class="subtitle">${esc(p.exchange_instrument_id.split(':')[1])} · ${p.position_side==='short'?'空':'多'}</div><form id="positionForm">${qty?`<div class="field"><label for="operationQty">数量</label><div class="inputwrap"><input id="operationQty" inputmode="decimal" autocomplete="off" required></div></div><div class="actions">${[25,50,75].map(v=>`<button type="button" data-action="percent" data-percent="${v}">${v}%</button>`).join('')}</div>`:''}${price?`<div class="field"><label for="operationPrice">${action==='tp'?'止盈价格':'止损价格'}</label><div class="inputwrap"><input id="operationPrice" inputmode="decimal" autocomplete="off" required></div></div>`:''}<div class="kv"><span>当前数量</span><span>${esc(p.position_qty)}</span></div><div class="error" id="operationError"></div><button type="submit" class="primary">核实并预览</button></form>${action==='protection'?`<div class="actions"><button data-action="tp-form" data-id="${esc(id)}" ${!p.capabilities?.tp?'disabled':''}>设置 / 修改止盈</button><button data-action="cancel-tp" data-id="${esc(id)}" ${!p.capabilities?.tp?'disabled':''}>取消人工止盈</button></div>`:''}`)}
async function submitPositionForm(){if(!formIntent)return;const params={};if($('#operationQty'))params.quantity=$('#operationQty').value.trim();if($('#operationPrice'))params.price=$('#operationPrice').value.trim();try{await preparePosition(formIntent.kind,formIntent.ticket_id,params)}catch(e){if($('#operationError'))$('#operationError').textContent=e.message;else notice(e.message)}}
async function preparePosition(kind,ticket_id,params){if(busy||!connected)return;busy=true;let op;
 try{op=await request('/operations/preview',{method:'POST',body:JSON.stringify({ticket_id,kind,...params,idempotency_key:crypto.randomUUID()})});show(heading('核实交易状态')+'<div class="empty">正在生成预览…</div>');
  for(let i=0;i<20&&op.state==='preview_requested';i++){await new Promise(r=>setTimeout(r,1000));op=await request('/operations/'+encodeURIComponent(op.operation_id))}
  if(op.state!=='previewed'||!op.preview)throw Error(op.first_blocker?operationReason(op.first_blocker):'预览暂不可用，请刷新后重试');
  const p=op.preview,rows=[['操作',{position_reduce:'市价减仓',position_close:'市价全平',protection_tighten:'收紧止损',manual_tp_set:'限价止盈',manual_tp_cancel:'取消人工止盈'}[kind]],['当前数量',p.source_quantity]];
  if(p.reduction_quantity)rows.push(['减仓数量',p.reduction_quantity],['剩余数量',p.remaining_quantity],['余仓管理','继续自动管理']);
  if(p.price)rows.push(['申请价格',p.price]);if(kind==='manual_tp_set'&&p.quantity)rows.push(['退出数量',p.quantity]);if(kind==='position_reduce')rows.push(['原止盈数量单','撤销'],['余仓转换目标',p.tp_trigger_price??'继续Runner']);
  if(kind==='manual_tp_set')rows.push(['原止盈','替换'],['成交方式','普通限价 · GTC']);if(kind==='manual_tp_cancel')rows.push(['原自动止盈','不恢复']);
  show(heading('确认操作')+rows.map(([k,v])=>`<div class="kv"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join('')+'<button class="primary" data-action="confirm">确认提交</button>');
  confirmAction=async()=>{if(busy)return;busy=true;close();render();try{const r=await signed('/operations/submit',{operation_id:op.operation_id,ticket_id,expected_version:op.version});notice('已受理 · 服务器继续执行');await showOperation(r.operation_id)}catch(e){notice(e.message)}finally{busy=false;await refresh()}};
 }catch(e){notice(e.message);close()}finally{busy=false}}
async function showOperation(id){try{const o=await request('/operations/'+encodeURIComponent(id));show(heading(operationLabels[o.state]||'处理中')+`<div class="kv"><span>操作编号</span><span>${esc(id.slice(-8))}</span></div><div class="kv"><span>状态</span><span>${esc(operationLabels[o.state]||o.state)}</span></div>${o.result?.actual_effects?`<div class="kv"><span>旧止盈</span><span>${o.result.actual_effects.retired_tp_order_id?'已撤销':o.result.actual_effects.old_tp_still_active?'保留':'无'}</span></div><div class="kv"><span>当前止损</span><span>${esc(o.result.actual_effects.protection_price)}</span></div>`:''}${o.first_blocker?`<div class="banner">${esc(operationReason(o.first_blocker))}</div>`:''}<button class="outline" data-action="operation" data-id="${esc(id)}">刷新进度</button>`)}catch(e){notice(e.message)}}
