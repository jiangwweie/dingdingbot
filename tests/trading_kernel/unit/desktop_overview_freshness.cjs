const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require(path.resolve('frontend/owner-console-v2/node_modules/typescript'));
const file = 'frontend/owner-console-v2/src/mapping/overviewSnapshot.ts';
const js = ts.transpileModule(fs.readFileSync(file,'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const moduleBox = {exports:{}};
vm.runInNewContext(js,{exports:moduleBox.exports,module:moduleBox});
const {effectiveOverviewFreshness, overviewLiveOptions} = moduleBox.exports;
const at = '2026-11-18T14:00:00.000Z', now = Date.parse(at);
for (const [age,want] of [[0,'fresh'],[20000,'fresh'],[20001,'stale'],[60001,'unavailable'],[-1,'contradictory']]) {
 assert.equal(effectiveOverviewFreshness('fresh',at,now+age),want);
}
assert.equal(effectiveOverviewFreshness('contradictory',at,now),'contradictory');
assert.equal(effectiveOverviewFreshness('unavailable',at,now),'unavailable');
assert.equal(effectiveOverviewFreshness('fresh',null,now),'unavailable');
// Browser/server clocks need not be identical; age is measured from arrival.
assert.equal(effectiveOverviewFreshness('fresh','2026-11-18T14:01:00.000Z',now+1000,now),'fresh');
assert.equal(effectiveOverviewFreshness('fresh',at,now+21000,now),'stale');
assert.equal(overviewLiveOptions.refetchInterval,15000);
assert.equal(overviewLiveOptions.refetchIntervalInBackground,false);
assert.equal(overviewLiveOptions.refetchOnWindowFocus,true);
assert.equal(overviewLiveOptions.refetchOnReconnect,true);
console.log('Overview polling and snapshot freshness passed');
