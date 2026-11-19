const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
const element = selector => {
  if (!elements.has(selector)) elements.set(selector, { innerHTML: '', hidden: false, addEventListener() {} });
  return elements.get(selector);
};
const context = vm.createContext({
  document: { querySelector: element, addEventListener() {}, hidden: false },
  navigator: { onLine: true }, window: { addEventListener() {} },
  clearTimeout() {}, setTimeout() {},
  indexedDB: { open() { const request = {}; queueMicrotask(() => { request.result = {
    close() {}, transaction() { return { objectStore() { return { get() {
      const result = {}; queueMicrotask(() => { result.result = null; result.onsuccess(); }); return result;
    } }; } }; },
  }; request.onsuccess(); }); return request; } }, queueMicrotask,
});
vm.runInContext(fs.readFileSync('frontend/owner-mobile/app.js', 'utf8'), context);
for (const [value, expected] of [
  ['0.999600000000000000', '0.9996'], ['1.007300000000000000', '1.0073'],
  ['0.000000120000000000', '0.00000012'], ['0.000000000000000001', '0.000000000000000001'],
  ['9007199254740993.123456789', '9,007,199,254,740,993.123456789'],
  ['65000.100000000000000000', '65,000.1'], ['0.000000000000000000', '0'],
  ['1.2000000000E-8', '0.000000012'], [null, '—'],
]) {
  assert.equal(vm.runInContext(`number(${JSON.stringify(value)})`, context), expected);
}
vm.runInContext(`session={device_id:'fixture'};positions=[{
 ticket_id:'t',exchange_instrument_id:'binance-usdm:XRPUSDT:perpetual',position_side:'short',
 strategy_group_id:'SOR-1H-001',selected_leverage:5,position_qty:'2604.7',
 average_fill_price:'0.999600000000000000',active_stop_price:'1.007300000000000000',
 management_mode:'AUTO',capabilities:{reduce:true,close:true,tighten:true,tp:true}
}];render()`, context);
assert.match(element('#screen').innerHTML, /0\.9996/);
assert.match(element('#screen').innerHTML, /1\.0073/);
vm.runInContext(`page='orders';ordersStatus='ready';orders=[{symbol:'XRPUSDT',kind:'Stop',price:'1.007300000000000000',quantity:'2604.7'}];render()`, context);
assert.match(element('#screen').innerHTML, /1\.0073/);
console.log('Exact mobile price formatting and position/order rendering passed');
