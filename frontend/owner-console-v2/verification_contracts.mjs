// Independent verification oracle; does not import the UI's mapping logic.
export function exactDisplay(actual, expected) {
  const normalize = v => String(v ?? '').trim().replace(/\s+/g, ' ').replace(/(?<=\d),(?=\d{3}(?:\D|$))/g, '');
  return normalize(actual) === normalize(expected);
}
export function sameIdentities(actual, expected) {
  return actual.length === expected.length && new Set(actual).size === actual.length &&
    [...actual].sort().every((v,i) => v === [...expected].sort()[i]);
}
export function authorityEvidence(kind, preview, now) {
  const r = preview?.runtime;
  if (!r) return {complete:false,state:'unknown'};
  const a = kind === 'orb' ? r.current_authority?.authority : null;
  const id = kind === 'orb' ? a?.selection_authority_id : r.current_authority_id;
  const outcome = kind === 'orb' ? a?.authority_outcome : r.current_authority_outcome;
  const start = kind === 'orb' ? a?.effective_from_ms : null;
  const end = kind === 'orb' ? a?.expires_at_ms : r.membership_valid_until_ms;
  let state, label;
  if (!id) { state='missing'; label=kind==='orb'?'权威缺失 / 未生效':'权威未生效 / 缺失'; }
  else if (!outcome || !Number.isFinite(end) || (kind==='orb' && !Number.isFinite(start))) return {complete:false,state:'unknown',id,outcome,start,end};
  else if (now >= end) { state='expired'; label=`权威已过期 (${outcome})`; }
  else if (start !== null && now < start) { state='pending'; label=`权威未生效 (${outcome})`; }
  else if (kind==='generic' && r.first_blocker) { state='blocked'; label=`准入阻断 · ${r.first_blocker}`; }
  else { state='active'; label=kind==='orb' && outcome==='VALID_EMPTY'?'权威生效 · 空集合入围 (VALID_EMPTY)':`权威有效 · ${outcome}`; }
  return {complete:true,state,label,id:id??null,outcome:outcome??null,start:start??null,end:end??null,
    limitation:kind==='generic'?'API does not expose effective_from_ms':null};
}
